"""Тесты auth middleware."""
import pytest
from tests.conftest import make_token


# ==================== Публичные пути ====================

async def test_public_root_no_token(client):
    r = await client.get("/")
    assert r.status_code == 200


async def test_public_login_no_token(client, mock_proxy_response):
    """POST /api/v1/auth/login — публичный, проксируется."""
    r = await client.post("/api/v1/auth/login", json={"email": "a@b.c", "password": "x"})
    assert r.status_code == 200


async def test_public_health_no_token(client):
    r = await client.get("/api/v1/health")
    # /api/v1/health не в public_paths! Проверим — должен требовать токен
    # (в public_paths есть '/api/v1/health' — да, есть)
    assert r.status_code in (200, 503)


# ==================== Защищённые пути без токена ====================

async def test_protected_api_no_token_401(client):
    r = await client.get("/api/v1/patients")
    assert r.status_code == 401
    assert r.json()["error"] == "Unauthorized"


async def test_protected_api_no_token_401_post(client):
    r = await client.post("/api/v1/patients", json={})
    assert r.status_code == 401


async def test_protected_html_no_token_redirect(client):
    """HTML-путь без токена → редирект на /."""
    r = await client.get("/dashboard", follow_redirects=False)
    assert r.status_code in (302, 307)
    assert r.headers["location"] == "/"


# ==================== Невалидный токен ====================

async def test_invalid_token_401(client):
    r = await client.get("/api/v1/patients", cookies={"access_token": "garbage"})
    assert r.status_code == 401
    assert r.json()["error"] == "Invalid token"


async def test_wrong_secret_token_401(client):
    token = make_token({"sub": "a@b.c"}, secret="another-secret")
    r = await client.get("/api/v1/patients", cookies={"access_token": token})
    assert r.status_code == 401
    assert r.json()["error"] == "Invalid token"


async def test_expired_token_401(client):
    import time
    token = make_token({"sub": "a@b.c", "exp": int(time.time()) - 100})
    r = await client.get("/api/v1/patients", cookies={"access_token": token})
    assert r.status_code == 401
    assert r.json()["error"] == "Token expired"


async def test_invalid_token_html_redirect(client):
    r = await client.get("/dashboard", cookies={"access_token": "garbage"}, follow_redirects=False)
    assert r.status_code in (302, 307)
    assert r.headers["location"] == "/"


# ==================== Валидный токен ====================

async def test_valid_token_passes_through(client, mock_proxy_response):
    token = make_token({"sub": "a@b.c", "user_id": 1, "role": "agent"})
    r = await client.get("/api/v1/patients", cookies={"access_token": token})
    # Прокси вызван, вернул 200 от мока
    assert r.status_code == 200


# ==================== OPTIONS пропускается ====================

async def test_options_bypasses_auth(client):
    r = await client.options("/api/v1/patients")
    # OPTIONS пропускается middleware, но роут не зарегистрирован → 405
    assert r.status_code == 405


# ==================== Bearer-токен в заголовке ====================

async def test_bearer_token_in_header(client):
    """Middleware читает только cookie. Bearer-заголовок НЕ поддерживается в gateway."""
    token = make_token({"sub": "a@b.c"})
    r = await client.get(
        "/api/v1/patients",
        headers={"Authorization": f"Bearer {token}"},
        follow_redirects=False,
    )
    # Gateway не смотрит в Authorization → 401 (нет cookie)
    assert r.status_code == 401