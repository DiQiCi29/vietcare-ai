from backend.app.core.database import Base
from backend.app.models.user import User, Customer, UserRole
from backend.app.models.product import Product, SoldItem
from backend.app.models.warranty import (
    WarrantyRequest,
    RequestStatusHistory,
    Attachment,
    Inspection,
    RequestStatus,
    ReceptionChannel
)
from backend.app.models.policy import WarrantyPolicy
from backend.app.models.chat import ChatSession, ChatMessage
from backend.app.models.notification import NotificationLog

__all__ = [
    "Base",
    "User",
    "Customer",
    "UserRole",
    "Product",
    "SoldItem",
    "WarrantyRequest",
    "RequestStatusHistory",
    "Attachment",
    "Inspection",
    "RequestStatus",
    "ReceptionChannel",
    "WarrantyPolicy",
    "ChatSession",
    "ChatMessage",
    "NotificationLog",
]
