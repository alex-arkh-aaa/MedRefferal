"""add_seed_data

Revision ID: xxxx
Revises: a799a240a7e2
Create Date: 2026-08-28 13:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import table, column


revision = '6e7f57f74f06'
down_revision = 'a799a240a7e2'
branch_labels = None
depends_on = None


# Специализации
specializations_data = [
    {"name": "Кардиология"},
    {"name": "Стоматология"},
    {"name": "Диагностика"},
    {"name": "Хирургия"},
    {"name": "Терапия"},
    {"name": "Педиатрия"},
    {"name": "Гинекология"},
    {"name": "Неврология"},
    {"name": "Офтальмология"},
    {"name": "Ортопедия"},
]

# Клиники
clinics_data = [
    {
        "name": "Медицинский центр 'Элита'",
        "address": "Москва, ул. Лечебная, 15",
        "location_url": "https://maps.google.com/..."
    },
    {
        "name": "Клиника 'Здоровье+'",
        "address": "Москва, пр. Мира, 45",
        "location_url": "https://maps.google.com/..."
    },
    {
        "name": "Стоматология 'Улыбка'",
        "address": "Москва, ул. Стоматологическая, 8",
        "location_url": "https://maps.google.com/..."
    },
    {
        "name": "Диагностический центр 'МРТ-Эксперт'",
        "address": "Москва, ул. Диагностическая, 12",
        "location_url": "https://maps.google.com/..."
    },
    {
        "name": "Гинекология 'Мать и дитя'",
        "address": "Москва, ул. Материнская, 3",
        "location_url": "https://maps.google.com/..."
    },
]


def upgrade():
    # Вставляем специализации
    specializations_table = table(
        'specializations',
        column('name', sa.String)
    )
    op.bulk_insert(specializations_table, specializations_data)
    
    # Вставляем клиники
    clinics_table = table(
        'clinics',
        column('name', sa.String),
        column('address', sa.String),
        column('location_url', sa.String)
    )
    op.bulk_insert(clinics_table, clinics_data)


def downgrade():
    op.execute("DELETE FROM specializations")
    op.execute("DELETE FROM clinics")