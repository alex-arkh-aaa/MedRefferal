## DOCKER
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

## ALEMBIC
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


## GIT

# 1. Убедись, что ты на develop и она актуальна
git checkout develop
git pull origin develop

# 2. Добавь изменения и закоммить
git add .
git commit -m "fix bugs"

# 3. Прогони тесты локально (опционально, но полезно)
cd backend\service_users
pytest -q
cd ..\..
cd backend\api_gateway
pytest -q
cd ..\..

# 4. Запушь develop
git push origin develop

# 5. Переключись на main и подтяни актуальную
git checkout main
git pull origin main

# 6. Смержи develop в main
git merge develop --no-edit

# 7. Запушь main — это триггерит CD
git push origin main

# 8. Вернись на develop для дальнейшей работы
git checkout develop