import secrets
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.db.session import get_db
from app.models import MonitorUser
from app.repositories import MonitorRepository
from app.utils.error_handler import create_error_response
from app.utils.logging import get_logger

logger = get_logger(__name__)

# ===== モニター管理用の最小限の管理API =====
# 招待制モニターベータの運用（会社追加/停止、上限変更、ユーザー招待/停止、
# 利用状況確認）を行うための管理API。専用の管理画面は今回のスコープでは
# 用意せず、この API を docs/MONITOR_ACCOUNT_MANAGEMENT.md の手順・
# scripts/manage_monitor_accounts.py のCLIから叩く運用とする。
# 全エンドポイントが require_admin（is_admin=Trueのログイン済みユーザー）必須。

router = APIRouter(prefix="/api/v1/admin", tags=["Admin"])


class CompanyCreate(BaseModel):
    name: str
    slug: str = Field(..., description="URLセーフな英数字ID（例: acme）。一意制約あり")
    monthly_credit_limit: Optional[int] = Field(
        None,
        ge=0,
        description=(
            "個別上書き。未指定ならplan_idのプラン、両方無ければ既定値にフォールバック。"
            "0は「アカウントは有効なまま、今月の分析だけ完全に止める」という意味（アカウント停止(is_active)とは別軸）"
        ),
    )
    plan_id: Optional[int] = Field(None, description="紐づけるプランのID（省略可）")
    notes: Optional[str] = None


class CompanyUpdate(BaseModel):
    monthly_credit_limit: Optional[int] = Field(
        None, ge=0, description="個別上書きを設定する（0=今月の分析を完全にブロック）"
    )
    clear_credit_limit_override: bool = Field(
        False, description="trueの場合、個別上書きを解除してプラン/既定値に戻す（monthly_credit_limitより優先）"
    )
    plan_id: Optional[int] = None
    is_active: Optional[bool] = None
    notes: Optional[str] = None


class PlanCreate(BaseModel):
    code: str = Field(..., description="一意な英数字コード（例: starter, growth, pro, monitor, enterprise）")
    name: str
    monthly_credit_limit: int = Field(..., ge=0)
    monthly_price_jpy: Optional[int] = Field(None, ge=0, description="個別見積プラン等はNULL可")
    marketing_note: Optional[str] = Field(None, description="例:「初期導入企業向けキャンペーン企画中」")
    is_public: bool = True
    display_order: int = 0
    effective_from: Optional[datetime] = None
    effective_to: Optional[datetime] = None


class PlanUpdate(BaseModel):
    name: Optional[str] = None
    monthly_credit_limit: Optional[int] = Field(None, ge=0)
    monthly_price_jpy: Optional[int] = Field(None, ge=0)
    clear_monthly_price_jpy: bool = False
    marketing_note: Optional[str] = None
    is_public: Optional[bool] = None
    display_order: Optional[int] = None
    effective_from: Optional[datetime] = None
    effective_to: Optional[datetime] = None
    is_active: Optional[bool] = None


class UserCreate(BaseModel):
    company_id: int
    email: str
    password: Optional[str] = Field(
        None, description="未指定の場合はランダム生成し、レスポンスに一度だけ含めて返す"
    )
    display_name: Optional[str] = None
    is_admin: bool = False


class UserUpdate(BaseModel):
    is_active: Optional[bool] = None
    new_password: Optional[str] = None
    display_name: Optional[str] = None


def _plan_dict(plan) -> Dict[str, Any]:
    return {
        "id": plan.id,
        "code": plan.code,
        "name": plan.name,
        "monthly_price_jpy": plan.monthly_price_jpy,
        "monthly_credit_limit": plan.monthly_credit_limit,
        "marketing_note": plan.marketing_note,
        "is_public": plan.is_public,
        "display_order": plan.display_order,
        "effective_from": plan.effective_from.isoformat() if plan.effective_from else None,
        "effective_to": plan.effective_to.isoformat() if plan.effective_to else None,
        "is_active": plan.is_active,
        "created_at": plan.created_at.isoformat(),
    }


def _company_dict(company, repo: MonitorRepository) -> Dict[str, Any]:
    usage = repo.get_usage_summary(company)
    effective_plan = repo.get_effective_plan(company)
    return {
        "id": company.id,
        "name": company.name,
        "slug": company.slug,
        # monthly_credit_limit: 個別上書きの生値（Noneならプラン/既定値任せ）。
        # 実効値は usage_this_month.limit（= resolve_monthly_credit_limitの結果）を見る。
        "monthly_credit_limit": company.monthly_credit_limit,
        "plan_id": company.plan_id,
        "plan": _plan_dict(effective_plan) if effective_plan else None,
        "limit_source": repo.describe_limit_source(company),
        "is_active": company.is_active,
        "notes": company.notes,
        "created_at": company.created_at.isoformat(),
        "usage_this_month": usage,
    }


def _user_dict(user: MonitorUser) -> Dict[str, Any]:
    return {
        "id": user.id,
        "company_id": user.company_id,
        "email": user.email,
        "display_name": user.display_name,
        "is_admin": user.is_admin,
        "is_active": user.is_active,
        "created_at": user.created_at.isoformat(),
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
    }


# ===== Companies =====

@router.post("/companies", response_model=Dict[str, Any])
async def create_company(
    payload: CompanyCreate,
    db: Session = Depends(get_db),
    _admin: MonitorUser = Depends(require_admin),
) -> Dict[str, Any]:
    repo = MonitorRepository(db)
    if repo.get_company_by_slug(payload.slug):
        error_response, status_code = create_error_response(
            error_message=f"slug '{payload.slug}' は既に使用されています。",
            error_code="COMPANY_SLUG_TAKEN",
            status_code=409,
        )
        raise HTTPException(status_code=status_code, detail=error_response)
    if payload.plan_id is not None and not repo.get_plan_by_id(payload.plan_id):
        raise HTTPException(status_code=404, detail="Plan not found")

    company = repo.create_company(
        name=payload.name,
        slug=payload.slug,
        monthly_credit_limit=payload.monthly_credit_limit,
        plan_id=payload.plan_id,
        notes=payload.notes,
    )
    logger.info(f"Monitor company created: {company.slug}")
    return _company_dict(company, repo)


@router.get("/companies", response_model=List[Dict[str, Any]])
async def list_companies(
    db: Session = Depends(get_db),
    _admin: MonitorUser = Depends(require_admin),
) -> List[Dict[str, Any]]:
    repo = MonitorRepository(db)
    return [_company_dict(c, repo) for c in repo.list_companies()]


@router.patch("/companies/{company_id}", response_model=Dict[str, Any])
async def update_company(
    company_id: int,
    payload: CompanyUpdate,
    db: Session = Depends(get_db),
    _admin: MonitorUser = Depends(require_admin),
) -> Dict[str, Any]:
    repo = MonitorRepository(db)
    if payload.plan_id is not None and not repo.get_plan_by_id(payload.plan_id):
        raise HTTPException(status_code=404, detail="Plan not found")

    company = repo.update_company(
        company_id,
        monthly_credit_limit=payload.monthly_credit_limit,
        clear_credit_limit_override=payload.clear_credit_limit_override,
        plan_id=payload.plan_id,
        is_active=payload.is_active,
        notes=payload.notes,
    )
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    logger.info(f"Monitor company updated: {company.slug}")
    return _company_dict(company, repo)


# ===== Pricing Plans =====

@router.post("/plans", response_model=Dict[str, Any])
async def create_plan(
    payload: PlanCreate,
    db: Session = Depends(get_db),
    _admin: MonitorUser = Depends(require_admin),
) -> Dict[str, Any]:
    repo = MonitorRepository(db)
    if repo.get_plan_by_code(payload.code):
        error_response, status_code = create_error_response(
            error_message=f"code '{payload.code}' は既に使用されています。",
            error_code="PLAN_CODE_TAKEN",
            status_code=409,
        )
        raise HTTPException(status_code=status_code, detail=error_response)

    plan = repo.create_plan(
        code=payload.code,
        name=payload.name,
        monthly_credit_limit=payload.monthly_credit_limit,
        monthly_price_jpy=payload.monthly_price_jpy,
        marketing_note=payload.marketing_note,
        is_public=payload.is_public,
        display_order=payload.display_order,
        effective_from=payload.effective_from,
        effective_to=payload.effective_to,
    )
    logger.info(f"Pricing plan created: {plan.code}")
    return _plan_dict(plan)


@router.get("/plans", response_model=List[Dict[str, Any]])
async def list_plans(
    db: Session = Depends(get_db),
    _admin: MonitorUser = Depends(require_admin),
) -> List[Dict[str, Any]]:
    repo = MonitorRepository(db)
    return [_plan_dict(p) for p in repo.list_plans()]


@router.patch("/plans/{plan_id}", response_model=Dict[str, Any])
async def update_plan(
    plan_id: int,
    payload: PlanUpdate,
    db: Session = Depends(get_db),
    _admin: MonitorUser = Depends(require_admin),
) -> Dict[str, Any]:
    repo = MonitorRepository(db)
    plan = repo.update_plan(
        plan_id,
        name=payload.name,
        monthly_credit_limit=payload.monthly_credit_limit,
        monthly_price_jpy=payload.monthly_price_jpy,
        clear_monthly_price_jpy=payload.clear_monthly_price_jpy,
        marketing_note=payload.marketing_note,
        is_public=payload.is_public,
        display_order=payload.display_order,
        effective_from=payload.effective_from,
        effective_to=payload.effective_to,
        is_active=payload.is_active,
    )
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    logger.info(f"Pricing plan updated: {plan.code}")
    return _plan_dict(plan)


# ===== Users =====

@router.post("/users", response_model=Dict[str, Any])
async def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    _admin: MonitorUser = Depends(require_admin),
) -> Dict[str, Any]:
    repo = MonitorRepository(db)
    if not repo.get_company_by_id(payload.company_id):
        raise HTTPException(status_code=404, detail="Company not found")
    if repo.get_user_by_email(payload.email):
        error_response, status_code = create_error_response(
            error_message=f"メールアドレス '{payload.email}' は既に登録されています。",
            error_code="USER_EMAIL_TAKEN",
            status_code=409,
        )
        raise HTTPException(status_code=status_code, detail=error_response)

    generated_password = payload.password or secrets.token_urlsafe(9)
    user = repo.create_user(
        company_id=payload.company_id,
        email=payload.email,
        password=generated_password,
        display_name=payload.display_name,
        is_admin=payload.is_admin,
    )
    logger.info(f"Monitor user invited: {user.email}")
    response = _user_dict(user)
    if not payload.password:
        # 生成したパスワードはハッシュ化前の平文をここでしか返せないため、
        # 招待作成レスポンスにのみ一度だけ含める（DBには保存しない）。
        response["generated_password"] = generated_password
    return response


@router.get("/users", response_model=List[Dict[str, Any]])
async def list_users(
    company_id: Optional[int] = None,
    db: Session = Depends(get_db),
    _admin: MonitorUser = Depends(require_admin),
) -> List[Dict[str, Any]]:
    repo = MonitorRepository(db)
    return [_user_dict(u) for u in repo.list_users(company_id=company_id)]


@router.patch("/users/{user_id}", response_model=Dict[str, Any])
async def update_user(
    user_id: int,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    _admin: MonitorUser = Depends(require_admin),
) -> Dict[str, Any]:
    repo = MonitorRepository(db)
    user = repo.update_user(
        user_id,
        is_active=payload.is_active,
        new_password=payload.new_password,
        display_name=payload.display_name,
    )
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    logger.info(f"Monitor user updated: {user.email}")
    return _user_dict(user)
