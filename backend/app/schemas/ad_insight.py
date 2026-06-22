"""
Pydantic schemas for Ad-Insight-Spec.
入れ子構造で JSON スキーマを完全に表現。
"""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


# ===== Nested Models =====

class AnalysisPeriod(BaseModel):
    """分析期間"""
    start: str = Field(..., description="ISO 8601 date format: YYYY-MM-DD")
    end: str = Field(..., description="ISO 8601 date format: YYYY-MM-DD")


class AssetMeta(BaseModel):
    """広告基本情報（asset_meta）"""
    ad_id: str = Field(..., description="広告プラットフォーム上での一意ID")
    platform: str = Field(..., description="広告媒体（meta, google, tiktok等）")
    campaign_name: str = Field(..., description="キャンペーン名")
    adset_name: str = Field(..., description="広告セット名")
    ad_name: str = Field(..., description="広告名")
    analysis_period: AnalysisPeriod = Field(..., description="分析期間")

    class Config:
        json_schema_extra = {
            "example": {
                "ad_id": "ad_123456789",
                "platform": "meta",
                "campaign_name": "Q3_Retargeting_Sale",
                "adset_name": "Website_Visitors_30d",
                "ad_name": "Static_Discount_20off",
                "analysis_period": {
                    "start": "2026-08-01",
                    "end": "2026-08-31"
                }
            }
        }


class AILabels(BaseModel):
    """LLM による自動ラベリング（ai_labels）"""
    hook_type: Optional[str] = Field(
        None,
        description="フック種類（discount, story, ugc, testimonial等）"
    )
    appeal_axis: Optional[str] = Field(
        None,
        description="訴求軸（price, quality, convenience, status等）"
    )
    target_audience: Optional[str] = Field(
        None,
        description="ターゲット層（new_users, cart_abandoners, loyal_customers等）"
    )
    emotion: Optional[str] = Field(
        None,
        description="感情的訴求（urgency, joy, trust, inspiration等）"
    )
    tone: Optional[str] = Field(
        None,
        description="トーン（casual, formal, luxury, humorous等）"
    )


class PlatformSpecific(BaseModel):
    """媒体特有フィールド（拡張可能）"""
    placement: Optional[str] = Field(None, description="Meta: fb_feed, ig_feed, ig_reels等")
    objective: Optional[str] = Field(None, description="Meta: OUTCOME_SALES, OUTCOME_LEADS等")
    budget: Optional[float] = Field(None, description="配信予算（円）")
    
    class Config:
        extra = "allow"  # 未知のフィールドを許容


class CreativeCore(BaseModel):
    """クリエイティブ要素詳細（creative_core）"""
    format: str = Field(..., description="フォーマット（static_image, video, carousel_image等）")
    primary_text: str = Field(..., description="プライマリテキスト（本文）")
    headline: str = Field(..., description="見出し")
    call_to_action: str = Field(..., description="CTA（行動喚起）")
    ai_labels: Optional[AILabels] = Field(None, description="LLM生成ラベル")
    platform_specific: Optional[PlatformSpecific] = Field(None, description="媒体特有フィールド")

    class Config:
        json_schema_extra = {
            "example": {
                "format": "static_image",
                "primary_text": "夏の終わりの特別セール！今なら全品20%OFF。",
                "headline": "期間限定20%OFF",
                "call_to_action": "詳しくはこちら",
                "ai_labels": {
                    "hook_type": "discount",
                    "appeal_axis": "price",
                    "target_audience": "cart_abandoners"
                }
            }
        }


class LandingPage(BaseModel):
    """ランディングページ情報（landing_page）"""
    url: str = Field(..., description="LP遷移先URL")
    fv_copy: str = Field(..., description="ファーストビュー訴求文")
    offer: str = Field(..., description="オファー内容")
    form_difficulty: Optional[str] = Field(
        None,
        description="フォーム難易度（low, medium, high）"
    )
    match_score_with_ad: Optional[float] = Field(
        None,
        ge=0.0,
        le=1.0,
        description="広告とのメッセージマッチスコア（0-1）"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "url": "https://example.com/sale",
                "fv_copy": "サマーセール開催中！",
                "offer": "20%割引クーポン",
                "form_difficulty": "low",
                "match_score_with_ad": 0.95
            }
        }


class Performance(BaseModel):
    """配信実績・KPI（performance）"""
    impressions: int = Field(..., ge=0, description="インプレッション数")
    clicks: int = Field(..., ge=0, description="クリック数")
    ctr: float = Field(..., ge=0.0, le=1.0, description="クリックスルーレート")
    spend: float = Field(..., ge=0.0, description="消化金額（円）")
    conversions: int = Field(..., ge=0, description="コンバージョン数")
    cpa: float = Field(..., ge=0.0, description="顧客獲得単価（円）")
    cvr: float = Field(..., ge=0.0, le=1.0, description="コンバージョンレート")
    reach: Optional[int] = Field(None, ge=0, description="リーチ数")
    frequency: Optional[float] = Field(None, ge=0.0, description="平均フリークエンシ")
    roas: Optional[float] = Field(None, ge=0.0, description="ROAS（Return on Ad Spend）")

    class Config:
        json_schema_extra = {
            "example": {
                "impressions": 150000,
                "clicks": 3000,
                "ctr": 0.02,
                "spend": 50000,
                "conversions": 50,
                "cpa": 1000,
                "cvr": 0.016,
                "reach": 120000,
                "frequency": 1.25
            }
        }


class Diagnostics(BaseModel):
    """診断結果・改善提案（diagnostics）"""
    creative_fatigue_risk: str = Field(
        ...,
        description="クリエイティブ疲弊リスク（low, medium, high）"
    )
    performance_status: str = Field(
        ...,
        description="パフォーマンス総合評価（excellent, good, fair, poor）"
    )
    lp_message_match_risk: Optional[str] = Field(
        None,
        description="LP一貫性リスク（low, medium, high）"
    )
    recommended_actions: List[str] = Field(
        ...,
        description="改善提案（複数）"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "creative_fatigue_risk": "low",
                "performance_status": "excellent",
                "lp_message_match_risk": "low",
                "recommended_actions": [
                    "現在のクリエイティブは好調。予算の増額を検討。",
                    "同様の価格訴求軸で動画フォーマットのテストを推奨。"
                ]
            }
        }


class DashboardSummary(BaseModel):
    """ダッシュボード用サマリー"""
    status_label: str = Field(..., description="ステータスラベル（Excellent, Good, Fair, Poor）")
    key_metric_highlight: str = Field(..., description="主要メトリクスのハイライト")


class Views(BaseModel):
    """UI表示用の整形済みサマリー（views）"""
    dashboard_summary: DashboardSummary = Field(..., description="ダッシュボード用サマリー")
    performance_ranking: Optional[str] = Field(None, description="ランキング内の相対位置（Top 10%等）")
    trend_indicator: Optional[str] = Field(None, description="トレンド（↑ +15%等）")

    class Config:
        json_schema_extra = {
            "example": {
                "dashboard_summary": {
                    "status_label": "Excellent",
                    "key_metric_highlight": "CPAが目標より20%低い"
                },
                "performance_ranking": "Top 10%",
                "trend_indicator": "↑ +15%"
            }
        }


class Metadata(BaseModel):
    """トレーサビリティ情報（_metadata）"""
    generated_at: str = Field(..., description="ISO 8601 形式の生成日時")
    data_source: str = Field(..., description="データソース（meta_graph_api, csv_import等）")
    ai_model_version: str = Field(..., description="使用したLLMモデル（gemini-2.0, gpt-4o等）")
    version: str = Field(..., description="JSON スキーマバージョン")

    class Config:
        json_schema_extra = {
            "example": {
                "generated_at": "2026-09-01T10:00:00Z",
                "data_source": "meta_graph_api",
                "ai_model_version": "gemini-2.0",
                "version": "1.0"
            }
        }


# ===== Top-level Request/Response Schema =====

class AdInsightCreate(BaseModel):
    """広告インサイト作成リクエスト"""
    asset_meta: AssetMeta
    creative_core: CreativeCore
    landing_page: LandingPage
    performance: Performance
    diagnostics: Diagnostics
    views: Views
    _metadata: Metadata = Field(..., alias="_metadata")

    class Config:
        populate_by_name = True  # alias の使用を許可


class AdInsight(AdInsightCreate):
    """広告インサイト（レスポンス）"""
    id: Optional[int] = Field(None, description="DB 上の主キー")
    created_at: Optional[datetime] = Field(None, description="作成日時")
    updated_at: Optional[datetime] = Field(None, description="更新日時")

    class Config:
        from_attributes = True  # SQLAlchemy モデルから属性を読み込み
