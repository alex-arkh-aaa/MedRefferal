# backend/service_users/alembic/env.py
from logging.config import fileConfig
import sys
from pathlib import Path

from sqlalchemy import create_engine, pool
from alembic import context

# Добавляем путь к приложению
sys.path.append(str(Path(__file__).parent.parent))

# Импортируем Base и модели
from app.database import Base
from app.models import User, EmailVerification    #, PartnerRequest, Partner, Category, Ad, AdCategory, Favorite

# Это объект конфигурации Alembic
config = context.config 

# Настраиваем логирование из alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Метаданные всех таблиц
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Запуск миграций в offline режиме (только генерация SQL)"""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Запуск миграций в online режиме (подключение к БД)"""
    # Используем СИНХРОННЫЙ движок для миграций
    connectable = create_engine(
        config.get_main_option("sqlalchemy.url"),
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


# Определяем режим запуска
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()