import os
from functools import lru_cache
from pydantic_settings import BaseSettings
from typing import Optional
from dotenv import load_dotenv

env_paths = [
    r"C:\Users\nario\.ad-insight-spec\.env",
    "/opt/ad-insight-spec/backend/.env",
    "/home/nario_o_0715_masa_0619/.ad-insight-spec/.env",
    "/root/.ad-insight-spec/.env",
    ".env"
]
for path in env_paths:
    if os.path.exists(path):
        load_dotenv(dotenv_path=path)
        break
else:
    load_dotenv()

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
        env_file = ".env"
        case_sensitive = True

@lru_cache()
def get_settings() -> Settings:
    """設定シングルトン取得"""
    return Settings()
