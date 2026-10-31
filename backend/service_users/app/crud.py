import sys
from sqlalchemy import delete, select, func, and_, or_, update, extract
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from datetime import date, datetime, timezone, timedelta
from typing import Optional, List, Tuple
from .models import *


# ==================== Agents ====================

async def create_user(
    db: AsyncSession,
    email: str,
    password_hash: str,
    full_name: str,
    phone: Optional[str] = None,
    about_myself: Optional[str] = None,
) -> Agent:
    agent = Agent(
        email=email,
        password_hash=password_hash,
        full_name=full_name,
        phone=phone,
        about_myself=about_myself,
        status="pending",
    )
    db.add(agent)
    await db.commit()
    await db.refresh(agent)
    return agent


async def get_user(db: AsyncSession, user_id: int) -> Optional[Agent]:
    result = await db.execute(select(Agent).where(Agent.id == user_id))
    return result.scalar_one_or_none()


async def get_user_by_email(db: AsyncSession, email: str) -> Optional[Agent]:
    result = await db.execute(select(Agent).where(Agent.email == email))
    return result.scalar_one_or_none()


get_agent_by_email = get_user_by_email


async def get_user_by_email_including_inactive(db: AsyncSession, email: str) -> Optional[Agent]:
    result = await db.execute(select(Agent).where(Agent.email == email))
    return result.scalar_one_or_none()


async def get_users(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 100,
    search: Optional[str] = None,
) -> Tuple[List[Agent], int]:
    query = select(Agent)
    if search:
        query = query.where(
            or_(
                Agent.email.ilike(f"%{search}%"),
                Agent.full_name.ilike(f"%{search}%"),
            )
        )

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar()

    query = query.offset(skip).limit(limit).order_by(Agent.created_at.desc())
    result = await db.execute(query)
    return result.scalars().all(), total


async def soft_delete_user(db: AsyncSession, user_id: int) -> Optional[Agent]:
    user = await get_user(db, user_id)
    if user:
        user.status = "inactive"
        user.deleted_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(user)
    return user


async def recover_account(db: AsyncSession, user_id: int) -> Optional[Agent]:
    user = await get_user(db, user_id)
    if user:
        user.status = "active"
        user.deleted_at = None
        await db.commit()
        await db.refresh(user)
    return user


async def admin_delete_user(db: AsyncSession, user_id: int) -> bool:
    await db.execute(delete(Agent).where(Agent.id == user_id))
    await db.commit()
    return True


# ==================== Agents (update / specializations) ====================

async def update_doctor(
    db: AsyncSession,
    doctor_id: int,
    **kwargs,
) -> Optional[Agent]:
    result = await db.execute(select(Agent).where(Agent.id == doctor_id))
    agent = result.scalar_one_or_none()
    if not agent:
        return None

    for key, value in kwargs.items():
        if value is not None and hasattr(agent, key):
            setattr(agent, key, value)

    agent.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(agent)
    return agent


update_agent = update_doctor


async def get_doctor_specializations(db: AsyncSession, doctor_id: int) -> List[Specialization]:
    result = await db.execute(
        select(Specialization)
        .join(AgentSpecialization)
        .where(
            AgentSpecialization.agent_id == doctor_id,
            AgentSpecialization.active == True,
        )
        .order_by(Specialization.name)
    )
    return result.scalars().all()


async def get_agent_specializations(db: AsyncSession, agent_id: int) -> List[AgentSpecialization]:
    result = await db.execute(
        select(AgentSpecialization)
        .options(selectinload(AgentSpecialization.specialization))
        .where(AgentSpecialization.agent_id == agent_id)
    )
    return result.scalars().all()


async def set_agent_specializations(
    db: AsyncSession,
    agent_id: int,
    specialization_ids: List[int],
) -> None:
    result = await db.execute(
        select(AgentSpecialization).where(AgentSpecialization.agent_id == agent_id)
    )
    existing = {link.specialization_id: link for link in result.scalars().all()}

    new_ids = set(specialization_ids)

    for spec_id, link in existing.items():
        if spec_id not in new_ids:
            await db.delete(link)

    for spec_id in specialization_ids:
        if spec_id not in existing:
            db.add(AgentSpecialization(agent_id=agent_id, specialization_id=spec_id, active=True))

    await db.commit()


async def toggle_agent_specialization(
    db: AsyncSession,
    agent_id: int,
    specialization_id: int,
    active: bool,
) -> Optional[AgentSpecialization]:
    result = await db.execute(
        select(AgentSpecialization).where(
            AgentSpecialization.agent_id == agent_id,
            AgentSpecialization.specialization_id == specialization_id,
        )
    )
    link = result.scalar_one_or_none()
    if not link:
        return None
    link.active = active
    await db.commit()
    await db.refresh(link)
    return link


# ==================== Change Email ====================

async def update_doctor_email(db: AsyncSession, doctor_id: int, new_email: str) -> Optional[Agent]:
    result = await db.execute(select(Agent).where(Agent.id == doctor_id))
    agent = result.scalar_one_or_none()
    if not agent:
        return None
    agent.email = new_email
    agent.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(agent)
    return agent


# ==================== Email Verification ====================

async def create_email_verification(
    db: AsyncSession,
    email: str,
    code: str,
    expires_minutes: int = 15,
) -> EmailVerification:
    expires_at = datetime.utcnow() + timedelta(minutes=expires_minutes)
    verification = EmailVerification(
        email=email,
        code=code,
        expires_at=expires_at,
    )
    db.add(verification)
    await db.commit()
    await db.refresh(verification)
    return verification


async def get_email_verification(
    db: AsyncSession,
    email: str,
    code: str,
) -> Optional[EmailVerification]:
    result = await db.execute(
        select(EmailVerification).where(
            EmailVerification.email == email,
            EmailVerification.code == code,
            EmailVerification.expires_at > datetime.utcnow(),
        )
    )
    return result.scalar_one_or_none()


async def delete_email_verification(db: AsyncSession, email: str):
    await db.execute(
        delete(EmailVerification).where(EmailVerification.email == email)
    )
    await db.commit()


async def get_doctor_stats(db: AsyncSession, doctor_id: int) -> dict:
    referrals_result = await db.execute(
        select(func.count()).where(Referral.agent_id == doctor_id)
    )
    total_referrals = referrals_result.scalar() or 0

    patients_result = await db.execute(
        select(func.count()).where(Patient.agent_id == doctor_id)
    )
    total_patients = patients_result.scalar() or 0

    return {"total_referrals": total_referrals, "total_patients": total_patients}


# ==================== Admins ====================

async def get_admin_by_email(db: AsyncSession, email: str) -> Optional[Admin]:
    result = await db.execute(select(Admin).where(Admin.email == email))
    return result.scalar_one_or_none()


async def get_admin(db: AsyncSession, admin_id: int) -> Optional[Admin]:
    result = await db.execute(select(Admin).where(Admin.id == admin_id))
    return result.scalar_one_or_none()


async def get_admin_clinics(db: AsyncSession, admin_id: int) -> List[Clinic]:
    result = await db.execute(
        select(Clinic).join(AdminClinic).where(AdminClinic.admin_id == admin_id)
    )
    return result.scalars().all()


async def get_admin_clinic_ids(db: AsyncSession, admin_id: int) -> List[int]:
    result = await db.execute(
        select(AdminClinic.clinic_id).where(AdminClinic.admin_id == admin_id)
    )
    return [r[0] for r in result.all()]


async def create_admin(
    db: AsyncSession,
    email: str,
    password_hash: str,
    full_name: str,
    phone: Optional[str],
    role: str = "admin",
    clinic_ids: Optional[List[int]] = None,
    permissions: Optional[dict] = None,
) -> Admin:
    admin = Admin(
        email=email,
        password_hash=password_hash,
        full_name=full_name,
        phone=phone,
        role=role,
        active=True,
        permissions=permissions or {},
    )
    db.add(admin)
    await db.commit()
    await db.refresh(admin)

    if clinic_ids:
        # Проверка, что клиники существуют
        result = await db.execute(select(Clinic.id).where(Clinic.id.in_(clinic_ids)))
        existing_ids = {r[0] for r in result.all()}
        missing = set(clinic_ids) - existing_ids
        if missing:
            raise ValueError(f"Клиники не найдены: {sorted(missing)}")
        for cid in clinic_ids:
            db.add(AdminClinic(admin_id=admin.id, clinic_id=cid))
        await db.commit()

    return admin


async def update_admin(
    db: AsyncSession,
    admin_id: int,
    clinic_ids: Optional[List[int]] = None,
    **kwargs,
) -> Optional[Admin]:
    result = await db.execute(select(Admin).where(Admin.id == admin_id))
    admin = result.scalar_one_or_none()
    if not admin:
        return None

    for key, value in kwargs.items():
        if value is not None and hasattr(admin, key):
            setattr(admin, key, value)

    admin.updated_at = datetime.utcnow()
    await db.commit()

    if clinic_ids:
        # Проверка, что клиники существуют
        result = await db.execute(select(Clinic.id).where(Clinic.id.in_(clinic_ids)))
        existing_ids = {r[0] for r in result.all()}
        missing = set(clinic_ids) - existing_ids
        if missing:
            raise ValueError(f"Клиники не найдены: {sorted(missing)}")
        for cid in clinic_ids:
            db.add(AdminClinic(admin_id=admin.id, clinic_id=cid))
        await db.commit()

    await db.refresh(admin)
    return admin


async def delete_admin(db: AsyncSession, admin_id: int) -> bool:
    admin = await get_admin(db, admin_id)
    if not admin:
        return False
    await db.execute(delete(Admin).where(Admin.id == admin_id))
    await db.commit()
    return True


async def list_admins(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 100,
    search: Optional[str] = None,
    clinic_id: Optional[int] = None,
) -> Tuple[List[Admin], int]:
    query = select(Admin).where(Admin.role != "chef")

    if search:
        query = query.where(
            or_(
                Admin.email.ilike(f"%{search}%"),
                Admin.full_name.ilike(f"%{search}%"),
            )
        )

    if clinic_id is not None:
        query = query.join(AdminClinic).where(AdminClinic.clinic_id == clinic_id)

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar()

    query = query.offset(skip).limit(limit).order_by(Admin.created_at.desc())
    result = await db.execute(query)
    return result.scalars().all(), total


# ==================== AgentClinics ====================

async def get_agent_clinics(db: AsyncSession, agent_id: int) -> List[Clinic]:
    result = await db.execute(
        select(Clinic).join(AgentClinic).where(AgentClinic.agent_id == agent_id)
    )
    return result.scalars().all()


async def get_agent_clinic_ids(db: AsyncSession, agent_id: int) -> List[int]:
    result = await db.execute(
        select(AgentClinic.clinic_id).where(AgentClinic.agent_id == agent_id)
    )
    return [r[0] for r in result.all()]


async def set_agent_clinics(db: AsyncSession, agent_id: int, clinic_ids: List[int]) -> None:
    await db.execute(delete(AgentClinic).where(AgentClinic.agent_id == agent_id))
    for cid in clinic_ids:
        db.add(AgentClinic(agent_id=agent_id, clinic_id=cid))
    await db.commit()


# ==================== AgentRates ====================

async def get_agent_rates(db: AsyncSession, agent_id: int) -> List[AgentRate]:
    result = await db.execute(
        select(AgentRate)
        .options(selectinload(AgentRate.specialization))
        .where(AgentRate.agent_id == agent_id)
    )
    return result.scalars().all()


async def get_agent_rate(
    db: AsyncSession,
    agent_id: int,
    specialization_id: int,
) -> Optional[AgentRate]:
    result = await db.execute(
        select(AgentRate).where(
            AgentRate.agent_id == agent_id,
            AgentRate.specialization_id == specialization_id,
        )
    )
    return result.scalar_one_or_none()


async def set_agent_rate(
    db: AsyncSession,
    agent_id: int,
    specialization_id: int,
    mode: str,
    custom_rate: Optional[float] = None,
) -> AgentRate:
    rate = await get_agent_rate(db, agent_id, specialization_id)
    if not rate:
        rate = AgentRate(
            agent_id=agent_id,
            specialization_id=specialization_id,
            mode=mode,
            custom_rate=custom_rate,
        )
        db.add(rate)
    else:
        rate.mode = mode
        rate.custom_rate = custom_rate
    await db.commit()
    await db.refresh(rate)
    return rate


# ==================== ClinicSpecialties ====================

async def get_clinic_specialties(
    db: AsyncSession,
    clinic_id: int,
    include_inactive: bool = False,
) -> List[ClinicSpecialty]:
    query = select(ClinicSpecialty).where(ClinicSpecialty.clinic_id == clinic_id)
    if not include_inactive:
        query = query.where(ClinicSpecialty.active == True)
    result = await db.execute(query.options(selectinload(ClinicSpecialty.specialization)))
    return result.scalars().all()


async def get_clinic_specialty(
    db: AsyncSession,
    clinic_id: int,
    specialization_id: int,
) -> Optional[ClinicSpecialty]:
    result = await db.execute(
        select(ClinicSpecialty).where(
            ClinicSpecialty.clinic_id == clinic_id,
            ClinicSpecialty.specialization_id == specialization_id,
        )
    )
    return result.scalar_one_or_none()


async def upsert_clinic_specialty(
    db: AsyncSession,
    clinic_id: int,
    specialization_id: int,
    default_rate: Optional[float],
    active: bool,
) -> ClinicSpecialty:
    cs = await get_clinic_specialty(db, clinic_id, specialization_id)
    if not cs:
        cs = ClinicSpecialty(
            clinic_id=clinic_id,
            specialization_id=specialization_id,
            default_rate=default_rate,
            active=active,
        )
        db.add(cs)
    else:
        cs.default_rate = default_rate
        cs.active = active
    await db.commit()
    await db.refresh(cs)
    return cs


# ==================== Clinics ====================

async def get_all_clinics(db: AsyncSession, only_active: bool = False) -> List[Clinic]:
    query = select(Clinic).order_by(Clinic.name)
    if only_active:
        query = query.where(Clinic.active == True)
    result = await db.execute(query)
    return result.scalars().all()


async def get_clinic(db: AsyncSession, clinic_id: int) -> Optional[Clinic]:
    result = await db.execute(select(Clinic).where(Clinic.id == clinic_id))
    return result.scalar_one_or_none()


async def create_clinic(
    db: AsyncSession,
    name: str,
    city: str,
    address: Optional[str] = None,
    phone: Optional[str] = None,
    active: bool = True,
    default_rate: float = 10.0,
) -> Clinic:
    clinic = Clinic(name=name, city=city, address=address, phone=phone, active=active)
    db.add(clinic)
    await db.flush()  # чтобы clinic.id появился, но транзакция ещё не закоммичена

    # Автоматически создаём ClinicSpecialty для всех специализаций из справочника
    specs = await db.execute(select(Specialization))
    for spec in specs.scalars().all():
        db.add(
            ClinicSpecialty(
                clinic_id=clinic.id,
                specialization_id=spec.id,
                default_rate=default_rate,
                active=True,
            )
        )

    await db.commit()
    await db.refresh(clinic)
    return clinic


async def update_clinic(db: AsyncSession, clinic_id: int, **kwargs) -> Optional[Clinic]:
    clinic = await get_clinic(db, clinic_id)
    if not clinic:
        return None
    for key, value in kwargs.items():
        if value is not None and hasattr(clinic, key):
            setattr(clinic, key, value)
    clinic.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(clinic)
    return clinic


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
    limit: int = 100,
) -> Tuple[List[Patient], int]:
    query = select(Patient).where(Patient.agent_id == doctor_id)

    if search:
        query = query.where(
            or_(
                Patient.full_name.ilike(f"%{search}%"),
                Patient.phone.ilike(f"%{search}%"),
                Patient.email.ilike(f"%{search}%"),
            )
        )
    if status:
        query = query.where(Patient.status == status)
    if gender:
        query = query.where(Patient.gender == gender)

    if age_from is not None or age_to is not None:
        current_year = datetime.utcnow().year
        if age_from is not None:
            year_limit = current_year - age_from
            query = query.where(extract("year", Patient.date_of_birth) <= year_limit)
        if age_to is not None:
            year_limit = current_year - age_to
            query = query.where(extract("year", Patient.date_of_birth) >= year_limit)

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar()

    query = query.offset(skip).limit(limit).order_by(Patient.created_at.desc())
    result = await db.execute(query)
    patients = result.scalars().all()

    for patient in patients:
        if patient.date_of_birth:
            age = datetime.utcnow().year - patient.date_of_birth.year
            if (datetime.utcnow().month, datetime.utcnow().day) < (
                patient.date_of_birth.month,
                patient.date_of_birth.day,
            ):
                age -= 1
            patient.age = age
        else:
            patient.age = None

    return patients, total


async def get_patient_by_id(db: AsyncSession, patient_id: int, doctor_id: int) -> Optional[Patient]:
    result = await db.execute(
        select(Patient).where(
            Patient.id == patient_id,
            Patient.agent_id == doctor_id,
        )
    )
    patient = result.scalar_one_or_none()
    if patient and patient.date_of_birth:
        age = datetime.utcnow().year - patient.date_of_birth.year
        if (datetime.utcnow().month, datetime.utcnow().day) < (
            patient.date_of_birth.month,
            patient.date_of_birth.day,
        ):
            age -= 1
        patient.age = age
    return patient


async def get_patient_by_email(
    db: AsyncSession,
    email: str,
    patient_id: Optional[int] = None,
) -> Optional[Patient]:
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
    info: Optional[str] = None,
) -> Patient:
    patient = Patient(
        agent_id=doctor_id,
        full_name=full_name,
        phone=phone,
        date_of_birth=date_of_birth,
        email=email,
        gender=gender,
        info=info,
        status="active",
    )
    db.add(patient)
    await db.commit()
    await db.refresh(patient)

    if patient.date_of_birth:
        age = datetime.utcnow().year - patient.date_of_birth.year
        if (datetime.utcnow().month, datetime.utcnow().day) < (
            patient.date_of_birth.month,
            patient.date_of_birth.day,
        ):
            age -= 1
        patient.age = age

    await add_history(db, "agent", doctor_id, "Добавлен пациент", full_name)
    return patient


async def update_patient(
    db: AsyncSession,
    patient_id: int,
    doctor_id: int,
    **kwargs,
) -> Optional[Patient]:
    result = await db.execute(
        select(Patient).where(Patient.id == patient_id, Patient.agent_id == doctor_id)
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
        if (datetime.utcnow().month, datetime.utcnow().day) < (
            patient.date_of_birth.month,
            patient.date_of_birth.day,
        ):
            age -= 1
        patient.age = age

    await add_history(db, "agent", doctor_id, "Обновлен пациент", patient.full_name)
    return patient


async def delete_patient(db: AsyncSession, patient_id: int, doctor_id: int) -> bool:
    patient = await get_patient_by_id(db, patient_id, doctor_id)
    if not patient:
        return False

    patient_name = patient.full_name
    result = await db.execute(
        delete(Patient).where(Patient.id == patient_id, Patient.agent_id == doctor_id)
    )
    await db.commit()

    if result.rowcount > 0:
        await add_history(db, "agent", doctor_id, "Удален пациент", patient_name)
        return True
    return False


async def get_patient_referrals_count(db: AsyncSession, patient_id: int) -> int:
    result = await db.execute(select(func.count()).where(Referral.patient_id == patient_id))
    return result.scalar()


async def get_patients_stats(db: AsyncSession, doctor_id: int) -> dict:
    total_result = await db.execute(
        select(func.count()).where(Patient.agent_id == doctor_id)
    )
    total = total_result.scalar() or 0

    active_result = await db.execute(
        select(func.count()).where(Patient.agent_id == doctor_id, Patient.status == "active")
    )
    active = active_result.scalar() or 0

    today = datetime.utcnow().date()
    first_day = date(today.year, today.month, 1)
    new_result = await db.execute(
        select(func.count()).where(
            Patient.agent_id == doctor_id,
            func.date(Patient.created_at) >= first_day,
        )
    )
    new_patients = new_result.scalar() or 0

    activity = round((active / total * 100), 1) if total > 0 else 0
    return {"total": total, "active": active, "new_patients": new_patients, "activity": activity}


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
    special_wishes: Optional[str] = None,
    amount: int = 0,
    commission_rate: Optional[float] = None,
    commission_amount: int = 0,
    specialty_name_at_confirmation: Optional[str] = None,
) -> Referral:
    referral = Referral(
        agent_id=doctor_id,
        clinic_id=clinic_id,
        patient_id=patient_id,
        specialization_id=specialization_id,
        amount=amount,
        expected_visit_start=expected_visit_start,
        expected_visit_end=expected_visit_end,
        med_indications=med_indications,
        special_wishes=special_wishes or "",
        status="new",
        payout_status="unpaid",
        commission_rate=commission_rate,
        commission_amount=commission_amount,
        specialty_name_at_confirmation=specialty_name_at_confirmation,
    )
    db.add(referral)
    await db.commit()
    await db.refresh(referral)

    referral.status_changed_at = referral.created_at
    await db.commit()
    await db.refresh(referral)

    patient = await get_patient_by_id(db, patient_id, doctor_id)
    clinic = await get_clinic(db, clinic_id)
    await add_history(
        db,
        "agent",
        doctor_id,
        "Создано направление",
        f"Для пациента {patient.full_name} в {clinic.name}",
    )
    return referral


async def get_referrals_by_doctor(
    db: AsyncSession,
    doctor_id: int,
    search: Optional[str] = None,
    status: Optional[str] = None,
    clinic_id: Optional[int] = None,
    skip: int = 0,
    limit: int = 100,
) -> Tuple[List[Referral], int]:
    query = select(Referral).where(Referral.agent_id == doctor_id)

    if search:
        query = query.join(Patient).where(Patient.full_name.ilike(f"%{search}%"))
    if status:
        query = query.where(Referral.status == status)
    if clinic_id:
        query = query.where(Referral.clinic_id == clinic_id)

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar()

    query = (
        query.offset(skip)
        .limit(limit)
        .order_by(Referral.created_at.desc())
        .options(
            selectinload(Referral.patient),
            selectinload(Referral.clinic),
            selectinload(Referral.specialization),
        )
    )
    result = await db.execute(query)
    return result.scalars().all(), total


async def get_referral_by_id(db: AsyncSession, referral_id: int, doctor_id: int) -> Optional[Referral]:
    result = await db.execute(
        select(Referral).where(Referral.id == referral_id, Referral.agent_id == doctor_id)
    )
    return result.scalar_one_or_none()


async def update_referral(
    db: AsyncSession,
    referral_id: int,
    doctor_id: int,
    **kwargs,
) -> Optional[Referral]:
    result = await db.execute(
        select(Referral).where(Referral.id == referral_id, Referral.agent_id == doctor_id)
    )
    referral = result.scalar_one_or_none()
    if not referral:
        return None

    old_status = referral.status
    for key, value in kwargs.items():
        if value is not None and hasattr(referral, key):
            setattr(referral, key, value)

    if "status" in kwargs and kwargs["status"] != old_status:
        referral.status_changed_at = datetime.utcnow()

    await db.commit()
    await db.refresh(referral)
    return referral


async def delete_referral(db: AsyncSession, referral_id: int, doctor_id: int) -> bool:
    referral = await get_referral_by_id(db, referral_id, doctor_id)
    if not referral:
        return False
    patient = await get_patient_by_id(db, referral.patient_id, doctor_id)
    await db.execute(
        delete(Referral).where(Referral.id == referral_id, Referral.agent_id == doctor_id)
    )
    await db.commit()
    await add_history(
        db,
        "agent",
        doctor_id,
        "Удалено направление",
        f"Направление #{referral_id} для пациента {patient.full_name if patient else '—'}",
    )
    return True


# ==================== Dashboard ====================

async def get_dashboard_stats(db: AsyncSession, doctor_id: int) -> dict:
    total_result = await db.execute(
        select(func.count()).where(Referral.agent_id == doctor_id)
    )
    total_referrals = total_result.scalar() or 0

    patients_result = await db.execute(
        select(func.count()).where(Patient.agent_id == doctor_id, Patient.status == "active")
    )
    active_patients = patients_result.scalar() or 0

    today = datetime.utcnow().date()
    today_result = await db.execute(
        select(func.count()).where(
            Referral.agent_id == doctor_id,
            func.date(Referral.created_at) == today,
        )
    )
    today_referrals = today_result.scalar() or 0

    upcoming_result = await db.execute(
        select(func.count()).where(
            Referral.agent_id == doctor_id,
            Referral.status == "approved",
            Referral.expected_visit_end >= today,
        )
    )
    upcoming_visits = upcoming_result.scalar() or 0

    return {
        "total_referrals": total_referrals,
        "active_patients": active_patients,
        "today_referrals": today_referrals,
        "upcoming_visits": upcoming_visits,
    }


async def get_recent_activity(db: AsyncSession, doctor_id: int, limit: int = 5) -> List[History]:
    result = await db.execute(
        select(History)
        .where(History.actor_type == "agent", History.actor_id == doctor_id)
        .order_by(History.created_at.desc())
        .limit(limit)
    )
    return result.scalars().all()


async def get_upcoming_appointments(db: AsyncSession, doctor_id: int, limit: int = 4) -> List[Referral]:
    result = await db.execute(
        select(Referral)
        .options(selectinload(Referral.patient), selectinload(Referral.clinic))
        .where(
            Referral.agent_id == doctor_id,
            Referral.status == "approved",
            Referral.expected_visit_end >= datetime.utcnow().date(),
        )
        .order_by(Referral.expected_visit_start.asc())
        .limit(limit)
    )
    return result.scalars().all()


async def get_top_clinics(db: AsyncSession, limit: int) -> List[dict]:
    result = await db.execute(
        select(
            Clinic.id,
            Clinic.name,
            Clinic.address,
            func.count(Referral.id).label("referrals_count"),
        )
        .join(Referral, Referral.clinic_id == Clinic.id)
        .group_by(Clinic.id)
        .order_by(func.count(Referral.id).desc())
    )
    return [
        {"id": r[0], "name": r[1], "address": r[2], "referrals_count": r[3]}
        for r in result.all()
    ]



# ==================== Agents (admin) ====================

async def get_agent(db: AsyncSession, agent_id: int) -> Optional[Agent]:
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    return result.scalar_one_or_none()


async def list_agents(
    db: AsyncSession,
    clinic_ids: Optional[List[int]] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
) -> Tuple[List[Agent], int]:
    query = select(Agent)

    if clinic_ids is not None:
        if not clinic_ids:
            return [], 0
        query = query.join(AgentClinic).where(AgentClinic.clinic_id.in_(clinic_ids))

    if status:
        query = query.where(Agent.status == status)

    if search:
        query = query.where(
            or_(
                Agent.email.ilike(f"%{search}%"),
                Agent.full_name.ilike(f"%{search}%"),
            )
        )

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar()

    query = query.offset(skip).limit(limit).order_by(Agent.created_at.desc())
    result = await db.execute(query)
    return result.scalars().all(), total


async def soft_delete_agent(db: AsyncSession, agent_id: int) -> Optional[Agent]:
    agent = await get_agent(db, agent_id)
    if agent:
        agent.status = "inactive"
        agent.deleted_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(agent)
    return agent


# ==================== History ====================

async def add_history(
    db: AsyncSession,
    actor_type: str,
    actor_id: int,
    label: str,
    text: str,
    actor_name: Optional[str] = None,
) -> History:
    history = History(
        label=label,
        text=text,
        actor_type=actor_type,
        actor_id=actor_id,
        actor_name=actor_name,
    )
    db.add(history)
    await db.commit()
    await db.refresh(history)
    return history


async def get_history(
    db: AsyncSession,
    actor_type: Optional[str] = None,
    actor_id: Optional[int] = None,
    limit: int = 100,
) -> List[History]:
    query = select(History)
    if actor_type:
        query = query.where(History.actor_type == actor_type)
    if actor_id is not None:
        query = query.where(History.actor_id == actor_id)
    query = query.order_by(History.created_at.desc()).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


# ==================== Reports ====================

async def get_reports_stats(
    db: AsyncSession,
    doctor_id: int,
    date_from: date,
    date_to: date,
) -> dict:
    period_days = (date_to - date_from).days + 1
    prev_date_to = date_from - timedelta(days=1)
    prev_date_from = prev_date_to - timedelta(days=period_days - 1)

    total_result = await db.execute(
        select(func.count()).where(
            Referral.agent_id == doctor_id,
            func.date(Referral.created_at) >= date_from,
            func.date(Referral.created_at) <= date_to,
        )
    )
    total_referrals = total_result.scalar() or 0

    completed_result = await db.execute(
        select(func.count()).where(
            Referral.agent_id == doctor_id,
            Referral.status == "approved",
            func.date(Referral.created_at) >= date_from,
            func.date(Referral.created_at) <= date_to,
        )
    )
    completed = completed_result.scalar() or 0

    revenue_result = await db.execute(
        select(func.coalesce(func.sum(Referral.commission_amount), 0)).where(
            Referral.agent_id == doctor_id,
            Referral.status == "approved",
            Referral.payout_status == "paid",
            func.date(Referral.created_at) >= date_from,
            func.date(Referral.created_at) <= date_to,
        )
    )
    total_revenue = revenue_result.scalar() or 0

    prev_completed_result = await db.execute(
        select(func.count()).where(
            Referral.agent_id == doctor_id,
            Referral.status == "approved",
            func.date(Referral.created_at) >= prev_date_from,
            func.date(Referral.created_at) <= prev_date_to,
        )
    )
    prev_completed = prev_completed_result.scalar() or 0

    growth_text = "0%"
    growth_positive = True
    if completed == 0 and prev_completed == 0:
        growth_text = "0%"
    elif prev_completed == 0:
        growth_text = f"+{completed} завершено"
    else:
        percent = round(((completed - prev_completed) / prev_completed) * 100, 1)
        if percent > 0:
            growth_text = f"+{percent}%"
            growth_positive = True
        elif percent < 0:
            growth_text = f"{percent}%"
            growth_positive = False
        else:
            growth_text = "0%"

    conversion = round((completed / total_referrals * 100), 1) if total_referrals > 0 else 0

    return {
        "total_revenue": int(total_revenue),
        "total_referrals": total_referrals,
        "completed_referrals": completed,
        "conversion": conversion,
        "days_in_period": period_days,
        "growth_text": growth_text,
        "growth_positive": growth_positive,
    }


# ==================== Goals ====================

async def get_current_goal(db: AsyncSession, doctor_id: int) -> Optional[Goal]:
    today = datetime.utcnow()
    result = await db.execute(
        select(Goal).where(
            Goal.agent_id == doctor_id,
            Goal.month == today.month,
            Goal.year == today.year,
        )
    )
    return result.scalar_one_or_none()


async def upsert_goal(
    db: AsyncSession,
    doctor_id: int,
    income_money: int,
    referrals: int,
    month: int,
    year: int,
) -> Goal:
    result = await db.execute(
        select(Goal).where(
            Goal.agent_id == doctor_id,
            Goal.month == month,
            Goal.year == year,
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.income_money = income_money
        existing.referrals = referrals
        await db.commit()
        await db.refresh(existing)
        return existing

    goal = Goal(
        agent_id=doctor_id,
        month=month,
        year=year,
        income_money=income_money,
        referrals=referrals,
    )
    db.add(goal)
    await db.commit()
    await db.refresh(goal)
    return goal


async def get_goal_facts(db: AsyncSession, doctor_id: int, month: int, year: int) -> dict:
    from calendar import monthrange

    first_day = date(year, month, 1)
    last_day = date(year, month, monthrange(year, month)[1])

    revenue_result = await db.execute(
        select(func.coalesce(func.sum(Referral.commission_amount), 0)).where(
            Referral.agent_id == doctor_id,
            Referral.status == "approved",
            Referral.payout_status == "paid",
            func.date(Referral.created_at) >= first_day,
            func.date(Referral.created_at) <= last_day,
        )
    )
    total_revenue = revenue_result.scalar() or 0

    referrals_result = await db.execute(
        select(func.count()).where(
            Referral.agent_id == doctor_id,
            func.date(Referral.created_at) >= first_day,
            func.date(Referral.created_at) <= last_day,
        )
    )
    total_referrals = referrals_result.scalar() or 0

    return {"total_revenue": int(total_revenue), "total_referrals": total_referrals}

