"""Create the dev customer (logs in without OTP) with one product per category.

Run from the project root: python -m backend.scripts.seed_dev_account
Idempotent: existing purchases are kept; a SQLite backup is made before any change.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import secrets
import sqlite3

from backend.scripts.seed_sample_products import add_months

ROOT = Path(__file__).resolve().parents[2]
PHONE = '0900000000'
NAME = 'Tài khoản Dev'
# (model, months since purchase, note) — a mix of warranty states for testing every screen.
PURCHASES = (
    ('FTKB35ZVMV', 2, 'Còn hạn bảo hành dài'),
    ('UA65U8500H', 6, 'Còn hạn bảo hành'),
    ('RF48A4000B4/SV', 10, 'Còn hạn bảo hành'),
    ('WW90T634DLN', 23, 'Sắp hết hạn bảo hành (dưới 1 tháng)'),
    ('DKA-05000E', 3, 'Còn hạn bảo hành (bảo hành 12 tháng)'),
    ('KD-55X75K', 30, 'Đã hết hạn bảo hành'),
)


def seed(database=ROOT / 'vietcare.db'):
    from backend.app.core.security import get_password_hash  # bcrypt is only needed here.

    today = datetime.now(timezone(timedelta(hours=7))).date()
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat(' ')
    with sqlite3.connect(database) as db:
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        products = []
        for model, months, note in PURCHASES:
            row = db.execute('SELECT id, default_warranty_months FROM products WHERE model=?', (model,)).fetchone()
            if not row:
                raise SystemExit(f'Thiếu sản phẩm trong danh mục: {model}')
            products.append((row, months, note))

        backup_dir = ROOT / '.backups'
        backup_dir.mkdir(exist_ok=True)
        with sqlite3.connect(backup_dir / f'vietcare-before-dev-{datetime.now():%Y%m%d-%H%M%S}.db') as backup:
            db.backup(backup)

        db.execute('BEGIN IMMEDIATE')
        customer = db.execute('SELECT id FROM customers WHERE phone=?', (PHONE,)).fetchone()
        if customer:
            customer_id = customer['id']
        else:
            # Password is random and unused: customers sign in by phone (OTP or dev bypass).
            customer_id = db.execute('''INSERT INTO customers
                (full_name, phone, email, hashed_password, is_first_login_changed, address, created_at, is_active)
                VALUES (?, ?, ?, ?, 1, ?, ?, 1)''', (
                NAME, PHONE, 'dev@vietcare.local', get_password_hash(secrets.token_urlsafe(16)),
                '01 Đường Thử Nghiệm, Q. Hải Châu, TP. Đà Nẵng', now)).lastrowid
        added = 0
        for product, months, note in products:
            if db.execute('SELECT 1 FROM sold_items WHERE customer_id=? AND product_id=?',
                          (customer_id, product['id'])).fetchone():
                continue
            purchase = add_months(today, -months)
            db.execute('''INSERT INTO sold_items
                (customer_id, product_id, serial_number, purchase_date, warranty_expire_date, notes, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)''', (
                customer_id, product['id'], f'DEV-{product["id"]:04d}', purchase.isoformat(),
                add_months(purchase, product['default_warranty_months'] or 24).isoformat(),
                f'Dữ liệu dev: {note}', now))
            added += 1
        db.commit()
        total = db.execute('SELECT COUNT(*) FROM sold_items WHERE customer_id=?', (customer_id,)).fetchone()[0]
    print(f'Khách hàng dev #{customer_id} ({PHONE}): thêm {added} sản phẩm, tổng {total} sản phẩm.')


if __name__ == '__main__':
    seed()
