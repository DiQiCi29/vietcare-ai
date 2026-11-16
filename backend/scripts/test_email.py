"""Send one test email to check the SMTP settings in .env.

Usage: python -m backend.scripts.test_email <địa_chỉ_nhận@gmail.com>
"""
import smtplib
import sys

from backend.app.core.config import settings
from backend.app.services.email_service import send_email, smtp_configured


def main(to):
    if not smtp_configured():
        sys.exit('Chưa cấu hình SMTP: điền SMTP_USER và SMTP_PASSWORD trong file .env rồi chạy lại.')
    print(f'Đang gửi thử qua {settings.SMTP_HOST}:{settings.SMTP_PORT} bằng tài khoản {settings.SMTP_USER} ...')
    try:
        send_email(to, '[VietCare] Email thử nghiệm', 'Nếu bạn nhận được email này, cấu hình gửi email của VietCare đã đúng.')
    except smtplib.SMTPAuthenticationError:
        sys.exit('Sai tài khoản hoặc mật khẩu ứng dụng (App Password). Kiểm tra lại SMTP_USER / SMTP_PASSWORD.')
    except (smtplib.SMTPException, OSError) as exc:
        sys.exit(f'Gửi thất bại: {type(exc).__name__}: {exc}')
    print(f'Đã gửi tới {to}. Kiểm tra hộp thư (cả mục Spam).')


if __name__ == '__main__':
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
