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
    experience: Optional[str] = None
    date_of_birth: Optional[date] = None
    about_myself: Optional[str] = None
    education: Optional[str] = None


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
    coordinates: str

    class Config:
        from_attributes = True

# ==================== Patient Schemas ====================

class PatientCreate(BaseModel):
    full_name: str = Field(..., min_length=1, description="ФИО обязательно")
    phone: str = Field(..., min_length=1, description="Телефон обязателен")
    date_of_birth: date = Field(..., description="Дата рождения обязательна")
    email: Optional[EmailStr] = None
    gender: str = Field(..., pattern="^(male|female)$", description="Пол обязателен (male/female)")
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


class PatientsStatsResponse(BaseModel):
    total: int
    active: int
    new_patients: int
    activity: float
    # ==================== Referral Schemas ====================

class ReferralCreate(BaseModel):
    clinic_id: int = Field(..., description="ID клиники")
    patient_id: int = Field(..., description="ID пациента")
    specialization_id: int = Field(..., description="ID специализации")
    expected_visit_start: date = Field(..., description="Начало ожидаемого периода визита")
    expected_visit_end: date = Field(..., description="Конец ожидаемого периода визита")
    med_indications: str = Field(..., min_length=1, description="Медицинские показания/жалобы")
    special_wishes: Optional[str] = Field(None, description="Особые пожелания")


class ReferralResponse(BaseModel):
    id: int
    doctor_id: int
    clinic_id: int
    patient_id: int
    specialization_id: int
    expected_visit_start: date
    expected_visit_end: date
    med_indications: str
    special_wishes: Optional[str]
    status: str
    created_at: datetime

    class Config:
        from_attributes = True



        # ==================== Referral Update Schemas ====================

class ReferralUpdate(BaseModel):
    status: Optional[str] = Field(None, pattern="^(appointed|confirmed|scheduled|completed|no-show|cancelled)$")
    expected_visit_start: Optional[date] = None
    expected_visit_end: Optional[date] = None
    med_indications: Optional[str] = None
    special_wishes: Optional[str] = None



    # ==================== Referral Response (расширенный) ====================

class ReferralDetailResponse(BaseModel):
    id: int
    doctor_id: int
    clinic_id: int
    patient_id: int
    specialization_id: int
    expected_visit_start: date
    expected_visit_end: date
    med_indications: str
    special_wishes: Optional[str]
    status: str
    created_at: datetime
    
    # Дополнительные поля для отображения
    patient_full_name: Optional[str] = None
    patient_phone: Optional[str] = None
    clinic_name: Optional[str] = None
    clinic_address: Optional[str] = None
    specialization_name: Optional[str] = None

    class Config:
        from_attributes = True




class DashboardStatsResponse(BaseModel):
    total_referrals: int
    active_patients: int
    today_referrals: int
    upcoming_visits: int





class RecentActivityResponse(BaseModel):
    id: int
    label: str
    info: str
    created_at: datetime

    class Config:
        from_attributes = True


class UpcomingAppointmentResponse(BaseModel):
    id: int
    patient_name: str
    clinic_name: str
    clinic_address: str
    expected_visit_start: date
    status: str

    class Config:
        from_attributes = True


class TopClinicResponse(BaseModel):
    id: int
    name: str
    address: str
    referrals_count: int

    class Config:
        from_attributes = True