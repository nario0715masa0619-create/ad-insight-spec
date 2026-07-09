"""
asset_data (v0) スキーマ — Phase 1（DBカラム追加 + v0スキーマ導入）。

`AdInsight.asset_data`（nullable JSON、backend/app/models/ad_insight.py）に
将来格納される「観測事実」ブロックの形状を定義する。現時点ではこのスキーマを
使って実際にデータを生成・保存するコードは無い（dual-writeはPhase 3）。
Phase 2の read adapter（backend/app/services/asset_evaluation_adapter.py）が
将来この形状から legacy `spec_data` を再構築する際の変換元になる。

設計はAntigravity側のローカルPoC（`AssetJsonV0`/`AssetMetaV0`等、
feature/asset-evaluation-split-phase1、未push・非公式）のレビューを踏まえつつ、
そのレビューで見つかった問題を修正して再設計したもの
（docs/plans/asset_evaluation_split_phase2_tasks.md の「オープン課題」参照）:

- オープン課題1（asset_meta名称衝突）: `AssetMetaV0` は
  `app.schemas.ad_insight.AssetMeta`（"legacy asset_meta"、spec_data.asset_meta）
  とは別クラスだが、legacy側の全フィールドを包含するスーパーセットとして設計した。
  将来のdowncastは欠落フィールドのnull埋めが不要になり、単純な転記で済む。
  "legacy asset_meta"（spec_data側）と"v0 asset_meta"（asset_data側、本ファイル）
  は別概念として明確に呼び分ける。
- オープン課題2（カット情報の一次情報源）: `AssetStructureV0.cuts`
  （`CutSpan.start_sec`/`end_sec`）を唯一の時間情報の正本とする。
  evaluation_data側（evaluation_v0.py）のvideo_cutsは既存の`VideoCutContent`を
  再利用し、start_seconds/end_secondsは定義しない（既存スキーマ通りOptionalのまま）。
  将来のdowncastで、cut_idをキーにこちらの値を補完する。
- `media_type` は独自enumを新設せず、既存の `FormatEnum`
  （app.schemas.ad_insight、creative_core.format と同じ語彙）をそのまま再利用する。
  これにより「video→video_static のマッピングを別途定義する」という
  Phase 2設計docの未決事項が不要になる。

既知の落とし穴（本セッション中に実際に2回踏んだ既知バグ）:
`AssetMetaV0.created_at` は `datetime` 型のため、Pydantic v1で `.dict()` を
直接使うと `TypeError: Object of type datetime is not JSON serializable` で
失敗する。DBに保存する際は必ず `json.loads(model.json())` を経由すること
（実際に保存するコードはPhase 3のdual-write実装時に書かれる）。
"""
from typing import List, Optional
from datetime import datetime
from enum import Enum

from pydantic.v1 import BaseModel, Field

from app.schemas.ad_insight import AnalysisPeriod, ExternalIds, SourceTypeEnum, FormatEnum


# ===== v0 asset_meta（"legacy asset_meta" のスーパーセット） =====

class AssetMetaV0(BaseModel):
    """
    asset_data.asset_meta（"v0 asset_meta"）。

    legacy `AssetMeta`（spec_data.asset_meta）の全フィールドに加え、
    ingestion（取り込み）時にしか分からない情報を追加で持つ。
    """
    # ----- legacy AssetMeta と同一のフィールド（そのまま転記可能にする） -----
    asset_id: str = Field(
        ...,
        description="一意素材ID（legacy asset_meta.asset_idと同一値）",
        regex=r"^asset_[a-z0-9_]+$",
    )
    asset_name: Optional[str] = Field(None, max_length=255)
    platform: Optional[str] = Field(None, description="meta / google / tiktok / unknown")
    ad_account_id: Optional[str] = Field(None)
    campaign_name: Optional[str] = Field(None, max_length=255)
    adset_name: Optional[str] = Field(None, max_length=255)
    ad_name: Optional[str] = Field(None, max_length=255)
    analysis_period: Optional[AnalysisPeriod] = Field(None)
    external_ids: Optional[ExternalIds] = Field(None)

    # ----- v0で新規追加（取り込み時点の情報） -----
    source_type: SourceTypeEnum = Field(..., description="local_file / api / hybrid")
    source_ref: Optional[str] = Field(
        None, description="元ファイルパスや外部APIレスポンスIDなど、取り込み元への参照"
    )
    created_at: datetime = Field(..., description="asset_data生成時刻（ISO 8601）")
    analysis_version: str = Field(default="v0", description="asset_data生成ロジックのバージョン")


# ===== media_info =====

class MediaInfoV0(BaseModel):
    """asset_data.media_info"""
    media_type: FormatEnum = Field(..., description="既存creative_core.formatと同一語彙")
    duration_seconds: Optional[float] = Field(None, description="動画長（秒）。画像の場合はNone")
    width: Optional[int] = Field(None)
    height: Optional[int] = Field(None)
    fps: Optional[float] = Field(None)
    aspect_ratio: Optional[str] = Field(None, description="例: 9:16, 1:1, 16:9")
    language: Optional[str] = Field(None, description="主言語（ja / en 等）")


# ===== asset_structure =====

class CutSpan(BaseModel):
    """カットの時間範囲。asset_structure.cutsの唯一の正本（オープン課題2の解決）"""
    cut_id: str = Field(...)
    start_sec: float = Field(..., ge=0)
    end_sec: float = Field(..., ge=0)


class TranscriptSegment(BaseModel):
    """ASR文字起こし結果の1区間"""
    text: str = Field(...)
    start_sec: float = Field(..., ge=0)
    end_sec: float = Field(..., ge=0)


class OcrSegment(BaseModel):
    """OCR検出結果の1区間"""
    text: str = Field(...)
    start_sec: float = Field(..., ge=0)
    end_sec: float = Field(..., ge=0)


class AssetStructureV0(BaseModel):
    """asset_data.asset_structure"""
    cuts: List[CutSpan] = Field(default_factory=list)
    transcript_segments: List[TranscriptSegment] = Field(default_factory=list)
    ocr_segments: List[OcrSegment] = Field(default_factory=list)


# ===== asset_annotations =====

class CtaModalityEnum(str, Enum):
    VISUAL = "visual"
    AUDIO = "audio"
    BOTH = "both"


class CtaCandidate(BaseModel):
    """CTA候補（画面上テキスト or 発話のいずれかで検出されたCTA表現）"""
    text: str = Field(...)
    modality: CtaModalityEnum = Field(...)


class AssetAnnotationsV0(BaseModel):
    """asset_data.asset_annotations"""
    brand_mentions: List[str] = Field(default_factory=list)
    product_mentions: List[str] = Field(default_factory=list)
    cta_candidates: List[CtaCandidate] = Field(default_factory=list)
    people_presence: Optional[bool] = Field(None)
    voiceover_presence: Optional[bool] = Field(None)
    subtitle_presence: Optional[bool] = Field(None)


# ===== asset_data 全体 =====

class AssetJsonV0(BaseModel):
    """AdInsight.asset_data に格納される全体構造"""
    asset_meta: AssetMetaV0
    media_info: MediaInfoV0
    asset_structure: AssetStructureV0
    asset_annotations: AssetAnnotationsV0
