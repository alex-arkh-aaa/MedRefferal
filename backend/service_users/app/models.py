from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, Date
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from .database import Base


class Doctor(Base):
    __tablename__ = "doctors"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(40), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(40), nullable=False)
    phone = Column(String(20), nullable=True)
    date_of_birth = Column(Date, nullable=True)
    experience = Column(String(20), nullable=True)
    education = Column(String(50), nullable=True)  # 👈 добавить
    about_myself = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    specializations = relationship("DoctorSpecialization", back_populates="doctor", cascade="all, delete-orphan")
    patients = relationship("Patient", back_populates="doctor")
    referrals = relationship("Referral", back_populates="doctor")
    goals = relationship("Goal", back_populates="doctor")
    history = relationship("History", back_populates="doctor")


class EmailVerification(Base):
    __tablename__ = "email_verifications"
    
    id = Column(Integer, primary_key=True, index=True)
    doctor_email = Column(String(40), nullable=False)
    code = Column(String(6), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Specialization(Base):
    __tablename__ = "specializations"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True, nullable=False)
    
    # Relationships
    doctors = relationship("DoctorSpecialization", back_populates="specialization")


class DoctorSpecialization(Base):
    __tablename__ = "doctors_specializations"
    
    id = Column(Integer, primary_key=True, index=True)
    doctor_id = Column(Integer, ForeignKey("doctors.id", ondelete="CASCADE"), nullable=False)
    specialization_id = Column(Integer, ForeignKey("specializations.id"), nullable=False)
    
    # Relationships
    doctor = relationship("Doctor", back_populates="specializations")
    specialization = relationship("Specialization", back_populates="doctors")


class Clinic(Base):
    __tablename__ = "clinics"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    address = Column(String(100), nullable=False)
    coordinates = Column(String(100), nullable=False)
    
    # Relationships
    referrals = relationship("Referral", back_populates="clinic")


class Patient(Base):
    __tablename__ = "patients"
    
    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String(40), nullable=False)
    date_of_birth = Column(Date, nullable=False)
    phone = Column(String(20), nullable=False)
    email = Column(String(255), nullable=True)
    gender = Column(String(10), nullable=False)  # 'М' или 'Ж'
    doctor_id = Column(Integer, ForeignKey("doctors.id"), nullable=False)
    info = Column(Text, nullable=True)
    status = Column(String(20), default="active", nullable=False)  # active, inactive

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    doctor = relationship("Doctor", back_populates="patients")
    referrals = relationship("Referral", back_populates="patient")


class Referral(Base):
    __tablename__ = "referrals"
    
    id = Column(Integer, primary_key=True, index=True)
    doctor_id = Column(Integer, ForeignKey("doctors.id"), nullable=False)
    clinic_id = Column(Integer, ForeignKey("clinics.id"), nullable=False)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    specialization_id = Column(Integer, ForeignKey("specializations.id"), nullable=False)
    expected_visit_start = Column(Date, nullable=False)
    expected_visit_end = Column(Date, nullable=False)
    med_indications = Column(Text, nullable=False)
    special_wishes = Column(Text, nullable=False)
    status = Column(String(255), nullable=False, default="appointed")
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    doctor = relationship("Doctor", back_populates="referrals")
    clinic = relationship("Clinic", back_populates="referrals")
    patient = relationship("Patient", back_populates="referrals")
    specialization = relationship("Specialization")


class Goal(Base):
    __tablename__ = "goals"
    
    id = Column(Integer, primary_key=True, index=True)
    doctor_id = Column(Integer, ForeignKey("doctors.id"), nullable=False)
    month = Column(Integer, nullable=False)  # 1-12
    year = Column(Integer, nullable=False)
    income_money = Column(Integer, nullable=False)
    referrals = Column(Integer, nullable=False)
    
    # Relationships
    doctor = relationship("Doctor", back_populates="goals")


class History(Base):
    __tablename__ = "history"
    
    id = Column(Integer, primary_key=True, index=True)
    doctor_id = Column(Integer, ForeignKey("doctors.id"), nullable=False)
    label = Column(String(100), nullable=False)
    info = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    doctor = relationship("Doctor", back_populates="history")