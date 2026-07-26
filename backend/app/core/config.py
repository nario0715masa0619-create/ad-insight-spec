"""
Application configuration module.

NOTE (2026-07-26): This module is currently unused — no code in this
repository imports `app.core.config`. The canonical settings module is
`app.config` (`Settings` / `get_settings()`), which is what
`app/db/session.py`, `app/main.py`, and the rest of the app actually use.
This file is left as-is (not deleted) pending a decision on whether it
should be removed or repurposed; see the db/session.py DATABASE_URL fix
task for context.
"""
import os
from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql://user:password@localhost:5432/ad_insight_spec"
    )
    
    # API
    api_title: str = "Ad-Insight-Spec API"
    api_version: str = "0.1.0"
    api_description: str = "Web広告分析・レポートサービス API"
    
    # LLM
    gemini_api_key: Optional[str] = os.getenv("GEMINI_API_KEY")
    openai_api_key: Optional[str] = os.getenv("OPENAI_API_KEY")
    
    # Meta
    meta_graph_api_key: Optional[str] = os.getenv("META_GRAPH_API_KEY")
    
    # Debug
    debug: bool = os.getenv("DEBUG", "false").lower() in ("true", "1")
    
    class Config:
        env_file = os.path.expanduser("~/.ad-insight-spec/.env")
        case_sensitive = False


settings = Settings()
