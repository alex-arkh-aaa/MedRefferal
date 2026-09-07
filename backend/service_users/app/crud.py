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

# ==================== Change Email ====================

async def update_doctor_email(db: AsyncSession, doctor_id: int, new_email: str) -> Optional[Doctor]:
    """Обновить email доктора (отдельная функция для безопасности)"""
    result = await db.execute(
        select(Doctor).where(Doctor.id == doctor_id)
    )
    doctor = result.scalar_one_or_none()
    
    if not doctor:
        return None
    
    doctor.email = new_email
    doctor.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(doctor)
    return doctor
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



async def get_doctor_stats(db: AsyncSession, doctor_id: int) -> dict:
    """Получить статистику доктора для профиля"""
    
    # Всего направлений
    referrals_result = await db.execute(
        select(func.count()).where(Referral.doctor_id == doctor_id)
    )
    total_referrals = referrals_result.scalar() or 0
    
    # Всего пациентов
    patients_result = await db.execute(
        select(func.count()).where(Patient.doctor_id == doctor_id)
    )
    total_patients = patients_result.scalar() or 0
    
    return {
        "total_referrals": total_referrals,
        "total_patients": total_patients
    }
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



async def get_patient_by_email(db: AsyncSession, email: str, patient_id: Optional[int] = None) -> Optional[Patient]:
    result = await db.execute(
        select(Patient).where(Patient.email == email, Patient.id != patient_id)
    )
    return result.scalar_one_or_none()


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
    await add_history(db, doctor_id, "Добавлен пациент", f"{full_name}")

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
    await add_history(db, doctor_id, "Обновлен пациент", f"{patient.full_name}")

    return patient


async def delete_patient(db: AsyncSession, patient_id: int, doctor_id: int) -> bool:
    """Удалить пациента"""
    patient = await get_patient_by_id(db, patient_id, doctor_id)
    print(patient, '----------------------------------')
    patient_name = patient.full_name
    result = await db.execute(
        delete(Patient).where(
            Patient.id == patient_id,
            Patient.doctor_id == doctor_id
        )
    )
    await db.commit()

    await add_history(db, doctor_id, "Удален пациент", f"{patient_name}")

    return result.rowcount > 0


async def get_patient_referrals_count(db: AsyncSession, patient_id: int) -> int:
    """Получить количество направлений у пациента"""
    result = await db.execute(
        select(func.count()).where(Referral.patient_id == patient_id)
    )
    return result.scalar()



async def get_patients_stats(db: AsyncSession, doctor_id: int) -> dict:
    """Получить статистику пациентов для дашборда"""
    
    from datetime import date, datetime
    
    # Всего пациентов
    total_result = await db.execute(
        select(func.count()).where(Patient.doctor_id == doctor_id)
    )
    total = total_result.scalar() or 0
    
    # Активные пациенты (status = 'active')
    active_result = await db.execute(
        select(func.count()).where(
            Patient.doctor_id == doctor_id,
            Patient.status == 'active'
        )
    )
    active = active_result.scalar() or 0
    
    # Новых за месяц (created_at >= начало месяца)
    today = datetime.utcnow().date()
    first_day = date(today.year, today.month, 1)
    new_result = await db.execute(
        select(func.count()).where(
            Patient.doctor_id == doctor_id,
            func.date(Patient.created_at) >= first_day
        )
    )
    new_patients = new_result.scalar() or 0
    
    # Активность (% активных от всех)
    activity = round((active / total * 100), 1) if total > 0 else 0
    
    return {
        "total": total,
        "active": active,
        "new_patients": new_patients,
        "activity": activity
    }

# ==================== Referrals ====================

async def create_referral(
    db: AsyncSession,
    doctor_id: int,
    clinic_id: int,
    patient_id: int,
    specialization_id: int,
    expected_visit_start: date,
    expected_visit_end: date,
    med_indications: str,
    special_wishes: Optional[str] = None
) -> Referral:
    """Создать новое направление"""
    
    referral = Referral(
        doctor_id=doctor_id,
        clinic_id=clinic_id,
        patient_id=patient_id,
        specialization_id=specialization_id,
        expected_visit_start=expected_visit_start,
        expected_visit_end=expected_visit_end,
        med_indications=med_indications,
        special_wishes=special_wishes or "",
        status="appointed"
    )
    db.add(referral)
    await db.commit()
    await db.refresh(referral)

    patient = await get_patient_by_id(db, patient_id, doctor_id)
    clinic = await db.execute(select(Clinic).where(Clinic.id == clinic_id))
    await add_history(db, doctor_id, "Создано направление", f"Для пациента {patient.full_name} в {clinic.scalar_one().name}")

    return referral


async def get_referrals_by_doctor(
    db: AsyncSession,
    doctor_id: int,
    skip: int = 0,
    limit: int = 100
) -> Tuple[List[Referral], int]:
    """Получить все направления доктора"""
    
    query = select(Referral).where(Referral.doctor_id == doctor_id)
    
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.execute(count_query)
    total = total.scalar()
    
    query = query.offset(skip).limit(limit).order_by(Referral.created_at.desc())
    result = await db.execute(query)
    referrals = result.scalars().all()
    
    return referrals, total



# ==================== Referrals (update & delete) ====================

async def update_referral(
    db: AsyncSession,
    referral_id: int,
    doctor_id: int,
    **kwargs
) -> Optional[Referral]:
    """Обновить направление"""
    
    result = await db.execute(
        select(Referral).where(
            Referral.id == referral_id,
            Referral.doctor_id == doctor_id
        )
    )
    referral = result.scalar_one_or_none()
    
    if not referral:
        return None
    
    for key, value in kwargs.items():
        if value is not None and hasattr(referral, key):
            setattr(referral, key, value)

    referral.updated_at = datetime.utcnow()  # 👈 добавь, если есть поле updated_at

    await db.commit()
    await db.refresh(referral)
    return referral


async def get_referral_by_id(
    db: AsyncSession,
    referral_id: int,
    doctor_id: int
) -> Optional[Referral]:
    """Получить направление по id"""
    
    result = await db.execute(
        select(Referral).where(
            Referral.id == referral_id,
            Referral.doctor_id == doctor_id
        )
    )
    return result.scalar_one_or_none()

async def delete_referral(
    db: AsyncSession,
    referral_id: int,
    doctor_id: int
) -> bool:
    """Удалить направление"""

    referral = await get_referral_by_id(db, referral_id, doctor_id)
    patient = await get_patient_by_id(db, referral.patient_id, doctor_id)
    
    
    result = await db.execute(
        delete(Referral).where(
            Referral.id == referral_id,
            Referral.doctor_id == doctor_id
        )
    )
    await db.commit()
    await add_history(db, doctor_id, "Удалено направление", f"Направление #{referral_id} для пациента {patient.full_name}")

    return result.rowcount > 0



# ==================== Referrals (with search) ====================

async def get_referrals_by_doctor(
    db: AsyncSession,
    doctor_id: int,
    search: Optional[str] = None,
    status: Optional[str] = None,
    clinic_id: Optional[int] = None,
    skip: int = 0,
    limit: int = 100
) -> Tuple[List[Referral], int]:
    """Получить направления доктора с фильтрами"""
    
    query = select(Referral).where(Referral.doctor_id == doctor_id)
    
    # Поиск по пациенту
    if search:
        query = query.join(Patient).where(
            Patient.full_name.ilike(f"%{search}%")
        )
    
    # Фильтр по статусу
    if status:
        query = query.where(Referral.status == status)
    
    # Фильтр по клинике
    if clinic_id:
        query = query.where(Referral.clinic_id == clinic_id)
    
    # Подсчет общего количества
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.execute(count_query)
    total = total.scalar()
    
    # Пагинация и сортировка
    query = query.offset(skip).limit(limit).order_by(Referral.created_at.desc())
    query = query.options(
        selectinload(Referral.patient),
        selectinload(Referral.clinic),
        selectinload(Referral.specialization)
    )
    result = await db.execute(query)
    referrals = result.scalars().all()
    
    return referrals, total



















async def get_dashboard_stats(db: AsyncSession, doctor_id: int) -> dict:
    """Получить статистику для дашборда"""
    
    # Всего направлений
    total_result = await db.execute(
        select(func.count()).where(Referral.doctor_id == doctor_id)
    )
    total_referrals = total_result.scalar() or 0
    
    # Активные пациенты (status = 'active')
    patients_result = await db.execute(
        select(func.count()).where(
            Patient.doctor_id == doctor_id,
            Patient.status == 'active'
        )
    )
    active_patients = patients_result.scalar() or 0
    
    # Новых направлений сегодня
    today = datetime.utcnow().date()
    today_result = await db.execute(
        select(func.count()).where(
            Referral.doctor_id == doctor_id,
            func.date(Referral.created_at) == today
        )
    )
    today_referrals = today_result.scalar() or 0
    
    # Предстоящие визиты (status = 'scheduled' и дата >= сегодня)
    upcoming_result = await db.execute(
        select(func.count()).where(
            Referral.doctor_id == doctor_id,
            Referral.status == 'scheduled',
            Referral.expected_visit_end >= today
        )
    )
    upcoming_visits = upcoming_result.scalar() or 0
    
    return {
        "total_referrals": total_referrals,
        "active_patients": active_patients,
        "today_referrals": today_referrals,
        "upcoming_visits": upcoming_visits
    }




async def get_recent_activity(db: AsyncSession, doctor_id: int, limit: int = 5) -> List[History]:
    """Получить последние действия доктора"""
    result = await db.execute(
        select(History)
        .where(History.doctor_id == doctor_id)
        .order_by(History.created_at.desc())
        .limit(limit)
    )
    return result.scalars().all()


async def get_upcoming_appointments(db: AsyncSession, doctor_id: int, limit: int = 4) -> List[Referral]:
    """Получить ближайшие визиты (статус scheduled)"""
    result = await db.execute(
        select(Referral)
        .options(
            selectinload(Referral.patient),
            selectinload(Referral.clinic)
        )
        .where(
            Referral.doctor_id == doctor_id,
            Referral.status == 'scheduled',
            Referral.expected_visit_end >= datetime.utcnow().date()
        )
        .order_by(Referral.expected_visit_start.asc())
        .limit(limit)
    )
    return result.scalars().all()


async def get_top_clinics(db: AsyncSession, limit: int) -> List[dict]:
    """Получить топ клиник по количеству направлений (все доктора)"""
    result = await db.execute(
        select(
            Clinic.id,
            Clinic.name,
            Clinic.address,
            func.count(Referral.id).label('referrals_count')
        )
        .join(Referral, Referral.clinic_id == Clinic.id)
        .group_by(Clinic.id)
        .order_by(func.count(Referral.id).desc())
    )
    return [{"id": r[0], "name": r[1], "address": r[2], "referrals_count": r[3]} for r in result.all()]



async def add_history(
    db: AsyncSession,
    doctor_id: int,
    label: str,
    info: str
) -> History:
    """Добавить запись в историю"""
    history = History(
        doctor_id=doctor_id,
        label=label,
        info=info
    )
    db.add(history)
    await db.commit()
    await db.refresh(history)
    return history
