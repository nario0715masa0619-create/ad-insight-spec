import secrets
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
    monthly_analysis_limit: int = Field(50, ge=1)
    notes: Optional[str] = None


class CompanyUpdate(BaseModel):
    monthly_analysis_limit: Optional[int] = Field(None, ge=1)
    is_active: Optional[bool] = None
    notes: Optional[str] = None


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


def _company_dict(company, repo: MonitorRepository) -> Dict[str, Any]:
    usage = repo.get_usage_summary(company)
    return {
        "id": company.id,
        "name": company.name,
        "slug": company.slug,
        "monthly_analysis_limit": company.monthly_analysis_limit,
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

    company = repo.create_company(
        name=payload.name,
        slug=payload.slug,
        monthly_analysis_limit=payload.monthly_analysis_limit,
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
    company = repo.update_company(
        company_id,
        monthly_analysis_limit=payload.monthly_analysis_limit,
        is_active=payload.is_active,
        notes=payload.notes,
    )
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    logger.info(f"Monitor company updated: {company.slug}")
    return _company_dict(company, repo)


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
