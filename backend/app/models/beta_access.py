from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.db.base import Base


class MonitorCompany(Base):
    """
    招待制モニターベータの会社（テナント）単位。

    月間分析上限はこの単位で管理する（ユーザー単位ではなく会社単位に絞る、
    という設計判断は docs/MONITOR_BETA_OPERATION.md 参照）。
    """

    __tablename__ = "monitor_companies"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    slug = Column(String(100), nullable=False, unique=True, index=True)
    monthly_analysis_limit = Column(Integer, nullable=False, default=50)
    is_active = Column(Boolean, nullable=False, default=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    users = relationship("MonitorUser", back_populates="company")

    def __repr__(self):
        return f"<MonitorCompany(id={self.id}, slug='{self.slug}')>"


class MonitorUser(Base):
    """
    招待されたモニターベータ利用者。自由登録経路は存在せず、管理者
    （またはCLI）がアカウントを発行することでのみ作成される。
    """

    __tablename__ = "monitor_users"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("monitor_companies.id"), nullable=False, index=True)
    email = Column(String(255), nullable=False, unique=True, index=True)
    password_hash = Column(String(255), nullable=False)
    display_name = Column(String(200), nullable=True)
    is_admin = Column(Boolean, nullable=False, default=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    last_login_at = Column(DateTime, nullable=True)

    company = relationship("MonitorCompany", back_populates="users")
    sessions = relationship("MonitorSession", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<MonitorUser(id={self.id}, email='{self.email}')>"


class MonitorSession(Base):
    """
    サーバー側で保持するログインセッション（署名付きトークンではなく、
    失効・強制ログアウトをシンプルに扱えるDB保持方式を採用）。
    """

    __tablename__ = "monitor_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("monitor_users.id"), nullable=False, index=True)
    token = Column(String(128), nullable=False, unique=True, index=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    expires_at = Column(DateTime, nullable=False)

    user = relationship("MonitorUser", back_populates="sessions")

    def __repr__(self):
        return f"<MonitorSession(id={self.id}, user_id={self.user_id})>"
