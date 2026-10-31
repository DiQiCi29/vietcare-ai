"""Read ticket facts only from the authenticated customer's records."""
import re
from datetime import timezone

from sqlalchemy import desc, or_

from backend.app.models.warranty import WarrantyRequest, RequestStatus
from backend.app.models.product import SoldItem
from backend.app.rag.intents import normalize
from backend.app.services.eligibility import VIETNAM_TZ, today_vietnam


def _local_time(value):
    return value.replace(tzinfo=timezone.utc).astimezone(VIETNAM_TZ).strftime('%H:%M %d/%m/%Y')


def ticket_data(req):
    history = [h for h in req.status_history if not h.is_internal_note]
    inspection = max(req.inspections, key=lambda row: (row.created_at, row.id), default=None)
    return {
        'id': req.id, 'request_code': req.request_code, 'status': req.status.value,
        'sold_item_id': req.sold_item_id,
        'product_name': req.sold_item.product.name if req.sold_item else 'Thiết bị trên phiếu',
        'technician_name': req.technician.name if req.technician else None,
        'appointment_date': req.appointment_date.strftime('%d/%m/%Y') if req.appointment_date else None,
        'updated_at': _local_time(req.updated_at),
        'latest_note': history[-1].notes if history else None,
        'repair_content': inspection.repair_content if inspection else None,
        'conclusion': inspection.conclusion.value if inspection and inspection.conclusion else None,
    }


def tracking_response(db, customer_id, query, sold_item=None, request_id=None, history=None):
    base = db.query(WarrantyRequest).outerjoin(SoldItem, SoldItem.id == WarrantyRequest.sold_item_id).filter(
        WarrantyRequest.customer_id == customer_id,
        or_(WarrantyRequest.sold_item_id.is_(None), SoldItem.warranty_expire_date >= today_vietnam()),
    )
    codes = re.findall(r'\bBH[-\s](\d{4})[-\s](\d+)\b', query, re.I)
    codes = [f'BH-{year}-{number}' for year, number in codes]
    all_tickets = any(s in normalize(query) for s in ('tat ca', 'cac phieu', 'phieu khac', 'con phieu', 'danh sach'))
    if request_id is not None and not codes and not all_tickets:
        base = base.filter(WarrantyRequest.id == request_id)
    elif codes:
        base = base.filter(WarrantyRequest.request_code.in_(codes))
    elif sold_item is not None and not all_tickets:
        base = base.filter(WarrantyRequest.sold_item_id == sold_item.id)
    elif not all_tickets and history:
        # Follow up the last displayed ticket, without trusting a client-provided owner.
        for message in reversed(history):
            if message.get('sender') == 'bot':
                prior_codes = re.findall(r'\bBH-\d{4}-\d+\b', message.get('message', ''), re.I)
                if len(prior_codes) == 1:
                    base = base.filter(WarrantyRequest.request_code == prior_codes[0].upper())
                break
    if not all_tickets and not codes and request_id is None:
        active = base.filter(WarrantyRequest.status.notin_([RequestStatus.COMPLETED, RequestStatus.REJECTED]))
        if active.count():
            base = active
    total = base.count()
    records = base.order_by(desc(WarrantyRequest.created_at), desc(WarrantyRequest.id)).limit(5).all()
    data = [ticket_data(req) for req in records]
    if not data:
        reply = 'Mình không tìm thấy phiếu phù hợp trong tài khoản của bạn. Bạn có thể xem mục Yêu cầu của tôi hoặc gửi mã phiếu cần tra cứu.'
    else:
        sections = []
        for row in data:
            lines = [f'**{row["request_code"]} — {row["product_name"]}**', f'Trạng thái hiện tại: **{row["status"]}**.']
            lines.append(f'Kỹ thuật viên: {row["technician_name"]}.' if row['technician_name'] else 'Chưa phân công kỹ thuật viên.')
            lines.append(f'Lịch hẹn: {row["appointment_date"]}.' if row['appointment_date'] else 'Chưa có lịch hẹn được ghi nhận; mình chưa thể báo thời gian đến hoặc hoàn tất.')
            if row['latest_note']:
                lines.append(f'Cập nhật gần nhất: {row["latest_note"]}')
            if row['repair_content']:
                lines.append(f'Nội dung sửa chữa: {row["repair_content"]}')
            if row['conclusion']:
                lines.append(f'Kết luận ghi nhận: {row["conclusion"]}.')
            lines.append(f'Dữ liệu cập nhật: {row["updated_at"]}.')
            sections.append('\n'.join(lines))
        reply = '\n\n'.join(sections)
        if total > len(data):
            reply += f'\n\nĐang hiển thị 5/{total} phiếu gần nhất. Bạn xem toàn bộ trong Yêu cầu của tôi hoặc nhập mã phiếu cụ thể.'
    return {'reply': reply, 'suggested_action': 'VIEW_WARRANTY_REQUESTS',
            'cited_policies': [], 'is_expired': False, 'response_mode': 'request_status',
            'requests': data, 'total_requests': total}
