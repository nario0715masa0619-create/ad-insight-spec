from datetime import datetime, timedelta
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models import MonitorCompany, MonitorUser, MonitorSession, CreditUsageLog
from app.core.security import hash_password, generate_session_token

SESSION_TTL_HOURS = 24 * 14  # 2週間。モニターベータはブラウザの自動ログイン維持を
# 優先し、頻繁な再ログインで離脱されるより長めに倒す（本格SaaSの厳格なセッション
# 管理とは別の判断。docs/MONITOR_BETA_OPERATION.md参照）。


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
        self, name: str, slug: str, monthly_credit_limit: int = 100, notes: Optional[str] = None
    ) -> MonitorCompany:
        company = MonitorCompany(
            name=name, slug=slug, monthly_credit_limit=monthly_credit_limit, notes=notes, is_active=True
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
        is_active: Optional[bool] = None,
        notes: Optional[str] = None,
    ) -> Optional[MonitorCompany]:
        company = self.get_company_by_id(company_id)
        if not company:
            return None
        if monthly_credit_limit is not None:
            company.monthly_credit_limit = monthly_credit_limit
        if is_active is not None:
            company.is_active = is_active
        if notes is not None:
            company.notes = notes
        self.db.commit()
        self.db.refresh(company)
        return company

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
        limit = company.monthly_credit_limit
        return {
            "used": used,
            "limit": limit,
            "remaining": max(limit - used, 0),
            "limit_reached": used >= limit,
        }

    def has_sufficient_credits(self, company: MonitorCompany, credit_cost: int, now: Optional[datetime] = None) -> bool:
        """`used + credit_cost <= monthly_credit_limit` を満たすかどうか。"""
        used = self.sum_credits_used_this_month(company.id, now=now)
        return used + credit_cost <= company.monthly_credit_limit
