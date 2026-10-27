"""Private identities and revocable opaque sessions; never training evidence."""
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class Account(Base):
    __tablename__ = 'accounts'
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(String(512))
    role: Mapped[str | None] = mapped_column(String(20), nullable=True, default='athlete')  # owner | athlete
    created_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    terms_accepted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    terms_version: Mapped[str | None] = mapped_column(String(20), nullable=True)


class AccountSession(Base):
    __tablename__ = 'account_sessions'
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    kind: Mapped[str] = mapped_column(String(20), default='session')


class AuthThrottle(Base):
    __tablename__ = 'auth_throttles'
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
