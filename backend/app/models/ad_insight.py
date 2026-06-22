"""
SQLAlchemy models for Ad-Insight-Spec.
MVP レベルの設計：JSON カラムで柔軟性を保つ。
"""
from datetime import datetime

from sqlalchemy import Column, Integer, String, Float, DateTime, JSON, Text
from sqlalchemy.sql import func

from app.db.base import Base


class AdInsight(Base):
    """
    広告インサイト マスターテーブル
    
    正規化：
    - asset_meta, creative_core, landing_page, performance, diagnostics, views は
      JSON / JSONB カラムで保持（MVP レベル）
    - 今後の分析効率化に応じて、normalized table に分割予定
    """
    __tablename__ = "ad_insights"

    # Primary Key
    id = Column(Integer, primary_key=True, index=True)

    # Asset Meta（広告基本情報）
    ad_id = Column(String(255), unique=True, index=True, nullable=False)
    platform = Column(String(50), index=True, nullable=False)  # meta, google, tiktok等
    campaign_name = Column(String(255), nullable=False)
    adset_name = Column(String(255), nullable=False)
    ad_name = Column(String(255), nullable=False)
    analysis_period_start = Column(String(10), nullable=False)  # YYYY-MM-DD
    analysis_period_end = Column(String(10), nullable=False)    # YYYY-MM-DD

    # JSON ペイロード（整形済み ad_insight_spec）
    asset_meta = Column(JSON, nullable=False)
    creative_core = Column(JSON, nullable=False)
    landing_page = Column(JSON, nullable=False)
    performance = Column(JSON, nullable=False)
    diagnostics = Column(JSON, nullable=False)
    views = Column(JSON, nullable=False)
    _metadata = Column(JSON, nullable=False)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Metadata
    data_source = Column(String(50), nullable=True)  # meta_graph_api, csv_import等
    ai_model_version = Column(String(50), nullable=True)  # gemini-2.0, gpt-4o等

    def __repr__(self):
        return f"<AdInsight(id={self.id}, ad_id={self.ad_id}, platform={self.platform})>"
