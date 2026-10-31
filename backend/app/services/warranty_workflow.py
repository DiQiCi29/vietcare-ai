from datetime import datetime

from fastapi import HTTPException

from backend.app.models.user import User, UserRole
from backend.app.models.warranty import (
    Inspection, RequestStatus as S, RequestStatusHistory, WarrantyRequest,
)

TRANSITIONS = {
    S.RECEIVED: {S.VERIFYING},
    S.VERIFYING: {S.PENDING_ADDITIONAL_INFO, S.REJECTED, S.ASSIGNED},
    S.PENDING_ADDITIONAL_INFO: {S.VERIFYING},
    S.ASSIGNED: {S.ASSIGNED, S.IN_PROGRESS},
    S.IN_PROGRESS: {S.COMPLETED},
    S.COMPLETED: set(),
    S.REJECTED: set(),
}


def check_request_access(actor, request):
    if actor.role == UserRole.TECHNICIAN and request.technician_id != actor.id:
        raise HTTPException(403, "Kỹ thuật viên chỉ được thao tác ca được giao")


def transition(db, request, actor, payload):
    """Validate every mutation before changing the request or adding its audit log."""
    check_request_access(actor, request)
    target = payload.new_status
    current = request.status
    if target not in TRANSITIONS[current]:
        raise HTTPException(409, "Chuyển trạng thái không đúng quy trình bảo hành")
    is_tech = actor.role == UserRole.TECHNICIAN
    declining = is_tech and current == target == S.ASSIGNED
    if is_tech:
        if not (declining or target in (S.IN_PROGRESS, S.COMPLETED)):
            raise HTTPException(403, "Kỹ thuật viên không được xác minh hoặc phân công")
        if payload.technician_id is not None or payload.appointment_date is not None:
            raise HTTPException(403, "Kỹ thuật viên không được sửa phân công hoặc lịch hẹn")
    elif target in (S.IN_PROGRESS, S.COMPLETED):
        raise HTTPException(403, "Kỹ thuật viên được giao phải nhận việc và hoàn tất ca")

    notes = (payload.notes or "").strip()
    if target in (S.REJECTED, S.PENDING_ADDITIONAL_INFO) or declining:
        if not notes:
            raise HTTPException(422, "Vui lòng ghi rõ lý do hoặc thông tin cần bổ sung")

    technician = None
    if target == S.ASSIGNED and not declining:
        technician = db.get(User, payload.technician_id) if payload.technician_id else None
        if not technician or technician.role != UserRole.TECHNICIAN or not technician.is_active:
            raise HTTPException(422, "Phải chọn kỹ thuật viên đang hoạt động")
        if not payload.appointment_date:
            raise HTTPException(422, "Phải chọn ngày hẹn")
    elif payload.technician_id is not None or payload.appointment_date is not None:
        raise HTTPException(422, "Chỉ cập nhật kỹ thuật viên và ngày hẹn khi phân công")

    if target == S.COMPLETED:
        if not (payload.repair_content or "").strip() or payload.conclusion is None:
            raise HTTPException(422, "Phải nhập kết luận và nội dung sửa chữa")
    elif any(value is not None for value in (payload.conclusion, payload.repair_content, payload.parts_replaced)):
        raise HTTPException(422, "Chỉ ghi biên bản khi hoàn tất sửa chữa")

    # Compare-and-swap prevents a stale request from overwriting another transition.
    values = {"status": target, "updated_at": datetime.utcnow()}
    if declining:
        values.update(technician_id=None, appointment_date=None)
    elif technician:
        values.update(technician_id=technician.id,
                      appointment_date=datetime.combine(payload.appointment_date, datetime.min.time()))
    if target == S.COMPLETED:
        values["completed_at"] = datetime.utcnow()
    changed = db.query(WarrantyRequest).filter(
        WarrantyRequest.id == request.id,
        WarrantyRequest.status == current,
        WarrantyRequest.technician_id == request.technician_id,
    ).update(values, synchronize_session=False)
    if changed != 1:
        raise HTTPException(409, "Phiếu vừa được cập nhật, vui lòng tải lại")
    db.expire(request)
    db.refresh(request)
    if target == S.COMPLETED:
        db.add(Inspection(request_id=request.id, technician_id=actor.id,
                          cause=notes, conclusion=payload.conclusion,
                          repair_content=payload.repair_content.strip(),
                          parts_replaced=payload.parts_replaced))
    db.add(RequestStatusHistory(request_id=request.id, status=target,
                               performed_by_id=actor.id,
                               notes=notes or f"Chuyển trạng thái sang: {target.value}"))
