"""
Integration-тесты для /api/v1/clinics и /api/v1/specializations.

Покрывают:
- публичный список (без токена → только активные)
- список для агента (только его клиники)
- список для админа (только его клиники)
- список для шефа (все)
- /clinics/{id}/specialties — права доступа
"""
import pytest
from app.models import Specialization


async def _setup_data(db_session):
    from app.models import Agent, Admin, Clinic, Specialization, AgentClinic, AdminClinic
    from app.security import get_password_hash

    c1 = Clinic(name="Clinic One", city="Moscow", active=True)
    c2 = Clinic(name="Clinic Two", city="SPb", active=True)
    c3 = Clinic(name="Clinic Inactive", city="Kazan", active=False)
    db_session.add_all([c1, c2, c3])

    agent = Agent(
        email="agent@example.com",
        password_hash=get_password_hash("password123"),
        full_name="Agent",
        status="active",
    )
    admin = Admin(
        email="admin@example.com",
        password_hash=get_password_hash("adminpass"),
        full_name="Admin",
        role="admin",
        active=True,
        permissions={},
    )
    chef = Admin(
        email="chef@example.com",
        password_hash=get_password_hash("chefpass"),
        full_name="Chef",
        role="chef",
        active=True,
        permissions={},
    )
    db_session.add_all([agent, admin, chef])
    await db_session.commit()
    await db_session.refresh(agent)
    await db_session.refresh(admin)
    await db_session.refresh(chef)
    await db_session.refresh(c1)
    await db_session.refresh(c2)

    db_session.add(AgentClinic(agent_id=agent.id, clinic_id=c1.id))
    db_session.add(AdminClinic(admin_id=admin.id, clinic_id=c2.id))
    await db_session.commit()

    return {
        "c1": c1, "c2": c2, "c3": c3,
        "agent": agent, "admin": admin, "chef": chef,
    }


async def _login(client, email, password):
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"access_token": r.cookies["access_token"]}


# ==================== Публичный список ====================

async def test_clinics_public_only_active(client, db_session):
    await _setup_data(db_session)
    r = await client.get("/api/v1/clinics")
    assert r.status_code == 200
    data = r.json()
    names = {c["name"] for c in data}
    assert "Clinic One" in names
    assert "Clinic Two" in names
    assert "Clinic Inactive" not in names  # inactive не видна без токена


# ==================== Список для агента ====================

async def test_clinics_agent_sees_only_own(client, db_session):
    data = await _setup_data(db_session)
    cookies = await _login(client, "agent@example.com", "password123")

    r = await client.get("/api/v1/clinics", cookies=cookies)
    assert r.status_code == 200
    result = r.json()
    assert len(result) == 1
    assert result[0]["name"] == "Clinic One"


# ==================== Список для админа ====================

async def test_clinics_admin_sees_only_own(client, db_session):
    await _setup_data(db_session)
    cookies = await _login(client, "admin@example.com", "adminpass")

    r = await client.get("/api/v1/clinics", cookies=cookies)
    assert r.status_code == 200
    result = r.json()
    assert len(result) == 1
    assert result[0]["name"] == "Clinic Two"


# ==================== Список для шефа ====================

async def test_clinics_chef_sees_all(client, db_session):
    await _setup_data(db_session)
    cookies = await _login(client, "chef@example.com", "chefpass")

    r = await client.get("/api/v1/clinics", cookies=cookies)
    assert r.status_code == 200
    names = {c["name"] for c in r.json()}
    assert "Clinic One" in names
    assert "Clinic Two" in names
    assert "Clinic Inactive" in names  # шеф видит и неактивные


# ==================== Специализации (справочник) ====================

async def test_specializations_public(client, db_session):
    from app.models import Specialization
    db_session.add(Specialization(name="Терапия"))
    db_session.add(Specialization(name="Хирургия"))
    await db_session.commit()

    r = await client.get("/api/v1/specializations")
    assert r.status_code == 200
    names = {s["name"] for s in r.json()}
    assert "Терапия" in names
    assert "Хирургия" in names


# ==================== /clinics/{id}/specialties ====================

async def test_clinic_specialties_agent_own(client, db_session):
    from app.models import ClinicSpecialty
    data = await _setup_data(db_session)
    cookies = await _login(client, "agent@example.com", "password123")

    spec = Specialization(name="Терапия")
    db_session.add(spec)
    await db_session.commit()
    await db_session.refresh(spec)
    db_session.add(ClinicSpecialty(
        clinic_id=data["c1"].id, specialization_id=spec.id,
        default_rate=15.0, active=True,
    ))
    await db_session.commit()

    r = await client.get(f"/api/v1/clinics/{data['c1'].id}/specialties", cookies=cookies)
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 1
    assert items[0]["specialization_name"] == "Терапия"
    assert items[0]["default_rate"] == 15.0


async def test_clinic_specialties_agent_foreign_403(client, db_session):
    data = await _setup_data(db_session)
    cookies = await _login(client, "agent@example.com", "password123")

    # c2 принадлежит админу, не агенту
    r = await client.get(f"/api/v1/clinics/{data['c2'].id}/specialties", cookies=cookies)
    assert r.status_code == 403


async def test_clinic_specialties_no_auth_401(client, db_session):
    data = await _setup_data(db_session)
    r = await client.get(f"/api/v1/clinics/{data['c1'].id}/specialties")
    assert r.status_code == 401