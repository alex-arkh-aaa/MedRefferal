from pydantic import BaseModel, EmailStr, Field, validator
from datetime import date, datetime
from typing import List, Optional
from enum import Enum


# ==================== Enums ====================

class UserRole(str, Enum):
    USER = "user"
    ADMIN = "admin"
    PARTNER = "partner"


class PartnerRequestStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


# ==================== Auth Schemas ====================

class DoctorRegister(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6)
    full_name: str = Field(..., min_length=1)
    phone: str = Field(...)
    code: int = Field(...)




class UserRegisterPartner(BaseModel):
    email: EmailStr
    full_name: str = Field(..., min_length=1)
    company_name: str = Field(..., min_length=1)
    phone: str = Field(..., min_length=1)
    description: Optional[str] = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class EmailVerify(BaseModel):
    email: EmailStr
    code: str = Field(..., min_length=6, max_length=6)


class EmailResend(BaseModel):
    email: EmailStr


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MessageResponse(BaseModel):
    message: str


# ==================== User Schemas ====================

class UserResponse(BaseModel):
    id: int
    email: EmailStr
    full_name: str
    phone: str
    created_at: datetime
    experience: str
    date_of_birth: date
    about_myself: str
    education: str


    class Config:
        from_attributes = True


class UserUpdate(BaseModel):
    full_name: Optional[str] = None


# ==================== Doctor Update Schemas ====================

class DoctorUpdate(BaseModel):
    full_name: Optional[str] = None
    #phone: Optional[str] = None
    date_of_birth: Optional[date] = None
    experience: Optional[str] = None
    about_myself: Optional[str] = None
    education: Optional[str] = None  # 👈 добавить

    specialization_ids: Optional[List[int]] = None  # список id специализаций


class DoctorSpecializationResponse(BaseModel):
    id: int
    name: str

    class Config:
        from_attributes = True

# ==================== Clinic Schemas ====================

class ClinicResponse(BaseModel):
    id: int
    name: str
    address: str
    location_url: str

    class Config:
        from_attributes = True

# ==================== Patient Schemas ====================

class PatientCreate(BaseModel):
    full_name: str = Field(..., min_length=1)
    phone: str = Field(..., min_length=1)
    date_of_birth: Optional[date] = None
    email: Optional[EmailStr] = None
    gender: Optional[str] = Field(None, pattern="^(male|female)$")
    info: Optional[str] = None


class PatientUpdate(BaseModel):
    full_name: Optional[str] = Field(None, min_length=1)
    phone: Optional[str] = Field(None, min_length=1)
    date_of_birth: Optional[date] = None
    email: Optional[EmailStr] = None
    gender: Optional[str] = Field(None, pattern="^(male|female)$")
    info: Optional[str] = None
    status: Optional[str] = Field(None, pattern="^(active|inactive|new)$")


class PatientResponse(BaseModel):
    id: int
    doctor_id: int
    full_name: str
    phone: str
    date_of_birth: Optional[date] = None
    email: Optional[str] = None
    gender: Optional[str] = None
    info: Optional[str] = None
    status: str
    age: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PatientListResponse(BaseModel):
    items: List[PatientResponse]
    total: int
    page: int
    limit: int
    pages: int