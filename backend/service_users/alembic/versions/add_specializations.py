"""add specializations

Revision ID: add_specializations
Revises: 3ed86b9cb8dc
Create Date: 2026-10-31

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import table, column

revision = 'add_specializations'
down_revision = '3ed86b9cb8dc'
branch_labels = None
depends_on = None

SPECS = [
    "Терапия (врачебная практика / семейная медицина)",
    "Хирургия (общая)",
    "Педиатрия (включая неонатологию)",
    "Акушерство и гинекология",
    "Неврология",
    "Кардиология (и детская кардиология)",
    "Онкология",
    "Травматология и ортопедия",
    "Офтальмология",
    "Оториноларингология (ЛОР)",
    "Дерматовенерология",
    "Психиатрия (наркология / судебная)",
    "Анестезиология и реаниматология",
    "Инфекционные болезни",
    "Рентгенология (включая радиологию)",
    "Ультразвуковая диагностика",
    "Функциональная диагностика",
    "Эндоскопия",
    "Клиническая лабораторная диагностика",
    "Стоматология",
    "Лабораторная диагностика",
]


def upgrade() -> None:
    op.execute("TRUNCATE TABLE specializations RESTART IDENTITY CASCADE")
    t = table('specializations', column('name', sa.String))
    op.bulk_insert(t, [{"name": n} for n in SPECS])
    # восстановить clinic_specialties для существующих клиник (5 из 6e7f57f74f06)
    op.execute("""
        INSERT INTO clinic_specialties (clinic_id, specialization_id, default_rate, active)
        SELECT c.id, s.id, 10.00, true
        FROM clinics c CROSS JOIN specializations s
        ON CONFLICT (clinic_id, specialization_id) DO NOTHING
    """)


def downgrade() -> None:
    op.execute("TRUNCATE TABLE specializations RESTART IDENTITY CASCADE")
    OLD = ["Кардиология","Стоматология","Диагностика","Хирургия","Терапия",
           "Педиатрия","Гинекология","Неврология","Офтальмология","Ортопедия"]
    t = table('specializations', column('name', sa.String))
    op.bulk_insert(t, [{"name": n} for n in OLD])