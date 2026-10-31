"""Add catalog products to the sample customer without replacing existing purchases.

Run from the project root: python -m backend.scripts.seed_sample_products --apply
The script is idempotent and makes a SQLite backup before adding records.
"""
import argparse
import calendar
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3

ROOT = Path(__file__).resolve().parents[2]
MODELS = ('FTKB60ZVMV', 'UA65U8500H', 'KD-55X75K', 'RF59C700ES9/SV',
          'RF48A4000B4/SV', 'WW90T634DLN', 'WA95CG4545BDSV')


def add_months(day, months):
    index = day.year * 12 + day.month - 1 + months
    year, month = divmod(index, 12)
    month += 1
    return day.replace(year=year, month=month, day=min(day.day, calendar.monthrange(year, month)[1]))


def seed(database, phone='0905123456', apply=False):
    if not database.is_file():
        raise ValueError('Database does not exist')
    today = datetime.now(timezone(timedelta(hours=7))).date()
    with sqlite3.connect(database) as db:
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        customer = db.execute('SELECT id FROM customers WHERE phone=?', (phone,)).fetchone()
        if not customer:
            raise ValueError('Sample customer does not exist')
        products = []
        for model in MODELS:
            row = db.execute('SELECT * FROM products WHERE model=?', (model,)).fetchone()
            if not row:
                raise ValueError(f'Catalog product missing: {model}')
            products.append(row)
        fan = db.execute('SELECT * FROM products WHERE category=? AND brand=? ORDER BY id LIMIT 1',
                         ('Quạt làm mát', 'Daikiosan')).fetchone()
        if not fan:
            raise ValueError('Daikiosan fan is missing from catalog')
        products.append(fan)
        additions = [p for p in products if not db.execute(
            'SELECT 1 FROM sold_items WHERE customer_id=? AND product_id=?',
            (customer['id'], p['id'])).fetchone()]
        backup_path = None
        if apply and additions:
            backup_dir = ROOT / '.backups'
            backup_dir.mkdir(exist_ok=True)
            backup_path = backup_dir / f'vietcare-before-demo-{datetime.now().strftime("%Y%m%d-%H%M%S-%f")}.db'
            with sqlite3.connect(backup_path) as backup:
                db.backup(backup)
            db.execute('BEGIN IMMEDIATE')
            purchase = today - timedelta(days=90)
            for product in additions:
                db.execute('''INSERT INTO sold_items
                    (customer_id, product_id, serial_number, purchase_date, warranty_expire_date, notes, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)''', (
                    customer['id'], product['id'], f'DEMO-{phone}-P{product["id"]:04d}', purchase.isoformat(),
                    add_months(purchase, product['default_warranty_months'] or 24).isoformat(),
                    'Sản phẩm bổ sung cho tài khoản khách hàng mẫu.', datetime.now(timezone.utc).replace(tzinfo=None).isoformat(' '),
                ))
            db.commit()
        totals = db.execute('''SELECT COUNT(*), SUM(warranty_expire_date >= ?), SUM(warranty_expire_date < ?)
            FROM sold_items WHERE customer_id=?''', (today.isoformat(), today.isoformat(), customer['id'])).fetchone()
        return {'added' if apply else 'would_add': len(additions), 'models': [p['model'] for p in additions],
                'total': totals[0], 'in_warranty': totals[1], 'expired': totals[2],
                'backup': str(backup_path) if backup_path else None}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    print(json.dumps(seed(ROOT / 'vietcare.db', apply=args.apply), ensure_ascii=True, indent=2))
