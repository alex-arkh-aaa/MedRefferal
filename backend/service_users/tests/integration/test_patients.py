"""
Integration-тесты для эндпоинтов /api/v1/patients.

Покрывают:
- создание пациента (успех, валидация Pydantic, дубликат email)
- список пациентов (только свои, пагинация)
- получение по ID (свой / чужой)
- обновление (свой / чужой)
- удаление (свой / чужой)
- статистика /patients/stats
- счётчик направлений /patients/{id}/referrals-count
"""
import pytest
from datetime import date


# ==================== Хелперы ====================

async def _create_agent(db_session, email: str, status: str = "active"):
    from app.models import Agent
    from app.security import get_password_hash
    agent = Agent(
        email=email,
        password_hash=get_password_hash("password123"),
        full_name=f"Agent {email}",
        phone="+79990000000",
        status=status,
    )
    db_session.add(agent)
    await db_session.commit()
    await db_session.refresh(agent)
    return agent


async def _create_clinic(db_session, name: str = "Test Clinic"):
    from app.models import Clinic
    clinic = Clinic(name=name, city="Moscow", address="ул. Тестовая, 1", phone="+74950000000", active=True)
    db_session.add(clinic)
    await db_session.commit()
    await db_session.refresh(clinic)
    return clinic


async def _create_specialization(db_session, name: str = "Терапия"):
    from app.models import Specialization
    spec = Specialization(name=name)
    db_session.add(spec)
    await db_session.commit()
    await db_session.refresh(spec)
    return spec


async def _login_agent(client, email: str, password: str = "password123"):
    """Логин агента, возвращает cookies для дальнейших запросов."""
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"access_token": r.cookies["access_token"]}


# ==================== Создание ====================

async def test_create_patient_ok(client, db_session):
    agent = await _create_agent(db_session, "p1@example.com")
    cookies = await _login_agent(client, "p1@example.com")

    r = await client.post("/api/v1/patients", cookies=cookies, json={
        "full_name": "Иванов Иван",
        "phone": "+79991234567",
        "date_of_birth": "1990-05-15",
        "gender": "male",
        "email": "patient1@example.com",
        "info": "Аллергия на пенициллин",
    })
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["full_name"] == "Иванов Иван"
    assert data["agent_id"] == agent.id
    assert data["status"] == "active"
    assert data["age"] is not None and data["age"] > 30


async def test_create_patient_minimal_fields(client, db_session):
    """Без email и info — должно работать (они Optional)."""
    await _create_agent(db_session, "p2@example.com")
    cookies = await _login_agent(client, "p2@example.com")

    r = await client.post("/api/v1/patients", cookies=cookies, json={
        "full_name": "Петров Пётр",
        "phone": "+79990000001",
        "date_of_birth": "1985-01-01",
        "gender": "male",
    })
    assert r.status_code == 200, r.text


async def test_create_patient_invalid_gender(client, db_session):
    await _create_agent(db_session, "p3@example.com")
    cookies = await _login_agent(client, "p3@example.com")

    r = await client.post("/api/v1/patients", cookies=cookies, json={
        "full_name": "X",
        "phone": "+7999",
        "date_of_birth": "1990-01-01",
        "gender": "unknown",  # не male/female
    })
    assert r.status_code == 422


async def test_create_patient_missing_required(client, db_session):
    await _create_agent(db_session, "p4@example.com")
    cookies = await _login_agent(client, "p4@example.com")

    r = await client.post("/api/v1/patients", cookies=cookies, json={
        "full_name": "X",
        # нет phone, date_of_birth, gender
    })
    assert r.status_code == 422


async def test_create_patient_duplicate_email(client, db_session):
    await _create_agent(db_session, "p5@example.com")
    cookies = await _login_agent(client, "p5@example.com")

    payload = {
        "full_name": "Дубль",
        "phone": "+79990000005",
        "date_of_birth": "1990-01-01",
        "gender": "female",
        "email": "dup-patient@example.com",
    }
    r1 = await client.post("/api/v1/patients", cookies=cookies, json=payload)
    assert r1.status_code == 200

    r2 = await client.post("/api/v1/patients", cookies=cookies, json=payload)
    assert r2.status_code == 400
    assert "email" in r2.json()["detail"].lower()


async def test_create_patient_requires_auth(client):
    r = await client.post("/api/v1/patients", json={
        "full_name": "X",
        "phone": "+7999",
        "date_of_birth": "1990-01-01",
        "gender": "male",
    })
    assert r.status_code == 401


# ==================== Список ====================

async def test_list_patients_only_own(client, db_session):
    """Агент A видит только своих пациентов, не видит пациентов агента B."""
    await _create_agent(db_session, "a@example.com")
    await _create_agent(db_session, "b@example.com")
    cookies_a = await _login_agent(client, "a@example.com")
    cookies_b = await _login_agent(client, "b@example.com")

    # A создаёт 2 пациентов
    for i in range(2):
        r = await client.post("/api/v1/patients", cookies=cookies_a, json={
            "full_name": f"A Patient {i}",
            "phone": f"+7999000{i:04d}",
            "date_of_birth": "1990-01-01",
            "gender": "male",
        })
        assert r.status_code == 200

    # B создаёт 1
    r = await client.post("/api/v1/patients", cookies=cookies_b, json={
        "full_name": "B Patient",
        "phone": "+79991111111",
        "date_of_birth": "1990-01-01",
        "gender": "female",
    })
    assert r.status_code == 200

    r = await client.get("/api/v1/patients", cookies=cookies_a)
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 2
    assert all(p["agent_id"] != None for p in data)
    names = [p["full_name"] for p in data]
    assert "B Patient" not in names


async def test_list_patients_search(client, db_session):
    await _create_agent(db_session, "s@example.com")
    cookies = await _login_agent(client, "s@example.com")

    await client.post("/api/v1/patients", cookies=cookies, json={
        "full_name": "Уникальный Поиск",
        "phone": "+79992222222",
        "date_of_birth": "1990-01-01",
        "gender": "male",
    })
    await client.post("/api/v1/patients", cookies=cookies, json={
        "full_name": "Другой Человек",
        "phone": "+79993333333",
        "date_of_birth": "1990-01-01",
        "gender": "male",
    })

    r = await client.get("/api/v1/patients?search=Уникальный", cookies=cookies)
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["full_name"] == "Уникальный Поиск"


# ==================== Получение по ID ====================

async def test_get_patient_own(client, db_session):
    await _create_agent(db_session, "g@example.com")
    cookies = await _login_agent(client, "g@example.com")

    r = await client.post("/api/v1/patients", cookies=cookies, json={
        "full_name": "Свой Пациент",
        "phone": "+79994444444",
        "date_of_birth": "1990-01-01",
        "gender": "male",
    })
    pid = r.json()["id"]

    r = await client.get(f"/api/v1/patients/{pid}", cookies=cookies)
    assert r.status_code == 200
    assert r.json()["id"] == pid


async def test_get_patient_foreign_404(client, db_session):
    """Агент B не может получить пациента агента A."""
    await _create_agent(db_session, "owner@example.com")
    await _create_agent(db_session, "thief@example.com")
    cookies_owner = await _login_agent(client, "owner@example.com")
    cookies_thief = await _login_agent(client, "thief@example.com")

    r = await client.post("/api/v1/patients", cookies=cookies_owner, json={
        "full_name": "Чужой",
        "phone": "+79995555555",
        "date_of_birth": "1990-01-01",
        "gender": "male",
    })
    pid = r.json()["id"]

    r = await client.get(f"/api/v1/patients/{pid}", cookies=cookies_thief)
    assert r.status_code == 404


# ==================== Обновление ====================

async def test_update_patient_own(client, db_session):
    await _create_agent(db_session, "u@example.com")
    cookies = await _login_agent(client, "u@example.com")

    r = await client.post("/api/v1/patients", cookies=cookies, json={
        "full_name": "Старое Имя",
        "phone": "+79996666666",
        "date_of_birth": "1990-01-01",
        "gender": "male",
    })
    pid = r.json()["id"]

    r = await client.put(f"/api/v1/patients/{pid}", cookies=cookies, json={
        "full_name": "Новое Имя",
        "info": "Обновлено",
    })
    assert r.status_code == 200
    data = r.json()
    assert data["full_name"] == "Новое Имя"
    assert data["info"] == "Обновлено"


async def test_update_patient_foreign_404(client, db_session):
    await _create_agent(db_session, "u2@example.com")
    await _create_agent(db_session, "u3@example.com")
    cookies_owner = await _login_agent(client, "u2@example.com")
    cookies_other = await _login_agent(client, "u3@example.com")

    r = await client.post("/api/v1/patients", cookies=cookies_owner, json={
        "full_name": "X",
        "phone": "+79997777777",
        "date_of_birth": "1990-01-01",
        "gender": "male",
    })
    pid = r.json()["id"]

    r = await client.put(f"/api/v1/patients/{pid}", cookies=cookies_other, json={
        "full_name": "Hacked",
    })
    assert r.status_code == 404


# ==================== Удаление ====================

async def test_delete_patient_own(client, db_session):
    await _create_agent(db_session, "d@example.com")
    cookies = await _login_agent(client, "d@example.com")

    r = await client.post("/api/v1/patients", cookies=cookies, json={
        "full_name": "Удаляемый",
        "phone": "+79998888888",
        "date_of_birth": "1990-01-01",
        "gender": "male",
    })
    pid = r.json()["id"]

    r = await client.delete(f"/api/v1/patients/{pid}", cookies=cookies)
    assert r.status_code == 200

    r = await client.get(f"/api/v1/patients/{pid}", cookies=cookies)
    assert r.status_code == 404


async def test_delete_patient_foreign_404(client, db_session):
    await _create_agent(db_session, "d2@example.com")
    await _create_agent(db_session, "d3@example.com")
    cookies_owner = await _login_agent(client, "d2@example.com")
    cookies_other = await _login_agent(client, "d3@example.com")

    r = await client.post("/api/v1/patients", cookies=cookies_owner, json={
        "full_name": "X",
        "phone": "+79999999999",
        "date_of_birth": "1990-01-01",
        "gender": "male",
    })
    pid = r.json()["id"]

    r = await client.delete(f"/api/v1/patients/{pid}", cookies=cookies_other)
    assert r.status_code == 404


# ==================== Статистика ====================

async def test_patients_stats(client, db_session):
    await _create_agent(db_session, "st@example.com")
    cookies = await _login_agent(client, "st@example.com")

    for i in range(3):
        await client.post("/api/v1/patients", cookies=cookies, json={
            "full_name": f"P{i}",
            "phone": f"+7999000010{i}",
            "date_of_birth": "1990-01-01",
            "gender": "male",
        })

    r = await client.get("/api/v1/patients/stats", cookies=cookies)
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 3
    assert data["active"] == 3
    assert data["new_patients"] == 3
    assert data["activity"] == 100.0


# ==================== Счётчик направлений ====================

async def test_patient_referrals_count_zero(client, db_session):
    await _create_agent(db_session, "rc@example.com")
    cookies = await _login_agent(client, "rc@example.com")

    r = await client.post("/api/v1/patients", cookies=cookies, json={
        "full_name": "Без направлений",
        "phone": "+79990000200",
        "date_of_birth": "1990-01-01",
        "gender": "male",
    })
    pid = r.json()["id"]

    r = await client.get(f"/api/v1/patients/{pid}/referrals-count", cookies=cookies)
    assert r.status_code == 200
    assert r.json()["referrals_count"] == 0