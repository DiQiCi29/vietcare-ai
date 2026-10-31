import enum
from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Enum, ForeignKey, Text
from sqlalchemy.orm import relationship
from backend.app.core.database import Base

class UserRole(str, enum.Enum):
    ADMIN = "ADMIN"
    CSKH = "CSKH"
    TECHNICIAN = "TECHNICIAN"

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(Enum(UserRole), default=UserRole.CSKH, nullable=False)
    phone = Column(String(20), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    assigned_requests = relationship("WarrantyRequest", back_populates="technician", foreign_keys="WarrantyRequest.technician_id")
    status_histories = relationship("RequestStatusHistory", back_populates="performer")
    inspections = relationship("Inspection", back_populates="technician")

class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String(100), nullable=False)
    phone = Column(String(20), unique=True, index=True, nullable=False)  # Login ID
    email = Column(String(100), nullable=False)  # Required for TB-01 notifications
    hashed_password = Column(String(255), nullable=False)
    is_first_login_changed = Column(Boolean, default=False)  # Must change password on first login
    address = Column(Text, nullable=True)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)

    # Relationships
    sold_items = relationship("SoldItem", back_populates="customer")
    requests = relationship("WarrantyRequest", back_populates="customer")
    chat_sessions = relationship("ChatSession", back_populates="customer")
