docker-compose up --build



Таблицы юзеров и пользователей можно посмореть через Docker Desktop: 
psql -U admin -d users_db

Другие команды:
\d table_name
\dt
\c orders_db
\l

\x auto
select * from users;

DELETE FROM users;
DROP TABLE users;



ALEMBIC
# Создать структуру Alembic в проекте
alembic init alembic

# Автоматическая генерация (по изменениям в моделях)
alembic revision --autogenerate -m "Описание изменений"

# Сокращенная версия
alembic revision -m "Описание" --autogenerate

# Создать пустую миграцию (для ручного написания)
alembic revision -m "Manual migration"

# Создать пустую миграцию без сообщения
alembic revision

# Создать миграцию с указанием конкретной версии
alembic revision --autogenerate -m "Описание" --head=xxxx


# Применить ВСЕ миграции (до последней версии)
alembic upgrade head

# Применить на 1 шаг вперед
alembic upgrade +1

# Применить до конкретной версии (по ID)
alembic upgrade b0c70cfff473

# Применить до последней версии с показом SQL (без выполнения)
alembic upgrade head --sql

# Применить с подробным выводом
alembic upgrade head --verbose


# Откатить на 1 шаг назад
alembic downgrade -1

# Откатить до конкретной версии
alembic downgrade b0c70cfff473

# Откатить до самого начала (пустая БД)
alembic downgrade base

# Откатить с показом SQL (без выполнения)
alembic downgrade -1 --sql


# Показать ТЕКУЩУЮ версию БД
alembic current

# Показать ИСТОРИЮ всех миграций
alembic history

# Показать историю с подробностями
alembic history --verbose

# Показать историю в виде графа
  alembic history --graph

# Показать список всех доступных команд
alembic --help

# Показать все ветки
alembic branches




Браузер
    ↓
NGINX (порт 80)
    ↓
API Gateway (порт 8000) ← 👈 JWT, безопасность, логи
    ↓
Service Users (порт 8000) ← 👈 Только бизнес-логика
Service Orders (порт 8000) ← 👈 Только бизнес-логика


API Gateway: проверка токенов и прав доступа
Service Users: создание токенов, хеширование паролей