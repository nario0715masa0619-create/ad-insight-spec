from sqlalchemy import Column, Integer, String, DateTime, JSON, Boolean, UniqueConstraint, Index
from sqlalchemy.sql import func
from datetime import datetime
from typing import Optional
from app.db.base import Base


class AdInsight(Base):
    """
    Ad-Insight-Spec の永続化モデル
    
    JSON 正本主義に基づき、ad_insight_spec 全体を spec_data (JSON) に格納。
    検索・フィルタリング用に最低限の項目のみ冗長保持。
    """
    
    __tablename__ = "ad_insights"
    
    # プライマリキー
    id: int = Column(Integer, primary_key=True, index=True)
    
    # 検索キー（重要）
    asset_id: str = Column(String(100), nullable=False, index=True)
    
    # バージョン管理
    version: int = Column(Integer, default=1, nullable=False)
    
    # フォーマット（video_static, image_static など）
    format: str = Column(String(50), nullable=False, index=True)
    
    # タイムスタンプ
    created_at: datetime = Column(DateTime, server_default=func.now(), nullable=False, index=True)
    updated_at: datetime = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    # 論理削除フラグ
    is_deleted: bool = Column(Boolean, default=False, nullable=False, index=True)
    deleted_at: datetime = Column(DateTime, nullable=True)
    
    # JSON 正本データ（ad_insight_spec v0.2 全体）
    spec_data: dict = Column(JSON, nullable=False)

    # ===== asset/evaluation split 用（Phase 1、2026-07-09〜） =====
    # 将来的な観測事実(asset_data)/評価・解釈(evaluation_data)分割の受け皿。
    # 現時点ではどちらも常に NULL（dual-writeはまだ実装していない、Phase 3で着手）。
    # 読み出し側は backend/app/services/asset_evaluation_adapter.py::resolve_spec_data
    # を経由するため、両方NULLの間は spec_data のみのレコードとして無変換で扱われる。
    # 詳細: docs/plans/asset_evaluation_split_phase2_tasks.md
    asset_data: Optional[dict] = Column(JSON, nullable=True)
    evaluation_data: Optional[dict] = Column(JSON, nullable=True)

    # ユニーク制約: (asset_id, version) の組み合わせで一意
    __table_args__ = (
        UniqueConstraint('asset_id', 'version', name='uq_asset_id_version'),
        Index('idx_asset_id_created', 'asset_id', 'created_at'),
    )
    
    def __repr__(self):
        return f"<AdInsight(id={self.id}, asset_id='{self.asset_id}', version={self.version})>"
