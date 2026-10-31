from datetime import datetime, timedelta, timezone

from fastapi import HTTPException

VIETNAM_TZ = timezone(timedelta(hours=7))


def today_vietnam():
    return datetime.now(VIETNAM_TZ).date()


def is_expired(item):
    return item.warranty_expire_date < today_vietnam()


def ensure_supported(item):
    if is_expired(item):
        raise HTTPException(403, "Sản phẩm đã hết bảo hành.")
