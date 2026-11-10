"""Point a sample customer at a real phone so Twilio OTP SMS reaches it.

Usage: python -m backend.scripts.set_customer_phone <current_phone> <new_phone>
"""
import re
import sys

from backend.app.core.database import SessionLocal
from backend.app.models.user import Customer


def main(current, new):
    new = re.sub(r'[\s.-]', '', new)
    if not re.fullmatch(r'0\d{9}', new):
        sys.exit('Số mới phải có dạng 0xxxxxxxxx (10 chữ số)')
    with SessionLocal() as db:
        customer = db.query(Customer).filter(Customer.phone == current).first()
        if not customer:
            sys.exit(f'Không tìm thấy khách hàng có số {current}')
        if db.query(Customer).filter(Customer.phone == new).first():
            sys.exit(f'Số {new} đã thuộc về khách hàng khác')
        customer.phone = new
        db.commit()
        print(f'Đã đổi số của khách hàng #{customer.id} thành {new}')


if __name__ == '__main__':
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
