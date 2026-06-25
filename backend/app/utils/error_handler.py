from typing import Optional, Dict, Any
from pydantic import BaseModel
from datetime import datetime
import uuid
from app.utils.logging import request_id_var, trace_id_var, get_logger

logger = get_logger(__name__)

class ErrorResponse(BaseModel):
    """統一エラーレスポンススキーマ"""
    
    success: bool = False
    error: str
    error_code: str
    request_id: str
    trace_id: str
    timestamp: str
    details: Optional[Dict[str, Any]] = None

def create_error_response(
    error_message: str,
    error_code: str = "INTERNAL_ERROR",
    status_code: int = 500,
    details: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    統一エラーレスポンス生成
    
    Args:
        error_message: エラーメッセージ
        error_code: エラーコード (e.g., "VALIDATION_ERROR", "LLM_ERROR", "OCR_ERROR")
        status_code: HTTP ステータスコード
        details: 詳細情報（オプション）
    
    Returns:
        エラーレスポンス dict
    """
    
    request_id = request_id_var.get() or str(uuid.uuid4())
    trace_id = trace_id_var.get() or str(uuid.uuid4())
    
    response = {
        "success": False,
        "error": error_message,
        "error_code": error_code,
        "request_id": request_id,
        "trace_id": trace_id,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "details": details or {}
    }
    
    # ログ出力
    logger.error(
        f"{error_code}: {error_message}",
        extra={
            "request_id": request_id,
            "trace_id": trace_id,
            "error_code": error_code,
            "details": details
        }
    )
    
    return response, status_code
