from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, Boolean
from sqlalchemy.orm import relationship
from .database import Base


class User(Base):
    __tablename__ = "users"
    id              = Column(Integer, primary_key=True, index=True)
    email           = Column(String, unique=True, index=True, nullable=False)
    username        = Column(String, nullable=False)
    hashed_password = Column(String, nullable=False)
    salary          = Column(Float, default=0.0)
    mfa_enabled     = Column(Boolean, default=False)
    mfa_code        = Column(String, nullable=True)
    mfa_code_expiry = Column(DateTime, nullable=True)
    created_at      = Column(DateTime, default=datetime.utcnow)

    transactions  = relationship("Transaction",   back_populates="owner", cascade="all, delete-orphan")
    goals         = relationship("FinancialGoal", back_populates="owner", cascade="all, delete-orphan")
    activity_logs = relationship("ActivityLog",   back_populates="owner", cascade="all, delete-orphan")


class Transaction(Base):
    __tablename__ = "transactions"
    id          = Column(Integer, primary_key=True, index=True)
    amount      = Column(Float,  nullable=False)
    type        = Column(String, nullable=False)
    category    = Column(String, nullable=False)
    description = Column(String, default="")
    date        = Column(DateTime, default=datetime.utcnow)
    user_id     = Column(Integer, ForeignKey("users.id"), nullable=False)
    owner       = relationship("User", back_populates="transactions")


class FinancialGoal(Base):
    __tablename__ = "financial_goals"
    id         = Column(Integer, primary_key=True, index=True)
    name       = Column(String, nullable=False)
    target     = Column(Float,  nullable=False)
    saved      = Column(Float,  default=0.0)
    deadline   = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    user_id    = Column(Integer, ForeignKey("users.id"), nullable=False)
    owner      = relationship("User", back_populates="goals")


class ActivityLog(Base):
    __tablename__ = "activity_logs"
    id         = Column(Integer, primary_key=True, index=True)
    action     = Column(String, nullable=False)
    detail     = Column(String, default="")
    timestamp  = Column(DateTime, default=datetime.utcnow)
    ip_address = Column(String, default="unknown")
    user_id    = Column(Integer, ForeignKey("users.id"), nullable=False)
    owner      = relationship("User", back_populates="activity_logs")
