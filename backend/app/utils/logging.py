import json
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, Optional
from pythonjsonlogger import jsonlogger
import contextvars

# Context var: request_id / trace_id
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar('request_id', default='')
trace_id_var: contextvars.ContextVar[str] = contextvars.ContextVar('trace_id', default='')

class StructuredFormatter(jsonlogger.JsonFormatter):
    """構造化ログ（JSON）フォーマッター"""
    
    def add_fields(self, log_record: Dict[str, Any], record: logging.LogRecord, message_dict: Dict[str, Any]) -> None:
        super().add_fields(log_record, record, message_dict)
        
        # タイムスタンプ追加
        log_record['timestamp'] = datetime.utcnow().isoformat() + "Z"
        
        # request_id / trace_id 追加
        log_record['request_id'] = request_id_var.get() or str(uuid.uuid4())
        log_record['trace_id'] = trace_id_var.get() or str(uuid.uuid4())
        
        # ログレベル、モジュール情報
        log_record['level'] = record.levelname
        log_record['logger'] = record.name
        log_record['module'] = record.module
        log_record['function'] = record.funcName

def setup_logging(log_level: str = "INFO", log_format: str = "json") -> logging.Logger:
    """ロギング初期化（JSON 形式）"""
    
    logger = logging.getLogger(__name__)
    logger.setLevel(getattr(logging, log_level.upper()))
    
    # ハンドラ設定
    handler = logging.StreamHandler()
    
    if log_format == "json":
        formatter = StructuredFormatter('%(timestamp)s %(level)s %(logger)s %(message)s')
    else:
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - [%(request_id)s] - %(message)s'
        )
    
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    
    return logger

def get_logger(name: str) -> logging.Logger:
    """ロガー取得"""
    return logging.getLogger(name)
