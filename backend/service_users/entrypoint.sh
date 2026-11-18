#!/bin/sh
set -e

echo "🔄 Waiting for PostgreSQL to be ready..."
until pg_isready -h postgres -U admin -d med_referral_db; do
  echo "⏳ PostgreSQL is not ready yet..."
  sleep 2
done
echo "✅ PostgreSQL is ready!"

echo "🔄 Running database migrations..."
alembic upgrade head
echo "✅ Migrations applied successfully!"

echo "🚀 Starting application..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload