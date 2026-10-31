from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean
from backend.app.core.database import Base

class WarrantyPolicy(Base):
    """
    Chính sách bảo hành (QT-05) - Nguồn tri thức Knowledge Base cho AI Chatbot RAG
    """
    __tablename__ = "warranty_policies"

    id = Column(Integer, primary_key=True, index=True)
    product_category = Column(String(100), nullable=False, index=True) # Điều hòa, Tivi, Tủ lạnh, Máy giặt, Quạt...
    brand = Column(String(100), nullable=True, index=True)             # Daikin, Samsung, LG, Casper...
    error_group = Column(String(100), nullable=True, index=True)      # Chảy nước, Không nguồn, Mất gas, Vỡ màn hình...
    title = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)                            # Nội dung quy định chi tiết
    is_covered = Column(Boolean, default=True)                        # Được hay từ chối bảo hành
    conditions = Column(Text, nullable=True)                          # Điều kiện đi kèm
    version = Column(String(20), default="1.0")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
