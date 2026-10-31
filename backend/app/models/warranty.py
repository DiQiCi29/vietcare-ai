import enum
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Enum, Boolean
from sqlalchemy.orm import relationship
from backend.app.core.database import Base

class RequestStatus(str, enum.Enum):
    RECEIVED = "Tiếp nhận"                       # Tiếp nhận
    VERIFYING = "Xác minh"                       # Xác minh
    PENDING_ADDITIONAL_INFO = "Chờ bổ sung"      # Chờ bổ sung
    REJECTED = "Từ chối bảo hành"                # Từ chối bảo hành
    ASSIGNED = "Phân công"                       # Phân công
    IN_PROGRESS = "Sửa chữa"                     # Sửa chữa
    COMPLETED = "Hoàn tất"                       # Hoàn tất

class ReceptionChannel(str, enum.Enum):
    WEB = "Web"
    PHONE = "Điện thoại"
    CHATBOT = "Chatbot"

class WarrantyConclusion(str, enum.Enum):
    ACCEPTED = "Được bảo hành"
    REJECTED = "Từ chối bảo hành"


class RequestCodeSequence(Base):
    __tablename__ = "request_code_sequences"

    period = Column(String(4), primary_key=True)
    last_number = Column(Integer, nullable=False, default=0)

class WarrantyRequest(Base):
    __tablename__ = "warranty_requests"

    id = Column(Integer, primary_key=True, index=True)
    request_code = Column(String(50), unique=True, index=True, nullable=False) # New: BH-MMYY-NNNN; historical codes retained.
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    sold_item_id = Column(Integer, ForeignKey("sold_items.id"), nullable=True) # Optional if manually created or not matched
    
    # Error information
    error_group = Column(String(100), nullable=False)  # Nhóm lỗi
    error_description = Column(Text, nullable=False)   # Mô tả hư hỏng
    support_address = Column(Text, nullable=False)     # Địa chỉ hỗ trợ
    
    channel = Column(Enum(ReceptionChannel), default=ReceptionChannel.WEB, nullable=False)
    status = Column(Enum(RequestStatus), default=RequestStatus.RECEIVED, nullable=False, index=True)
    is_verification_needed = Column(Boolean, default=False)
    
    # Personnel involved
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # Staff who created via phone
    technician_id = Column(Integer, ForeignKey("users.id"), nullable=True)       # Assigned technician
    appointment_date = Column(DateTime, nullable=True)                           # Lịch hẹn
    
    # KPI Tracking
    repeat_call_count = Column(Integer, default=0) # CS-08: Số cuộc gọi lặp lại hỏi tiến độ
    
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    # Relationships
    customer = relationship("Customer", back_populates="requests")
    sold_item = relationship("SoldItem", back_populates="warranty_requests")
    technician = relationship("User", back_populates="assigned_requests", foreign_keys=[technician_id])
    status_history = relationship("RequestStatusHistory", back_populates="request", order_by="RequestStatusHistory.created_at.asc()")
    attachments = relationship("Attachment", back_populates="request")
    inspections = relationship("Inspection", back_populates="request")
    notifications = relationship("NotificationLog", back_populates="request")

class RequestStatusHistory(Base):
    """
    Append-only log of every status transition (Section 3: Chỉ thêm, không sửa/xóa)
    """
    __tablename__ = "request_status_history"

    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(Integer, ForeignKey("warranty_requests.id"), nullable=False)
    status = Column(Enum(RequestStatus), nullable=False)
    performed_by_id = Column(Integer, ForeignKey("users.id"), nullable=True) # Null if performed by customer (e.g. initial submit)
    notes = Column(Text, nullable=True)
    is_internal_note = Column(Boolean, default=False) # Ghi chú nội bộ chỉ nhân viên thấy
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    request = relationship("WarrantyRequest", back_populates="status_history")
    performer = relationship("User", back_populates="status_histories")

class Attachment(Base):
    __tablename__ = "attachments"

    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(Integer, ForeignKey("warranty_requests.id"), nullable=False)
    file_type = Column(String(20), nullable=False) # 'image' or 'video'
    file_path = Column(String(500), nullable=False)
    file_name = Column(String(255), nullable=True)
    file_size = Column(Integer, nullable=True) # bytes
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    request = relationship("WarrantyRequest", back_populates="attachments")

class Inspection(Base):
    """
    Biên bản kiểm tra / sửa chữa của Kỹ thuật viên (KT-04, KT-05)
    """
    __tablename__ = "inspections"

    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(Integer, ForeignKey("warranty_requests.id"), nullable=False)
    technician_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    cause = Column(Text, nullable=True) # Nguyên nhân lỗi
    conclusion = Column(Enum(WarrantyConclusion), nullable=True) # Kết luận bảo hành
    repair_content = Column(Text, nullable=True) # Nội dung sửa chữa
    parts_replaced = Column(Text, nullable=True) # Linh kiện thay thế
    inspection_image_url = Column(String(500), nullable=True) # Ảnh sau sửa / kiểm tra
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    request = relationship("WarrantyRequest", back_populates="inspections")
    technician = relationship("User", back_populates="inspections")
