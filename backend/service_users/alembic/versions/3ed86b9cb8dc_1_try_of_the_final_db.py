"""1 try of the final db

Revision ID: 3ed86b9cb8dc
Revises: 00ebc10d1104
Create Date: 2026-10-31 14:08:07.540357

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '3ed86b9cb8dc'
down_revision: Union[str, None] = '00ebc10d1104'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. admins: DROP unique constraint (уникальность остаётся через ix_admins_email)
    op.execute("ALTER TABLE admins DROP CONSTRAINT IF EXISTS admins_email_key")

    # 2. agent_specializations: индексы
    op.execute("DROP INDEX IF EXISTS ix_doctors_specializations_id")
    op.execute("CREATE INDEX IF NOT EXISTS ix_agent_specializations_id ON agent_specializations (id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_agent_specializations_agent_id ON agent_specializations (agent_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_agent_specializations_specialization_id ON agent_specializations (specialization_id)")

    # 3. TIMESTAMP → TIMESTAMPTZ (с USING, иначе PostgreSQL не кастует)
    op.execute("ALTER TABLE agents ALTER COLUMN created_at TYPE TIMESTAMPTZ USING created_at AT TIME ZONE 'UTC'")
    op.execute("ALTER TABLE agents ALTER COLUMN updated_at TYPE TIMESTAMPTZ USING updated_at AT TIME ZONE 'UTC'")
    op.execute("ALTER TABLE patients ALTER COLUMN created_at TYPE TIMESTAMPTZ USING created_at AT TIME ZONE 'UTC'")
    op.execute("ALTER TABLE patients ALTER COLUMN updated_at TYPE TIMESTAMPTZ USING updated_at AT TIME ZONE 'UTC'")
    op.execute("ALTER TABLE referrals ALTER COLUMN created_at TYPE TIMESTAMPTZ USING created_at AT TIME ZONE 'UTC'")
    op.execute("ALTER TABLE referrals ALTER COLUMN status_changed_at TYPE TIMESTAMPTZ USING status_changed_at AT TIME ZONE 'UTC'")
    op.execute("ALTER TABLE email_verifications ALTER COLUMN created_at TYPE TIMESTAMPTZ USING created_at AT TIME ZONE 'UTC'")
    op.execute("ALTER TABLE email_verifications ALTER COLUMN expires_at TYPE TIMESTAMPTZ USING expires_at AT TIME ZONE 'UTC'")

    # 4. NOT NULL
    op.execute("UPDATE referrals SET created_at = now() WHERE created_at IS NULL")
    op.alter_column('agents', 'created_at', nullable=False)
    op.alter_column('agents', 'updated_at', nullable=False)
    op.alter_column('patients', 'created_at', nullable=False)
    op.alter_column('patients', 'updated_at', nullable=False)
    op.alter_column('referrals', 'created_at', nullable=False)
    op.alter_column('email_verifications', 'created_at', nullable=False)

    # 5. clinics.address → VARCHAR(255), NULL
    op.alter_column(
        'clinics', 'address',
        existing_type=sa.VARCHAR(length=100),
        type_=sa.String(length=255),
        existing_nullable=False,
        nullable=True,
    )

    # 6. FK-индексы
    op.execute("CREATE INDEX IF NOT EXISTS ix_email_verifications_email ON email_verifications (email)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_goals_agent_id ON goals (agent_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_patients_agent_id ON patients (agent_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_referrals_agent_id ON referrals (agent_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_referrals_clinic_id ON referrals (clinic_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_referrals_patient_id ON referrals (patient_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_referrals_specialization_id ON referrals (specialization_id)")

    # 7. DROP is_paid (данные уже в payout_status)
    op.drop_column('referrals', 'is_paid')


def downgrade() -> None:
    # is_paid — обратно (пустой, данные не восстанавливаем)
    op.add_column(
        'referrals',
        sa.Column('is_paid', sa.BOOLEAN(), server_default=sa.text('false'), autoincrement=False, nullable=False),
    )

    # FK-индексы
    op.execute("DROP INDEX IF EXISTS ix_referrals_specialization_id")
    op.execute("DROP INDEX IF EXISTS ix_referrals_patient_id")
    op.execute("DROP INDEX IF EXISTS ix_referrals_clinic_id")
    op.execute("DROP INDEX IF EXISTS ix_referrals_agent_id")
    op.execute("DROP INDEX IF EXISTS ix_patients_agent_id")
    op.execute("DROP INDEX IF EXISTS ix_goals_agent_id")
    op.execute("DROP INDEX IF EXISTS ix_email_verifications_email")

    # clinics.address → VARCHAR(100), NOT NULL
    op.alter_column(
        'clinics', 'address',
        existing_type=sa.String(length=255),
        type_=sa.VARCHAR(length=100),
        existing_nullable=True,
        nullable=False,
    )

    # NOT NULL → nullable (обратно)
    op.alter_column('referrals', 'created_at', nullable=True)
    op.alter_column('patients', 'updated_at', nullable=True)
    op.alter_column('patients', 'created_at', nullable=True)
    op.alter_column('email_verifications', 'created_at', nullable=True)
    op.alter_column('agents', 'updated_at', nullable=True)
    op.alter_column('agents', 'created_at', nullable=True)

    # TIMESTAMPTZ → TIMESTAMP (с USING, обратно)
    op.execute("ALTER TABLE agents ALTER COLUMN created_at TYPE TIMESTAMP USING created_at AT TIME ZONE 'UTC'")
    op.execute("ALTER TABLE agents ALTER COLUMN updated_at TYPE TIMESTAMP USING updated_at AT TIME ZONE 'UTC'")
    op.execute("ALTER TABLE patients ALTER COLUMN created_at TYPE TIMESTAMP USING created_at AT TIME ZONE 'UTC'")
    op.execute("ALTER TABLE patients ALTER COLUMN updated_at TYPE TIMESTAMP USING updated_at AT TIME ZONE 'UTC'")
    op.execute("ALTER TABLE referrals ALTER COLUMN created_at TYPE TIMESTAMP USING created_at AT TIME ZONE 'UTC'")
    op.execute("ALTER TABLE referrals ALTER COLUMN status_changed_at TYPE TIMESTAMP USING status_changed_at AT TIME ZONE 'UTC'")
    op.execute("ALTER TABLE email_verifications ALTER COLUMN created_at TYPE TIMESTAMP USING created_at AT TIME ZONE 'UTC'")
    op.execute("ALTER TABLE email_verifications ALTER COLUMN expires_at TYPE TIMESTAMP USING expires_at AT TIME ZONE 'UTC'")

    # agent_specializations: обратно
    op.execute("DROP INDEX IF EXISTS ix_agent_specializations_specialization_id")
    op.execute("DROP INDEX IF EXISTS ix_agent_specializations_agent_id")
    op.execute("DROP INDEX IF EXISTS ix_agent_specializations_id")
    op.execute("CREATE INDEX IF NOT EXISTS ix_doctors_specializations_id ON agent_specializations (id)")

    # admins: обратно unique constraint
    op.execute("ALTER TABLE admins ADD CONSTRAINT admins_email_key UNIQUE (email)")