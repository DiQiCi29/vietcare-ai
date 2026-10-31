from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Date
from sqlalchemy.orm import relationship
from backend.app.core.database import Base

class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    model = Column(String(100), nullable=False, unique=True, index=True)
    brand = Column(String(100), nullable=True, index=True)
    category = Column(String(100), nullable=False, index=True)  # Tivi, Máy lạnh, Tủ lạnh, Máy giặt, Quạt...
    default_warranty_months = Column(Integer, default=24, nullable=False)
    image_url = Column(String(500), nullable=True)
    specifications = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    sold_items = relationship("SoldItem", back_populates="product")

class SoldItem(Base):
    __tablename__ = "sold_items"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    serial_number = Column(String(100), unique=True, index=True, nullable=False)
    purchase_date = Column(Date, nullable=False)
    warranty_expire_date = Column(Date, nullable=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    product = relationship("Product", back_populates="sold_items")
    customer = relationship("Customer", back_populates="sold_items")
    warranty_requests = relationship("WarrantyRequest", back_populates="sold_item")
    chat_sessions = relationship("ChatSession", back_populates="sold_item")
