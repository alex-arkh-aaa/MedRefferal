import asyncio
from fastapi import Body, FastAPI, Depends, HTTPException, Response, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload
from contextlib import asynccontextmanager
from typing import Optional
import sys
import os
from app.models import *

from .database import get_db
from . import crud
from .schemas import *
from .security import *
from .crud import *


from faststream.rabbit import RabbitBroker

broker = RabbitBroker("amqp://guest:guest@rabbitmq:5672/")


# ==================== Lifespan ====================
@asynccontextmanager
async def lifespan(app: FastAPI):
    #print("🔄 Подключение к RabbitMQ...", file=sys.stderr)
    try:
        max_retries = 30
        for attempt in range(max_retries):
            try:
                await broker.connect()
                #print("✅ Брокер подключен", file=sys.stderr)
                break
            except Exception as e:
                #print(f"❌ Попытка {attempt + 1}/{max_retries} не удалась: {e}", file=sys.stderr)
                if attempt < max_retries - 1:
                    await asyncio.sleep(2)
                else:
                    raise

        from faststream.rabbit import RabbitQueue
        await broker.declare_queue(RabbitQueue("email_queue"))
        #print("✅ Очередь email_queue объявлена", file=sys.stderr)
    except Exception as e:
        print(f"❌ Ошибка: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
    yield
    await broker.close()


# ==================== App ====================
app = FastAPI(
    title="Medpoint API",
    description="Платформа медицинских агентов",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:8000", "http://localhost"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)
    
# ==================== Dependencies ====================

async def get_current_agent(
    request: Request,
    db: AsyncSession = Depends(get_db),
 ) -> Agent:
    """Только для агентских роутов. Если role != 'agent' — 403."""
    token = request.cookies.get("access_token")
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:]

    if not token:
        raise HTTPException(status_code=401, detail="Не предоставлен токен")

    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Невалидный или истёкший токен")

    role = payload.get("role")
    if role != "agent":
        raise HTTPException(status_code=403, detail="Доступ только для агентов")

    user_email = payload.get("sub")
    if not user_email:
        raise HTTPException(status_code=401, detail="Неверный формат токена")

    agent = await crud.get_user_by_email(db, user_email)
    if not agent:
        raise HTTPException(status_code=401, detail="Пользователь не найден")

    if agent.status == "inactive" or agent.status == "rejected":
        raise HTTPException(status_code=403, detail="Аккаунт отключён или отклонён")

    if agent.status == "pending":
        raise HTTPException(status_code=403, detail="Аккаунт ожидает подтверждения")

    return agent


async def get_current_admin(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Admin:
    """Только для админских роутов. Если role not in ('admin', 'chef') — 403."""
    token = request.cookies.get("access_token")
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:]

    if not token:
        raise HTTPException(status_code=401, detail="Не предоставлен токен")

    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Невалидный или истёкший токен")

    role = payload.get("role")
    if role not in ("admin", "chef"):
        raise HTTPException(status_code=403, detail="Доступ только для администраторов")

    admin_id = payload.get("user_id")
    if not admin_id:
        raise HTTPException(status_code=401, detail="Неверный формат токена")

    admin = await crud.get_admin(db, admin_id)
    if not admin or not admin.active:
        raise HTTPException(status_code=403, detail="Администратор не найден или отключён")

    return admin


async def get_current_chef(
    admin: Admin = Depends(get_current_admin),
) -> Admin:
    """Только для шефа. Если role != 'chef' — 403."""
    if admin.role != "chef":
        raise HTTPException(status_code=403, detail="Доступ только для администратора портала")
    return admin


# Алиас для старых роутов
get_current_doctor = get_current_agent


# ==================== Health ====================

@app.get("/api/v1/health")
async def health():
    return {"status": "ok", "service": "Medpoint is ready!"}


# ==================== Auth ====================

@app.post("/api/v1/auth/send_code", response_model=MessageResponse)
async def send_code(
    email: str = Body(..., embed=True),
    db: AsyncSession = Depends(get_db),
):
    existing_agent = await crud.get_user_by_email_including_inactive(db, email)
    if existing_agent:
        raise HTTPException(status_code=400, detail="Пользователь с таким email уже существует")

    existing_admin = await crud.get_admin_by_email(db, email)
    if existing_admin:
        raise HTTPException(status_code=400, detail="Этот email занят администратором")

    import random
    code = f"{random.randint(100000, 999999)}"
    await crud.create_email_verification(db, email, code)

    email_data = {
        "email": email,
        "subject": "Medpoint — код подтверждения",
        "message": f"{code} — ваш код для регистрации",
    }
    await broker.publish(email_data, queue="email_queue")

    return MessageResponse(message="Код подтверждения отправлен на почту")


@app.post("/api/v1/auth/register", response_model=MessageResponse)
async def register_agent(
    data: DoctorRegister,
    db: AsyncSession = Depends(get_db),
):
    res = await crud.get_email_verification(db, data.email, str(data.code))
    if not res:
        raise HTTPException(status_code=400, detail="Код не подходит! Попробуйте ещё раз")

    existing_user = await crud.get_user_by_email_including_inactive(db, data.email)
    if existing_user:
        # if existing_user.status == "inactive":
        #     raise HTTPException(status_code=400, detail="Этот email был удалён. Восстановление невозможно, зарегистрируйтесь с другим email")
        raise HTTPException(status_code=400, detail="Пользователь с таким email уже существует")

    existing_admin = await crud.get_admin_by_email(db, data.email)
    if existing_admin:
        raise HTTPException(status_code=400, detail="Этот email занят администратором")

    hashed_password = get_password_hash(data.password)

    new_user = await crud.create_user(
        db=db,
        email=data.email,
        password_hash=hashed_password,
        full_name=data.full_name,
        phone=data.phone,
        about_myself=data.comment,
    )

    await crud.delete_email_verification(db, data.email)

    return MessageResponse(message="Вы успешно зарегистрировались!")


@app.post("/api/v1/auth/login", response_model=TokenResponse)
async def login(
    data: UserLogin,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    # 1. Пробуем как агента
    agent = await crud.get_user_by_email(db, data.email)
    if agent and verify_password(data.password, agent.password_hash):
        if agent.status == "inactive":
            raise HTTPException(status_code=403, detail="Аккаунт отключён")
        if agent.status == "rejected":
            raise HTTPException(status_code=403, detail="Регистрация отклонена")
        if agent.status == "pending":
            raise HTTPException(status_code=403, detail="Аккаунт ожидает подтверждения")

        token_data = {
            "sub": agent.email,
            "user_id": agent.id,
            "full_name": agent.full_name,
            "role": "agent",
        }
        expires_minutes = int(os.getenv("ACC_TOKEN_EXP_MIN"))
        if data.remember_me:
            expires_minutes = 60 * 24 * 30

        access_token = create_access_token(data=token_data, expires_delta=expires_minutes)
        response.set_cookie(
            key="access_token",
            value=access_token,
            httponly=True,
            secure=False,
            samesite="lax",
            max_age=60 * expires_minutes,
            path="/",
        )
        return TokenResponse(access_token=access_token)

    # 2. Пробуем как админа
    admin = await crud.get_admin_by_email(db, data.email)
    if admin and verify_password(data.password, admin.password_hash):
        if not admin.active:
            raise HTTPException(status_code=403, detail="Администратор отключён")

        token_data = {
            "sub": admin.email,
            "user_id": admin.id,
            "full_name": admin.full_name,
            "role": admin.role,  # 'admin' или 'chef'
        }
        expires_minutes = int(os.getenv("ACC_TOKEN_EXP_MIN"))
        if data.remember_me:
            expires_minutes = 60 * 24 * 30

        access_token = create_access_token(data=token_data, expires_delta=expires_minutes)
        response.set_cookie(
            key="access_token",
            value=access_token,
            httponly=True,
            secure=False,
            samesite="lax",
            max_age=60 * expires_minutes,
            path="/",
        )
        return TokenResponse(access_token=access_token)

    raise HTTPException(status_code=401, detail="Неверный email или пароль")


@app.post("/api/v1/auth/logout", response_model=MessageResponse)
async def logout(response: Response):
    response.delete_cookie("access_token", path="/")
    return MessageResponse(message="Выход выполнен")


@app.get("/api/v1/auth/me")
async def get_me(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    token = request.cookies.get("access_token")
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:]

    if not token:
        raise HTTPException(status_code=401, detail="Не предоставлен токен")

    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Невалидный или истёкший токен")

    role = payload.get("role")

    if role == "agent":
        agent = await get_current_agent(request, db)
        return {
            "role": "agent",
            "id": agent.id,
            "email": agent.email,
            "full_name": agent.full_name,
            "phone": agent.phone,
            "status": agent.status,
            "created_at": agent.created_at,
            "experience": agent.experience,
            "date_of_birth": agent.date_of_birth,
            "about_myself": agent.about_myself,
            "education": agent.education,
            "column_order": agent.column_order,
        }

    if role in ("admin", "chef"):
        admin = await get_current_admin(request, db)
        clinic_ids = await crud.get_admin_clinic_ids(db, admin.id) if admin.role == "admin" else []
        return {
            "role": admin.role,
            "id": admin.id,
            "email": admin.email,
            "full_name": admin.full_name,
            "phone": admin.phone,
            "active": admin.active,
            "permissions": admin.permissions,
            "clinic_ids": clinic_ids,
        }

    raise HTTPException(status_code=403, detail="Неизвестная роль")


# ==================== Agent profile ====================

@app.delete("/api/v1/auth/me", response_model=MessageResponse)
async def delete_me(
    data: UserLogin,
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    user = await crud.get_user_by_email(db, data.email)
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Неверный email или пароль")

    await crud.soft_delete_user(db, current_agent.id)
    return MessageResponse(message="Аккаунт удалён. Данные будут храниться 3 месяца")


@app.post("/api/v1/auth/recover_account", response_model=MessageResponse)
async def recover_account(
    data: UserLogin,
    db: AsyncSession = Depends(get_db),
):
    user = await crud.get_user_by_email(db, data.email)
    if not user:
        raise HTTPException(status_code=401, detail="Неверный email или пароль")

    if not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Неверный email или пароль")

    if user.status == "active":
        return MessageResponse(message="Аккаунт не удалён, восстановление не требуется")

    await crud.recover_account(db, user.id)
    return MessageResponse(message="Аккаунт восстановлен")


@app.put("/api/v1/auth/profile")
async def update_profile(
    data: DoctorUpdate,
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    update_data = data.dict(exclude_unset=True)

    if "specialization_ids" in update_data:
        spec_ids = update_data.pop("specialization_ids")
        await crud.set_agent_specializations(db, current_agent.id, spec_ids)

    agent = await crud.update_agent(db, current_agent.id, **update_data)
    if not agent:
        raise HTTPException(status_code=404, detail="Агент не найден")

    return {
        "id": agent.id,
        "email": agent.email,
        "full_name": agent.full_name,
        "phone": agent.phone,
        "created_at": agent.created_at,
        "experience": agent.experience,
        "date_of_birth": agent.date_of_birth,
        "about_myself": agent.about_myself,
        "education": agent.education,
    }


@app.get("/api/v1/auth/specializations", response_model=List[DoctorSpecializationResponse])
async def get_my_specializations(
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    return await crud.get_doctor_specializations(db, current_agent.id)


@app.get("/api/v1/specializations", response_model=List[DoctorSpecializationResponse])
async def get_all_specializations(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Specialization).order_by(Specialization.name))
    return result.scalars().all()


@app.get("/api/v1/auth/stats")
async def get_doctor_stats(
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    return await crud.get_doctor_stats(db, current_agent.id)


# ==================== Change Email / Password ====================

@app.post("/api/v1/auth/change_email_send_code", response_model=MessageResponse)
async def change_email_send_code(
    new_email: str = Body(..., embed=True),
    db: AsyncSession = Depends(get_db),
):
    existing = await crud.get_user_by_email(db, new_email)
    if existing:
        raise HTTPException(status_code=400, detail="Этот email уже используется")

    import random
    code = f"{random.randint(100000, 999999)}"
    await crud.create_email_verification(db, new_email, code)

    print(f"📧 Код для смены email на {new_email}: {code}")
    email_data = {
        "email": new_email,
        "subject": "Подтверждение смены email в Medpoint",
        "message": f"{code} — ваш код для подтверждения смены email",
    }
    await broker.publish(email_data, queue="email_queue")

    return MessageResponse(message="Код отправлен на новый email")


@app.post("/api/v1/auth/confirm_change_email", response_model=MessageResponse)
async def confirm_change_email(
    data: ChangeEmail,
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    verification = await crud.get_email_verification(db, data.new_email, data.code)
    if not verification:
        raise HTTPException(status_code=400, detail="Неверный или истёкший код")

    existing = await crud.get_user_by_email(db, data.new_email)
    if existing:
        raise HTTPException(status_code=400, detail="Email уже используется")

    await crud.update_agent(db, current_agent.id, email=data.new_email)
    await crud.delete_email_verification(db, data.new_email)

    return MessageResponse(message="Email успешно изменён")


@app.post("/api/v1/auth/change_password", response_model=MessageResponse)
async def change_password(
    data: ChangePassword,
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    if not verify_password(data.current_password, current_agent.password_hash):
        raise HTTPException(status_code=400, detail="Неверный текущий пароль")

    if data.new_password != data.confirm_password:
        raise HTTPException(status_code=400, detail="Пароли не совпадают")

    new_hash = get_password_hash(data.new_password)
    await crud.update_agent(db, current_agent.id, password_hash=new_hash)

    return MessageResponse(message="Пароль успешно изменён")


@app.put("/api/v1/auth/column_order")
async def update_column_order(
    data: ColumnOrderUpdate,
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    agent = await crud.update_agent(db, current_agent.id, column_order=data.column_order)
    if not agent:
        raise HTTPException(status_code=404, detail="Агент не найден")
    return {"column_order": agent.column_order}


# ==================== Clinics (public) ====================

@app.get("/api/v1/clinics", response_model=List[ClinicResponse])
async def get_clinics(db: AsyncSession = Depends(get_db)):
    return await crud.get_all_clinics(db, only_active=True)


# ==================== Patients ====================

@app.get("/api/v1/patients", response_model=List[PatientResponse])
async def get_patients(
    search: Optional[str] = None,
    status: Optional[str] = None,
    gender: Optional[str] = None,
    age_from: Optional[int] = None,
    age_to: Optional[int] = None,
    page: int = 1,
    limit: int = 20,
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    skip = (page - 1) * limit
    patients, total = await crud.get_patients_by_doctor(
        db=db,
        doctor_id=current_agent.id,
        search=search,
        status=status,
        gender=gender,
        age_from=age_from,
        age_to=age_to,
        skip=skip,
        limit=limit,
    )
    return patients


@app.get("/api/v1/patients/stats", response_model=PatientsStatsResponse)
async def get_patients_stats(
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    return await crud.get_patients_stats(db, current_agent.id)


@app.get("/api/v1/patients/{patient_id}", response_model=PatientResponse)
async def get_patient(
    patient_id: int,
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    patient = await crud.get_patient_by_id(db, patient_id, current_agent.id)
    if not patient:
        raise HTTPException(status_code=404, detail="Пациент не найден")
    return patient


@app.post("/api/v1/patients", response_model=PatientResponse)
async def create_patient(
    data: PatientCreate,
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    existing_patient = await crud.get_patient_by_email(db, data.email) if data.email else None
    if existing_patient:
        raise HTTPException(status_code=400, detail="Пациент с таким email уже существует")

    if not data.full_name:
        raise HTTPException(status_code=400, detail="ФИО обязательно")
    if not data.phone:
        raise HTTPException(status_code=400, detail="Телефон обязателен")
    if not data.date_of_birth:
        raise HTTPException(status_code=400, detail="Дата рождения обязательна")
    if not data.gender:
        raise HTTPException(status_code=400, detail="Пол обязателен")
    if data.gender not in ["male", "female"]:
        raise HTTPException(status_code=400, detail="Пол должен быть 'male' или 'female'")

    patient = await crud.create_patient(
        db=db,
        doctor_id=current_agent.id,
        full_name=data.full_name,
        phone=data.phone,
        date_of_birth=data.date_of_birth,
        email=data.email,
        gender=data.gender,
        info=data.info,
    )
    return patient


@app.put("/api/v1/patients/{patient_id}", response_model=PatientResponse)
async def update_patient(
    patient_id: int,
    data: PatientUpdate,
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    if data.email:
        existing_patient = await crud.get_patient_by_email(db, data.email, patient_id)
        if existing_patient:
            raise HTTPException(status_code=400, detail="Пациент с таким email уже существует")

    update_data = data.dict(exclude_unset=True)
    patient = await crud.update_patient(
        db=db,
        patient_id=patient_id,
        doctor_id=current_agent.id,
        **update_data,
    )
    if not patient:
        raise HTTPException(status_code=404, detail="Пациент не найден")
    return patient


@app.delete("/api/v1/patients/{patient_id}", response_model=MessageResponse)
async def delete_patient(
    patient_id: int,
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    deleted = await crud.delete_patient(db, patient_id, current_agent.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Пациент не найден")
    return MessageResponse(message="Пациент удалён")


@app.get("/api/v1/patients/{patient_id}/referrals-count")
async def get_patient_referrals_count(
    patient_id: int,
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    patient = await crud.get_patient_by_id(db, patient_id, current_agent.id)
    if not patient:
        raise HTTPException(status_code=404, detail="Пациент не найден")
    count = await crud.get_patient_referrals_count(db, patient_id)
    return {"patient_id": patient_id, "referrals_count": count}


# ==================== Referrals ====================

@app.post("/api/v1/referrals", response_model=ReferralResponse)
async def create_referral(
    data: ReferralCreate,
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    clinic = await crud.get_clinic(db, data.clinic_id)
    if not clinic:
        raise HTTPException(status_code=404, detail="Клиника не найдена")

    patient = await crud.get_patient_by_id(db, data.patient_id, current_agent.id)
    if not patient:
        raise HTTPException(status_code=404, detail="Пациент не найден")

    spec = await db.get(Specialization, data.specialization_id)
    if not spec:
        raise HTTPException(status_code=404, detail="Специализация не найдена")

    if data.expected_visit_start > data.expected_visit_end:
        raise HTTPException(status_code=400, detail="Дата начала позже окончания")
    delta = data.expected_visit_end - data.expected_visit_start
    if delta.days > 30:
        raise HTTPException(status_code=400, detail="Период не больше 30 дней")

    # Ставка
    clinic_spec = await crud.get_clinic_specialty(db, data.clinic_id, data.specialization_id)
    agent_rate = await crud.get_agent_rate(db, current_agent.id, data.specialization_id)

    commission_rate = None
    if agent_rate and agent_rate.mode == "custom" and agent_rate.custom_rate is not None:
        commission_rate = float(agent_rate.custom_rate)
    elif clinic_spec and clinic_spec.active and clinic_spec.default_rate is not None:
        commission_rate = float(clinic_spec.default_rate)

    amount = data.amount if hasattr(data, "amount") and data.amount else 0
    commission_amount = int(round(amount * (commission_rate or 0) / 100))

    referral = await crud.create_referral(
        db=db,
        doctor_id=current_agent.id,
        clinic_id=data.clinic_id,
        patient_id=data.patient_id,
        specialization_id=data.specialization_id,
        expected_visit_start=data.expected_visit_start,
        expected_visit_end=data.expected_visit_end,
        med_indications=data.med_indications,
        special_wishes=data.special_wishes,
        amount=amount,
        commission_rate=commission_rate,
        commission_amount=commission_amount,
        specialty_name_at_confirmation=spec.name,
    )
    return referral


@app.get("/api/v1/referrals", response_model=List[ReferralDetailResponse])
async def get_referrals(
    search: Optional[str] = None,
    status: Optional[str] = None,
    clinic_id: Optional[int] = None,
    page: int = 1,
    limit: int = 10,
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    if page < 1:
        page = 1
    if limit < 1 or limit > 100:
        limit = 10
    skip = (page - 1) * limit

    referrals, total = await crud.get_referrals_by_doctor(
        db=db,
        doctor_id=current_agent.id,
        search=search,
        status=status,
        clinic_id=clinic_id,
        skip=skip,
        limit=limit,
    )
    result = []
    for r in referrals:
        result.append(
            ReferralDetailResponse(
                id=r.id,
                agent_id=r.agent_id,
                clinic_id=r.clinic_id,
                patient_id=r.patient_id,
                specialization_id=r.specialization_id,
                expected_visit_start=r.expected_visit_start,
                expected_visit_end=r.expected_visit_end,
                med_indications=r.med_indications,
                special_wishes=r.special_wishes,
                status=r.status,
                status_changed_at=r.status_changed_at,
                commission_amount=r.commission_amount,
                is_paid=(r.payout_status == "paid"),
                created_at=r.created_at,
                patient_full_name=r.patient.full_name,
                patient_phone=r.patient.phone,
                clinic_name=r.clinic.name,
                clinic_address=r.clinic.address,
                specialization_name=r.specialization.name if r.specialization else None,
            )
        )
    return result


@app.put("/api/v1/referrals/{referral_id}", response_model=ReferralDetailResponse)
async def update_referral(
    referral_id: int,
    data: ReferralUpdate,
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    if data.expected_visit_start and data.expected_visit_end:
        if data.expected_visit_start > data.expected_visit_end:
            raise HTTPException(status_code=400, detail="Дата начала позже окончания")
        delta = data.expected_visit_end - data.expected_visit_start
        if delta.days > 30:
            raise HTTPException(status_code=400, detail="Период не больше 30 дней")

    update_data = data.dict(exclude_unset=True)
    referral = await crud.update_referral(
        db=db,
        referral_id=referral_id,
        agent_id=current_agent.id,
        **update_data,
    )
    if not referral:
        raise HTTPException(status_code=404, detail="Направление не найдено")

    result = await db.execute(
        select(Referral)
        .options(
            selectinload(Referral.patient),
            selectinload(Referral.clinic),
            selectinload(Referral.specialization),
        )
        .where(Referral.id == referral_id)
    )
    referral = result.scalar_one()

    return ReferralDetailResponse(
        id=referral.id,
        agent_id=referral.agent_id,
        clinic_id=referral.clinic_id,
        patient_id=referral.patient_id,
        specialization_id=referral.specialization_id,
        expected_visit_start=referral.expected_visit_start,
        expected_visit_end=referral.expected_visit_end,
        med_indications=referral.med_indications,
        special_wishes=referral.special_wishes,
        status=referral.status,
        status_changed_at=referral.status_changed_at,
        commission_amount=referral.commission_amount,
        is_paid=(referral.payout_status == "paid"),
        created_at=referral.created_at,
        patient_full_name=referral.patient.full_name,
        patient_phone=referral.patient.phone,
        clinic_name=referral.clinic.name,
        clinic_address=referral.clinic.address,
        specialization_name=referral.specialization.name if referral.specialization else None,
    )


@app.delete("/api/v1/referrals/{referral_id}", response_model=MessageResponse)
async def delete_referral(
    referral_id: int,
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    deleted = await crud.delete_referral(db, referral_id, current_agent.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Направление не найдено")
    return MessageResponse(message="Направление удалено")


# ==================== Dashboard ====================

@app.get("/api/v1/dashboard/stats", response_model=DashboardStatsResponse)
async def get_dashboard_stats(
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    return await crud.get_dashboard_stats(db, current_agent.id)


@app.get("/api/v1/dashboard/activity", response_model=List[RecentActivityResponse])
async def get_recent_activity(
    limit: int = 5,
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    return await crud.get_recent_activity(db, current_agent.id, limit)


@app.get("/api/v1/dashboard/appointments", response_model=List[UpcomingAppointmentResponse])
async def get_upcoming_appointments(
    limit: int = 4,
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    appointments = await crud.get_upcoming_appointments(db, current_agent.id, limit)
    return [
        {
            "id": a.id,
            "patient_name": a.patient.full_name,
            "clinic_name": a.clinic.name,
            "clinic_address": a.clinic.address,
            "expected_visit_start": a.expected_visit_start,
            "status": a.status,
        }
        for a in appointments
    ]


@app.get("/api/v1/dashboard/top-clinics", response_model=List[TopClinicResponse])
async def get_top_clinics(limit: int = 4, db: AsyncSession = Depends(get_db)):
    return await crud.get_top_clinics(db, limit)


# ==================== Reports / Goals ====================

from datetime import date as date_type


@app.get("/api/v1/reports/stats", response_model=ReportsStatsResponse)
async def get_reports_stats(
    date_from: date_type,
    date_to: date_type,
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    if date_from > date_to:
        raise HTTPException(status_code=400, detail="Дата 'с' позже 'по'")
    return await crud.get_reports_stats(db, current_agent.id, date_from, date_to)


@app.get("/api/v1/goals/current", response_model=Optional[GoalResponse])
async def get_current_goal(
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    return await crud.get_current_goal(db, current_agent.id)


@app.put("/api/v1/goals", response_model=GoalResponse)
async def update_goal(
    data: GoalCreate,
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    return await crud.upsert_goal(
        db=db,
        doctor_id=current_agent.id,
        income_money=data.income_money,
        referrals=data.referrals,
        month=data.month,
        year=data.year,
    )


@app.get("/api/v1/goals/facts")
async def get_goal_facts(
    month: int,
    year: int,
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    return await crud.get_goal_facts(db, current_agent.id, month, year)


# ==================== Admin: Agents ====================

@app.get("/api/v1/agents", response_model=List[AgentResponse])
async def list_agents_endpoint(
    status: Optional[str] = None,
    search: Optional[str] = None,
    clinic_id: Optional[int] = None,
    page: int = 1,
    limit: int = 100,
    admin: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Список агентов. Шеф — все, админ — только его клиник."""
    if admin.role == "chef":
        clinic_ids = None
    else:
        clinic_ids = await crud.get_admin_clinic_ids(db, admin.id)
        if not clinic_ids:
            return []
        if clinic_id is not None:
            if clinic_id not in clinic_ids:
                raise HTTPException(status_code=403, detail="Нет доступа")
            clinic_ids = [clinic_id]

    skip = (page - 1) * limit
    agents, total = await crud.list_agents(
        db=db,
        clinic_ids=clinic_ids,
        status=status,
        search=search,
        skip=skip,
        limit=limit,
    )

    result = []
    for a in agents:
        result.append(await _build_agent_response(db, a))
    return result


@app.get("/api/v1/agents/{agent_id}", response_model=AgentResponse)
async def get_agent_endpoint(
    agent_id: int,
    admin: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    agent = await crud.get_agent(db, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Агент не найден")

    if admin.role != "chef":
        admin_clinic_ids = await crud.get_admin_clinic_ids(db, admin.id)
        agent_clinic_ids = await crud.get_agent_clinic_ids(db, agent_id)
        if not set(admin_clinic_ids) & set(agent_clinic_ids):
            raise HTTPException(status_code=403, detail="Нет доступа к агенту")

    return await _build_agent_response(db, agent)


@app.put("/api/v1/agents/{agent_id}", response_model=AgentResponse)
async def update_agent_endpoint(
    agent_id: int,
    data: AgentUpdate,
    admin: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    agent = await crud.get_agent(db, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Агент не найден")

    if admin.role != "chef":
        admin_clinic_ids = await crud.get_admin_clinic_ids(db, admin.id)
        agent_clinic_ids = await crud.get_agent_clinic_ids(db, agent_id)
        if not set(admin_clinic_ids) & set(agent_clinic_ids):
            raise HTTPException(status_code=403, detail="Нет доступа к агенту")

    update_data = data.dict(exclude_unset=True)

    clinic_ids = update_data.pop("clinic_ids", None)
    specialization_ids = update_data.pop("specialization_ids", None)

    if update_data:
        await crud.update_agent(db, agent_id, **update_data)

    if clinic_ids is not None:
        if admin.role != "chef":
            admin_clinic_ids = await crud.get_admin_clinic_ids(db, admin.id)
            if not set(clinic_ids).issubset(set(admin_clinic_ids)):
                raise HTTPException(status_code=403, detail="Нельзя привязать к чужой клинике")
        await crud.set_agent_clinics(db, agent_id, clinic_ids)

    if specialization_ids is not None:
        await crud.set_agent_specializations(db, agent_id, specialization_ids)

    agent = await crud.get_agent(db, agent_id)
    return await _build_agent_response(db, agent)


@app.post("/api/v1/agents/{agent_id}/approve", response_model=AgentResponse)
async def approve_agent_endpoint(
    agent_id: int,
    data: AgentApprove,
    admin: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    agent = await crud.get_agent(db, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Агент не найден")
    if agent.status != "pending":
        raise HTTPException(status_code=400, detail="Агент не в статусе 'pending'")

    if admin.role != "chef":
        admin_clinic_ids = await crud.get_admin_clinic_ids(db, admin.id)
        if not set(data.clinic_ids).issubset(set(admin_clinic_ids)):
            raise HTTPException(status_code=403, detail="Нельзя привязать к чужой клинике")

    await crud.update_agent(
        db, agent_id,
        status="active",
        admin_id=data.admin_id if admin.role == "chef" else admin.id,
    )
    await crud.set_agent_clinics(db, agent_id, data.clinic_ids)
    if data.specialization_ids:
        await crud.set_agent_specializations(db, agent_id, data.specialization_ids)

    await crud.add_history(
        db, "admin", admin.id,
        "Агент одобрен",
        f"Агент #{agent_id} ({agent.email}) одобрен",
        admin.full_name,
    )

    email_data = {
        "email": agent.email,
        "subject": "Medpoint — регистрация одобрена",
        "message": f"Ваша заявка одобрена! Войдите в систему: http://localhost/",
    }
    await broker.publish(email_data, queue="email_queue")

    agent = await crud.get_agent(db, agent_id)
    return await _build_agent_response(db, agent)


@app.post("/api/v1/agents/{agent_id}/reject", response_model=AgentResponse)
async def reject_agent_endpoint(
    agent_id: int,
    data: AgentReject,
    admin: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    agent = await crud.get_agent(db, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Агент не найден")
    if agent.status != "pending":
        raise HTTPException(status_code=400, detail="Агент не в статусе 'pending'")

    if admin.role != "chef":
        admin_clinic_ids = await crud.get_admin_clinic_ids(db, admin.id)
        agent_clinic_ids = await crud.get_agent_clinic_ids(db, agent_id)
        if not set(admin_clinic_ids) & set(agent_clinic_ids):
            raise HTTPException(status_code=403, detail="Нет доступа")

    await crud.update_agent(
        db, agent_id,
        status="rejected",
        about_myself=(agent.about_myself or "") + f"\n\n[Отклонено: {data.decision_reason}]",
    )

    await crud.add_history(
        db, "admin", admin.id,
        "Агент отклонён",
        f"Агент #{agent_id} ({agent.email}): {data.decision_reason}",
        admin.full_name,
    )

    email_data = {
        "email": agent.email,
        "subject": "Medpoint — регистрация отклонена",
        "message": f"Ваша заявка отклонена.\nПричина: {data.decision_reason}",
    }
    await broker.publish(email_data, queue="email_queue")

    agent = await crud.get_agent(db, agent_id)
    return await _build_agent_response(db, agent)


@app.delete("/api/v1/agents/{agent_id}", response_model=MessageResponse)
async def delete_agent_endpoint(
    agent_id: int,
    admin: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    agent = await crud.get_agent(db, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Агент не найден")

    if admin.role != "chef":
        admin_clinic_ids = await crud.get_admin_clinic_ids(db, admin.id)
        agent_clinic_ids = await crud.get_agent_clinic_ids(db, agent_id)
        if not set(admin_clinic_ids) & set(agent_clinic_ids):
            raise HTTPException(status_code=403, detail="Нет доступа")

    await crud.soft_delete_agent(db, agent_id)
    await crud.add_history(
        db, "admin", admin.id, "Агент удалён",
        f"Агент #{agent_id} ({agent.email})", admin.full_name,
    )
    return MessageResponse(message="Агент удалён")


# ==================== Admin: Agents helper ====================

async def _build_agent_response(db: AsyncSession, agent: Agent) -> AgentResponse:
    clinic_ids = await crud.get_agent_clinic_ids(db, agent.id)
    specializations = await crud.get_agent_specializations(db, agent.id)
    return AgentResponse(
        id=agent.id,
        email=agent.email,
        full_name=agent.full_name,
        phone=agent.phone,
        date_of_birth=agent.date_of_birth,
        experience=agent.experience,
        education=agent.education,
        about_myself=agent.about_myself,
        status=agent.status,
        admin_id=agent.admin_id,
        column_order=agent.column_order,
        created_at=agent.created_at,
        updated_at=agent.updated_at,
        clinic_ids=clinic_ids,
        specialization_ids=[s.specialization_id for s in specializations],
    )


# ==================== Admin: Admins CRUD ====================

@app.get("/api/v1/admins", response_model=List[AdminResponse])
async def list_admins_endpoint(
    chef: Admin = Depends(get_current_chef),
    db: AsyncSession = Depends(get_db),
):
    admins, total = await crud.list_admins(db)
    result = []
    for a in admins:
        clinic_ids = await crud.get_admin_clinic_ids(db, a.id)
        result.append(AdminResponse(
            id=a.id, email=a.email, full_name=a.full_name, phone=a.phone,
            role=a.role, active=a.active, permissions=a.permissions or {},
            clinic_ids=clinic_ids,
        ))
    return result


@app.post("/api/v1/admins", response_model=AdminResponse)
async def create_admin_endpoint(
    data: AdminCreate,
    chef: Admin = Depends(get_current_chef),
    db: AsyncSession = Depends(get_db),
):
    existing = await crud.get_admin_by_email(db, data.email)
    if existing:
        raise HTTPException(status_code=400, detail="Email занят")

    hashed = get_password_hash(data.password)
    admin = await crud.create_admin(
        db=db,
        email=data.email,
        password_hash=hashed,
        full_name=data.full_name,
        phone=data.phone,
        role="admin",
        clinic_ids=data.clinic_ids,
    )
    return AdminResponse(
        id=admin.id, email=admin.email, full_name=admin.full_name, phone=admin.phone,
        role=admin.role, active=admin.active, permissions=admin.permissions or {},
        clinic_ids=data.clinic_ids,
    )


@app.put("/api/v1/admins/{admin_id}", response_model=AdminResponse)
async def update_admin_endpoint(
    admin_id: int,
    data: AdminUpdate,
    chef: Admin = Depends(get_current_chef),
    db: AsyncSession = Depends(get_db),
):
    admin = await crud.get_admin(db, admin_id)
    if not admin:
        raise HTTPException(status_code=404, detail="Админ не найден")
    if admin.role == "chef":
        raise HTTPException(status_code=400, detail="Шефа нельзя редактировать")

    update_data = data.dict(exclude_unset=True)
    clinic_ids = update_data.pop("clinic_ids", None)

    if update_data:
        await crud.update_admin(db, admin_id, **update_data)
    if clinic_ids is not None:
        await crud.update_admin(db, admin_id, clinic_ids=clinic_ids)

    admin = await crud.get_admin(db, admin_id)
    clinic_ids = await crud.get_admin_clinic_ids(db, admin_id)
    return AdminResponse(
        id=admin.id, email=admin.email, full_name=admin.full_name, phone=admin.phone,
        role=admin.role, active=admin.active, permissions=admin.permissions or {},
        clinic_ids=clinic_ids,
    )


@app.delete("/api/v1/admins/{admin_id}", response_model=MessageResponse)
async def delete_admin_endpoint(
    admin_id: int,
    chef: Admin = Depends(get_current_chef),
    db: AsyncSession = Depends(get_db),
):
    admin = await crud.get_admin(db, admin_id)
    if not admin:
        raise HTTPException(status_code=404, detail="Админ не найден")
    if admin.role == "chef":
        raise HTTPException(status_code=400, detail="Шефа нельзя удалить")

    await crud.delete_admin(db, admin_id)
    return MessageResponse(message="Админ удалён")


# ==================== Admin: Clinics ====================

@app.post("/api/v1/clinics", response_model=ClinicResponse)
async def create_clinic_endpoint(
    data: ClinicCreate,
    chef: Admin = Depends(get_current_chef),
    db: AsyncSession = Depends(get_db),
):
    clinic = await crud.create_clinic(
        db=db,
        name=data.name,
        city=data.city,
        address=data.address,
        phone=data.phone,
        active=data.active,
        default_rate=data.default_rate if hasattr(data, "default_rate") and data.default_rate is not None else 10.0,
    )
    return clinic


@app.put("/api/v1/clinics/{clinic_id}", response_model=ClinicResponse)
async def update_clinic_endpoint(
    clinic_id: int,
    data: ClinicUpdate,
    admin: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    clinic = await crud.get_clinic(db, clinic_id)
    if not clinic:
        raise HTTPException(status_code=404, detail="Клиника не найдена")

    if admin.role != "chef":
        admin_clinic_ids = await crud.get_admin_clinic_ids(db, admin.id)
        if clinic_id not in admin_clinic_ids:
            raise HTTPException(status_code=403, detail="Нет доступа")

    update_data = data.dict(exclude_unset=True)
    clinic = await crud.update_clinic(db, clinic_id, **update_data)
    return clinic


# ==================== Admin: ClinicSpecialties ====================

@app.get("/api/v1/clinics/{clinic_id}/specialties", response_model=List[ClinicSpecialtyResponse])
async def get_clinic_specialties_endpoint(
    clinic_id: int,
    admin: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    if admin.role != "chef":
        admin_clinic_ids = await crud.get_admin_clinic_ids(db, admin.id)
        if clinic_id not in admin_clinic_ids:
            raise HTTPException(status_code=403, detail="Нет доступа")

    items = await crud.get_clinic_specialties(db, clinic_id, include_inactive=True)
    return [
        ClinicSpecialtyResponse(
            id=cs.id,
            clinic_id=cs.clinic_id,
            specialization_id=cs.specialization_id,
            specialization_name=cs.specialization.name if cs.specialization else "",
            default_rate=float(cs.default_rate) if cs.default_rate is not None else None,
            active=cs.active,
        )
        for cs in items
    ]


@app.put("/api/v1/clinics/{clinic_id}/specialties/{spec_id}", response_model=ClinicSpecialtyResponse)
async def upsert_clinic_specialty_endpoint(
    clinic_id: int,
    spec_id: int,
    data: ClinicSpecialtyUpdate,
    admin: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    if admin.role != "chef":
        admin_clinic_ids = await crud.get_admin_clinic_ids(db, admin.id)
        if clinic_id not in admin_clinic_ids:
            raise HTTPException(status_code=403, detail="Нет доступа")

    cs = await crud.upsert_clinic_specialty(
        db=db, clinic_id=clinic_id, specialization_id=spec_id,
        default_rate=data.default_rate, active=data.active,
    )
    return ClinicSpecialtyResponse(
        id=cs.id,
        clinic_id=cs.clinic_id,
        specialization_id=cs.specialization_id,
        specialization_name=cs.specialization.name if cs.specialization else "",
        default_rate=float(cs.default_rate) if cs.default_rate is not None else None,
        active=cs.active,
    )


# ==================== Admin: AgentRates ====================

@app.get("/api/v1/agents/{agent_id}/rates", response_model=List[AgentRateResponse])
async def get_agent_rates_endpoint(
    agent_id: int,
    admin: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    if admin.role != "chef":
        admin_clinic_ids = await crud.get_admin_clinic_ids(db, admin.id)
        agent_clinic_ids = await crud.get_agent_clinic_ids(db, agent_id)
        if not set(admin_clinic_ids) & set(agent_clinic_ids):
            raise HTTPException(status_code=403, detail="Нет доступа")

    rates = await crud.get_agent_rates(db, agent_id)
    return [
        AgentRateResponse(
            id=r.id,
            agent_id=r.agent_id,
            specialization_id=r.specialization_id,
            specialization_name=r.specialization.name if r.specialization else "",
            mode=r.mode,
            custom_rate=float(r.custom_rate) if r.custom_rate is not None else None,
        )
        for r in rates
    ]


@app.put("/api/v1/agents/{agent_id}/rates/{spec_id}", response_model=AgentRateResponse)
async def set_agent_rate_endpoint(
    agent_id: int,
    spec_id: int,
    data: AgentRateUpdate,
    admin: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    if admin.role != "chef":
        admin_clinic_ids = await crud.get_admin_clinic_ids(db, admin.id)
        agent_clinic_ids = await crud.get_agent_clinic_ids(db, agent_id)
        if not set(admin_clinic_ids) & set(agent_clinic_ids):
            raise HTTPException(status_code=403, detail="Нет доступа")

    if data.mode == "custom" and data.custom_rate is None:
        raise HTTPException(status_code=400, detail="Для режима 'custom' нужен custom_rate")

    rate = await crud.set_agent_rate(
        db=db, agent_id=agent_id, specialization_id=spec_id,
        mode=data.mode, custom_rate=data.custom_rate,
    )
    return AgentRateResponse(
        id=rate.id,
        agent_id=rate.agent_id,
        specialization_id=rate.specialization_id,
        specialization_name=rate.specialization.name if rate.specialization else "",
        mode=rate.mode,
        custom_rate=float(rate.custom_rate) if rate.custom_rate is not None else None,
    )