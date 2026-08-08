from datetime import datetime, timedelta
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models import MonitorCompany, MonitorUser, MonitorSession, CreditUsageLog, PricingPlan
from app.core.security import hash_password, generate_session_token

SESSION_TTL_HOURS = 24 * 14  # 2週間。モニターベータはブラウザの自動ログイン維持を
# 優先し、頻繁な再ログインで離脱されるより長めに倒す（本格SaaSの厳格なセッション
# 管理とは別の判断。docs/MONITOR_BETA_OPERATION.md参照）。

# 会社に個別上書き(monthly_credit_limit)も紐づいたプランも無い場合の最終フォールバック。
# PR #91（プラン概念導入前）のデフォルト値(100)と一致させ、プラン未設定の既存運用の
# 挙動を変えない。resolve_monthly_credit_limit() 参照。
DEFAULT_MONTHLY_CREDIT_LIMIT = 100


def current_month_start(now: Optional[datetime] = None) -> datetime:
    """当月1日 00:00:00（毎月1日リセット方式の基準時刻）"""
    now = now or datetime.utcnow()
    return datetime(now.year, now.month, 1)


class MonitorRepository:
    """招待制モニターベータの会社/ユーザー/セッション/利用状況を扱うDBアクセス層"""

    def __init__(self, db: Session):
        self.db = db

    # ===== Company =====

    def create_company(
        self,
        name: str,
        slug: str,
        monthly_credit_limit: Optional[int] = None,
        plan_id: Optional[int] = None,
        notes: Optional[str] = None,
    ) -> MonitorCompany:
        """
        monthly_credit_limit を省略(None)した場合、その会社は個別上書きを持たない
        状態で作成される（plan_id が設定されていればそのプランの上限に従い、
        どちらも無ければ DEFAULT_MONTHLY_CREDIT_LIMIT にフォールバックする。
        resolve_monthly_credit_limit() 参照）。
        """
        company = MonitorCompany(
            name=name,
            slug=slug,
            monthly_credit_limit=monthly_credit_limit,
            plan_id=plan_id,
            notes=notes,
            is_active=True,
        )
        self.db.add(company)
        self.db.commit()
        self.db.refresh(company)
        return company

    def get_company_by_id(self, company_id: int) -> Optional[MonitorCompany]:
        return self.db.query(MonitorCompany).filter(MonitorCompany.id == company_id).first()

    def get_company_by_slug(self, slug: str) -> Optional[MonitorCompany]:
        return self.db.query(MonitorCompany).filter(MonitorCompany.slug == slug).first()

    def list_companies(self) -> List[MonitorCompany]:
        return self.db.query(MonitorCompany).order_by(MonitorCompany.created_at).all()

    def update_company(
        self,
        company_id: int,
        monthly_credit_limit: Optional[int] = None,
        clear_credit_limit_override: bool = False,
        plan_id: Optional[int] = None,
        is_active: Optional[bool] = None,
        notes: Optional[str] = None,
    ) -> Optional[MonitorCompany]:
        """
        monthly_credit_limit を指定すると個別上書きを設定する。
        clear_credit_limit_override=True の場合は上書きを解除（NULLに戻す）し、
        以後はプラン（またはフォールバック）に従う。両方同時指定時は
        clear が優先される（上書きしてから消す、ではなく「今回は消す」を優先）。
        """
        company = self.get_company_by_id(company_id)
        if not company:
            return None
        if clear_credit_limit_override:
            company.monthly_credit_limit = None
        elif monthly_credit_limit is not None:
            company.monthly_credit_limit = monthly_credit_limit
        if plan_id is not None:
            company.plan_id = plan_id
        if is_active is not None:
            company.is_active = is_active
        if notes is not None:
            company.notes = notes
        self.db.commit()
        self.db.refresh(company)
        return company

    # ===== Pricing Plan =====

    def create_plan(
        self,
        code: str,
        name: str,
        monthly_credit_limit: int,
        monthly_price_jpy: Optional[int] = None,
        marketing_note: Optional[str] = None,
        is_public: bool = True,
        display_order: int = 0,
        effective_from: Optional[datetime] = None,
        effective_to: Optional[datetime] = None,
    ) -> PricingPlan:
        plan = PricingPlan(
            code=code,
            name=name,
            monthly_credit_limit=monthly_credit_limit,
            monthly_price_jpy=monthly_price_jpy,
            marketing_note=marketing_note,
            is_public=is_public,
            display_order=display_order,
            effective_from=effective_from,
            effective_to=effective_to,
            is_active=True,
        )
        self.db.add(plan)
        self.db.commit()
        self.db.refresh(plan)
        return plan

    def get_plan_by_id(self, plan_id: int) -> Optional[PricingPlan]:
        return self.db.query(PricingPlan).filter(PricingPlan.id == plan_id).first()

    def get_plan_by_code(self, code: str) -> Optional[PricingPlan]:
        return self.db.query(PricingPlan).filter(PricingPlan.code == code).first()

    def list_plans(self, public_only: bool = False) -> List[PricingPlan]:
        query = self.db.query(PricingPlan)
        if public_only:
            query = query.filter(PricingPlan.is_public == True)  # noqa: E712
        return query.order_by(PricingPlan.display_order, PricingPlan.id).all()

    def update_plan(
        self,
        plan_id: int,
        name: Optional[str] = None,
        monthly_credit_limit: Optional[int] = None,
        monthly_price_jpy: Optional[int] = None,
        clear_monthly_price_jpy: bool = False,
        marketing_note: Optional[str] = None,
        is_public: Optional[bool] = None,
        display_order: Optional[int] = None,
        effective_from: Optional[datetime] = None,
        effective_to: Optional[datetime] = None,
        is_active: Optional[bool] = None,
    ) -> Optional[PricingPlan]:
        plan = self.get_plan_by_id(plan_id)
        if not plan:
            return None
        if name is not None:
            plan.name = name
        if monthly_credit_limit is not None:
            plan.monthly_credit_limit = monthly_credit_limit
        if clear_monthly_price_jpy:
            plan.monthly_price_jpy = None
        elif monthly_price_jpy is not None:
            plan.monthly_price_jpy = monthly_price_jpy
        if marketing_note is not None:
            plan.marketing_note = marketing_note
        if is_public is not None:
            plan.is_public = is_public
        if display_order is not None:
            plan.display_order = display_order
        if effective_from is not None:
            plan.effective_from = effective_from
        if effective_to is not None:
            plan.effective_to = effective_to
        if is_active is not None:
            plan.is_active = is_active
        self.db.commit()
        self.db.refresh(plan)
        return plan

    def upsert_plan_by_code(
        self,
        code: str,
        name: str,
        monthly_credit_limit: int,
        monthly_price_jpy: Optional[int] = None,
        marketing_note: Optional[str] = None,
        is_public: bool = True,
        display_order: int = 0,
        effective_from: Optional[datetime] = None,
        effective_to: Optional[datetime] = None,
    ) -> PricingPlan:
        """
        初期プラン投入(seed)用の冪等な upsert。update_plan()の「指定した
        フィールドだけ部分更新する」PATCH的な挙動とは異なり、ここでは渡された
        引数をそのプランの完全な望ましい状態として扱う（例えば
        monthly_price_jpy=None を渡せば、既存の価格設定があっても明示的に
        NULLへ戻す。Monitor/Enterpriseのように価格を「個別見積」で持つプランを
        何度再投入しても意図通りの状態に揃うようにするため）。

        例外として is_active には一切触れない。既存プランを無効化する運用
        （update_plan の is_active=False）は明示的な操作であるべきで、
        seedの再実行で意図せず復活してしまうのを避けるため。
        """
        plan = self.get_plan_by_code(code)
        if plan is None:
            return self.create_plan(
                code=code,
                name=name,
                monthly_credit_limit=monthly_credit_limit,
                monthly_price_jpy=monthly_price_jpy,
                marketing_note=marketing_note,
                is_public=is_public,
                display_order=display_order,
                effective_from=effective_from,
                effective_to=effective_to,
            )

        plan.name = name
        plan.monthly_credit_limit = monthly_credit_limit
        plan.monthly_price_jpy = monthly_price_jpy
        plan.marketing_note = marketing_note
        plan.is_public = is_public
        plan.display_order = display_order
        plan.effective_from = effective_from
        plan.effective_to = effective_to
        self.db.commit()
        self.db.refresh(plan)
        return plan

    def get_effective_plan(self, company: MonitorCompany, now: Optional[datetime] = None) -> Optional[PricingPlan]:
        """
        company に紐づくプランが「現時点で有効」なら返す。無効・期間外・
        プラン未紐付けの場合は None（呼び出し側はフォールバックへ進む）。
        """
        if not company.plan_id:
            return None
        plan = self.get_plan_by_id(company.plan_id)
        if not plan or not plan.is_active:
            return None
        now = now or datetime.utcnow()
        if plan.effective_from and now < plan.effective_from:
            return None
        if plan.effective_to and now >= plan.effective_to:
            return None
        return plan

    def resolve_monthly_credit_limit(self, company: MonitorCompany, now: Optional[datetime] = None) -> int:
        """
        実効クレジット上限を「会社個別の上書き > 紐づいたプラン > フォールバック」
        の優先順位で解決する。
        """
        if company.monthly_credit_limit is not None:
            return company.monthly_credit_limit
        plan = self.get_effective_plan(company, now=now)
        if plan is not None:
            return plan.monthly_credit_limit
        return DEFAULT_MONTHLY_CREDIT_LIMIT

    # ===== User =====

    def create_user(
        self,
        company_id: int,
        email: str,
        password: str,
        display_name: Optional[str] = None,
        is_admin: bool = False,
    ) -> MonitorUser:
        user = MonitorUser(
            company_id=company_id,
            email=email.strip().lower(),
            password_hash=hash_password(password),
            display_name=display_name,
            is_admin=is_admin,
            is_active=True,
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def get_user_by_id(self, user_id: int) -> Optional[MonitorUser]:
        return self.db.query(MonitorUser).filter(MonitorUser.id == user_id).first()

    def get_user_by_email(self, email: str) -> Optional[MonitorUser]:
        return self.db.query(MonitorUser).filter(MonitorUser.email == email.strip().lower()).first()

    def list_users(self, company_id: Optional[int] = None) -> List[MonitorUser]:
        query = self.db.query(MonitorUser)
        if company_id is not None:
            query = query.filter(MonitorUser.company_id == company_id)
        return query.order_by(MonitorUser.created_at).all()

    def update_user(
        self,
        user_id: int,
        is_active: Optional[bool] = None,
        new_password: Optional[str] = None,
        display_name: Optional[str] = None,
    ) -> Optional[MonitorUser]:
        user = self.get_user_by_id(user_id)
        if not user:
            return None
        if is_active is not None:
            user.is_active = is_active
            if is_active is False:
                # 停止時は既存セッションも即座に無効化する
                self.db.query(MonitorSession).filter(MonitorSession.user_id == user_id).delete()
        if new_password is not None:
            user.password_hash = hash_password(new_password)
        if display_name is not None:
            user.display_name = display_name
        self.db.commit()
        self.db.refresh(user)
        return user

    def touch_last_login(self, user_id: int) -> None:
        self.db.query(MonitorUser).filter(MonitorUser.id == user_id).update(
            {MonitorUser.last_login_at: datetime.utcnow()}
        )
        self.db.commit()

    # ===== Session =====

    def create_session(self, user_id: int) -> MonitorSession:
        session = MonitorSession(
            user_id=user_id,
            token=generate_session_token(),
            expires_at=datetime.utcnow() + timedelta(hours=SESSION_TTL_HOURS),
        )
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        return session

    def get_valid_session(self, token: str) -> Optional[MonitorSession]:
        return (
            self.db.query(MonitorSession)
            .filter(MonitorSession.token == token, MonitorSession.expires_at > datetime.utcnow())
            .first()
        )

    def delete_session(self, token: str) -> None:
        self.db.query(MonitorSession).filter(MonitorSession.token == token).delete()
        self.db.commit()

    # ===== Credit usage / quota =====
    # 「実行前チェック→成功時のみ消費確定」方式（予約/返却の状態機械は持たない）。
    # credit_usage_logs に行がある = 成功した分析でクレジットが消費された、を
    # 意味するため、失敗した分析はここに一切現れず、消費計算にも影響しない。

    def sum_credits_used_this_month(self, company_id: int, now: Optional[datetime] = None) -> int:
        """当月1日以降に消費が確定した（=分析が成功した）company_idのクレジット合計。

        対応する分析結果(ad_insights)が後から論理削除されても、このログ行自体は
        削除されないため「削除して上限を回避する」ことはできない。
        """
        month_start = current_month_start(now)
        return (
            self.db.query(func.coalesce(func.sum(CreditUsageLog.credit_cost), 0))
            .filter(CreditUsageLog.company_id == company_id, CreditUsageLog.created_at >= month_start)
            .scalar()
            or 0
        )

    def record_credit_usage(
        self,
        company_id: int,
        user_id: int,
        credit_cost: int,
        analysis_type: str,
        asset_id: Optional[str] = None,
        asset_version: Optional[int] = None,
    ) -> CreditUsageLog:
        """分析成功時にのみ呼び出し、クレジット消費を確定する。"""
        log = CreditUsageLog(
            company_id=company_id,
            user_id=user_id,
            asset_id=asset_id,
            asset_version=asset_version,
            credit_cost=credit_cost,
            analysis_type=analysis_type,
        )
        self.db.add(log)
        self.db.commit()
        self.db.refresh(log)
        return log

    def get_usage_summary(self, company: MonitorCompany, now: Optional[datetime] = None) -> dict:
        used = self.sum_credits_used_this_month(company.id, now=now)
        limit = self.resolve_monthly_credit_limit(company, now=now)
        return {
            "used": used,
            "limit": limit,
            "remaining": max(limit - used, 0),
            "limit_reached": used >= limit,
        }

    def has_sufficient_credits(self, company: MonitorCompany, credit_cost: int, now: Optional[datetime] = None) -> bool:
        """`used + credit_cost <= 実効monthly_credit_limit` を満たすかどうか。"""
        used = self.sum_credits_used_this_month(company.id, now=now)
        limit = self.resolve_monthly_credit_limit(company, now=now)
        return used + credit_cost <= limit
