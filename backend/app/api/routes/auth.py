from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, _extract_token
from app.db.session import get_db
from app.models import MonitorUser
from app.repositories import MonitorRepository
from app.core.security import verify_password
from app.utils.error_handler import create_error_response
from app.utils.logging import request_id_var, trace_id_var, get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/auth", tags=["Auth"])


class LoginRequest(BaseModel):
    email: str
    password: str


def _user_payload(user: MonitorUser, repo: MonitorRepository) -> Dict[str, Any]:
    company = repo.get_company_by_id(user.company_id)
    usage = repo.get_usage_summary(company) if company else None
    return {
        "email": user.email,
        "display_name": user.display_name,
        "is_admin": user.is_admin,
        "company": {
            "name": company.name if company else None,
            "slug": company.slug if company else None,
        },
        "usage": usage,
    }


@router.post("/login", response_model=Dict[str, Any])
async def login(payload: LoginRequest, db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    招待制モニターベータのログイン。

    自由登録経路は存在しない。メールアドレスは常に小文字化して照合する。
    メール不存在・パスワード不一致・停止中アカウントのいずれも同一の
    汎用エラーメッセージ/エラーコードを返す（招待制であることを踏まえ、
    どの理由で失敗したかを外部から推測されないようにするため）。
    """
    repo = MonitorRepository(db)
    user = repo.get_user_by_email(payload.email)

    generic_error = (
        "メールアドレスまたはパスワードが正しくありません。招待メールに記載の"
        "情報をご確認のうえ再度お試しください。"
    )

    if not user or not verify_password(payload.password, user.password_hash):
        error_response, status_code = create_error_response(
            error_message=generic_error, error_code="INVALID_CREDENTIALS", status_code=401
        )
        raise HTTPException(status_code=status_code, detail=error_response)

    if not user.is_active:
        error_response, status_code = create_error_response(
            error_message=generic_error, error_code="INVALID_CREDENTIALS", status_code=401
        )
        raise HTTPException(status_code=status_code, detail=error_response)

    company = repo.get_company_by_id(user.company_id)
    if not company or not company.is_active:
        error_response, status_code = create_error_response(
            error_message=generic_error, error_code="INVALID_CREDENTIALS", status_code=401
        )
        raise HTTPException(status_code=status_code, detail=error_response)

    session = repo.create_session(user.id)
    repo.touch_last_login(user.id)

    logger.info(
        "Monitor user logged in",
        extra={
            "user_email": user.email,
            "company_slug": company.slug,
            "request_id": request_id_var.get(),
            "trace_id": trace_id_var.get(),
        },
    )

    return {
        "session_token": session.token,
        "expires_at": session.expires_at.isoformat(),
        **_user_payload(user, repo),
    }


@router.post("/logout", response_model=Dict[str, str])
async def logout(
    authorization: Optional[str] = Header(None), db: Session = Depends(get_db)
) -> Dict[str, str]:
    """ログアウト。トークンが無い/既に無効でも常に成功扱い（冪等）にする。"""
    token = _extract_token(authorization)
    if token:
        MonitorRepository(db).delete_session(token)
    return {"message": "Logged out"}


@router.get("/me", response_model=Dict[str, Any])
async def me(
    current_user: MonitorUser = Depends(get_current_user), db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """現在ログイン中ユーザーの情報 + 当月の利用状況（残数表示のポーリング用）"""
    repo = MonitorRepository(db)
    return _user_payload(current_user, repo)
