import sys
from sqlalchemy import delete, select, func, and_, or_, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from datetime import date, datetime, timezone, timedelta
from typing import Optional, List, Tuple
from .models import *
# from .schemas import AdFilterParams


# ==================== Users ====================

async def create_user(
    db: AsyncSession,
    email: str,
    password_hash: str,
    full_name: str,
    phone: Optional[str] = None,
) -> Doctor:
    doctor = Doctor(
        email=email,
        password_hash=password_hash,
        full_name=full_name,
        phone=phone,
    )
    db.add(doctor)
    await db.commit()
    await db.refresh(doctor)
    return doctor


async def get_user(db: AsyncSession, user_id: int) -> Optional[Doctor]:
    result = await db.execute(
        select(Doctor).where(Doctor.id == user_id)
    )
    return result.scalar_one_or_none()


async def get_user_by_email(db: AsyncSession, email: str) -> Optional[Doctor]:
    result = await db.execute(
        select(Doctor).where(Doctor.email == email)
    )
    return result.scalar_one_or_none()


async def get_user_by_email_including_inactive(db: AsyncSession, email: str) -> Optional[Doctor]:
    """Получить пользователя даже если is_active=False (нужно для проверки при регистрации)"""
    result = await db.execute(select(Doctor).where(Doctor.email == email))
    return result.scalar_one_or_none()


async def get_users(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 100,
    search: Optional[str] = None
) -> Tuple[List[Doctor], int]:
    query = select(Doctor)
    
    
    if search:
        query = query.where(
            or_(
                Doctor.email.ilike(f"%{search}%"),
                Doctor.full_name.ilike(f"%{search}%")
            )
        )
    
    # Подсчёт общего количества
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.execute(count_query)
    total = total.scalar()
    
    # Пагинация
    query = query.offset(skip).limit(limit).order_by(Doctor.created_at.desc())
    result = await db.execute(query)
    users = result.scalars().all()
    
    return users, total


async def soft_delete_user(db: AsyncSession, user_id: int) -> Optional[Doctor]:
    """Soft delete — помечаем пользователя как удалённого"""
    user = await get_user(db, user_id)
    if user:
        user.is_active = False
        user.deleted_at = datetime.utcnow()

        await db.commit()
        await db.refresh(user)
    return user


async def recover_account(db: AsyncSession, user_id: int) -> Optional[Doctor]:
    """Восстановление аккаунта — помечаем пользователя как is_active=True"""
    user = await get_user(db, user_id)
    if user:
        user.is_active = True
        user.deleted_at = None

        await db.commit()
        await db.refresh(user)
    return user


async def admin_delete_user(db: AsyncSession, user_id: int) -> bool:
    """Полное удаление любого юзера"""
    
    await db.execute(
        delete(Doctor).where(Doctor.id == user_id)
    )
    await db.commit()



# ==================== Doctors (update) ====================

async def update_doctor(
    db: AsyncSession,
    doctor_id: int,
    **kwargs
) -> Optional[Doctor]:
    """Обновить данные доктора"""
    result = await db.execute(
        select(Doctor).where(Doctor.id == doctor_id)
    )
    doctor = result.scalar_one_or_none()
    
    if not doctor:
        return None
    
    for key, value in kwargs.items():
        if value is not None and hasattr(doctor, key):
            setattr(doctor, key, value)
    
    doctor.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(doctor)
    return doctor


async def get_doctor_specializations(db: AsyncSession, doctor_id: int) -> List[Specialization]:
    """Получить специализации доктора"""
    result = await db.execute(
        select(Specialization)
        .join(DoctorSpecialization)
        .where(DoctorSpecialization.doctor_id == doctor_id)
        .order_by(Specialization.name)
    )
    return result.scalars().all()


# ==================== Email Verification ====================

async def create_email_verification(
    db: AsyncSession,
    email: str,
    code: str,
    expires_minutes: int = 15
) -> EmailVerification:
    expires_at = datetime.utcnow() + timedelta(minutes=expires_minutes)
    verification = EmailVerification(
        doctor_email=email,
        code=code,
        expires_at=expires_at
    )
    db.add(verification)
    await db.commit()
    await db.refresh(verification)
    return verification


async def get_email_verification(
    db: AsyncSession,
    email: str,
    code: str
) -> Optional[EmailVerification]:
    
    result = await db.execute(
        select(EmailVerification).where(
            EmailVerification.doctor_email == email,
            EmailVerification.code == code,
            EmailVerification.expires_at > datetime.utcnow()
        )
    )

    return result.scalar_one_or_none()


async def delete_email_verification(db: AsyncSession, email: str):
    await db.execute(
        delete(EmailVerification).where(EmailVerification.doctor_email == email)
    )
    await db.commit()




# ==================== Clinics ====================

async def get_all_clinics(db: AsyncSession) -> List[Clinic]:
    """Получить все клиники"""
    result = await db.execute(
        select(Clinic).order_by(Clinic.name)
    )
    return result.scalars().all()



# ==================== Patients ====================

async def get_patients_by_doctor(
    db: AsyncSession,
    doctor_id: int,
    search: Optional[str] = None,
    status: Optional[str] = None,
    gender: Optional[str] = None,
    age_from: Optional[int] = None,
    age_to: Optional[int] = None,
    skip: int = 0,
    limit: int = 100
) -> Tuple[List[Patient], int]:
    """Получить пациентов доктора с фильтрами"""
    
    query = select(Patient).where(Patient.doctor_id == doctor_id)
    
    # Поиск
    if search:
        query = query.where(
            or_(
                Patient.full_name.ilike(f"%{search}%"),
                Patient.phone.ilike(f"%{search}%"),
                Patient.email.ilike(f"%{search}%")
            )
        )
    
    # Статус
    if status:
        query = query.where(Patient.status == status)
    
    # Пол
    if gender:
        query = query.where(Patient.gender == gender)
    
    # Возраст (расчет через дату рождения)
    if age_from is not None or age_to is not None:
        # В PostgreSQL можно использовать EXTRACT
        from sqlalchemy import extract
        current_year = datetime.utcnow().year
        
        if age_from is not None:
            year_limit = current_year - age_from
            query = query.where(extract('year', Patient.date_of_birth) <= year_limit)
        
        if age_to is not None:
            year_limit = current_year - age_to
            query = query.where(extract('year', Patient.date_of_birth) >= year_limit)
    
    # Подсчет общего количества
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.execute(count_query)
    total = total.scalar()
    
    # Пагинация и сортировка
    query = query.offset(skip).limit(limit).order_by(Patient.created_at.desc())
    result = await db.execute(query)
    patients = result.scalars().all()
    
    # Добавляем age в каждый объект (вычисляем на лету)
    for patient in patients:
        if patient.date_of_birth:
            age = datetime.utcnow().year - patient.date_of_birth.year
            # Корректировка если день рождения еще не наступил
            if (datetime.utcnow().month, datetime.utcnow().day) < (patient.date_of_birth.month, patient.date_of_birth.day):
                age -= 1
            patient.age = age
        else:
            patient.age = None
    
    return patients, total


async def get_patient_by_id(db: AsyncSession, patient_id: int, doctor_id: int) -> Optional[Patient]:
    """Получить пациента по id (с проверкой, что принадлежит доктору)"""
    result = await db.execute(
        select(Patient).where(
            Patient.id == patient_id,
            Patient.doctor_id == doctor_id
        )
    )
    patient = result.scalar_one_or_none()
    
    if patient and patient.date_of_birth:
        age = datetime.utcnow().year - patient.date_of_birth.year
        if (datetime.utcnow().month, datetime.utcnow().day) < (patient.date_of_birth.month, patient.date_of_birth.day):
            age -= 1
        patient.age = age
    
    return patient


async def create_patient(
    db: AsyncSession,
    doctor_id: int,
    full_name: str,
    phone: str,
    date_of_birth: Optional[date] = None,
    email: Optional[str] = None,
    gender: Optional[str] = None,
    info: Optional[str] = None
) -> Patient:
    """Создать нового пациента"""
    
    patient = Patient(
        doctor_id=doctor_id,
        full_name=full_name,
        phone=phone,
        date_of_birth=date_of_birth,
        email=email,
        gender=gender,
        info=info,
        status="active"
    )
    db.add(patient)
    await db.commit()
    await db.refresh(patient)
    
    if patient.date_of_birth:
        age = datetime.utcnow().year - patient.date_of_birth.year
        if (datetime.utcnow().month, datetime.utcnow().day) < (patient.date_of_birth.month, patient.date_of_birth.day):
            age -= 1
        patient.age = age
    
    return patient


async def update_patient(
    db: AsyncSession,
    patient_id: int,
    doctor_id: int,
    **kwargs
) -> Optional[Patient]:
    """Обновить данные пациента"""
    
    result = await db.execute(
        select(Patient).where(
            Patient.id == patient_id,
            Patient.doctor_id == doctor_id
        )
    )
    patient = result.scalar_one_or_none()
    
    if not patient:
        return None
    
    for key, value in kwargs.items():
        if value is not None and hasattr(patient, key):
            setattr(patient, key, value)
    
    patient.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(patient)
    
    if patient.date_of_birth:
        age = datetime.utcnow().year - patient.date_of_birth.year
        if (datetime.utcnow().month, datetime.utcnow().day) < (patient.date_of_birth.month, patient.date_of_birth.day):
            age -= 1
        patient.age = age
    
    return patient


async def delete_patient(db: AsyncSession, patient_id: int, doctor_id: int) -> bool:
    """Удалить пациента"""
    result = await db.execute(
        delete(Patient).where(
            Patient.id == patient_id,
            Patient.doctor_id == doctor_id
        )
    )
    await db.commit()
    return result.rowcount > 0


async def get_patient_referrals_count(db: AsyncSession, patient_id: int) -> int:
    """Получить количество направлений у пациента"""
    result = await db.execute(
        select(func.count()).where(Referral.patient_id == patient_id)
    )
    return result.scalar()
