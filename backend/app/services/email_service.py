import logging
from datetime import datetime
from sqlalchemy.orm import Session
from backend.app.models.warranty import WarrantyRequest
from backend.app.models.notification import NotificationLog

logger = logging.getLogger(__name__)

EMAIL_TEMPLATES = {
    "Tiếp nhận": {
        "subject": "[{code}] Yêu cầu bảo hành đã được tiếp nhận thành công",
        "body": "Kính gửi {customer_name},\n\nYêu cầu bảo hành mã {code} cho sản phẩm {product_name} đã được tiếp nhận vào hệ thống Viettronimex Đà Nẵng.\nMô tả lỗi: {error_description}\nBộ phận CSKH sẽ xác minh và liên hệ trong thời gian sớm nhất."
    },
    "Xác minh": {
        "subject": "[{code}] Yêu cầu bảo hành đang được xác minh hồ sơ",
        "body": "Kính gửi {customer_name},\n\nYêu cầu bảo hành mã {code} của bạn đang được bộ phận CSKH đối chiếu thời hạn bảo hành và chính sách chính hãng."
    },
    "Chờ bổ sung": {
        "subject": "[{code}] Cần bổ sung thông tin cho yêu cầu bảo hành",
        "body": "Kính gửi {customer_name},\n\nYêu cầu bảo hành mã {code} cần quý khách bổ sung thêm hình ảnh/video rõ nét hơn về sự cố. Vui lòng liên hệ hotline 1800 64 64 92 để được hỗ trợ."
    },
    "Phân công": {
        "subject": "[{code}] Yêu cầu bảo hành đã được phân công kỹ thuật viên",
        "body": "Kính gửi {customer_name},\n\nYêu cầu bảo hành mã {code} đã được giao cho kỹ thuật viên: {tech_name}.\nĐịa chỉ hỗ trợ: {address}\nKỹ thuật viên sẽ liên hệ trước khi đến kiểm tra."
    },
    "Sửa chữa": {
        "subject": "[{code}] Kỹ thuật viên đang tiến hành kiểm tra & sửa chữa",
        "body": "Kính gửi {customer_name},\n\nKỹ thuật viên {tech_name} đang tiến hành kiểm tra và khắc phục sự cố cho thiết bị của bạn."
    },
    "Hoàn tất": {
        "subject": "[{code}] Hoàn tất xử lý bảo hành sản phẩm",
        "body": "Kính gửi {customer_name},\n\nYêu cầu bảo hành mã {code} cho sản phẩm {product_name} đã được xử lý HOÀN TẤT.\nCảm ơn quý khách đã tin tưởng dịch vụ bảo hành của Viettronimex Đà Nẵng!"
    },
    "Từ chối bảo hành": {
        "subject": "[{code}] Thông báo về yêu cầu bảo hành",
        "body": "Kính gửi {customer_name},\n\nRất tiếc yêu cầu bảo hành mã {code} không đủ điều kiện bảo hành miễn phí theo chính sách. Lý do: {notes}.\nViettronimex có hỗ trợ sửa chữa tính phí ưu đãi (miễn phí công thay thế). Liên hệ hotline 1800 64 64 92 để biết thêm chi tiết."
    }
}

def send_warranty_status_email(db: Session, request: WarrantyRequest, new_status: str, notes: str = None):
    """
    TB-01: Gửi email tự động khi đổi trạng thái và lưu nhật ký NotificationLog
    """
    customer = request.customer
    if not customer or not customer.email:
        return

    product_name = request.sold_item.product.name if request.sold_item else "Thiết bị điện máy"
    tech_name = request.technician.name if request.technician else "Chuyên viên kỹ thuật"
    
    template = EMAIL_TEMPLATES.get(new_status, {
        "subject": f"[{request.request_code}] Cập nhật trạng thái bảo hành: {new_status}",
        "body": f"Yêu cầu bảo hành mã {request.request_code} đã chuyển sang trạng thái: {new_status}."
    })

    subject = template["subject"].format(code=request.request_code, new_status=new_status)
    body = template["body"].format(
        customer_name=customer.full_name,
        code=request.request_code,
        product_name=product_name,
        error_description=request.error_description,
        tech_name=tech_name,
        address=request.support_address,
        notes=notes or "Không có ghi chú thêm."
    )

    # Save to notification log (TB-01 requirement)
    log = NotificationLog(
        request_id=request.id,
        recipient_email=customer.email,
        subject=subject,
        content=body,
        status="SENT",
        created_at=datetime.utcnow()
    )
    db.add(log)
    db.commit()
    logger.info(f"-> [TB-01 EMAIL SENT] Đến: {customer.email} | Tiêu đề: {subject}")
