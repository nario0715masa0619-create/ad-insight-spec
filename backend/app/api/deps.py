from typing import Optional

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import MonitorUser
from app.repositories import MonitorRepository
from app.utils.error_handler import create_error_response


def _unauthorized(message: str, error_code: str = "UNAUTHORIZED") -> HTTPException:
    error_response, status_code = create_error_response(
        error_message=message, error_code=error_code, status_code=401
    )
    return HTTPException(status_code=status_code, detail=error_response)


def _extract_token(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip()
    # ヘッダーにスキーム無しでトークンだけが入っているケースも許容する
    # （Streamlit側は必ず "Bearer <token>" 形式で送るが、curl等での手動運用時の
    # 取りこぼしを減らすためのフォールバック）
    return authorization.strip() or None


def get_current_user(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
) -> MonitorUser:
    """
    招待制モニターベータのログイン状態を検証する FastAPI 依存関数。

    Authorization: Bearer <session_token> ヘッダーを検証し、有効な
    MonitorUser を返す。無効・期限切れ・停止中ユーザー・停止中会社の
    いずれの場合も 401 を返す（存在有無で区別せず、常に同じ汎用メッセージに
    するのは招待制であることの意図的な設計）。
    """
    token = _extract_token(authorization)
    if not token:
        raise _unauthorized("ログインが必要です。メールアドレスとパスワードでログインしてください。")

    repo = MonitorRepository(db)
    session = repo.get_valid_session(token)
    if not session:
        raise _unauthorized("セッションが無効か期限切れです。再度ログインしてください。", error_code="SESSION_EXPIRED")

    user = repo.get_user_by_id(session.user_id)
    if not user or not user.is_active:
        raise _unauthorized("このアカウントは無効化されています。管理者にお問い合わせください。", error_code="ACCOUNT_DISABLED")

    company = repo.get_company_by_id(user.company_id)
    if not company or not company.is_active:
        raise _unauthorized(
            "この会社のモニター利用は現在停止中です。管理者にお問い合わせください。", error_code="COMPANY_DISABLED"
        )

    return user


def require_admin(current_user: MonitorUser = Depends(get_current_user)) -> MonitorUser:
    """管理者専用エンドポイント用。認証済みだが管理者でない場合は403。"""
    if not current_user.is_admin:
        error_response, status_code = create_error_response(
            error_message="この操作には管理者権限が必要です。",
            error_code="ADMIN_REQUIRED",
            status_code=403,
        )
        raise HTTPException(status_code=status_code, detail=error_response)
    return current_user
