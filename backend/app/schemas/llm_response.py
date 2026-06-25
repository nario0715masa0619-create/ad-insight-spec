from pydantic import BaseModel, Field, ConfigDict
from typing import List, Dict, Any, Optional

class VisualsSchema(BaseModel):
    """画像・映像の視覚的特性"""
    dominant_colors: List[str] = Field(..., description="主要色リスト", min_length=1)
    composition: str = Field(..., description="構図の説明", min_length=5)
    style: str = Field(..., description="デザインスタイル", min_length=3)
    clarity: str = Field(..., description="視認性（高/中/低）", pattern="^(高|中|低)$")
    
    model_config = ConfigDict(strict=True)

class ToneSchema(BaseModel):
    """トーン・メッセージング"""
    primary_tone: List[str] = Field(..., description="主要なトーン", min_length=1)
    emotional_appeal: str = Field(..., description="感情的訴求", pattern="^(論理的|感情的|混合)$")
    call_to_action: str = Field(..., description="CTA の強度", pattern="^(強|中|弱)$")
    
    model_config = ConfigDict(strict=True)

class CreativeCoreSchema(BaseModel):
    """CreativeCore の完全 Schema"""
    visuals: VisualsSchema = Field(..., description="ビジュアル分析")
    tone: ToneSchema = Field(..., description="トーン分析")
    ai_labels: List[str] = Field(..., description="AI ラベル", min_length=1, max_length=15)
    
    model_config = ConfigDict(strict=True)

class LLMResponseSchema(BaseModel):
    """LLM 分析結果の完全 Schema"""
    success: bool = Field(default=True)
    model: str = Field(..., description="使用モデル名")
    creative_core: Optional[CreativeCoreSchema] = Field(default=None, description="CreativeCore 分析結果")
    retry_count: int = Field(default=0, ge=0, le=3)
    error_details: Optional[str] = Field(default=None, description="エラー時の詳細")
    
    model_config = ConfigDict(strict=True)
