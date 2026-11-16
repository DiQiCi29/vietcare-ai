import logging
import smtplib
import ssl
import threading
from datetime import datetime
from email.message import EmailMessage
from email.utils import formataddr

from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.core.database import SessionLocal
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
        return False

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

    # Save to notification log (TB-01 requirement), then deliver in the background so the
    # staff action never waits on (or fails because of) the mail server.
    configured = smtp_configured()
    log = NotificationLog(
        request_id=request.id,
        recipient_email=customer.email,
        subject=subject,
        content=body,
        status="PENDING" if configured else "NOT_CONFIGURED",
        created_at=datetime.utcnow()
    )
    db.add(log)
    db.commit()
    if not configured:
        logger.info(f"-> [TB-01 EMAIL CHƯA GỬI - chưa cấu hình SMTP] Đến: {customer.email} | Tiêu đề: {subject}")
        return False
    threading.Thread(target=_deliver, args=(log.id, customer.email, subject, body), daemon=True).start()
    return True


def smtp_configured():
    return bool(settings.SMTP_HOST and settings.SMTP_USER and settings.SMTP_PASSWORD)


def send_email(to, subject, body):
    """Send one plain-text email through the configured SMTP server (Gmail: port 587 + App Password)."""
    msg = EmailMessage()
    msg["Subject"] = subject
    # Gmail rewrites any other From address to the login account, so default to SMTP_USER.
    msg["From"] = formataddr((settings.EMAILS_FROM_NAME, settings.EMAILS_FROM_EMAIL or settings.SMTP_USER))
    msg["To"] = to
    msg.set_content(body + "\n\n---\nViettronimex Đà Nẵng - Tổng đài bảo hành miễn phí: 1800 64 64 92\n"
                    "Email được gửi tự động, vui lòng không trả lời email này.")
    context = ssl.create_default_context()
    if settings.SMTP_PORT == 465:
        with smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, context=context, timeout=20) as server:
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.send_message(msg)
    else:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20) as server:
            server.starttls(context=context)
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.send_message(msg)


def _deliver(log_id, to, subject, body):
    error = None
    try:
        send_email(to, subject, body)
    except (smtplib.SMTPException, OSError) as exc:
        # Never log the password; the exception text from smtplib does not contain it.
        error = f"{type(exc).__name__}: {exc}"[:500]
    with SessionLocal() as db:
        log = db.get(NotificationLog, log_id)
        if log:
            log.status = "FAILED" if error else "SENT"
            log.error_message = error
            db.commit()
    if error:
        logger.warning(f"-> [TB-01 EMAIL LỖI] Đến: {to} | {error}")
    else:
        logger.info(f"-> [TB-01 EMAIL SENT] Đến: {to} | Tiêu đề: {subject}")
