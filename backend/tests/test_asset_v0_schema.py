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
from app.schemas.ad_insight import SourceTypeEnum, FormatEnum, InputModeEnum, FilePaths
from app.schemas.llm_response import CreativeCoreSchema, VisualsSchema, ToneSchema


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
        "mode": InputModeEnum.FILE_ONLY,
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


class TestAssetMetaV0Phase2Batch2Fields:
    """Phase 2 downcastバッチ2で追加した mode/file_paths フィールド
    （docs/plans/asset_evaluation_split_phase2_tasks.md「🗂 6項目の保存方針比較」）"""

    def test_mode_is_required(self):
        with pytest.raises(ValidationError):
            _make_asset_meta_v0(mode=None)

    def test_mode_accepts_existing_enum(self):
        meta = _make_asset_meta_v0(mode=InputModeEnum.FILE_PLUS_LP_PLUS_MANUAL_KPI)
        assert meta.mode == InputModeEnum.FILE_PLUS_LP_PLUS_MANUAL_KPI

    def test_file_paths_is_optional(self):
        meta = _make_asset_meta_v0()
        assert meta.file_paths is None

    def test_file_paths_accepts_existing_type(self):
        meta = _make_asset_meta_v0(
            file_paths=FilePaths(creative_video="/tmp/input.mp4", creative_images=None, landing_page_html=None)
        )
        assert meta.file_paths.creative_video == "/tmp/input.mp4"

    def test_source_ref_and_file_paths_can_coexist(self):
        """source_refとfile_pathsは意図的に別役割として両方持てる
        （asset_v0.pyモジュールdocstring参照）"""
        meta = _make_asset_meta_v0(
            source_ref="/tmp/input.mp4",
            file_paths=FilePaths(creative_video="/tmp/input.mp4", creative_images=None, landing_page_html=None),
        )
        assert meta.source_ref == "/tmp/input.mp4"
        assert meta.file_paths.creative_video == "/tmp/input.mp4"


class TestAssetStructureV0OcrExtractedText:
    """Phase 2 downcastバッチ2で追加した ocr_extracted_text フィールド。
    ocr_segments（カット単位OCR）とは別データであることを固定する。"""

    def test_defaults_to_empty_string(self):
        structure = AssetStructureV0()
        assert structure.ocr_extracted_text == ""

    def test_independent_from_ocr_segments(self):
        structure = AssetStructureV0(
            ocr_segments=[OcrSegment(text="カット単位のOCR", start_sec=0.0, end_sec=5.0)],
            ocr_extracted_text="動画全体の単一OCRパス結果",
        )
        assert structure.ocr_segments[0].text == "カット単位のOCR"
        assert structure.ocr_extracted_text == "動画全体の単一OCRパス結果"
        assert structure.ocr_extracted_text != structure.ocr_segments[0].text


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


class TestEvaluationJsonV0CreativeCore:
    """Phase 2 downcastバッチ2で追加した creative_core フィールド
    （llm_response.CreativeCoreSchemaをそのまま再利用、新規型は作らない）"""

    def _make_evaluation(self, **overrides):
        data = {
            "evaluation_meta": EvaluationMetaV0(
                evaluated_at=datetime(2026, 7, 9, 12, 30, 0),
                evaluator_model="gpt-4o",
            ),
            "diagnostics": {
                "qualitative": {
                    "creative_fatigue_risk": "low",
                    "creative_fatigue_basis": "テスト用の根拠テキストです",
                }
            },
        }
        data.update(overrides)
        return EvaluationJsonV0(**data)

    def test_creative_core_defaults_to_none(self):
        evaluation = self._make_evaluation()
        assert evaluation.creative_core is None

    def test_creative_core_accepts_existing_llm_response_type(self):
        evaluation = self._make_evaluation(
            creative_core=CreativeCoreSchema(
                visuals=VisualsSchema(
                    dominant_colors=["#FF6B6B", "#FFFFFF"],
                    composition="中央寄せの構図",
                    style="モダン",
                    clarity="高",
                ),
                tone=ToneSchema(
                    primary_tone=["professional"],
                    emotional_appeal="論理的",
                    call_to_action="強",
                ),
                ai_labels=["finance", "trust"],
            )
        )
        assert evaluation.creative_core.visuals.clarity == "高"
        assert evaluation.creative_core.tone.emotional_appeal == "論理的"
        assert evaluation.creative_core.ai_labels == ["finance", "trust"]
