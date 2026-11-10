import os
from typing import List, Union
from pydantic import AnyHttpUrl, validator
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "VietCare AI - Quản lý bảo hành Viettronimex Đà Nẵng"
    VERSION: str = "1.0.0"
    DEBUG: bool = True
    API_V1_STR: str = "/api/v1"
    
    SECRET_KEY: str = "vietcare-super-secret-key-change-in-production-12345678"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440 # 24 hours
    
    DATABASE_URL: str = "sqlite:///./vietcare.db"
    
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.5-flash"
    
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    EMAILS_FROM_EMAIL: str = "baohanh@vietro.com.vn"
    EMAILS_FROM_NAME: str = "Viettronimex Bảo Hành"
    
    # Customer OTP login. Leave Twilio values empty to use the on-screen demo code.
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_VERIFY_SERVICE_SID: str = ""
    OTP_TTL_SECONDS: int = 300
    OTP_RESEND_SECONDS: int = 30
    OTP_MAX_ATTEMPTS: int = 5
    # Dev/demo customers that log in without an OTP (comma-separated). Empty string disables it.
    OTP_BYPASS_PHONES: str = "0900000000"

    @property
    def otp_bypass_phones(self) -> set:
        return {p.strip() for p in self.OTP_BYPASS_PHONES.split(",") if p.strip()}

    UPLOAD_DIR: str = "./uploads"
    MAX_UPLOAD_SIZE_MB: int = 25

    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()
