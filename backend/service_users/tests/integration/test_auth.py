import pytest


# ==================== Health ====================

async def test_health(client):
    r = await client.get("/api/v1/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"


# ==================== send_code ====================

async def test_send_code_ok(client):
    r = await client.post("/api/v1/auth/send_code", json={"email": "new@example.com"})
    assert r.status_code == 200
    assert "Код" in r.json()["message"]
    # Проверяем, что публикация в RabbitMQ была вызвана
    client.mock_publish.assert_awaited()


async def test_send_code_existing_agent(client, db_session):
    """Если email уже занят агентом — 400."""
    from app.models import Agent
    from app.security import get_password_hash

    db_session.add(Agent(
        email="exists@example.com",
        password_hash=get_password_hash("x"),
        full_name="Test",
        status="pending",
    ))
    await db_session.commit()

    r = await client.post("/api/v1/auth/send_code", json={"email": "exists@example.com"})
    assert r.status_code == 400
    assert "уже существует" in r.json()["detail"]


async def test_send_code_invalid_email(client):
    r = await client.post("/api/v1/auth/send_code", json={"email": "not-an-email"})
    assert r.status_code == 422  # Pydantic EmailStr


# ==================== register ====================

async def test_register_ok(client, db_session):
    """Полный путь: код создаётся в БД, затем регистрация."""
    from app.crud import create_email_verification

    await create_email_verification(db_session, "reg@example.com", "123456")

    r = await client.post("/api/v1/auth/register", json={
        "email": "reg@example.com",
        "password": "password123",
        "full_name": "Иван Иванов",
        "phone": "+79991234567",
        "code": 123456,
    })
    assert r.status_code == 200
    assert "успешно" in r.json()["message"].lower()

    # Проверяем, что агент создан со статусом pending
    from sqlalchemy import select
    from app.models import Agent
    result = await db_session.execute(select(Agent).where(Agent.email == "reg@example.com"))
    agent = result.scalar_one()
    assert agent.status == "pending"
    assert agent.full_name == "Иван Иванов"


async def test_register_wrong_code(client, db_session):
    from app.crud import create_email_verification
    await create_email_verification(db_session, "reg2@example.com", "111111")

    r = await client.post("/api/v1/auth/register", json={
        "email": "reg2@example.com",
        "password": "password123",
        "full_name": "Иван",
        "phone": "+7999",
        "code": 999999,  # неверный
    })
    assert r.status_code == 400
    assert "Код не подходит" in r.json()["detail"]


async def test_register_duplicate_email(client, db_session):
    from app.models import Agent
    from app.security import get_password_hash
    from app.crud import create_email_verification

    db_session.add(Agent(
        email="dup@example.com",
        password_hash=get_password_hash("x"),
        full_name="Existing",
        status="pending",
    ))
    await db_session.commit()
    await create_email_verification(db_session, "dup@example.com", "222222")

    r = await client.post("/api/v1/auth/register", json={
        "email": "dup@example.com",
        "password": "password123",
        "full_name": "New",
        "phone": "+7999",
        "code": 222222,
    })
    assert r.status_code == 400
    assert "уже существует" in r.json()["detail"]


async def test_register_short_password(client):
    r = await client.post("/api/v1/auth/register", json={
        "email": "short@example.com",
        "password": "123",  # < 8
        "full_name": "X",
        "phone": "+7999",
        "code": 123456,
    })
    assert r.status_code == 422  # Pydantic min_length


# ==================== login ====================

async def test_login_ok_agent(client, db_session):
    from app.models import Agent
    from app.security import get_password_hash

    db_session.add(Agent(
        email="active@example.com",
        password_hash=get_password_hash("password123"),
        full_name="Active Agent",
        status="active",
    ))
    await db_session.commit()

    r = await client.post("/api/v1/auth/login", json={
        "email": "active@example.com",
        "password": "password123",
    })
    assert r.status_code == 200
    data = r.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    # Cookie должна установиться
    assert "access_token" in r.cookies


async def test_login_wrong_password(client, db_session):
    from app.models import Agent
    from app.security import get_password_hash

    db_session.add(Agent(
        email="wp@example.com",
        password_hash=get_password_hash("correct"),
        full_name="X",
        status="active",
    ))
    await db_session.commit()

    r = await client.post("/api/v1/auth/login", json={
        "email": "wp@example.com",
        "password": "wrong",
    })
    assert r.status_code == 401
    assert "Неверный email или пароль" in r.json()["detail"]


async def test_login_pending_agent_forbidden(client, db_session):
    from app.models import Agent
    from app.security import get_password_hash

    db_session.add(Agent(
        email="pending@example.com",
        password_hash=get_password_hash("password123"),
        full_name="Pending",
        status="pending",
    ))
    await db_session.commit()

    r = await client.post("/api/v1/auth/login", json={
        "email": "pending@example.com",
        "password": "password123",
    })
    assert r.status_code == 403
    assert "ожидает подтверждения" in r.json()["detail"]


async def test_login_inactive_agent_forbidden(client, db_session):
    from app.models import Agent
    from app.security import get_password_hash

    db_session.add(Agent(
        email="inactive@example.com",
        password_hash=get_password_hash("password123"),
        full_name="Inactive",
        status="inactive",
    ))
    await db_session.commit()

    r = await client.post("/api/v1/auth/login", json={
        "email": "inactive@example.com",
        "password": "password123",
    })
    assert r.status_code == 403
    assert "отключён" in r.json()["detail"].lower()


async def test_login_nonexistent_user(client):
    r = await client.post("/api/v1/auth/login", json={
        "email": "nobody@example.com",
        "password": "whatever",
    })
    assert r.status_code == 401


async def test_login_admin(client, db_session):
    from app.models import Admin
    from app.security import get_password_hash

    db_session.add(Admin(
        email="admin@example.com",
        password_hash=get_password_hash("adminpass"),
        full_name="Admin",
        role="admin",
        active=True,
        permissions={},
    ))
    await db_session.commit()

    r = await client.post("/api/v1/auth/login", json={
        "email": "admin@example.com",
        "password": "adminpass",
    })
    assert r.status_code == 200
    assert "access_token" in r.json()


# ==================== logout ====================

async def test_logout(client):
    r = await client.post("/api/v1/auth/logout")
    assert r.status_code == 200
    assert "Выход" in r.json()["message"]


# ==================== me ====================

async def test_me_without_token(client):
    r = await client.get("/api/v1/auth/me")
    assert r.status_code == 401


async def test_me_with_valid_token(client, db_session):
    from app.models import Agent
    from app.security import get_password_hash, create_access_token
    import os

    agent = Agent(
        email="me@example.com",
        password_hash=get_password_hash("x"),
        full_name="Me Agent",
        status="active",
    )
    db_session.add(agent)
    await db_session.commit()
    await db_session.refresh(agent)

    token = create_access_token(
        {"sub": agent.email, "user_id": agent.id, "role": "agent"},
        expires_delta=int(os.getenv("ACC_TOKEN_EXP_MIN", "60")),
    )
    r = await client.get("/api/v1/auth/me", cookies={"access_token": token})
    assert r.status_code == 200
    data = r.json()
    assert data["role"] == "agent"
    assert data["email"] == "me@example.com"