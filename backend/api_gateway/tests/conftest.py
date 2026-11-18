import os
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport

# Env до импорта app
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-pytest-only")
os.environ.setdefault("JWT_ALGORITHM", "HS256")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")

# Мокаем Redis ДО импорта app.main (rate_limiting.py создаёт r = redis.from_url)
import fakeredis
_fake_redis = fakeredis.FakeRedis(decode_responses=True)
with patch("redis.from_url", return_value=_fake_redis):
    from app.main import app


@pytest.fixture
def fake_redis():
    """Доступ к фейковому Redis (можно чистить между тестами)."""
    _fake_redis.flushall()
    yield _fake_redis
    _fake_redis.flushall()


@pytest_asyncio.fixture
async def client(fake_redis):
    """AsyncClient поверх FastAPI. Cookie jar чистится перед каждым тестом."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        ac.cookies.clear()   # ← гарантируем чистое состояние
        yield ac
        ac.cookies.clear()


def make_token(payload: dict, secret: str = None, algorithm: str = None):
    """Хелпер: создать JWT для тестов."""
    from jose import jwt
    secret = secret or os.environ["JWT_SECRET_KEY"]
    algorithm = algorithm or os.environ["JWT_ALGORITHM"]
    return jwt.encode(payload, secret, algorithm=algorithm)


@pytest.fixture
def mock_proxy_response():
    """
    Мок httpx.AsyncClient.request — возвращает заданный ответ.
    Использование:
        mock_proxy_response.status_code = 200
        mock_proxy_response.json_data = {"ok": True}
    """
    class MockResponse:
        def __init__(self):
            self.status_code = 200
            self.json_data = {"ok": True}
            self.headers = {"content-type": "application/json"}
            self.content = b'{"ok": true}'

        def json(self):
            return self.json_data

        def get_list(self, name):
            return []

    resp = MockResponse()
    with patch("httpx.AsyncClient.request", new=AsyncMock(return_value=resp)) as m:
        m.response = resp
        yield m