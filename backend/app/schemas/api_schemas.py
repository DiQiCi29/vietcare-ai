from pydantic import BaseModel, Field
from backend.app.models.warranty import RequestStatus, WarrantyConclusion
from typing import Optional, List
from datetime import datetime, date

# Auth Schemas
class LoginRequest(BaseModel):
    username_or_phone: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    user_type: str # 'customer' or 'staff'
    name: str
    role: Optional[str] = None
    phone_or_email: str
    is_first_login: bool = False

# Customer Schemas
class CustomerProductOut(BaseModel):
    id: int
    product_name: str
    model: Optional[str] = None
    brand: Optional[str] = None
    category: Optional[str] = None
    serial_number: Optional[str] = None
    purchase_date: Optional[str] = None
    warranty_expire_date: Optional[str] = None
    is_expired: bool
    image_url: Optional[str] = None
    active_request_id: Optional[int] = None

# Warranty Request Schemas
class CreateRequestInput(BaseModel):
    sold_item_id: Optional[int] = None
    customer_phone: Optional[str] = None # For phone call reception by CSKH
    customer_name: Optional[str] = None
    customer_email: Optional[str] = None
    error_group: str
    error_description: str
    support_address: str
    channel: str = "Web" # "Web" or "Điện thoại"
    images: Optional[str] = None

class StatusUpdateInput(BaseModel):
    new_status: RequestStatus
    notes: Optional[str] = None
    technician_id: Optional[int] = None
    appointment_date: Optional[date] = None
    conclusion: Optional[WarrantyConclusion] = None
    repair_content: Optional[str] = None
    parts_replaced: Optional[str] = None

class VerifyInput(BaseModel):
    action: str
    notes: str = ""

class AssignInput(BaseModel):
    technician_id: int
    appointment_date: date
    notes: str = ""

class CompleteInput(BaseModel):
    conclusion: WarrantyConclusion
    repair_content: str
    parts_replaced: Optional[str] = None

# Chat Schema
class ChatInput(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    sold_item_id: Optional[int] = None
    session_id: Optional[str] = Field(default=None, max_length=50)
    request_id: Optional[int] = Field(default=None, gt=0)
    history: Optional[List[dict]] = Field(default=None, max_length=8)

class ContactInput(BaseModel):
    phone: str
    message: str = Field(min_length=1, max_length=2000)
    sold_item_id: int = Field(gt=0)
