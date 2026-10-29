"""chef and admins

Revision ID: 4e372c0c78b5
Revises: a9c8667245f8
Create Date: 2026-10-27 13:56:52.841835

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4e372c0c78b5'
down_revision: Union[str, None] = 'a9c8667245f8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ============================================================
    # 1. ADMINS + ADMIN_CLINICS
    # ============================================================
    op.create_table(
        "admins",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("email", sa.String(length=40), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=40), nullable=False),
        sa.Column("phone", sa.String(length=20), nullable=True),
        sa.Column("role", sa.String(length=20), nullable=False, server_default="admin"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("permissions", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_admins_id", "admins", ["id"])
    op.create_index("ix_admins_email", "admins", ["email"], unique=True)
    op.create_index("ix_admins_role", "admins", ["role"])
    op.create_index(
        "uq_admins_chef",
        "admins",
        ["role"],
        unique=True,
        postgresql_where=sa.text("role = 'chef'"),
    )

    op.create_table(
        "admin_clinics",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("admin_id", sa.Integer(), nullable=False),
        sa.Column("clinic_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["admin_id"], ["admins.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["clinic_id"], ["clinics.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("admin_id", "clinic_id", name="uq_admin_clinic"),
    )
    op.create_index("ix_admin_clinics_id", "admin_clinics", ["id"])
    op.create_index("ix_admin_clinics_admin_id", "admin_clinics", ["admin_id"])
    op.create_index("ix_admin_clinics_clinic_id", "admin_clinics", ["clinic_id"])

    # ============================================================
    # 2. DOCTORS → AGENTS
    # ============================================================
    op.rename_table("doctors", "agents")
    op.execute("ALTER INDEX ix_doctors_id RENAME TO ix_agents_id")
    op.execute("ALTER INDEX ix_doctors_email RENAME TO ix_agents_email")

    op.add_column("agents", sa.Column("status", sa.String(length=20), nullable=True))
    op.add_column("agents", sa.Column("admin_id", sa.Integer(), nullable=True))
    op.add_column("agents", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))

    op.create_foreign_key(
        "fk_agents_admin_id", "agents", "admins", ["admin_id"], ["id"], ondelete="SET NULL"
    )
    op.create_index("ix_agents_status", "agents", ["status"])
    op.create_index("ix_agents_admin_id", "agents", ["admin_id"])

    # ВАЖНО: сначала заполняем, потом ставим NOT NULL
    op.execute("UPDATE agents SET status = 'active' WHERE status IS NULL")
    op.alter_column("agents", "status", nullable=False, server_default="pending")

    # ============================================================
    # 3. FK doctor_id → agent_id
    # ============================================================
    op.alter_column("patients", "doctor_id", new_column_name="agent_id")
    op.alter_column("referrals", "doctor_id", new_column_name="agent_id")
    op.alter_column("goals", "doctor_id", new_column_name="agent_id")

    op.rename_table("doctors_specializations", "agent_specializations")
    op.alter_column("agent_specializations", "doctor_id", new_column_name="agent_id")
    op.add_column(
        "agent_specializations",
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.create_unique_constraint(
        "uq_agent_specialization", "agent_specializations", ["agent_id", "specialization_id"]
    )

    # ============================================================
    # 4. CLINICS: убрать coordinates, добавить city/phone/active
    # ============================================================
    op.add_column("clinics", sa.Column("city", sa.String(length=100), nullable=True))
    op.add_column("clinics", sa.Column("phone", sa.String(length=20), nullable=True))
    op.add_column(
        "clinics",
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.execute("""
        UPDATE clinics
        SET city = COALESCE(NULLIF(TRIM(SPLIT_PART(address, ',', 1)), ''), 'Не указан')
    """)
    op.alter_column("clinics", "city", nullable=False)
    op.drop_column("clinics", "coordinates")

    # ============================================================
    # 5. AGENT_CLINICS
    # ============================================================
    op.create_table(
        "agent_clinics",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("agent_id", sa.Integer(), nullable=False),
        sa.Column("clinic_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["clinic_id"], ["clinics.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("agent_id", "clinic_id", name="uq_agent_clinic"),
    )
    op.create_index("ix_agent_clinics_id", "agent_clinics", ["id"])
    op.create_index("ix_agent_clinics_agent_id", "agent_clinics", ["agent_id"])
    op.create_index("ix_agent_clinics_clinic_id", "agent_clinics", ["clinic_id"])

    # ============================================================
    # 6. AGENT_RATES
    # ============================================================
    op.create_table(
        "agent_rates",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("agent_id", sa.Integer(), nullable=False),
        sa.Column("specialization_id", sa.Integer(), nullable=False),
        sa.Column("mode", sa.String(length=20), nullable=False, server_default="clinic"),
        sa.Column("custom_rate", sa.Numeric(5, 2), nullable=True),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["specialization_id"], ["specializations.id"]),
        sa.UniqueConstraint("agent_id", "specialization_id", name="uq_agent_rate"),
    )
    op.create_index("ix_agent_rates_id", "agent_rates", ["id"])
    op.create_index("ix_agent_rates_agent_id", "agent_rates", ["agent_id"])
    op.create_index("ix_agent_rates_specialization_id", "agent_rates", ["specialization_id"])

    # ============================================================
    # 7. CLINIC_SPECIALTIES
    # ============================================================
    op.create_table(
        "clinic_specialties",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("clinic_id", sa.Integer(), nullable=False),
        sa.Column("specialization_id", sa.Integer(), nullable=False),
        sa.Column("default_rate", sa.Numeric(5, 2), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.ForeignKeyConstraint(["clinic_id"], ["clinics.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["specialization_id"], ["specializations.id"]),
        sa.UniqueConstraint("clinic_id", "specialization_id", name="uq_clinic_specialty"),
    )
    op.create_index("ix_clinic_specialties_id", "clinic_specialties", ["id"])
    op.create_index("ix_clinic_specialties_clinic_id", "clinic_specialties", ["clinic_id"])
    op.create_index("ix_clinic_specialties_specialization_id", "clinic_specialties", ["specialization_id"])

    op.execute("""
        INSERT INTO clinic_specialties (clinic_id, specialization_id, default_rate, active)
        SELECT c.id, s.id, 10.00, true
        FROM clinics c CROSS JOIN specializations s
        ON CONFLICT (clinic_id, specialization_id) DO NOTHING
    """)

    # ============================================================
    # 8. REGISTRATIONS
    # ============================================================
    op.create_table(
        "registrations",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=40), nullable=False),
        sa.Column("email", sa.String(length=40), nullable=False),
        sa.Column("phone", sa.String(length=20), nullable=True),
        sa.Column("specialty", sa.String(length=100), nullable=False),
        sa.Column("clinic_id", sa.Integer(), nullable=False),
        sa.Column("admin_id", sa.Integer(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by", sa.Integer(), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("agent_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["clinic_id"], ["clinics.id"]),
        sa.ForeignKeyConstraint(["admin_id"], ["admins.id"]),
        sa.ForeignKeyConstraint(["reviewed_by"], ["admins.id"]),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"]),
    )
    op.create_index("ix_registrations_id", "registrations", ["id"])
    op.create_index("ix_registrations_email", "registrations", ["email"])
    op.create_index("ix_registrations_clinic_id", "registrations", ["clinic_id"])
    op.create_index("ix_registrations_admin_id", "registrations", ["admin_id"])
    op.create_index("ix_registrations_agent_id", "registrations", ["agent_id"])

    # ============================================================
    # 9. REFERRALS: новые поля + маппинг статусов
    # ============================================================
    op.add_column("referrals", sa.Column("amount", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("referrals", sa.Column("payout_status", sa.String(length=20), nullable=False, server_default="unpaid"))
    op.add_column("referrals", sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("referrals", sa.Column("payment_reference", sa.String(length=255), nullable=True))
    op.add_column("referrals", sa.Column("commission_rate", sa.Numeric(5, 2), nullable=True))
    op.add_column("referrals", sa.Column("specialty_name_at_confirmation", sa.String(length=255), nullable=True))

    op.execute("""
        UPDATE referrals
        SET payout_status = CASE WHEN is_paid = true THEN 'paid' ELSE 'unpaid' END
    """)
    op.execute("""
        UPDATE referrals
        SET amount = commission_amount
        WHERE amount = 0 AND commission_amount > 0
    """)
    op.execute("""
        UPDATE referrals
        SET status = CASE
            WHEN status IN ('confirmed', 'scheduled', 'completed') THEN 'approved'
            WHEN status IN ('cancelled', 'no-show') THEN 'rejected'
            ELSE 'new'
        END
    """)
    op.alter_column("referrals", "status", server_default="new")

    # ============================================================
    # 10. HISTORY: сливаем старую в новую
    # ============================================================
    op.create_table(
        "history_new",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("label", sa.String(length=100), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("actor_type", sa.String(length=20), nullable=False),
        sa.Column("actor_id", sa.Integer(), nullable=True),
        sa.Column("actor_name", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_history_new_id", "history_new", ["id"])
    op.create_index("ix_history_new_actor_type", "history_new", ["actor_type"])
    op.create_index("ix_history_new_actor_id", "history_new", ["actor_id"])
    op.create_index("ix_history_new_created_at", "history_new", ["created_at"])

    op.execute("""
        INSERT INTO history_new (label, text, actor_type, actor_id, actor_name, created_at)
        SELECT label, info, 'agent', doctor_id, NULL, created_at
        FROM history
    """)
    op.drop_table("history")
    op.rename_table("history_new", "history")
    op.execute("ALTER INDEX ix_history_new_id RENAME TO ix_history_id")
    op.execute("ALTER INDEX ix_history_new_actor_type RENAME TO ix_history_actor_type")
    op.execute("ALTER INDEX ix_history_new_actor_id RENAME TO ix_history_actor_id")
    op.execute("ALTER INDEX ix_history_new_created_at RENAME TO ix_history_created_at")

    # ============================================================
    # 11. EMAIL_VERIFICATIONS: doctor_email → email
    # ============================================================
    op.alter_column("email_verifications", "doctor_email", new_column_name="email")

    # ============================================================
    # 12. СИДЫ: шеф
    # ============================================================
    op.execute("""
        INSERT INTO admins (email, password_hash, full_name, role, active, permissions)
        VALUES (
            'chef@medpoint.local',
            '$argon2id$v=19$m=65536,t=3,p=4$H4Owtpay1ppzDiGEMCbE+A$tZtADgVzglJGQiYNYMG4jQWvZJcrz26BwZfkzRpbAXw',
            'Администратор портала',
            'chef',
            true,
            '{}'::json
        )
        ON CONFLICT (email) DO NOTHING
    """)


def downgrade() -> None:
    op.execute("DELETE FROM admins WHERE role = 'chef'")

    op.alter_column("email_verifications", "email", new_column_name="doctor_email")

    op.create_table(
        "history_old",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("doctor_id", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=100), nullable=False),
        sa.Column("info", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.execute("""
        INSERT INTO history_old (doctor_id, label, info, created_at)
        SELECT actor_id, label, text, created_at
        FROM history
        WHERE actor_type = 'agent' AND actor_id IS NOT NULL
    """)
    op.drop_table("history")
    op.rename_table("history_old", "history")
    op.create_index("ix_history_id", "history", ["id"])

    op.execute("""
        UPDATE referrals
        SET status = CASE
            WHEN status = 'new' THEN 'appointed'
            WHEN status = 'approved' THEN 'completed'
            WHEN status = 'rejected' THEN 'cancelled'
            ELSE status
        END
    """)
    op.drop_column("referrals", "specialty_name_at_confirmation")
    op.drop_column("referrals", "commission_rate")
    op.drop_column("referrals", "payment_reference")
    op.drop_column("referrals", "paid_at")
    op.drop_column("referrals", "payout_status")
    op.drop_column("referrals", "amount")

    op.drop_table("registrations")
    op.drop_table("clinic_specialties")
    op.drop_table("agent_rates")
    op.drop_table("agent_clinics")

    op.add_column("clinics", sa.Column("coordinates", sa.String(length=100), nullable=True))
    op.execute("UPDATE clinics SET coordinates = ''")
    op.alter_column("clinics", "coordinates", nullable=False)
    op.drop_column("clinics", "active")
    op.drop_column("clinics", "phone")
    op.drop_column("clinics", "city")

    op.drop_constraint("uq_agent_specialization", "agent_specializations", type_="unique")
    op.drop_column("agent_specializations", "active")
    op.alter_column("agent_specializations", "agent_id", new_column_name="doctor_id")
    op.rename_table("agent_specializations", "doctors_specializations")

    op.alter_column("goals", "agent_id", new_column_name="doctor_id")
    op.alter_column("referrals", "agent_id", new_column_name="doctor_id")
    op.alter_column("patients", "agent_id", new_column_name="doctor_id")

    op.add_column("agents", sa.Column("is_active", sa.Boolean(), nullable=True))
    op.execute("UPDATE agents SET is_active = (status = 'active')")
    op.alter_column("agents", "is_active", nullable=False, server_default=sa.text("true"))
    op.drop_index("ix_agents_admin_id", "agents")
    op.drop_index("ix_agents_status", "agents")
    op.drop_constraint("fk_agents_admin_id", "agents", type_="foreignkey")
    op.drop_column("agents", "deleted_at")
    op.drop_column("agents", "admin_id")
    op.drop_column("agents", "status")

    op.rename_table("agents", "doctors")
    op.execute("ALTER INDEX ix_agents_id RENAME TO ix_doctors_id")
    op.execute("ALTER INDEX ix_agents_email RENAME TO ix_doctors_email")

    op.drop_index("uq_admins_chef", "admins")
    op.drop_table("admin_clinics")
    op.drop_table("admins")