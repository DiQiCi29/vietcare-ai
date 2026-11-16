"""Point a sample customer at a real mailbox so status emails can be checked.

Usage: python -m backend.scripts.set_customer_email <số_điện_thoại> <email>
"""
import re
import sys

from backend.app.core.database import SessionLocal
from backend.app.models.user import Customer


def main(phone, email):
    email = email.strip()
    if not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', email):
        sys.exit('Email không hợp lệ')
    with SessionLocal() as db:
        customer = db.query(Customer).filter(Customer.phone == phone).first()
        if not customer:
            sys.exit(f'Không tìm thấy khách hàng có số {phone}')
        customer.email = email
        db.commit()
        print(f'Đã đổi email của {customer.full_name} ({phone}) thành {email}')


if __name__ == '__main__':
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
