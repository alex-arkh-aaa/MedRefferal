from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, ForeignKey, Text, Date,
    Numeric, JSON, UniqueConstraint, Index
)
from sqlalchemy.orm import relationship
from datetime import datetime
from .database import Base


# ==================== AGENT (бывший Doctor) ====================

class Agent(Base):
    __tablename__ = "agents"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(40), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(40), nullable=False)
    phone = Column(String(20), nullable=True)
    date_of_birth = Column(Date, nullable=True)
    experience = Column(String(20), nullable=True)
    education = Column(String(50), nullable=True)
    about_myself = Column(Text, nullable=True)
    column_order = Column(JSON, nullable=True, default=lambda: [
        "patient", "clinic", "specialization",
        "created_at", "visit_period", "status",
        "status_changed_at", "commission_amount",
        "is_paid", "actions"
    ])

    # pending / active / inactive / rejected
    status = Column(String(20), nullable=False, default="pending", index=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    admin_id = Column(Integer, ForeignKey("admins.id", ondelete="SET NULL"), nullable=True, index=True)

    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    admin = relationship("Admin", back_populates="agents", foreign_keys=[admin_id])
    clinics = relationship("AgentClinic", back_populates="agent", cascade="all, delete-orphan")
    specializations = relationship("AgentSpecialization", back_populates="agent", cascade="all, delete-orphan")
    rates = relationship("AgentRate", back_populates="agent", cascade="all, delete-orphan")
    patients = relationship("Patient", back_populates="agent")
    referrals = relationship("Referral", back_populates="agent")
    goals = relationship("Goal", back_populates="agent")


# ==================== ADMIN ====================

class Admin(Base):
    __tablename__ = "admins"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(40), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(40), nullable=False)
    phone = Column(String(20), nullable=True)
    role = Column(String(20), nullable=False, default="admin", index=True)  # 'chef' | 'admin'
    active = Column(Boolean, nullable=False, default=True)
    permissions = Column(JSON, nullable=False, default=dict)  # {"reviewRegistrations": false}
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    clinics = relationship("AdminClinic", back_populates="admin", cascade="all, delete-orphan")
    agents = relationship("Agent", back_populates="admin", foreign_keys="Agent.admin_id")


# Один шеф — partial unique index
Index(
    "uq_admins_chef",
    Admin.role,
    unique=True,
    postgresql_where=(Admin.role == "chef"),
)


class AdminClinic(Base):
    __tablename__ = "admin_clinics"
    __table_args__ = (UniqueConstraint("admin_id", "clinic_id", name="uq_admin_clinic"),)

    id = Column(Integer, primary_key=True, index=True)
    admin_id = Column(Integer, ForeignKey("admins.id", ondelete="CASCADE"), nullable=False, index=True)
    clinic_id = Column(Integer, ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False, index=True)

    admin = relationship("Admin", back_populates="clinics")
    clinic = relationship("Clinic", back_populates="admins")


# ==================== CLINIC ====================

class Clinic(Base):
    __tablename__ = "clinics"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    city = Column(String(100), nullable=False)
    address = Column(String(255), nullable=True)
    phone = Column(String(20), nullable=True)
    active = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    admins = relationship("AdminClinic", back_populates="clinic", cascade="all, delete-orphan")
    agents = relationship("AgentClinic", back_populates="clinic", cascade="all, delete-orphan")
    specialties = relationship("ClinicSpecialty", back_populates="clinic", cascade="all, delete-orphan")
    referrals = relationship("Referral", back_populates="clinic")


# ==================== SPECIALIZATION ====================

class Specialization(Base):
    __tablename__ = "specializations"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True, nullable=False)

    # Relationships
    agents = relationship("AgentSpecialization", back_populates="specialization")
    clinics = relationship("ClinicSpecialty", back_populates="specialization")
    agent_rates = relationship("AgentRate", back_populates="specialization")
    referrals = relationship("Referral", back_populates="specialization")


# ==================== AGENT ↔ CLINIC ====================

class AgentClinic(Base):
    __tablename__ = "agent_clinics"
    __table_args__ = (UniqueConstraint("agent_id", "clinic_id", name="uq_agent_clinic"),)

    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(Integer, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True)
    clinic_id = Column(Integer, ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False, index=True)

    agent = relationship("Agent", back_populates="clinics")
    clinic = relationship("Clinic", back_populates="agents")


# ==================== AGENT ↔ SPECIALIZATION ====================

class AgentSpecialization(Base):
    __tablename__ = "agent_specializations"
    __table_args__ = (UniqueConstraint("agent_id", "specialization_id", name="uq_agent_specialization"),)

    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(Integer, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True)
    specialization_id = Column(Integer, ForeignKey("specializations.id"), nullable=False, index=True)
    active = Column(Boolean, nullable=False, default=True)

    agent = relationship("Agent", back_populates="specializations")
    specialization = relationship("Specialization", back_populates="agents")


# ==================== AGENT RATE ====================

class AgentRate(Base):
    __tablename__ = "agent_rates"
    __table_args__ = (UniqueConstraint("agent_id", "specialization_id", name="uq_agent_rate"),)

    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(Integer, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True)
    specialization_id = Column(Integer, ForeignKey("specializations.id"), nullable=False, index=True)
    mode = Column(String(20), nullable=False, default="clinic")  # 'clinic' | 'custom'
    custom_rate = Column(Numeric(5, 2), nullable=True)

    agent = relationship("Agent", back_populates="rates")
    specialization = relationship("Specialization", back_populates="agent_rates")


# ==================== CLINIC ↔ SPECIALIZATION ====================

class ClinicSpecialty(Base):
    __tablename__ = "clinic_specialties"
    __table_args__ = (UniqueConstraint("clinic_id", "specialization_id", name="uq_clinic_specialty"),)

    id = Column(Integer, primary_key=True, index=True)
    clinic_id = Column(Integer, ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False, index=True)
    specialization_id = Column(Integer, ForeignKey("specializations.id"), nullable=False, index=True)
    default_rate = Column(Numeric(5, 2), nullable=True)
    active = Column(Boolean, nullable=False, default=True)

    clinic = relationship("Clinic", back_populates="specialties")
    specialization = relationship("Specialization", back_populates="clinics")


# ==================== PATIENT ====================

class Patient(Base):
    __tablename__ = "patients"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String(40), nullable=False)
    date_of_birth = Column(Date, nullable=False)
    phone = Column(String(20), nullable=False)
    email = Column(String(255), nullable=True)
    gender = Column(String(10), nullable=False)  # 'male' | 'female'
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=False, index=True)
    info = Column(Text, nullable=True)
    status = Column(String(20), default="active", nullable=False)  # active, inactive

    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    agent = relationship("Agent", back_populates="patients")
    referrals = relationship("Referral", back_populates="patient")


# ==================== REFERRAL ====================

class Referral(Base):
    __tablename__ = "referrals"

    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=False, index=True)
    clinic_id = Column(Integer, ForeignKey("clinics.id"), nullable=False, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False, index=True)
    specialization_id = Column(Integer, ForeignKey("specializations.id"), nullable=False, index=True)

    amount = Column(Integer, nullable=False, default=0)  # стоимость услуги
    expected_visit_start = Column(Date, nullable=False)
    expected_visit_end = Column(Date, nullable=False)
    med_indications = Column(Text, nullable=False)
    special_wishes = Column(Text, nullable=False, default="")

    status = Column(String(255), nullable=False, default="new")  # new / approved / rejected
    status_changed_at = Column(DateTime(timezone=True), nullable=True)

    commission_rate = Column(Numeric(5, 2), nullable=True)
    commission_amount = Column(Integer, nullable=False, default=0)
    specialty_name_at_confirmation = Column(String(255), nullable=True)

    payout_status = Column(String(20), nullable=False, default="unpaid")  # unpaid / processing / paid
    paid_at = Column(DateTime(timezone=True), nullable=True)
    payment_reference = Column(String(255), nullable=True)

    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    agent = relationship("Agent", back_populates="referrals")
    clinic = relationship("Clinic", back_populates="referrals")
    patient = relationship("Patient", back_populates="referrals")
    specialization = relationship("Specialization", back_populates="referrals")


# ==================== GOAL ====================

class Goal(Base):
    __tablename__ = "goals"

    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=False, index=True)
    month = Column(Integer, nullable=False)
    year = Column(Integer, nullable=False)
    income_money = Column(Integer, nullable=False)
    referrals = Column(Integer, nullable=False)

    agent = relationship("Agent", back_populates="goals")


# ==================== HISTORY (единая) ====================

class History(Base):
    __tablename__ = "history"

    id = Column(Integer, primary_key=True, index=True)
    label = Column(String(100), nullable=False)
    text = Column(Text, nullable=False)
    actor_type = Column(String(20), nullable=False, index=True)  # 'agent' | 'admin' | 'chef' | 'system'
    actor_id = Column(Integer, nullable=True, index=True)
    actor_name = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False, index=True)


# ==================== EMAIL VERIFICATION ====================

class EmailVerification(Base):
    __tablename__ = "email_verifications"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(40), nullable=False, index=True)
    code = Column(String(6), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)