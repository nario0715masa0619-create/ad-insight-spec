from pydantic.v1 import BaseModel, Field, validator
from typing import List, Dict, Any, Optional
from enum import Enum

# ===== 改善コメント用の新スキーマ =====

class PriorityLevel(str, Enum):
    """改善優先度"""
    P0 = "P0"  # 必須
    P1 = "P1"  # 強く推奨
    P2 = "P2"  # 推奨
    P3 = "P3"  # 参考

class ImprovementComment(BaseModel):
    """構造化改善コメント"""
    
    issue_summary: str = Field(..., description="問題の簡潔な要約", min_length=5, max_length=100)
    target_scope: str = Field(..., description="対象箇所（具体的な部位を明記）", min_length=3, max_length=50)
    evidence: str = Field(..., description="改善根拠（なぜそう判断したか）", min_length=10, max_length=200)
    recommended_action: str = Field(..., description="具体的な改善アクション", min_length=10, max_length=150)
    priority: PriorityLevel = Field(default=PriorityLevel.P2, description="優先度")
    expected_impact: str = Field(..., description="改善による期待効果", min_length=5, max_length=100)
    confidence: float = Field(default=0.8, ge=0.0, le=1.0, description="推奨の信頼度（0.0～1.0）")

class ImprovementCommentsSchema(BaseModel):
    """改善コメント集合（複数の観点）"""
    
    comments: List[ImprovementComment] = Field(default=[], description="改善コメントリスト")
    total_count: int = Field(default=0, description="改善コメント総数")
    summary: Optional[str] = Field(default=None, description="全体的な改善方針サマリー")

class LLMImprovementValidationError(BaseModel):
    """改善コメント生成時のバリデーションエラー（fail-soft）"""
    
    success: bool = False
    error_code: str = Field(..., description="エラーコード")
    reason: str = Field(..., description="エラー理由")
    fallback_content: Optional[Dict[str, Any]] = Field(default=None, description="代替内容（部分的に有効な結果）")


class VisualsSchema(BaseModel):
    """画像・映像の視覚的特性"""
    dominant_colors: List[str] = Field(..., description="主要色リスト", min_length=1)
    composition: str = Field(..., description="構図の説明", min_length=5)
    style: str = Field(..., description="デザインスタイル", min_length=3)
    clarity: str = Field(..., description="視認性（高/中/低）", regex="^(高|中|低)$")
    
    class Config:
        strict = True

class ToneSchema(BaseModel):
    """トーン・メッセージング"""
    primary_tone: List[str] = Field(..., description="主要なトーン", min_length=1)
    emotional_appeal: str = Field(..., description="感情的訴求", regex="^(論理的|感情的|混合)$")
    call_to_action: str = Field(..., description="CTA の強度", regex="^(強|中|弱)$")
    
    class Config:
        strict = True

class CreativeCoreSchema(BaseModel):
    """CreativeCore の完全 Schema"""
    visuals: VisualsSchema = Field(..., description="ビジュアル分析")
    tone: ToneSchema = Field(..., description="トーン分析")
    ai_labels: List[str] = Field(..., description="AI ラベル", min_length=1, max_length=15)
    
    class Config:
        strict = True

class LLMResponseSchema(BaseModel):
    """LLM 分析結果の完全 Schema"""
    success: bool = Field(default=True)
    model: str = Field(..., description="使用モデル名")
    creative_core: Optional[CreativeCoreSchema] = Field(default=None, description="CreativeCore 分析結果")
    retry_count: int = Field(default=0, ge=0, le=3)
    error_details: Optional[str] = Field(default=None, description="エラー時の詳細")
    
    class Config:
        strict = True
