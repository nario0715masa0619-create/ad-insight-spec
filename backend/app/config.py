import os
from functools import lru_cache
from pydantic_settings import BaseSettings
from typing import Optional
from dotenv import load_dotenv

# 環境変数を優先する。systemd の EnvironmentFile 経由で既に os.environ に
# 値が入っている場合、load_dotenv() は既存の値を上書きしない（override=False）。
# cwd 依存を避けるため、参照先は絶対パス1箇所に固定する。
_ENV_FILE = "/etc/ad-insight-spec/.env"
if os.path.exists(_ENV_FILE):
    load_dotenv(dotenv_path=_ENV_FILE)

class Settings(BaseSettings):
    """アプリケーション設定（環境変数ベース）"""
    
    # API 設定
    API_TITLE: str = "Ad-Insight-Spec API"
    API_VERSION: str = "v1"
    DEBUG: bool = os.getenv("DEBUG", "False").lower() == "true"
    
    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./ad_insight.db")
    
    # LLM
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "gpt")
    
    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FORMAT: str = "json"  # json または text
    
    # CORS
    CORS_ORIGINS: list = [
        "http://localhost:3000",
        "http://localhost:8501",
        "http://127.0.0.1:8501"
    ]
    
    # API 設定
    API_TIMEOUT_SECONDS: int = int(os.getenv("API_TIMEOUT_SECONDS", "60"))
    API_RATE_LIMIT: int = int(os.getenv("API_RATE_LIMIT", "100"))  # requests per minute
    
    class Config:
        env_file = None  # dotenv 読込は上記で明示的に行うため、pydantic-settings 自身の
                          # env_file 自動探索（.env 内の未知キーで extra_forbidden クラッシュの原因）を無効化
        case_sensitive = True

@lru_cache()
def get_settings() -> Settings:
    """設定シングルトン取得"""
    return Settings()
