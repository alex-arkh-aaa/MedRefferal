import os
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from unittest.mock import AsyncMock, patch

# Обязательно до импорта app: env-переменные, которые читает security.py
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-pytest-only")
os.environ.setdefault("JWT_ALGORITHM", "HS256")
os.environ.setdefault("ACC_TOKEN_EXP_MIN", "60")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

from app.database import Base, get_db
from app.main import app


@pytest_asyncio.fixture
async def db_engine():
    """Отдельный in-memory SQLite движок на каждый тест."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine):
    """Сессия для прямых манипуляций с БД в тестах."""
    TestingSessionLocal = sessionmaker(
        db_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with TestingSessionLocal() as session:
        yield session


@pytest_asyncio.fixture
async def client(db_engine):
    """
    AsyncClient поверх FastAPI с подменой get_db на тестовую БД
    и заглушкой RabbitMQ-брокера (чтобы не лезть в реальный RabbitMQ).
    """
    TestingSessionLocal = sessionmaker(
        db_engine, class_=AsyncSession, expire_on_commit=False
    )

    async def override_get_db():
        async with TestingSessionLocal() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    # Подменяем публикацию в RabbitMQ — тесты не должны требовать брокер
    with patch("app.main.broker.publish", new=AsyncMock()) as mock_publish:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            ac.mock_publish = mock_publish  # удобно проверять в тестах
            yield ac

    app.dependency_overrides.clear()