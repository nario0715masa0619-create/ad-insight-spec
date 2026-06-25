"""
Pydantic models for Ad-Insight-Spec v0.2
File-First Strategy対応版

Structure:
- InputMetadata: 入力モード・ソース記録
- AssetMeta: 素材メタデータ（file-first）
- CreativeCore: 素材内容分析
- LandingPage: LP分析（optional）
- Performance: KPI（optional、mode依存）
- Diagnostics: 定性+定量診断
- Views: UI表示用（生成版）
- Metadata: スキーマ・ツールバージョン

Mode依存の strict/optional:
- file_only: performance=null, landing_page=null
- file_plus_lp: performance=null
- file_plus_lp_plus_manual_kpi: 全フィールド必須or最適値
- api_import_ready: 全フィールド必須（Phase 2）
"""

from typing import Optional, List, Dict, Any
from pydantic.v1 import BaseModel, Field, validator, root_validator
from datetime import datetime
from enum import Enum


# ===== Enumerations =====

class InputModeEnum(str, Enum):
    """入力モード"""
    FILE_ONLY = "file_only"
    FILE_PLUS_LP = "file_plus_lp"
    FILE_PLUS_LP_PLUS_MANUAL_KPI = "file_plus_lp_plus_manual_kpi"
    API_IMPORT_READY = "api_import_ready"


class SourceTypeEnum(str, Enum):
    """データソース種別"""
    LOCAL_FILE = "local_file"
    API = "api"
    HYBRID = "hybrid"


class FormatEnum(str, Enum):
    """クリエイティブフォーマット"""
    VIDEO_STATIC = "video_static"
    IMAGE_STATIC = "image_static"
    IMAGE_CAROUSEL = "image_carousel"
    TEXT_ONLY = "text_only"
    MIXED = "mixed"


class HookTypeEnum(str, Enum):
    """Hook タイプ（LLM判定）"""
    BENEFIT = "benefit"
    CURIOSITY = "curiosity"
    PAIN_POINT = "pain_point"
    SOCIAL_PROOF = "social_proof"
    SCARCITY = "scarcity"
    OTHER = "other"


class ToneEnum(str, Enum):
    """トーン分類"""
    PROFESSIONAL = "professional"
    CASUAL = "casual"
    HUMOROUS = "humorous"
    URGENT = "urgent"
    INSPIRATIONAL = "inspirational"
    OTHER = "other"


class RiskLevelEnum(str, Enum):
    """リスク評価レベル"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class PerformanceStatusEnum(str, Enum):
    """パフォーマンスステータス"""
    EXCELLENT = "excellent"
    GOOD = "good"
    FAIR = "fair"
    POOR = "poor"


class FormDifficultyEnum(str, Enum):
    """フォーム難易度"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# ===== Input Metadata =====

class FilePaths(BaseModel):
    """入力ファイルパス情報"""
    creative_video: Optional[str] = Field(None, description="入力ビデオファイルパス")
    creative_images: Optional[List[str]] = Field(None, description="入力画像ファイルパスリスト")
    landing_page_html: Optional[str] = Field(None, description="LPのローカルHTMLファイルパス")

    class Config:
        schema_extra = {
            "example": {
                "creative_video": "/downloads/ad_001_video.mp4",
                "creative_images": None,
                "landing_page_html": "/downloads/lp_snapshot.html"
            }
        }


class InputMetadata(BaseModel):
    """入力メタデータ（どのモードで入力されたか）"""
    mode: InputModeEnum = Field(..., description="入力モード")
    source_type: SourceTypeEnum = Field(..., description="データソース種別")
    input_timestamp: datetime = Field(..., description="入力実行時刻（ISO 8601）")
    file_paths: Optional[FilePaths] = Field(None, description="ローカルファイルパス（ローカル開発用）")
    api_source: Optional[str] = Field(None, description="Meta/Google/TikTok（Phase 2以降）")

    class Config:
        schema_extra = {
            "example": {
                "mode": "file_plus_lp_plus_manual_kpi",
                "source_type": "local_file",
                "input_timestamp": "2026-06-23T14:00:00Z",
                "file_paths": {
                    "creative_video": "/downloads/video.mp4",
                    "creative_images": None,
                    "landing_page_html": "/downloads/lp.html"
                }
            }
        }


# ===== Asset Meta =====

class AnalysisPeriod(BaseModel):
    """分析期間"""
    start: Optional[str] = Field(None, description="ISO 8601 (YYYY-MM-DD)")
    end: Optional[str] = Field(None, description="ISO 8601 (YYYY-MM-DD)")

    @validator('start', 'end')
    def validate_date_format(cls, v):
        """YYYY-MM-DD フォーマット検証"""
        if v is not None:
            try:
                datetime.strptime(v, '%Y-%m-%d')
            except ValueError:
                raise ValueError('Date must be in YYYY-MM-DD format')
        return v


class ExternalIds(BaseModel):
    """外部ID連携用（Phase 2以降）"""
    meta_ad_id: Optional[str] = Field(None, description="Meta Ads ID")
    google_ad_id: Optional[str] = Field(None, description="Google Ads ID")
    tiktok_ad_id: Optional[str] = Field(None, description="TikTok Ads ID")

    class Config:
        extra = "allow"  # 将来の ID 種別に対応


class AssetMeta(BaseModel):
    """素材メタデータ（file-first）"""
    asset_id: str = Field(
        ...,
        description="一意素材ID (asset_platform_hash または asset_YYYYMMDD_HHmmss_platform_uuid)",
        regex=r"^asset_[a-z0-9_]+$"
    )
    asset_name: Optional[str] = Field(None, description="ユーザー指定の素材名", max_length=255)
    platform: Optional[str] = Field(None, description="meta / google / tiktok / unknown")
    ad_account_id: Optional[str] = Field(None, description="Meta Ad Account ID")
    campaign_name: Optional[str] = Field(None, description="キャンペーン名", max_length=255)
    adset_name: Optional[str] = Field(None, description="アドセット名", max_length=255)
    ad_name: Optional[str] = Field(None, description="広告名", max_length=255)
    analysis_period: Optional[AnalysisPeriod] = Field(None, description="分析期間")
    external_ids: Optional[ExternalIds] = Field(None, description="外部ID連携用")

    class Config:
        schema_extra = {
            "example": {
                "asset_id": "asset_20260623_140000_local_summer01",
                "asset_name": "Summer Campaign Video v2",
                "platform": "unknown",
                "campaign_name": "Summer 2026 Promo"
            }
        }


# ===== Creative Core =====

class VisualElements(BaseModel):
    """ビジュアル分析結果"""
    dominant_colors: Optional[List[str]] = Field(None, description="配色分析（#RRGGBB形式）")
    detected_objects: Optional[List[str]] = Field(None, description="画像内物体検出")
    text_overlay_detected: Optional[bool] = Field(None, description="テキストオーバーレイ有無")
    brand_elements: Optional[bool] = Field(None, description="ブランド要素（ロゴ等）有無")

    class Config:
        schema_extra = {
            "example": {
                "dominant_colors": ["#FF6B6B", "#FFFFFF"],
                "detected_objects": ["laptop", "person_working", "checkmark"],
                "text_overlay_detected": True,
                "brand_elements": True
            }
        }


class ToneAndEmotion(BaseModel):
    """トーン・感情分析（LLM判定）"""
    primary_tone: Optional[ToneEnum] = Field(None, description="プライマリトーン")
    detected_emotion: Optional[List[str]] = Field(None, description="検出感情リスト")
    target_audience_inferred: Optional[str] = Field(None, description="推定ターゲット層")

    class Config:
        schema_extra = {
            "example": {
                "primary_tone": "inspirational",
                "detected_emotion": ["excitement", "trust"],
                "target_audience_inferred": "18-35, SaaS entrepreneurs"
            }
        }


class AiLabels(BaseModel):
    """LLMラベリング結果"""
    hook_type: Optional[HookTypeEnum] = Field(None, description="Hook タイプ")
    appeal_type: Optional[str] = Field(None, description="emotional / rational / hybrid")
    identified_pain_points: Optional[List[str]] = Field(None, description="抽出された課題")
    identified_benefits: Optional[List[str]] = Field(None, description="抽出された利点")

    class Config:
        schema_extra = {
            "example": {
                "hook_type": "benefit",
                "appeal_type": "emotional",
                "identified_pain_points": ["time_consuming", "complex_setup"],
                "identified_benefits": ["saves_time", "high_conversion"]
            }
        }


class CreativeCore(BaseModel):
    """素材コンテンツ分析"""
    format: FormatEnum = Field(..., description="クリエイティブフォーマット")
    duration_seconds: Optional[float] = Field(None, description="動画長（秒）")
    primary_text: Optional[str] = Field(None, description="広告文・キャプション")
    headline: Optional[str] = Field(None, description="見出し")
    body_text: Optional[str] = Field(None, description="本文")
    call_to_action: Optional[str] = Field(None, description="CTA")
    visual_elements: Optional[VisualElements] = Field(None, description="ビジュアル分析")
    tone_and_emotion: Optional[ToneAndEmotion] = Field(None, description="トーン・感情分析")
    ai_labels: Optional[AiLabels] = Field(None, description="LLMラベリング")
    platform_specific: Optional[Dict[str, Any]] = Field(None, description="プラットフォーム固有メタ")

    class Config:
        schema_extra = {
            "example": {
                "format": "video_static",
                "duration_seconds": 30,
                "primary_text": "あなたの時間を取り戻す。簡単LP作成で成約率2倍。",
                "headline": "あなたの時間を取り戻す"
            }
        }


# ===== Landing Page =====

class MessageConsistency(BaseModel):
    """メッセージ整合性分析"""
    match_score: Optional[float] = Field(None, description="スコア（0.0～1.0）")
    consistency_basis: Optional[str] = Field(None, description="根拠説明（LLM分析）")
    key_alignment_points: Optional[List[str]] = Field(None, description="一致点リスト")
    mismatch_areas: Optional[List[str]] = Field(None, description="ズレ箇所リスト")
    analyzed_at: Optional[datetime] = Field(None, description="分析時刻")

    @validator('match_score')
    def validate_match_score(cls, v):
        if v is not None and not (0.0 <= v <= 1.0):
            raise ValueError('match_score must be between 0.0 and 1.0')
        return v

    class Config:
        schema_extra = {
            "example": {
                "match_score": 0.92,
                "consistency_basis": "広告文『成約率2倍』とLP『成約率2倍』が完全一致。トーンも統一。",
                "key_alignment_points": ["成約率向上（両方で言及）"],
                "mismatch_areas": []
            }
        }


class LpPageStructure(BaseModel):
    """ページ構成分析"""
    has_hero_section: Optional[bool] = Field(None, description="Hero セクション有無")
    has_social_proof: Optional[bool] = Field(None, description="ソーシャルプルーフ有無")
    has_faq_section: Optional[bool] = Field(None, description="FAQ セクション有無")
    estimated_scroll_depth_for_form: Optional[str] = Field(None, description="above_fold / mid_page / below_fold")


class LandingPage(BaseModel):
    """LP分析（optional）"""
    url: Optional[str] = Field(None, description="LP URL")
    fv_copy: Optional[str] = Field(None, description="FV（First View）コピー")
    fv_headline: Optional[str] = Field(None, description="FV見出し")
    offer: Optional[str] = Field(None, description="オファー内容")
    form_difficulty: Optional[FormDifficultyEnum] = Field(None, description="フォーム難易度")
    form_field_count: Optional[int] = Field(None, description="フォーム項目数")
    cta_button_text: Optional[str] = Field(None, description="CTAボタンテキスト")
    message_consistency: Optional[MessageConsistency] = Field(None, description="メッセージ整合性分析")
    lp_page_structure: Optional[LpPageStructure] = Field(None, description="ページ構成分析")

    class Config:
        schema_extra = {
            "example": {
                "url": "https://example.com/lp/summer-promo",
                "fv_copy": "簡単LP作成ツール。2分で成約率2倍のLPが作れる。",
                "offer": "30日間無料トライアル"
            }
        }


# ===== Performance =====

class Performance(BaseModel):
    """KPI（optional、mode依存）"""
    impressions: Optional[int] = Field(None, description="インプレッション数", ge=0)
    clicks: Optional[int] = Field(None, description="クリック数", ge=0)
    ctr: Optional[float] = Field(None, description="CTR (0.0～1.0)", ge=0.0, le=1.0)
    spend: Optional[float] = Field(None, description="広告費（通貨単位）", ge=0.0)
    conversions: Optional[int] = Field(None, description="コンバージョン数", ge=0)
    conversion_value: Optional[float] = Field(None, description="総売上等", ge=0.0)
    cpa: Optional[float] = Field(None, description="顧客獲得単価", ge=0.0)
    cvr: Optional[float] = Field(None, description="CVR (0.0～1.0)", ge=0.0, le=1.0)
    roas: Optional[float] = Field(None, description="ROAS (sell/spend)", ge=0.0)
    reach: Optional[int] = Field(None, description="リーチ数", ge=0)
    frequency: Optional[float] = Field(None, description="平均フリーケンシー", ge=0.0)

    @root_validator
    def calculate_metrics(cls, values):
        """KPIから自動計算可能なメトリクスを補完"""
        impressions = values.get('impressions')
        clicks = values.get('clicks')
        conversions = values.get('conversions')
        spend = values.get('spend')
        conversion_value = values.get('conversion_value')
        reach = values.get('reach')

        # CTR自動計算
        if values.get('ctr') is None and impressions and clicks and impressions > 0:
            values['ctr'] = clicks / impressions

        # CVR自動計算
        if values.get('cvr') is None and clicks and conversions and clicks > 0:
            values['cvr'] = conversions / clicks

        # CPA自動計算
        if values.get('cpa') is None and spend and conversions and conversions > 0:
            values['cpa'] = spend / conversions

        # ROAS自動計算
        if values.get('roas') is None and conversion_value and spend and spend > 0:
            values['roas'] = conversion_value / spend

        # Frequency自動計算
        if values.get('frequency') is None and impressions and reach and reach > 0:
            values['frequency'] = impressions / reach

        return values

    class Config:
        schema_extra = {
            "example": {
                "impressions": 45000,
                "clicks": 1350,
                "ctr": 0.03,
                "spend": 180000,
                "conversions": 45,
                "cpa": 4000,
                "cvr": 0.0333,
                "roas": 2.5
            }
        }


# ===== Diagnostics =====

class QualitativeDiagnostics(BaseModel):
    """定性診断（KPI不要）"""
    creative_fatigue_risk: RiskLevelEnum = Field(..., description="Creative Fatigue リスク")
    creative_fatigue_basis: str = Field(..., description="根拠説明")
    creative_fatigue_indicators: Optional[List[str]] = Field(None, description="リスク指標")
    message_clarity_score: Optional[float] = Field(None, description="メッセージ明確性（0.0～1.0）")
    message_clarity_basis: Optional[str] = Field(None, description="根拠説明")
    lp_message_match_risk: Optional[RiskLevelEnum] = Field(None, description="LP 整合性リスク")
    lp_message_match_basis: Optional[str] = Field(None, description="根拠説明")
    form_usability_concern: Optional[RiskLevelEnum] = Field(None, description="フォーム難易度評価")
    form_usability_basis: Optional[str] = Field(None, description="根拠説明")
    audience_relevance_concern: Optional[RiskLevelEnum] = Field(None, description="ターゲット適合度")
    audience_relevance_basis: Optional[str] = Field(None, description="根拠説明")
    recommended_creative_improvements: Optional[List[str]] = Field(None, description="改善案リスト")

    @validator('message_clarity_score')
    def validate_clarity_score(cls, v):
        if v is not None and not (0.0 <= v <= 1.0):
            raise ValueError('message_clarity_score must be between 0.0 and 1.0')
        return v

    class Config:
        schema_extra = {
            "example": {
                "creative_fatigue_risk": "low",
                "creative_fatigue_basis": "フック『成約率2倍』は具体的で新規性あり。",
                "message_clarity_score": 0.95
            }
        }


class QuantitativeDiagnostics(BaseModel):
    """定量診断（KPI必須）"""
    performance_status: Optional[PerformanceStatusEnum] = Field(None, description="パフォーマンスステータス")
    performance_status_basis: Optional[str] = Field(None, description="根拠説明")
    ctr_assessment: Optional[PerformanceStatusEnum] = Field(None, description="CTR評価")
    ctr_benchmark_comparison: Optional[str] = Field(None, description="ベンチマーク比較")
    cvr_assessment: Optional[PerformanceStatusEnum] = Field(None, description="CVR評価")
    cvr_benchmark_comparison: Optional[str] = Field(None, description="ベンチマーク比較")
    roas_assessment: Optional[PerformanceStatusEnum] = Field(None, description="ROAS評価")
    roas_benchmark_comparison: Optional[str] = Field(None, description="ベンチマーク比較")
    efficiency_score: Optional[float] = Field(None, description="効率スコア（0.0～1.0）")
    recommended_optimizations: Optional[List[str]] = Field(None, description="最適化提案リスト")

    @validator('efficiency_score')
    def validate_efficiency_score(cls, v):
        if v is not None and not (0.0 <= v <= 1.0):
            raise ValueError('efficiency_score must be between 0.0 and 1.0')
        return v

    class Config:
        schema_extra = {
            "example": {
                "performance_status": "excellent",
                "ctr_assessment": "excellent",
                "efficiency_score": 0.91
            }
        }


class Diagnostics(BaseModel):
    """診断結果（定性+定量）"""
    qualitative: QualitativeDiagnostics = Field(..., description="定性診断")
    quantitative: Optional[QuantitativeDiagnostics] = Field(None, description="定量診断（KPI入力時のみ）")


# ===== Views =====

class DashboardSummary(BaseModel):
    """ダッシュボード表示用"""
    status_label: Optional[str] = Field(None, description="Excellent / Good / Fair / Poor")
    key_metric_highlight: Optional[str] = Field(None, description="主要成果を1行で")
    status_color: Optional[str] = Field(None, description="16進数カラーコード（#RRGGBB）")


class RecommendedAction(BaseModel):
    """推奨アクション"""
    priority: Optional[str] = Field(None, description="high / medium / low")
    action: Optional[str] = Field(None, description="改善案テキスト")
    expected_impact: Optional[str] = Field(None, description="期待される改善効果")


class Views(BaseModel):
    """UI表示用（生成版）"""
    dashboard_summary: Optional[DashboardSummary] = Field(None)
    performance_ranking: Optional[str] = Field(None, description="Top 10% / Average / Bottom 30%")
    trend_indicator: Optional[str] = Field(None, description="+15% / -58%")
    creative_fatigue_visual: Optional[str] = Field(None, description="● Low / ◐ Medium / ◯ High")
    lp_match_visual: Optional[str] = Field(None, description="✓ Aligned / ⚠ Partial / ✗ Misaligned")
    recommended_actions_display: Optional[List[RecommendedAction]] = Field(None)


# ===== Metadata =====

class AnalysisToolsUsed(BaseModel):
    """使用したツール・ライブラリ"""
    ocr_engine: Optional[str] = Field(None, description="tesseract / google_vision / aws_textract")
    video_frame_extractor: Optional[str] = Field(None, description="opencv / ffmpeg")
    web_scraper: Optional[str] = Field(None, description="beautifulsoup / selenium")

    class Config:
        extra = "allow"  # 将来のツール追加に対応


class Metadata(BaseModel):
    """スキーマ・ツールバージョン"""
    generated_at: datetime = Field(..., description="生成時刻（ISO 8601）")
    data_source: str = Field(..., description="meta_api / google_api / tiktok_api / local_file / hybrid")
    ai_model_version: str = Field(..., description="gemini-2.0-flash / gpt-4o / claude-opus / other")
    json_schema_version: str = Field(default="v0.2", description="JSON スキーマバージョン")
    input_mode: InputModeEnum = Field(..., description="入力モード")
    analysis_tools_used: Optional[AnalysisToolsUsed] = Field(None)
    processing_time_ms: Optional[int] = Field(None, description="処理時間（ミリ秒）")
    validation_status: Optional[str] = Field(None, description="passed / warnings / failed")
    validation_notes: Optional[List[str]] = Field(None, description="バリデーション時のメモ")

    class Config:
        schema_extra = {
            "example": {
                "generated_at": "2026-06-23T14:35:00Z",
                "data_source": "local_file",
                "ai_model_version": "gemini-2.0-flash",
                "input_mode": "file_plus_lp_plus_manual_kpi"
            }
        }


# ===== Main Ad Insight Spec =====

class AdInsightSpec(BaseModel):
    """Ad-Insight-Spec v0.2（完全版）"""
    input_metadata: InputMetadata = Field(..., description="入力メタデータ")
    asset_meta: AssetMeta = Field(..., description="素材メタデータ")
    creative_core: CreativeCore = Field(..., description="素材コンテンツ分析")
    landing_page: Optional[LandingPage] = Field(None, description="LP分析（optional）")
    performance: Optional[Performance] = Field(None, description="KPI（optional）")
    diagnostics: Diagnostics = Field(..., description="診断結果")
    views: Optional[Views] = Field(None, description="UI表示用")
    metadata: Metadata = Field(..., alias="_metadata", description="スキーマ・バージョン情報")

    @root_validator
    def validate_mode_requirements(cls, values):
        """入力モードに応じた必須フィールドバリデーション"""
        input_metadata = values.get('input_metadata')
        landing_page = values.get('landing_page')
        performance = values.get('performance')

        if input_metadata:
            mode = input_metadata.mode

            # file_only: landing_page と performance は null
            if mode == InputModeEnum.FILE_ONLY:
                if landing_page is not None:
                    raise ValueError("landing_page must be null in file_only mode")
                if performance is not None:
                    raise ValueError("performance must be null in file_only mode")

            # file_plus_lp: performance は null
            elif mode == InputModeEnum.FILE_PLUS_LP:
                if landing_page is None:
                    raise ValueError("landing_page is required in file_plus_lp mode")
                if performance is not None:
                    raise ValueError("performance must be null in file_plus_lp mode")

            # file_plus_lp_plus_manual_kpi: 全て必須
            elif mode == InputModeEnum.FILE_PLUS_LP_PLUS_MANUAL_KPI:
                if landing_page is None:
                    raise ValueError("landing_page is required in file_plus_lp_plus_manual_kpi mode")
                if performance is None:
                    raise ValueError("performance is required in file_plus_lp_plus_manual_kpi mode")

        return values

    class Config:
        schema_extra = {
            "title": "Ad-Insight-Spec v0.2",
            "description": "Comprehensive ad creative and landing page diagnostic specification",
            "examples": [
                {
                    "input_metadata": {"mode": "file_only"},
                    "asset_meta": {"asset_id": "asset_..."},
                    "creative_core": {"format": "video_static"}
                }
            ]
        }


# ===== Simplified Models for Input =====

class AdInsightCreate(BaseModel):
    """入力時の簡略版（API エンドポイント用）"""
    input_metadata: InputMetadata
    asset_meta: AssetMeta
    creative_core: CreativeCore
    landing_page: Optional[LandingPage] = None
    performance: Optional[Performance] = None


class AdInsightUpdate(BaseModel):
    """更新用（一部フィールドのみ）"""
    diagnostics: Optional[Diagnostics] = None
    views: Optional[Views] = None


# ===== Batch Models =====

class AdInsightSpecList(BaseModel):
    """複数件リスト"""
    items: List[AdInsightSpec]
    total_count: int
    page: int
    page_size: int
