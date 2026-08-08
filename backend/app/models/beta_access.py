from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.db.base import Base


class MonitorCompany(Base):
    """
    招待制モニターベータの会社（テナント）単位。

    月次クレジット上限はこの単位で管理する（ユーザー単位ではなく会社単位に絞る、
    という設計判断は docs/MONITOR_BETA_OPERATION.md 参照）。プラン名・料金体系は
    今回のスコープでは持たず、会社ごとに `monthly_credit_limit` を個別設定する
    運用（Monitor運用専用）に留める。将来の商用プラン化はここに
    `subscription_plan` 等を追加する形で拡張できる。
    """

    __tablename__ = "monitor_companies"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    slug = Column(String(100), nullable=False, unique=True, index=True)
    monthly_credit_limit = Column(Integer, nullable=False, default=100)
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


class CreditUsageLog(Base):
    """
    クレジット消費ログ。「実行前チェック→成功時のみ消費確定」方式のため、
    ここに行が作られる = 分析が成功しクレジットが消費された、を意味する
    （予約(reserved)/返却(refunded)状態は今回のスコープでは持たない。
    失敗した分析は行自体が作られないので、消費計算に一切含まれない）。

    月次の利用量はこのテーブルを都度集計して求める（集計用のスナップショット
    テーブルは持たない）。ad_insights の件数集計をそのまま踏襲した設計判断で、
    キャッシュと実体の同期漏れというクラスのバグを構造的に避けられる。
    """

    __tablename__ = "credit_usage_logs"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("monitor_companies.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("monitor_users.id"), nullable=False)
    asset_id = Column(String(100), nullable=True, index=True)
    asset_version = Column(Integer, nullable=True)
    credit_cost = Column(Integer, nullable=False)
    # analyze() の mode パラメータをそのまま記録する（例: "file_only"）。
    # Light/Standard/Heavyのような表示ラベルへの変換は表示側の責務とする。
    analysis_type = Column(String(50), nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False, index=True)

    def __repr__(self):
        return f"<CreditUsageLog(id={self.id}, company_id={self.company_id}, credit_cost={self.credit_cost})>"
