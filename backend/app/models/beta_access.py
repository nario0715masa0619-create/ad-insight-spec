from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.db.base import Base


class PricingPlan(Base):
    """
    価格・プラン定義（Starter/Growth/Pro/Monitor/Enterpriseなど）をデータとして
    保持するためのテーブル。プラン名・価格・付与クレジット・マーケティング文言を
    コードの定数ではなくここに持たせることで、価格改定やキャンペーン文言の変更を
    コード変更・再デプロイなしで行えるようにする。

    決済・請求とは接続しておらず、あくまで「会社にどれだけのクレジット上限が
    デフォルトで付与されるか」の定義元としてのみ機能する（商用販売導線・
    実際の請求処理は今回のスコープ外。docs/MONITOR_BETA_OPERATION.md参照）。
    """

    __tablename__ = "pricing_plans"

    id = Column(Integer, primary_key=True, index=True)
    # 会社への紐付けは plan_id（FK）で行うが、CLI/APIでの人間向け指定・検索には
    # code を使う（例: "starter"）。id参照にすることで、後からcodeの文言を
    # 調整してもFK関係自体は壊れない。
    code = Column(String(50), nullable=False, unique=True, index=True)
    name = Column(String(200), nullable=False)
    # 個別見積（Enterprise等）は価格を公開しないため NULL を許容する。
    monthly_price_jpy = Column(Integer, nullable=True)
    monthly_credit_limit = Column(Integer, nullable=False)
    marketing_note = Column(Text, nullable=True)
    is_public = Column(Boolean, nullable=False, default=True)
    display_order = Column(Integer, nullable=False, default=0)
    # 両方NULLなら常に有効。将来の価格改定時に旧プランを終了させつつ履歴として
    # 残す、新プランを予告日から有効にする、といった運用に使う。
    effective_from = Column(DateTime, nullable=True)
    effective_to = Column(DateTime, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    companies = relationship("MonitorCompany", back_populates="plan")

    def __repr__(self):
        return f"<PricingPlan(id={self.id}, code='{self.code}')>"


class MonitorCompany(Base):
    """
    招待制モニターベータの会社（テナント）単位。

    月次クレジット上限の実効値は「会社個別の上書き(monthly_credit_limit) >
    紐づいたプラン(plan)の monthly_credit_limit > 既定のフォールバック値」の
    優先順位で解決する（MonitorRepository.resolve_monthly_credit_limit参照）。
    monthly_credit_limit を NULL にすると「個別上書きなし、プランに従う」を
    表現できる。プランも紐付いていない会社は最後にフォールバック値を使う
    （PR #91時点の挙動との後方互換のための保険）。
    """

    __tablename__ = "monitor_companies"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    slug = Column(String(100), nullable=False, unique=True, index=True)
    plan_id = Column(Integer, ForeignKey("pricing_plans.id"), nullable=True, index=True)
    # nullable化: NULLは「個別上書きなし、プラン(またはフォールバック)に従う」を意味する。
    monthly_credit_limit = Column(Integer, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    plan = relationship("PricingPlan", back_populates="companies")
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

    token_hash には生のセッショントークンのSHA-256ハッシュのみを保存し、
    生トークン自体はDBに一切残さない（DB漏洩時にそのままAuthorizationヘッダーへ
    貼り付けて悪用されることを防ぐため。app/core/security.py::hash_session_token
    参照）。生トークンはログインAPIのレスポンスとしてクライアントに一度返す
    だけで、サーバー側では保持しない。
    """

    __tablename__ = "monitor_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("monitor_users.id"), nullable=False, index=True)
    token_hash = Column(String(128), nullable=False, unique=True, index=True)
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
