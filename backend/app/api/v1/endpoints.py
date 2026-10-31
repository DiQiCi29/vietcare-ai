from datetime import datetime, date
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, File, Form, UploadFile
from fastapi.responses import FileResponse
from pydantic import ValidationError
from pathlib import Path
import logging
from sqlalchemy.orm import Session
from sqlalchemy import or_, desc

from backend.app.core.database import get_db
from backend.app.core.security import verify_password, create_access_token
from backend.app.models.user import User, Customer, UserRole
from backend.app.models.product import Product, SoldItem
from backend.app.models.warranty import (
    WarrantyRequest, RequestStatusHistory, RequestStatus, ReceptionChannel, Inspection, WarrantyConclusion, Attachment
)
from backend.app.models.chat import ChatSession, ChatMessage
from backend.app.models.notification import NotificationLog
from backend.app.schemas.api_schemas import (
    LoginRequest, TokenResponse, CustomerProductOut, CreateRequestInput, StatusUpdateInput, ChatInput
)
from backend.app.rag.retriever import retrieve_relevant_policies, sync_policies_to_vector_store
from backend.app.rag.chain import generate_chat_response
from backend.app.services.email_service import send_warranty_status_email

from backend.app.core.auth import (
    get_current_actor, require_staff, require_manager, require_customer, require_admin, check_customer_access,
)
from backend.app.services.warranty_workflow import transition, check_request_access
from backend.app.schemas.api_schemas import VerifyInput, AssignInput, CompleteInput

from backend.app.services.eligibility import ensure_supported, is_expired, today_vietnam
from backend.app.services.chat_tracking import tracking_response, ticket_data
from backend.app.rag.intents import is_create_request_query, is_tracking_query, normalize
from backend.app.schemas.api_schemas import ContactInput
from backend.app.core.config import settings
from backend.app.services.business_hours import is_overdue, sla_data, local_time, utc_now
from backend.app.services.request_codes import allocate_request_code
from backend.app.services.attachments import stage_media, remove_staged, TYPES

router = APIRouter()

# --------------------------------------------------------------------------
# 1. AUTHENTICATION (Cả Khách hàng đăng nhập bằng SĐT & Nhân viên bằng Username)
# --------------------------------------------------------------------------
@router.post("/auth/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    identity = payload.username_or_phone.strip()
    
    # 1. Check Customer table (Phone number)
    customer = db.query(Customer).filter(Customer.phone == identity).first()
    if customer:
        if not customer.is_active:
            raise HTTPException(403, "Tài khoản đã bị khóa")
        if not verify_password(payload.password, customer.hashed_password):
            raise HTTPException(status_code=400, detail="Mật khẩu không chính xác")
        token = create_access_token(subject=str(customer.id), role="CUSTOMER")
        return TokenResponse(
            access_token=token,
            user_id=customer.id,
            user_type="customer",
            name=customer.full_name,
            role="CUSTOMER",
            phone_or_email=customer.phone,
            is_first_login=not customer.is_first_login_changed
        )

    # 2. Check Staff User table (Username or Email)
    staff = db.query(User).filter(
        or_(User.username == identity, User.email == identity)
    ).first()
    if staff:
        if not staff.is_active:
            raise HTTPException(403, "Tài khoản đã bị khóa")
        if not verify_password(payload.password, staff.hashed_password):
            raise HTTPException(status_code=400, detail="Mật khẩu không chính xác")
        token = create_access_token(subject=str(staff.id), role=staff.role.value)
        return TokenResponse(
            access_token=token,
            user_id=staff.id,
            user_type="staff",
            name=staff.name,
            role=staff.role.value,
            phone_or_email=staff.email,
            is_first_login=False
        )

    raise HTTPException(status_code=404, detail="Tài khoản không tồn tại trên hệ thống")

# --------------------------------------------------------------------------
# 1.1 PUBLIC PRODUCT CATALOG (CHO DASHBOARD SHOWCASE)
# --------------------------------------------------------------------------
@router.get("/products")
def get_public_products(
    category: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 40,
    db: Session = Depends(get_db)
):
    query = db.query(Product)
    if category and category != "ALL":
        query = query.filter(Product.category == category)
    if search:
        s = search.lower().strip()
        query = query.filter(
            or_(
                Product.name.ilike(f"%{s}%"),
                Product.model.ilike(f"%{s}%"),
                Product.brand.ilike(f"%{s}%")
            )
        )
    products = query.limit(limit).all()
    return [
        {
            "id": p.id,
            "name": p.name,
            "model": p.model,
            "brand": p.brand or "Chính hãng",
            "category": p.category,
            "warranty_months": p.default_warranty_months,
            "image_url": p.image_url or "https://vietro.com.vn/uploads/files/Untitled-2-01%20copy.png"
        }
        for p in products
    ]

# --------------------------------------------------------------------------
# 2. CUSTOMER APIS
# --------------------------------------------------------------------------
@router.get("/customer/products/{phone}", response_model=List[CustomerProductOut], response_model_exclude_none=True)
def get_customer_products(phone: str, db: Session = Depends(get_db), actor=Depends(get_current_actor)):
    customer = db.query(Customer).filter(Customer.phone == phone).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Không tìm thấy khách hàng")
    check_customer_access(actor, customer)

    items = db.query(SoldItem).filter(SoldItem.customer_id == customer.id).all()
    results = []
    today = today_vietnam()

    for item in items:
        if is_expired(item) and isinstance(actor, Customer):
            results.append(CustomerProductOut(id=item.id, product_name=item.product.name,
                                               image_url=item.product.image_url, is_expired=True))
            continue
        # Check active request
        active_req = db.query(WarrantyRequest).filter(
            WarrantyRequest.sold_item_id == item.id,
            WarrantyRequest.status.notin_([RequestStatus.COMPLETED, RequestStatus.REJECTED])
        ).first()

        results.append(CustomerProductOut(
            id=item.id,
            product_name=item.product.name,
            model=item.product.model,
            brand=item.product.brand or "",
            category=item.product.category,
            serial_number=item.serial_number,
            purchase_date=item.purchase_date.strftime("%d/%m/%Y"),
            warranty_expire_date=item.warranty_expire_date.strftime("%d/%m/%Y"),
            is_expired=today > item.warranty_expire_date,
            image_url=item.product.image_url,
            active_request_id=active_req.id if active_req else None
        ))

    return results

@router.get("/customer/requests/{phone}")
def get_customer_requests(phone: str, db: Session = Depends(get_db), actor=Depends(get_current_actor)):
    customer = db.query(Customer).filter(Customer.phone == phone).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Không tìm thấy khách hàng")
    check_customer_access(actor, customer)

    query = db.query(WarrantyRequest).outerjoin(SoldItem, WarrantyRequest.sold_item_id == SoldItem.id).filter(
        WarrantyRequest.customer_id == customer.id
    )
    if isinstance(actor, Customer):
        query = query.filter(or_(WarrantyRequest.sold_item_id.is_(None), SoldItem.warranty_expire_date >= today_vietnam()))
    requests = query.order_by(desc(WarrantyRequest.created_at)).all()

    out = []
    for r in requests:
        timeline = []
        for h in r.status_history:
            if h.is_internal_note:
                continue
            timeline.append({
                "status": h.status.value,
                "note": h.notes,
                "time": local_time(h.created_at).strftime("%H:%M - %d/%m/%Y")
            })
        out.append({
            "id": r.id,
            "request_code": r.request_code,
            "product_name": r.sold_item.product.name if r.sold_item else "Thiết bị điện máy",
            "model": r.sold_item.product.model if r.sold_item else "",
            "serial": r.sold_item.serial_number if r.sold_item else "",
            "error_group": r.error_group,
            "error_description": r.error_description,
            "channel": r.channel.value,
            "status": r.status.value,
            "technician_name": r.technician.name if r.technician else "Chưa phân công",
            "appointment_date": r.appointment_date.strftime("%d/%m/%Y") if r.appointment_date else None,
            "created_at": local_time(r.created_at).strftime("%d/%m/%Y %H:%M"),
            "timeline": timeline,
            "attachments": [attachment_data(a) for a in r.attachments],
            **sla_data(r),
        })
    return out

@router.post("/customer/requests")
def create_warranty_request(payload: CreateRequestInput, db: Session = Depends(get_db), actor=Depends(get_current_actor)):
    return persist_warranty_request(payload, db, actor)


@router.post("/customer/requests-with-media")
async def create_request_with_media(payload: str = Form(..., max_length=20000),
                                    files: List[UploadFile] = File(default=[]),
                                    db: Session = Depends(get_db), actor=Depends(require_customer)):
    try:
        data = CreateRequestInput.model_validate_json(payload)
    except ValidationError:
        raise HTTPException(422, "Thông tin yêu cầu không hợp lệ")
    staged = await stage_media(files)
    try:
        return persist_warranty_request(data, db, actor, staged)
    except BaseException:
        db.rollback()
        remove_staged(staged)
        raise


def persist_warranty_request(payload, db, actor, media=None):
    if isinstance(actor, User) and actor.role not in (UserRole.ADMIN, UserRole.CSKH):
        raise HTTPException(403, "Chỉ CSKH hoặc quản trị viên được tạo phiếu thay khách")
    if isinstance(actor, Customer):
        if payload.customer_phone and payload.customer_phone != actor.phone:
            raise HTTPException(403, "Không được tạo phiếu cho khách hàng khác")
        if payload.channel != "Web":
            raise HTTPException(403, "Khách hàng chỉ được tạo phiếu qua Web")
        if not payload.sold_item_id:
            raise HTTPException(422, "Phải chọn sản phẩm đã mua")
        payload.customer_phone = actor.phone
    if not payload.sold_item_id:
        raise HTTPException(422, "Phải chọn sản phẩm đã mua để kiểm tra thời hạn bảo hành")
    if payload.sold_item_id:
        item = db.get(SoldItem, payload.sold_item_id)
        if not item:
            raise HTTPException(404, "Không tìm thấy sản phẩm đã mua")
        check_customer_access(actor, item.customer)
        ensure_supported(item)
        if payload.customer_phone and item.customer.phone != payload.customer_phone:
            raise HTTPException(422, "Sản phẩm không thuộc khách hàng này")
    # 1. Determine customer
    customer = None
    if payload.customer_phone:
        customer = db.query(Customer).filter(Customer.phone == payload.customer_phone).first()
        if not customer:
            # Create new customer if staff is registering by phone (QT-04)
            from backend.app.core.security import get_password_hash
            customer = Customer(
                full_name=payload.customer_name or f"Khách hàng {payload.customer_phone}",
                phone=payload.customer_phone,
                email=payload.customer_email or f"{payload.customer_phone}@vietro.customer.vn",
                address=payload.support_address,
                hashed_password=get_password_hash("123456")
            )
            db.add(customer)
            db.commit()
            db.refresh(customer)

    if not customer and payload.sold_item_id:
        sold_item = db.query(SoldItem).filter(SoldItem.id == payload.sold_item_id).first()
        if sold_item:
            customer = sold_item.customer

    if not customer:
        raise HTTPException(status_code=400, detail="Không xác định được thông tin khách hàng")

    # 2. Prevent duplicate pending requests for the same item (KH-Quy tắc)
    if payload.sold_item_id:
        active = db.query(WarrantyRequest).filter(
            WarrantyRequest.sold_item_id == payload.sold_item_id,
            WarrantyRequest.status.notin_([RequestStatus.COMPLETED, RequestStatus.REJECTED])
        ).first()
        if active:
            raise HTTPException(status_code=400, detail=f"Sản phẩm này đang có yêu cầu xử lý ({active.request_code}), vui lòng không gửi trùng.")

    # Allocate a number transactionally; existing historical codes stay unchanged.
    created = utc_now()
    req_code = allocate_request_code(db, created)

    req = WarrantyRequest(
        request_code=req_code,
        customer_id=customer.id,
        created_by_user_id=actor.id if isinstance(actor, User) else None,
        sold_item_id=payload.sold_item_id,
        error_group=payload.error_group,
        error_description=payload.error_description,
        support_address=payload.support_address,
        channel=ReceptionChannel.PHONE if payload.channel == "Điện thoại" else ReceptionChannel.WEB,
        status=RequestStatus.RECEIVED,
        created_at=created
    )
    db.add(req)
    db.flush()

    # 4. Add initial status history (append-only)
    hist = RequestStatusHistory(
        request_id=req.id,
        status=RequestStatus.RECEIVED,
        notes=f"Yêu cầu được tiếp nhận qua kênh {payload.channel}",
        created_at=datetime.utcnow()
    )
    db.add(hist)
    for file in media or []:
        db.add(Attachment(request_id=req.id, **{key: value for key, value in file.items() if key != 'absolute_path'}))
    db.commit()
    db.refresh(req)

    # 5. Send automated email notification (TB-01)
    try:
        send_warranty_status_email(db, req, RequestStatus.RECEIVED.value)
    except Exception:
        db.rollback()
        logging.getLogger(__name__).warning("Không ghi được thông báo cho phiếu %s", req.id)

    return {
        "success": True,
        "request_code": req.request_code,
        "message": "Gửi yêu cầu bảo hành thành công!",
        "request_id": req.id
    }


def attachment_data(attachment):
    return {'id': attachment.id, 'file_name': attachment.file_name,
            'file_type': attachment.file_type, 'file_size': attachment.file_size,
            'url': f'{settings.API_V1_STR}/attachments/{attachment.id}'}


def accessible_request(db, request_id, actor):
    request = db.get(WarrantyRequest, request_id)
    if not request:
        raise HTTPException(404, 'Không tìm thấy yêu cầu')
    if isinstance(actor, Customer):
        check_customer_access(actor, request.customer)
        if request.sold_item:
            ensure_supported(request.sold_item)
    else:
        check_request_access(actor, request)
    return request


@router.get('/requests/{request_id}')
def get_request_detail(request_id: int, db: Session = Depends(get_db), actor=Depends(get_current_actor)):
    req = accessible_request(db, request_id, actor)
    return {
        'id': req.id, 'request_code': req.request_code,
        'product_name': req.sold_item.product.name if req.sold_item else 'Thiết bị điện máy',
        'model': req.sold_item.product.model if req.sold_item else '',
        'customer_name': req.customer.full_name, 'customer_phone': req.customer.phone,
        'support_address': req.support_address, 'error_group': req.error_group,
        'error_description': req.error_description, 'status': req.status.value,
        'technician_name': req.technician.name if req.technician else 'Chưa phân công',
        'appointment_date': req.appointment_date.strftime('%d/%m/%Y') if req.appointment_date else None,
        'created_at': local_time(req.created_at).isoformat(), **sla_data(req),
        'timeline': [{'status': h.status.value, 'note': h.notes,
                      'time': local_time(h.created_at).strftime('%H:%M %d/%m/%Y')}
                     for h in req.status_history if not isinstance(actor, Customer) or not h.is_internal_note],
        'attachments': [attachment_data(a) for a in req.attachments],
        'inspections': [{'conclusion': i.conclusion.value if i.conclusion else '',
                         'repair_content': i.repair_content, 'parts_replaced': i.parts_replaced}
                        for i in req.inspections],
    }


@router.get('/attachments/{attachment_id}')
def get_attachment(attachment_id: int, db: Session = Depends(get_db), actor=Depends(get_current_actor)):
    attachment = db.get(Attachment, attachment_id)
    if not attachment:
        raise HTTPException(404, 'Không tìm thấy tệp')
    accessible_request(db, attachment.request_id, actor)
    root = Path(settings.UPLOAD_DIR).resolve()
    path = (root / attachment.file_path).resolve()
    if not path.is_relative_to(root) or not path.is_file() or path.suffix.lower() not in TYPES:
        raise HTTPException(404, 'Không tìm thấy tệp')
    return FileResponse(path, media_type=TYPES[path.suffix.lower()][1],
                        headers={'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff'})

@router.post("/customer/contact")
def submit_customer_contact(payload: ContactInput, db: Session = Depends(get_db), actor=Depends(require_customer)):
    if payload.phone.strip() != actor.phone:
        raise HTTPException(403, "Không được gửi liên hệ thay khách hàng khác")
    if not payload.message.strip():
        raise HTTPException(422, "Vui lòng nhập nội dung cần hỗ trợ")
    # Callback requests are tickets too: apply the same ownership, expiry and duplicate rules.
    return create_warranty_request(CreateRequestInput(
        sold_item_id=payload.sold_item_id, customer_phone=actor.phone,
        error_group="Yêu cầu gọi lại / Hỗ trợ", error_description=payload.message.strip(),
        support_address=actor.address or "Liên hệ qua SĐT", channel="Web",
    ), db=db, actor=actor)


@router.post("/customer/chat")
def chat_with_ai(payload: ChatInput, db: Session = Depends(get_db), actor=Depends(require_customer)):
    query = payload.query.strip()
    if not query:
        raise HTTPException(422, "Vui lòng nhập câu hỏi")
    session = None
    history = []
    if payload.session_id:
        session = db.query(ChatSession).filter(ChatSession.session_id == payload.session_id).first()
        if session and session.customer_id != actor.id:
            raise HTTPException(403, "Không được truy cập hội thoại này")
        if session:
            previous = db.query(ChatMessage).filter(ChatMessage.session_id == session.id).order_by(
                ChatMessage.created_at.desc(), ChatMessage.id.desc()).limit(8).all()
            history = [{"sender": m.sender, "message": m.message} for m in reversed(previous)]

    creating = is_create_request_query(query)
    tracking = not creating and is_tracking_query(query, history)
    own_request = None
    if payload.request_id is not None:
        own_request = db.query(WarrantyRequest).filter(WarrantyRequest.id == payload.request_id,
                                                      WarrantyRequest.customer_id == actor.id).first()
        if not own_request:
            raise HTTPException(404, "Không tìm thấy phiếu trong tài khoản của bạn")
        if own_request.sold_item:
            ensure_supported(own_request.sold_item)
    sold_item = None
    if payload.sold_item_id:
        sold_item = db.get(SoldItem, payload.sold_item_id)
        if not sold_item:
            raise HTTPException(404, "Không tìm thấy sản phẩm")
        check_customer_access(actor, sold_item.customer)
        ensure_supported(sold_item)
    elif not tracking:
        # Resolve explicit device names/models from this customer's purchases only.
        items = db.query(SoldItem).filter(SoldItem.customer_id == actor.id).all()
        text = normalize(query).replace('may lanh', 'dieu hoa')
        matches = [item for item in items if normalize(item.product.model) in text]
        if not matches:
            matches = [item for item in items if normalize(item.product.category).replace('may lanh', 'dieu hoa') in text]
        if len(matches) == 1:
            sold_item = matches[0]
        elif session and session.sold_item_id:
            sold_item = db.get(SoldItem, session.sold_item_id)
        elif own_request and own_request.sold_item:
            sold_item = own_request.sold_item
        if sold_item:
            check_customer_access(actor, sold_item.customer)
            ensure_supported(sold_item)

    # Changing products must not carry an accident or diagnosis across devices.
    if session and sold_item and session.sold_item_id != sold_item.id:
        history = []
        session.sold_item_id = sold_item.id

    if tracking:
        response_data = tracking_response(db, actor.id, query, sold_item=sold_item,
                                          request_id=payload.request_id, history=history)
    else:
        from backend.app.rag.vector_store import vector_store
        if not vector_store.documents:
            sync_policies_to_vector_store(db)
        retrieved = retrieve_relevant_policies(query, sold_item=sold_item, top_k=5, chat_history=history)
        response_data = generate_chat_response(query, retrieved, sold_item=sold_item, chat_history=history)
        if sold_item:
            response_data["sold_item_id"] = sold_item.id
            active = db.query(WarrantyRequest).filter(
                WarrantyRequest.customer_id == actor.id, WarrantyRequest.sold_item_id == sold_item.id,
                WarrantyRequest.status.notin_([RequestStatus.COMPLETED, RequestStatus.REJECTED]),
            ).first()
            if active and response_data.get("suggested_action") == "CREATE_WARRANTY_REQUEST":
                response_data["suggested_action"] = "VIEW_WARRANTY_REQUESTS"
                response_data["requests"] = [ticket_data(active)]
                if creating:
                    response_data["reply"] = f"Sản phẩm đang có phiếu **{active.request_code}** ở trạng thái **{active.status.value}**. Bạn chưa thể tạo thêm phiếu khi phiếu này còn đang xử lý; hãy theo dõi phiếu hiện tại bên dưới."
                else:
                    response_data["reply"] += f"\n\nSản phẩm đang có phiếu **{active.request_code}** ({active.status.value}); bạn có thể theo dõi phiếu này, không cần tạo phiếu mới."

    if payload.session_id:
        if not session:
            session = ChatSession(session_id=payload.session_id, customer_id=actor.id,
                                  sold_item_id=sold_item.id if sold_item else None)
            db.add(session)
            db.flush()
        db.add_all([
            ChatMessage(session_id=session.id, sender="user", message=query),
            ChatMessage(session_id=session.id, sender="bot", message=response_data["reply"],
                        suggested_action=response_data.get("suggested_action")),
        ])
        db.commit()
    return response_data


# --------------------------------------------------------------------------
# 4. STAFF & TECHNICIAN APIS (CENTRALIZED MANAGEMENT)
# --------------------------------------------------------------------------
@router.get("/staff/requests")
def get_all_requests(
    status_filter: Optional[str] = None,
    channel_filter: Optional[str] = None,
    technician_id: Optional[int] = None,
    search: Optional[str] = None,
    appointment_from: Optional[date] = None,
    appointment_to: Optional[date] = None,
    pending_only: bool = False,
    repeat_calls_only: bool = False,
    overdue_only: bool = False,
    db: Session = Depends(get_db),
    actor=Depends(require_staff),
):
    query = db.query(WarrantyRequest).order_by(desc(WarrantyRequest.created_at))

    if appointment_from and appointment_to and appointment_from > appointment_to:
        raise HTTPException(422, "Ngày bắt đầu phải trước hoặc bằng ngày kết thúc")
    if appointment_from:
        query = query.filter(WarrantyRequest.appointment_date >= datetime.combine(appointment_from, datetime.min.time()))
    if appointment_to:
        query = query.filter(WarrantyRequest.appointment_date <= datetime.combine(appointment_to, datetime.max.time()))
    if pending_only:
        query = query.filter(WarrantyRequest.status.in_([
            RequestStatus.RECEIVED, RequestStatus.VERIFYING,
            RequestStatus.PENDING_ADDITIONAL_INFO, RequestStatus.ASSIGNED,
        ]))
    if repeat_calls_only:
        query = query.filter(WarrantyRequest.repeat_call_count > 0)

    if actor.role == UserRole.TECHNICIAN:
        technician_id = actor.id

    if technician_id:
        query = query.filter(WarrantyRequest.technician_id == technician_id)

    if status_filter and status_filter != "ALL":
        query = query.filter(WarrantyRequest.status == status_filter)

    if channel_filter and channel_filter != "ALL":
        query = query.filter(WarrantyRequest.channel == channel_filter)

    requests = query.all()
    now = utc_now()
    if overdue_only:
        requests = [r for r in requests if is_overdue(r, now)]

    # In-memory filter for search (code, customer name, phone)
    if search:
        s = search.lower().strip()
        requests = [
            r for r in requests
            if s in r.request_code.lower()
            or s in r.customer.full_name.lower()
            or s in r.customer.phone.lower()
        ]

    out = []
    for r in requests:
        out.append({
            "id": r.id,
            "request_code": r.request_code,
            "customer_name": r.customer.full_name,
            "customer_phone": r.customer.phone,
            "product_name": r.sold_item.product.name if r.sold_item else "Nhập tay qua cuộc gọi",
            "model": r.sold_item.product.model if r.sold_item else "",
            "error_group": r.error_group,
            "error_description": r.error_description,
            "support_address": r.support_address,
            "channel": r.channel.value,
            "status": r.status.value,
            "technician_id": r.technician_id,
            "technician_name": r.technician.name if r.technician else "Chưa phân công",
            "appointment_date": r.appointment_date.strftime("%d/%m/%Y") if r.appointment_date else None,
            "repeat_call_count": r.repeat_call_count,
            "created_at": local_time(r.created_at).strftime("%d/%m/%Y %H:%M"),
            "attachment_count": len(r.attachments),
            **sla_data(r, now),
        })
    return out

def load_request(db, request_id, actor):
    req = db.get(WarrantyRequest, request_id)
    if not req:
        raise HTTPException(404, "Không tìm thấy yêu cầu")
    check_request_access(actor, req)
    return req


def finish_transition(db, req, payload):
    db.commit()
    db.refresh(req)
    send_warranty_status_email(db, req, req.status.value, notes=payload.notes)
    return {"success": True, "status": req.status.value, "message": "Cập nhật yêu cầu thành công"}


@router.put("/staff/requests/{request_id}/status")
def update_request_status(request_id: int, payload: StatusUpdateInput,
                          db: Session = Depends(get_db), actor=Depends(require_staff)):
    req = load_request(db, request_id, actor)
    transition(db, req, actor, payload)
    return finish_transition(db, req, payload)


@router.post("/staff/requests/{request_id}/verify")
def verify_request(request_id: int, payload: VerifyInput,
                   db: Session = Depends(get_db), actor=Depends(require_manager)):
    req = load_request(db, request_id, actor)
    actions = {"VALID": RequestStatus.VERIFYING, "REJECT": RequestStatus.REJECTED,
               "NEED_INFO": RequestStatus.PENDING_ADDITIONAL_INFO}
    if payload.action not in actions:
        raise HTTPException(422, "Hành động xác minh không hợp lệ")
    target = actions[payload.action]
    if target in (RequestStatus.REJECTED, RequestStatus.PENDING_ADDITIONAL_INFO) and not payload.notes.strip():
        raise HTTPException(422, "Phải ghi lý do hoặc thông tin cần bổ sung")
    # The UI records a verification result in one submit; retain both audit steps.
    if target != RequestStatus.VERIFYING and req.status in (RequestStatus.RECEIVED, RequestStatus.PENDING_ADDITIONAL_INFO):
        transition(db, req, actor, StatusUpdateInput(new_status=RequestStatus.VERIFYING,
                                                   notes="CSKH bắt đầu xác minh hồ sơ"))
    change = StatusUpdateInput(new_status=target, notes=payload.notes)
    transition(db, req, actor, change)
    return finish_transition(db, req, change)


@router.post("/staff/requests/{request_id}/assign")
def assign_technician(request_id: int, payload: AssignInput,
                      db: Session = Depends(get_db), actor=Depends(require_manager)):
    req = load_request(db, request_id, actor)
    change = StatusUpdateInput(new_status=RequestStatus.ASSIGNED, **payload.model_dump())
    transition(db, req, actor, change)
    return finish_transition(db, req, change)


@router.post("/staff/requests/{request_id}/complete")
def complete_request(request_id: int, payload: CompleteInput,
                     db: Session = Depends(get_db), actor=Depends(require_staff)):
    req = load_request(db, request_id, actor)
    change = StatusUpdateInput(new_status=RequestStatus.COMPLETED, **payload.model_dump())
    transition(db, req, actor, change)
    return finish_transition(db, req, change)


@router.post("/staff/requests/{request_id}/repeat-call")
def mark_repeat_call(request_id: int, db: Session = Depends(get_db), actor=Depends(require_manager)):
    """CS-08: Nút đánh dấu khách gọi hỏi tiến độ để đếm KPI"""
    req = db.query(WarrantyRequest).filter(WarrantyRequest.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Không tìm thấy yêu cầu")
    req.repeat_call_count += 1
    db.commit()
    return {"success": True, "repeat_call_count": req.repeat_call_count}

@router.get("/staff/technicians")
def get_technicians(db: Session = Depends(get_db), actor=Depends(require_manager)):
    techs = db.query(User).filter(User.role == UserRole.TECHNICIAN, User.is_active == True).all()
    return [{"id": t.id, "name": t.name, "phone": t.phone} for t in techs]

@router.get("/staff/kpi")
def get_kpi_stats(db: Session = Depends(get_db), actor=Depends(require_manager)):
    total = db.query(WarrantyRequest).count()
    web_count = db.query(WarrantyRequest).filter(WarrantyRequest.channel == ReceptionChannel.WEB).count()
    phone_count = db.query(WarrantyRequest).filter(WarrantyRequest.channel == ReceptionChannel.PHONE).count()
    completed_count = db.query(WarrantyRequest).filter(WarrantyRequest.status == RequestStatus.COMPLETED).count()
    waiting_count = db.query(WarrantyRequest).filter(WarrantyRequest.status.in_([
        RequestStatus.RECEIVED, RequestStatus.VERIFYING,
        RequestStatus.PENDING_ADDITIONAL_INFO, RequestStatus.ASSIGNED,
    ])).count()
    
    # Sum repeat calls
    from sqlalchemy import func
    repeat_sum = db.query(func.sum(WarrantyRequest.repeat_call_count)).scalar() or 0
    now = utc_now()
    overdue_count = sum(is_overdue(r, now) for r in db.query(WarrantyRequest).filter(WarrantyRequest.status == RequestStatus.RECEIVED))

    return {
        "total_requests": total,
        "web_count": web_count,
        "phone_count": phone_count,
        "web_ratio": round((web_count / total * 100) if total > 0 else 0, 1),
        "completed_count": completed_count,
        "waiting_count": waiting_count,
        "overdue_count": overdue_count,
        "repeat_calls": int(repeat_sum),
        "active_policies": 11
    }


@router.get('/admin/overview')
def get_admin_overview(db: Session = Depends(get_db), actor=Depends(require_admin)):
    from sqlalchemy import func
    statuses = db.query(WarrantyRequest.status, func.count(WarrantyRequest.id)).group_by(WarrantyRequest.status).all()
    technicians = db.query(User).filter(User.role == UserRole.TECHNICIAN, User.is_active == True).all()
    work = []
    for tech in technicians:
        counts = dict(db.query(WarrantyRequest.status, func.count(WarrantyRequest.id))
                      .filter(WarrantyRequest.technician_id == tech.id).group_by(WarrantyRequest.status).all())
        work.append({'id': tech.id, 'name': tech.name,
                     'assigned': counts.get(RequestStatus.ASSIGNED, 0),
                     'in_progress': counts.get(RequestStatus.IN_PROGRESS, 0),
                     'completed': counts.get(RequestStatus.COMPLETED, 0)})
    return {'kpi': get_kpi_stats(db=db, actor=actor),
            'statuses': [{'status': status.value, 'count': count} for status, count in statuses],
            'technicians': work}
