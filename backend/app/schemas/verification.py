"""
CampaignPilot 検証機能のスキーマ。

CampaignPilotの提案が、Meta Ads Managerだけでは出にくい新規の原因特定・改善案を
生み、実行と成果改善につながるかを記録するための検証用スキーマ。
ad_insight_spec（分析結果本体）とは独立しており、既存スキーマの変更は伴わない。
"""
from typing import Optional, Dict, Any, List, Literal
from datetime import datetime

from pydantic import BaseModel, Field, model_validator

# ===== Enum 相当（Literal） =====

AwarenessRating = Literal[
    "already_knew",           # 既に気づいていた
    "realized_when_told",     # 言われて初めて気づいた
    "questionable_validity",  # 妥当性に疑問
    "cannot_judge",           # 判断不能
]

OriginalityRating = Literal[
    "could_have_suggested_myself",       # 自分でも出していた
    "could_not_have_suggested_myself",   # 自分では先に出せなかった
    "generic",                           # 一般論
    "hard_to_execute",                   # 実行しにくい
    "unnecessary",                       # 不要
]

FollowupCheckpoint = Literal["week_2", "week_4"]


# ===== VerificationCase =====

class VerificationCaseCreate(BaseModel):
    case_name: str = Field(..., min_length=1, max_length=200, description="案件名/クライアント名")
    asset_id: Optional[str] = Field(None, description="紐づく ad_insights.asset_id（任意）")
    asset_version: Optional[int] = Field(
        None, description="asset_id が示す分析結果のうち、提示したバージョン（asset_id指定時は必須）"
    )
    pre_hearing_notes: Optional[Dict[str, Any]] = Field(None, description="事前ヒアリング内容")

    @model_validator(mode="after")
    def _require_asset_version_with_asset_id(self) -> "VerificationCaseCreate":
        if self.asset_id and self.asset_version is None:
            raise ValueError("asset_id を指定する場合は asset_version（提示したバージョン）も必須です。")
        if self.asset_version is not None and not self.asset_id:
            raise ValueError("asset_version は asset_id とセットで指定してください。")
        return self


class PresentationEvaluationUpdate(BaseModel):
    presentation_evaluation: Dict[str, Any] = Field(..., description="CampaignPilot提示後の総合評価")


class VerificationCaseSummary(BaseModel):
    id: int
    case_name: str
    asset_id: Optional[str]
    asset_version: Optional[int]
    created_at: datetime
    updated_at: Optional[datetime]
    suggestion_count: int = 0

    model_config = {"from_attributes": True}


# ===== SuggestionEvaluation =====

class SuggestionEvaluationCreate(BaseModel):
    suggestion_key: str = Field(..., min_length=1, max_length=300, description="提案タイトル/識別ラベル")
    suggestion_text: Optional[str] = Field(None, description="提案内容のコピー")
    awareness_rating: AwarenessRating
    originality_rating: OriginalityRating


class SuggestionEvaluationUpdate(BaseModel):
    awareness_rating: Optional[AwarenessRating] = None
    originality_rating: Optional[OriginalityRating] = None


class FollowupResponse(BaseModel):
    checkpoint: FollowupCheckpoint
    executed: Optional[bool]
    result_change: Optional[str]
    recorded_at: datetime

    model_config = {"from_attributes": True}


class SuggestionEvaluationResponse(BaseModel):
    id: int
    case_id: int
    suggestion_key: str
    suggestion_text: Optional[str]
    awareness_rating: str
    originality_rating: str
    created_at: datetime
    updated_at: Optional[datetime]
    followups: List[FollowupResponse] = []

    model_config = {"from_attributes": True}


class VerificationCaseDetail(BaseModel):
    id: int
    case_name: str
    asset_id: Optional[str]
    asset_version: Optional[int]
    pre_hearing_notes: Optional[Dict[str, Any]]
    presentation_evaluation: Optional[Dict[str, Any]]
    created_at: datetime
    updated_at: Optional[datetime]
    suggestion_evaluations: List[SuggestionEvaluationResponse] = []

    model_config = {"from_attributes": True}


# ===== Followup =====

class FollowupUpsert(BaseModel):
    executed: Optional[bool] = None
    result_change: Optional[str] = None
