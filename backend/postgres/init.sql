-- postgres/init.sql
-- Расширения для основной БД (создаётся автоматически через POSTGRES_DB)
\c med_referral_db;

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";