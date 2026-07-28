FROM python:3.12

WORKDIR /app

# Устанавливаем postgresql-client для pg_isready
RUN apt-get update && apt-get install -y postgresql-client && rm -rf /var/lib/apt/lists/*

# Копируем зависимости
COPY reqs.txt .
RUN pip install --no-cache-dir -r reqs.txt

# Копируем alembic
COPY alembic.ini .
COPY alembic/ ./alembic/

# Копируем код приложения
COPY app/ ./app/

# Копируем entrypoint
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["./entrypoint.sh"]