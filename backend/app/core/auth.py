from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.core.database import get_db
from backend.app.models.user import Customer, User, UserRole

bearer = HTTPBearer(auto_error=False)


def get_current_actor(
    credentials: HTTPAuthorizationCredentials = Depends(bearer),
    db: Session = Depends(get_db),
):
    unauthorized = HTTPException(401, "Phiên đăng nhập không hợp lệ hoặc đã hết hạn", headers={"WWW-Authenticate": "Bearer"})
    if not credentials:
        raise unauthorized
    try:
        claims = jwt.decode(credentials.credentials, settings.SECRET_KEY,
                            algorithms=[settings.ALGORITHM],
                            options={"require_exp": True, "require_sub": True})
        role = claims.get("role")
        if role not in {"CUSTOMER", *(r.value for r in UserRole)}:
            raise unauthorized
        model = Customer if role == "CUSTOMER" else User
        actor = db.get(model, int(claims["sub"]))
    except (JWTError, ValueError, TypeError, KeyError):
        raise unauthorized
    if not actor or not actor.is_active:
        raise unauthorized
    if isinstance(actor, User) and actor.role.value != role:
        raise unauthorized
    return actor


def require_staff(actor=Depends(get_current_actor)):
    if not isinstance(actor, User):
        raise HTTPException(403, "Chỉ nhân viên được thực hiện thao tác này")
    return actor


def require_manager(actor=Depends(require_staff)):
    if actor.role not in (UserRole.ADMIN, UserRole.CSKH):
        raise HTTPException(403, "Chỉ CSKH hoặc quản trị viên được thực hiện thao tác này")
    return actor


def require_customer(actor=Depends(get_current_actor)):
    if not isinstance(actor, Customer):
        raise HTTPException(403, "Chỉ khách hàng được thực hiện thao tác này")
    return actor


def require_admin(actor=Depends(require_staff)):
    if actor.role != UserRole.ADMIN:
        raise HTTPException(403, "Chỉ trưởng phòng hoặc quản trị viên được xem tổng quan")
    return actor


def check_customer_access(actor, customer):
    if isinstance(actor, Customer) and actor.id == customer.id:
        return
    if isinstance(actor, User) and actor.role in (UserRole.ADMIN, UserRole.CSKH):
        return
    raise HTTPException(403, "Không được truy cập dữ liệu khách hàng này")
