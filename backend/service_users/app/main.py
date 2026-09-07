import asyncio
from fastapi import Body, FastAPI, Depends, HTTPException, Response, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
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
    print("🔄 Начинаем создание таблиц...", file=sys.stderr)
    try:
        # await create_tables()
        # print("✅ Таблицы созданы/проверены", file=sys.stderr)

        # Подключаем брокера С ПОВТОРНЫМИ ПОПЫТКАМИ
        print("🔄 Подключение к RabbitMQ...", file=sys.stderr)
        
        max_retries = 30
        for attempt in range(max_retries):
            try:
                await broker.connect()
                print("✅ Брокер подключен", file=sys.stderr)
                break
            except Exception as e:
                print(f"❌ Попытка {attempt + 1}/{max_retries} не удалась: {e}", file=sys.stderr)
                if attempt < max_retries - 1:
                    print(f"⏳ Повтор через 2 секунды...", file=sys.stderr)
                    await asyncio.sleep(2)
                else:
                    print("❌ Не удалось подключиться к RabbitMQ после всех попыток", file=sys.stderr)
                    raise
        
        # Объявляем очередь
        from faststream.rabbit import RabbitQueue
        await broker.declare_queue(RabbitQueue("email_queue"))
        print("✅ Очередь email_queue объявлена", file=sys.stderr)

    except Exception as e:
        print(f"❌ Ошибка: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
    yield

    await broker.close()


# ==================== App ====================

app = FastAPI(
    title="StudentPass API",
    description="Платформа студенческих скидок",
    version="1.0.0",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==================== Dependencies ====================

async def get_current_doctor(
    request: Request,
    db: AsyncSession = Depends(get_db)
) -> Optional[Doctor]:
    """Извлекает текущего пользователя из токена в cookie или Authorization header"""
    
    # Пробуем взять токен из cookie
    token = request.cookies.get("access_token")
    
    # Если нет в cookie, пробуем из Authorization header
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:]
    
    if not token:
        raise HTTPException(status_code=401, detail="Не предоставлен токен")
    
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Невалидный или истёкший токен")
    
    user_email = payload.get("sub")
    if not user_email:
        raise HTTPException(status_code=401, detail="Неверный формат токена")
    
    doctor = await crud.get_user_by_email(db, user_email)
    if not doctor:
        raise HTTPException(status_code=401, detail="Пользователь не найден или удалён")
    
    return doctor


# ==================== Health ====================

@app.get("/api/v1/health")
async def health():
    return {"status": "ok", "service": "Med Referral is ready!"}


# ==================== Auth Routes ====================
@app.post("/api/v1/auth/send_code", response_model=MessageResponse)
async def send_code(
    email: str = Body(..., embed=True),
    db: AsyncSession = Depends(get_db)
):
    # Проверяем, существует ли пользователь (включая неактивных)
    existing_doctor = await crud.get_user_by_email_including_inactive(db, email)
    if existing_doctor:
        raise HTTPException(status_code=400, detail="Пользователь с таким email уже существует")
        
    # Генерируем код подтверждения (6 цифр)
    import random
    code = f"{random.randint(100000, 999999)}"
    
    # Сохраняем код в email_verifications
    await crud.create_email_verification(db, email, code)
    
    email_data = {
        "email": email,
        "subject": "Добро пожаловать в MedRefferal!",
        "message": f"{code} - Ваш код для регистрации на портале",
    }
    
    await broker.publish(email_data, queue="email_queue")
    
    return MessageResponse(message="Код подтверждения отправлен на почту")



@app.post("/api/v1/auth/register", response_model=MessageResponse)
async def register_doctor(
    data: DoctorRegister,
    db: AsyncSession = Depends(get_db)
):
    res = await crud.get_email_verification(db, data.email, str(data.code))
    
    if res:

        # Проверяем, существует ли пользователь (включая неактивных)
        existing_user = await crud.get_user_by_email_including_inactive(db, data.email)
        if existing_user:
            if not existing_user.is_active:
                raise HTTPException(status_code=400, detail="Этот email был удалён. Восстановление невозможно, зарегистрируйтесь с другим email")
            raise HTTPException(status_code=400, detail="Пользователь с таким email уже существует")
        
        # Хешируем пароль
        hashed_password = get_password_hash(data.password)
        
        # Создаём пользователя
        # if data.email == 'alex.arkhangelskiy@yandex.ru':
        #     new_user = await crud.create_user(
        #         db=db,
        #         email=data.email,
        #         password_hash=hashed_password,
        #         full_name=data.full_name,
        #         role=UserRole.ADMIN
        #     )
        
        
        new_user = await crud.create_user(
            db=db,
            email=data.email,
            password_hash=hashed_password,
            full_name=data.full_name,
            phone=data.phone
        )

        await crud.delete_email_verification(db, data.email)
        
        return MessageResponse(message="Вы успешно зарегистрировались!")
    
    else:
        raise HTTPException(status_code=400, detail="Код не подходит! Попробуйте еще раз")


@app.post("/api/v1/auth/login", response_model=TokenResponse)
async def login(
    data: UserLogin,
    response: Response,
    db: AsyncSession = Depends(get_db)
):
    user = await crud.get_user_by_email(db, data.email)
    if not user:
        raise HTTPException(status_code=401, detail="Такого пользователя не существует")

    
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Неверный email или пароль")
    
    token_data = {
        "sub": user.email,
        "user_id": user.id,
        "full_name": user.full_name
    }

    expires_minutes = int(os.getenv('ACC_TOKEN_EXP_MIN'))
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
        path="/"
    )
    
    return TokenResponse(access_token=access_token)


@app.post("/api/v1/auth/logout", response_model=MessageResponse)
async def logout(response: Response):
    response.delete_cookie("access_token", path="/")
    return MessageResponse(message="Выход выполнен")


@app.get("/api/v1/auth/me", response_model=UserResponse)
async def get_me(current_user: Doctor = Depends(get_current_doctor)):
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        phone=current_user.phone,
        created_at=current_user.created_at,
        experience=current_user.experience,
        date_of_birth=current_user.date_of_birth,
        about_myself=current_user.about_myself,
        education=current_user.education
    )


@app.delete("/api/v1/auth/me", response_model=MessageResponse)
async def delete_me(
    data: UserLogin,
    current_user: Doctor = Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db)
):
    
    user = await crud.get_user_by_email(db, data.email)
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Неверный email или пароль")
    

    await crud.soft_delete_user(db, current_user.id)
    return MessageResponse(message="Аккаунт удалён. Данные будут храниться 3 месяца")


@app.post("/api/v1/auth/recover_account", response_model=MessageResponse)
async def recover_account(
    data: UserLogin,
    db: AsyncSession = Depends(get_db)
):
    user = await crud.get_user_by_email(db, data.email)
    if user.is_active == True: 
        return MessageResponse(message='На данный момент аккаунт не является удаленным!')
    
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Неверный email или пароль")
    
    
    await crud.recover_account(db, user.id)
    return MessageResponse(message='Аккаунт восстановлен!')



@app.put("/api/v1/auth/profile", response_model=UserResponse)
async def update_profile(
    data: DoctorUpdate,
    current_user: Doctor = Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db)
):
    """Обновить профиль доктора"""
    
    update_data = data.dict(exclude_unset=True)
    print(update_data)
    # Если переданы специализации — обновляем их
    if "specialization_ids" in update_data:
        spec_ids = update_data.pop("specialization_ids")
        
        # Удаляем старые специализации
        await db.execute(
            delete(DoctorSpecialization).where(
                DoctorSpecialization.doctor_id == current_user.id
            )
        )
        
        # Добавляем новые
        for spec_id in spec_ids:
            db.add(DoctorSpecialization(
                doctor_id=current_user.id,
                specialization_id=spec_id
            ))
            # Обновляем остальные поля
    doctor = await crud.update_doctor(db, current_user.id, **update_data)
    
    if not doctor:
        raise HTTPException(status_code=404, detail="Доктор не найден")
    
    return UserResponse(
            id=current_user.id,
            email=current_user.email,
            full_name=current_user.full_name,
            phone=current_user.phone,
            created_at=current_user.created_at,
            experience=current_user.experience,
            date_of_birth=current_user.date_of_birth,
            about_myself=current_user.about_myself,
            education=current_user.education
        )


@app.get("/api/v1/auth/specializations", response_model=List[DoctorSpecializationResponse])
async def get_my_specializations(
    current_user: Doctor = Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db)
):
    """Получить специализации текущего доктора"""
    specializations = await crud.get_doctor_specializations(db, current_user.id)
    return specializations


@app.get("/api/v1/specializations", response_model=List[DoctorSpecializationResponse])
async def get_all_specializations(
    db: AsyncSession = Depends(get_db)
):
    """Получить все доступные специализации (для выбора в профиле)"""
    result = await db.execute(
        select(Specialization).order_by(Specialization.name)
    )
    return result.scalars().all()






@app.get("/api/v1/auth/stats")
async def get_doctor_stats(
    current_user: Doctor = Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db)
):
    """Получить статистику доктора (направления и пациенты)"""
    return await crud.get_doctor_stats(db, current_user.id)

# ==================== Clinics Routes ====================
@app.get("/api/v1/clinics", response_model=List[ClinicResponse])
async def get_clinics(
    db: AsyncSession = Depends(get_db)
):
    """Получить список всех клиник"""
    clinics = await crud.get_all_clinics(db)
    return clinics

# ==================== Patients Routes ====================
@app.get("/api/v1/patients", response_model=List[PatientResponse])
async def get_patients(
    search: Optional[str] = None,
    status: Optional[str] = None,
    gender: Optional[str] = None,
    age_from: Optional[int] = None,
    age_to: Optional[int] = None,
    page: int = 1,
    limit: int = 20,
    current_user: Doctor = Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db)
):
    """Получить список пациентов текущего доктора"""
    
    skip = (page - 1) * limit
    
    patients, total = await crud.get_patients_by_doctor(
        db=db,
        doctor_id=current_user.id,
        search=search,
        status=status,
        gender=gender,
        age_from=age_from,
        age_to=age_to,
        skip=skip,
        limit=limit
    )
    return patients


@app.get("/api/v1/patients/stats", response_model=PatientsStatsResponse)
async def get_patients_stats(
    current_user: Doctor = Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db)
):
    """Получить статистику пациентов"""
    return await crud.get_patients_stats(db, current_user.id)


@app.get("/api/v1/patients/{patient_id}", response_model=PatientResponse)
async def get_patient(
    patient_id: int,
    current_user: Doctor = Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db)
):
    """Получить пациента по id"""
    
    patient = await crud.get_patient_by_id(db, patient_id, current_user.id)
    if not patient:
        raise HTTPException(status_code=404, detail="Пациент не найден")
    
    return patient

@app.post("/api/v1/patients", response_model=PatientResponse)
async def create_patient(
    data: PatientCreate,
    current_user: Doctor = Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db)
):
    """Создать нового пациента (все поля обязательны)"""
    existing_patient = await crud.get_patient_by_email(db, data.email)
    if existing_patient:
        raise HTTPException(status_code=400, detail="Пользователь с таким email уже существует")


    # Проверяем наличие всех обязательных полей
    if not data.full_name:
        raise HTTPException(status_code=400, detail="ФИО обязательно для заполнения")
    
    if not data.phone:
        raise HTTPException(status_code=400, detail="Телефон обязателен для заполнения")
    
    if not data.date_of_birth:
        raise HTTPException(status_code=400, detail="Дата рождения обязательна для заполнения")
    
    if not data.gender:
        raise HTTPException(status_code=400, detail="Пол обязателен для заполнения")
    
    # Проверка формата пола
    if data.gender not in ['male', 'female']:
        raise HTTPException(status_code=400, detail="Пол должен быть 'male' или 'female'")
    
    patient = await crud.create_patient(
        db=db,
        doctor_id=current_user.id,
        full_name=data.full_name,
        phone=data.phone,
        date_of_birth=data.date_of_birth,
        email=data.email,
        gender=data.gender,
        info=data.info
    )
    
    return patient

@app.put("/api/v1/patients/{patient_id}", response_model=PatientResponse)
async def update_patient(
    patient_id: int,
    data: PatientUpdate,
    current_user: Doctor = Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db)
):
    """Обновить данные пациента"""

    if data.email:
        existing_patient = await crud.get_patient_by_email(db, data.email, patient_id)
        if existing_patient:
            raise HTTPException(status_code=400, detail="Пользователь с таким email уже существует")

        
    update_data = data.dict(exclude_unset=True)

    patient = await crud.update_patient(
        db=db,
        patient_id=patient_id,
        doctor_id=current_user.id,
        **update_data
    )
    
    if not patient:
        raise HTTPException(status_code=404, detail="Пациент не найден")
    
    return patient






@app.delete("/api/v1/patients/{patient_id}", response_model=MessageResponse)
async def delete_patient(
    patient_id: int,
    current_user: Doctor = Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db)
):
    """Удалить пациента"""
    deleted = await crud.delete_patient(db, patient_id, current_user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Пациент не найден")
    
    return MessageResponse(message="Пациент удален")

@app.get("/api/v1/patients/{patient_id}/referrals-count", response_model=dict)
async def get_patient_referrals_count(
    patient_id: int,
    current_user: Doctor = Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db)
):
    """Получить количество направлений пациента"""
    
    # Проверяем, что пациент принадлежит доктору
    patient = await crud.get_patient_by_id(db, patient_id, current_user.id)
    if not patient:
        raise HTTPException(status_code=404, detail="Пациент не найден")
    
    count = await crud.get_patient_referrals_count(db, patient_id)
    return {"patient_id": patient_id, "referrals_count": count}







# ==================== Referrals Routes ====================
@app.post("/api/v1/referrals", response_model=ReferralResponse)
async def create_referral(
    data: ReferralCreate,
    current_user: Doctor = Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db)
):
    """Создать новое направление"""
    
    # Проверяем, что клиника существует
    clinic = await db.get(Clinic, data.clinic_id)
    if not clinic:
        raise HTTPException(status_code=404, detail="Клиника не найдена")
    
    # Проверяем, что пациент существует и принадлежит доктору
    patient = await crud.get_patient_by_id(db, data.patient_id, current_user.id)
    if not patient:
        raise HTTPException(status_code=404, detail="Пациент не найден")
    
    # Проверяем, что специализация существует
    specialization = await db.get(Specialization, data.specialization_id)
    if not specialization:
        raise HTTPException(status_code=404, detail="Специализация не найдена")
    
    # Проверяем даты
    if data.expected_visit_start > data.expected_visit_end:
        raise HTTPException(status_code=400, detail="Дата начала не может быть позже даты окончания")
    
    # Проверяем, что период не больше 30 дней
    delta = data.expected_visit_end - data.expected_visit_start
    if delta.days > 30:
        raise HTTPException(status_code=400, detail="Период не должен превышать 30 дней")
    
    referral = await crud.create_referral(
        db=db,
        doctor_id=current_user.id,
        clinic_id=data.clinic_id,
        patient_id=data.patient_id,
        specialization_id=data.specialization_id,
        expected_visit_start=data.expected_visit_start,
        expected_visit_end=data.expected_visit_end,
        med_indications=data.med_indications,
        special_wishes=data.special_wishes
    )
    
    return referral

@app.get("/api/v1/referrals", response_model=List[ReferralDetailResponse])
async def get_referrals(
    search: Optional[str] = None,
    status: Optional[str] = None,
    clinic_id: Optional[int] = None,
    page: int = 1,
    limit: int = 20,
    current_user: Doctor = Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db)
):
    """Получить все направления текущего доктора с фильтрами"""
    
    skip = (page - 1) * limit
    
    referrals, total = await crud.get_referrals_by_doctor(
        db=db,
        doctor_id=current_user.id,
        search=search,
        status=status,
        clinic_id=clinic_id,
        skip=skip,
        limit=limit
    )
    
    # Формируем ответ с дополнительными данными
    result = []
    for referral in referrals:
        result.append(ReferralDetailResponse(
            id=referral.id,
            doctor_id=referral.doctor_id,
            clinic_id=referral.clinic_id,
            patient_id=referral.patient_id,
            specialization_id=referral.specialization_id,
            expected_visit_start=referral.expected_visit_start,
            expected_visit_end=referral.expected_visit_end,
            med_indications=referral.med_indications,
            special_wishes=referral.special_wishes,
            status=referral.status,
            created_at=referral.created_at,
            patient_full_name=referral.patient.full_name,
            patient_phone=referral.patient.phone,
            clinic_name=referral.clinic.name,
            clinic_address=referral.clinic.address,
            specialization_name=referral.specialization.name
        ))
    
    return result


# ==================== Referrals Routes (update & delete) ====================
@app.put("/api/v1/referrals/{referral_id}", response_model=ReferralDetailResponse)
async def update_referral(
    referral_id: int,
    data: ReferralUpdate,
    current_user: Doctor = Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db)
):
    """Обновить направление"""
    
    # Проверяем даты
    if data.expected_visit_start and data.expected_visit_end:
        if data.expected_visit_start > data.expected_visit_end:
            raise HTTPException(status_code=400, detail="Дата начала не может быть позже даты окончания")
        
        delta = data.expected_visit_end - data.expected_visit_start
        if delta.days > 30:
            raise HTTPException(status_code=400, detail="Период не должен превышать 30 дней")
    
    update_data = data.dict(exclude_unset=True)
    
    referral = await crud.update_referral(
        db=db,
        referral_id=referral_id,
        doctor_id=current_user.id,
        **update_data
    )
    
    if not referral:
        raise HTTPException(status_code=404, detail="Направление не найдено")
    
    # Подгружаем связанные данные для ответа
    result = await db.execute(
        select(Referral)
        .options(
            selectinload(Referral.patient),
            selectinload(Referral.clinic),
            selectinload(Referral.specialization)
        )
        .where(Referral.id == referral_id)
    )
    referral = result.scalar_one()
    
    return ReferralDetailResponse(
        id=referral.id,
        doctor_id=referral.doctor_id,
        clinic_id=referral.clinic_id,
        patient_id=referral.patient_id,
        specialization_id=referral.specialization_id,
        expected_visit_start=referral.expected_visit_start,
        expected_visit_end=referral.expected_visit_end,
        med_indications=referral.med_indications,
        special_wishes=referral.special_wishes,
        status=referral.status,
        created_at=referral.created_at,
        patient_full_name=referral.patient.full_name,
        patient_phone=referral.patient.phone,
        clinic_name=referral.clinic.name,
        clinic_address=referral.clinic.address,
        specialization_name=referral.specialization.name
    )

@app.delete("/api/v1/referrals/{referral_id}", response_model=MessageResponse)
async def delete_referral(
    referral_id: int,
    current_user: Doctor = Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db)
):
    """Удалить направление"""
    
    deleted = await crud.delete_referral(db, referral_id, current_user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Направление не найдено")
    
    return MessageResponse(message="Направление удалено")


# ==================== Dashboard Routes ====================
@app.get("/api/v1/dashboard/stats", response_model=DashboardStatsResponse)
async def get_dashboard_stats(
    current_user: Doctor = Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db)
):
    """Получить статистику для дашборда"""
    return await crud.get_dashboard_stats(db, current_user.id)

@app.get("/api/v1/dashboard/activity", response_model=List[RecentActivityResponse])
async def get_recent_activity(
    limit: int = 5,
    current_user: Doctor = Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db)
):
    """Получить последние действия"""
    activity = await crud.get_recent_activity(db, current_user.id, limit)
    return activity

@app.get("/api/v1/dashboard/appointments", response_model=List[UpcomingAppointmentResponse])
async def get_upcoming_appointments(
    limit: int = 4,
    current_user: Doctor = Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db)
):
    """Получить ближайшие визиты"""
    appointments = await crud.get_upcoming_appointments(db, current_user.id, limit)
    return [{
        "id": a.id,
        "patient_name": a.patient.full_name,
        "clinic_name": a.clinic.name,
        "clinic_address": a.clinic.address,
        "expected_visit_start": a.expected_visit_start,
        "status": a.status
    } for a in appointments]

@app.get("/api/v1/dashboard/top-clinics", response_model=List[TopClinicResponse])
async def get_top_clinics(
    limit: int = 4,
    db: AsyncSession = Depends(get_db)
):
    """Получить топ клиник по направлениям"""
    return await crud.get_top_clinics(db, limit)



# ==================== Change Email & Password Routes ====================

@app.post("/api/v1/auth/change_email_send_code", response_model=MessageResponse)
async def change_email_send_code(
    new_email: str = Body(..., embed=True),
    db: AsyncSession = Depends(get_db)
):
    """Отправить код на новый email для смены почты"""
    
    # Проверяем, не занят ли email
    existing = await crud.get_user_by_email(db, new_email)
    if existing:
        raise HTTPException(status_code=400, detail="Этот email уже используется")
    
    # Генерируем код
    import random
    code = f"{random.randint(100000, 999999)}"
    
    # Сохраняем код
    await crud.create_email_verification(db, new_email, code)
    
    print(f"📧 Код для смены email на {new_email}: {code}")
    
    email_data = {
        "email": new_email,
        "subject": "Подтверждение смены email в MedReferral",
        "message": f"{code} - Ваш код для подтверждения смены email",
    }
    
    await broker.publish(email_data, queue="email_queue")
    
    return MessageResponse(message="Код отправлен на новый email")


@app.post("/api/v1/auth/confirm_change_email", response_model=MessageResponse)
async def confirm_change_email(
    data: ChangeEmail,
    current_user: Doctor = Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db)
):
    """Подтвердить смену email"""
    
    # Проверяем код
    verification = await crud.get_email_verification(db, data.new_email, data.code)
    if not verification:
        raise HTTPException(status_code=400, detail="Неверный или истёкший код")
    
    # Проверяем, не занят ли email
    existing = await crud.get_user_by_email(db, data.new_email)
    if existing:
        raise HTTPException(status_code=400, detail="Email уже используется")
    
    # 👇 Используем существующую функцию update_doctor
    await crud.update_doctor(db, current_user.id, email=data.new_email)
    
    # Удаляем код
    await crud.delete_email_verification(db, data.new_email)
    
    return MessageResponse(message="Email успешно изменен")


@app.post("/api/v1/auth/change_password", response_model=MessageResponse)
async def change_password(
    data: ChangePassword,
    current_user: Doctor = Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db)
):
    """Сменить пароль"""
    
    # Проверяем старый пароль
    if not verify_password(data.current_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Неверный текущий пароль")
    
    # Проверяем, что новый и подтверждение совпадают
    if data.new_password != data.confirm_password:
        raise HTTPException(status_code=400, detail="Пароли не совпадают")
    
    # Хешируем новый пароль
    new_hash = get_password_hash(data.new_password)
    
    # Обновляем
    await crud.update_doctor(db, current_user.id, password_hash=new_hash)
    
    return MessageResponse(message="Пароль успешно изменен")