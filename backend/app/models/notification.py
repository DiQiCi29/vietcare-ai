from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from backend.app.core.database import Base

class NotificationLog(Base):
    """
    Nhật ký thông báo email gửi cho khách (TB-01: lưu thời gian, gửi thành công hay lỗi, có nút Gửi lại email)
    """
    __tablename__ = "notification_logs"

    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(Integer, ForeignKey("warranty_requests.id"), nullable=False)
    recipient_email = Column(String(100), nullable=False)
    subject = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    status = Column(String(20), default="SENT") # 'SENT', 'FAILED', 'PENDING'
    error_message = Column(Text, nullable=True)
    retry_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    request = relationship("WarrantyRequest", back_populates="notifications")
