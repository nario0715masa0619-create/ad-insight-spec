import json
from datetime import datetime

import pytest
from pydantic.v1 import ValidationError

from app.schemas.asset_v0 import (
    AssetJsonV0,
    AssetMetaV0,
    MediaInfoV0,
    AssetStructureV0,
    AssetAnnotationsV0,
    CutSpan,
    TranscriptSegment,
    OcrSegment,
    CtaCandidate,
    CtaModalityEnum,
)
from app.schemas.evaluation_v0 import EvaluationJsonV0, EvaluationMetaV0
from app.schemas.ad_insight import SourceTypeEnum, FormatEnum


def _make_asset_meta_v0(**overrides) -> AssetMetaV0:
    data = {
        "asset_id": "asset_meta_test_0001",
        "asset_name": "テスト素材",
        "platform": "meta",
        "campaign_name": "テストキャンペーン",
        "adset_name": "テストアドセット",
        "ad_name": "テスト広告",
        "source_type": SourceTypeEnum.LOCAL_FILE,
        "source_ref": "/tmp/input.mp4",
        "created_at": datetime(2026, 7, 9, 12, 0, 0),
    }
    data.update(overrides)
    return AssetMetaV0(**data)


class TestAssetMetaV0SupersetOfLegacy:
    """オープン課題1の解決: AssetMetaV0はlegacy AssetMetaの全フィールドを持つスーパーセット"""

    def test_legacy_fields_are_all_accepted(self):
        meta = _make_asset_meta_v0()
        assert meta.platform == "meta"
        assert meta.campaign_name == "テストキャンペーン"
        assert meta.adset_name == "テストアドセット"
        assert meta.ad_name == "テスト広告"

    def test_legacy_fields_are_optional_like_legacy_asset_meta(self):
        meta = _make_asset_meta_v0(platform=None, campaign_name=None, adset_name=None, ad_name=None)
        assert meta.platform is None

    def test_v0_only_fields_required(self):
        with pytest.raises(ValidationError):
            AssetMetaV0(asset_id="asset_meta_test_0002")

    def test_invalid_asset_id_format_rejected(self):
        with pytest.raises(ValidationError):
            _make_asset_meta_v0(asset_id="not-a-valid-id")


class TestAssetJsonV0Construction:
    def test_full_asset_json_v0_construction(self):
        asset = AssetJsonV0(
            asset_meta=_make_asset_meta_v0(),
            media_info=MediaInfoV0(
                media_type=FormatEnum.VIDEO_STATIC,
                duration_seconds=15.9,
                width=1080,
                height=1920,
            ),
            asset_structure=AssetStructureV0(
                cuts=[CutSpan(cut_id="cut_1", start_sec=0.0, end_sec=5.0)],
                transcript_segments=[TranscriptSegment(text="こんにちは", start_sec=0.0, end_sec=2.0)],
                ocr_segments=[OcrSegment(text="今だけ限定", start_sec=0.0, end_sec=5.0)],
            ),
            asset_annotations=AssetAnnotationsV0(
                brand_mentions=["ブランドA"],
                cta_candidates=[CtaCandidate(text="今すぐ購入", modality=CtaModalityEnum.VISUAL)],
                people_presence=True,
            ),
        )
        assert asset.asset_meta.asset_id == "asset_meta_test_0001"
        assert asset.asset_structure.cuts[0].cut_id == "cut_1"

    def test_empty_asset_structure_lists_default_to_empty(self):
        structure = AssetStructureV0()
        assert structure.cuts == []
        assert structure.transcript_segments == []
        assert structure.ocr_segments == []


class TestDatetimeJsonSerializationFootgun:
    """
    既知バグ回帰テスト: AssetMetaV0.created_at等のdatetimeフィールドは、
    Pydantic v1で `.dict()` を直接使うと `TypeError: Object of type datetime
    is not JSON serializable` になる（本セッション中に実際に2回踏んだバグと
    同一パターン）。`json.loads(model.json())` を使えば安全にJSON化できる
    ことをここで固定する。
    """

    def test_dict_then_json_dumps_raises_typeerror(self):
        meta = _make_asset_meta_v0()
        with pytest.raises(TypeError):
            json.dumps(meta.dict())

    def test_model_json_then_loads_is_safe(self):
        meta = _make_asset_meta_v0()
        result = json.loads(meta.json())
        assert result["created_at"] == "2026-07-09T12:00:00"
        assert result["asset_id"] == "asset_meta_test_0001"


class TestEvaluationJsonV0Construction:
    """EvaluationJsonV0が既存のDiagnostics/Performance/LandingPage型をそのまま再利用できること"""

    def test_construction_with_minimal_diagnostics(self):
        evaluation = EvaluationJsonV0(
            evaluation_meta=EvaluationMetaV0(
                evaluated_at=datetime(2026, 7, 9, 12, 30, 0),
                evaluator_model="gpt-4o",
            ),
            diagnostics={
                "qualitative": {
                    "creative_fatigue_risk": "low",
                    "creative_fatigue_basis": "テスト用の根拠テキストです",
                }
            },
        )
        assert evaluation.evaluation_meta.evaluator_model == "gpt-4o"
        assert evaluation.diagnostics.qualitative.creative_fatigue_risk == "low"
        assert evaluation.performance is None
        assert evaluation.landing_page_analysis is None

    def test_evaluated_at_json_serialization_is_safe(self):
        evaluation_meta = EvaluationMetaV0(
            evaluated_at=datetime(2026, 7, 9, 12, 30, 0),
            evaluator_model="gpt-4o",
        )
        result = json.loads(evaluation_meta.json())
        assert result["evaluated_at"] == "2026-07-09T12:30:00"
