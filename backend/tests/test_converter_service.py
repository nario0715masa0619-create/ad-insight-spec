"""
ConverterService の asset_data (AssetJsonV0) / evaluation_data (EvaluationJsonV0)
生成ロジックのテスト（Phase 2 P1: 生成ロジック実装、DB保存挙動は対象外）。

spec_data（既存のad_insight_spec v0.2）の生成・検証は変更していないため、
ここでは新規追加した asset_data/evaluation_data の組み立てに絞ってテストする。
"""
import json

import pytest

from app.services.converter_service import ConverterService


def _video_ingestion_result(file_path="/tmp/input.mp4"):
    return {"format": "video_static", "file_path": file_path}


def _image_ingestion_result(file_path="/tmp/input.png"):
    return {"format": "image_static", "file_path": file_path}


def _video_metadata_result(**overrides):
    data = {
        "asset_id": "asset_test_conv_0001",
        "asset_name": "Test Ad",
        "duration_seconds": 15.5,
        "resolution": "1080x1920",
        "fps": 30.0,
    }
    data.update(overrides)
    return data


def _lp_result():
    return {
        "url": "https://example.com/lp",
        "fv_copy": "LPコピー",
        "fv_headline": "見出し",
        "offer": "特別オファー",
        "form_fields_count": 3,
        "primary_cta": "今すぐ購入",
        "has_hero_section": True,
        "has_social_proof": True,
        "has_faq_section": False,
        "estimated_scroll_depth_for_form": 0.5,
    }


def _ocr_result():
    return {"success": True, "ocr_extracted_text": "画面上のテキスト", "confidence": 0.9}


def _llm_result(**creative_core_overrides):
    creative_core = {
        "visuals": {"dominant_colors": ["#000000"]},
        "tone": {"primary_tone": ["professional"]},
        "ai_labels": ["finance"],
        "llm_model": "gpt-4o",
        "llm_success": True,
        "llm_retry_count": 0,
        "llm_error": None,
    }
    creative_core.update(creative_core_overrides)
    return {
        "creative_core": creative_core,
        "recommendations": ["改善案1"],
        "video_cuts": None,
        "improvements": None,
        "improvements_error": None,
        "decision_support": None,
        "decision_support_error": None,
    }


def _kpi_result():
    return {
        "impressions": 1000,
        "clicks": 50,
        "conversions": 5,
        "spend": 10000.0,
        "conversion_value": 50000.0,
        "reach": 800,
    }


def _video_cuts():
    return [
        {
            "cut_id": "cut_1",
            "start_seconds": 0.0,
            "end_seconds": 5.0,
            "frame_path": "/tmp/f1.jpg",
            "ocr_text": "今だけ限定",
        },
        {
            "cut_id": "cut_2",
            "start_seconds": 5.0,
            "end_seconds": 10.0,
            "frame_path": "/tmp/f2.jpg",
            "ocr_text": "",
        },
    ]


class TestAssetDataEvaluationDataGeneration:
    """フル入力（file_plus_lp_plus_manual_kpi, video）で asset_data/evaluation_data が生成されること"""

    def _run(self):
        service = ConverterService()
        return service.execute(
            mode="file_plus_lp_plus_manual_kpi",
            ingestion_result=_video_ingestion_result(),
            metadata_result=_video_metadata_result(),
            lp_result=_lp_result(),
            video_result={},
            ocr_result=_ocr_result(),
            llm_result=_llm_result(),
            kpi_result=_kpi_result(),
            video_cuts=_video_cuts(),
        )

    def test_spec_data_still_produced_unchanged(self):
        result = self._run()
        assert result["asset_meta"]["asset_id"] == "asset_test_conv_0001"
        assert result["creative_core"]["format"] == "video_static"

    def test_asset_data_present_with_expected_shape(self):
        result = self._run()
        asset_data = result["asset_data"]
        assert asset_data is not None
        assert asset_data["asset_meta"]["asset_id"] == "asset_test_conv_0001"
        assert asset_data["asset_meta"]["source_type"] == "local_file"
        assert asset_data["asset_meta"]["source_ref"] == "/tmp/input.mp4"
        assert asset_data["asset_meta"]["analysis_version"] == "v0"
        assert asset_data["media_info"]["media_type"] == "video_static"
        assert asset_data["media_info"]["duration_seconds"] == 15.5
        assert asset_data["media_info"]["width"] == 1080
        assert asset_data["media_info"]["height"] == 1920
        assert asset_data["media_info"]["fps"] == 30.0

    def test_asset_structure_cuts_derived_from_video_cuts(self):
        result = self._run()
        cuts = result["asset_data"]["asset_structure"]["cuts"]
        assert len(cuts) == 2
        assert cuts[0] == {"cut_id": "cut_1", "start_sec": 0.0, "end_sec": 5.0}
        assert cuts[1] == {"cut_id": "cut_2", "start_sec": 5.0, "end_sec": 10.0}

    def test_ocr_segments_only_include_cuts_with_nonempty_text(self):
        result = self._run()
        ocr_segments = result["asset_data"]["asset_structure"]["ocr_segments"]
        assert len(ocr_segments) == 1
        assert ocr_segments[0]["text"] == "今だけ限定"
        assert ocr_segments[0]["start_sec"] == 0.0
        assert ocr_segments[0]["end_sec"] == 5.0

    def test_transcript_segments_stay_empty_no_fabrication(self):
        """ASRはセグメント単位タイムスタンプを保持していないため、捏造せず空のまま"""
        result = self._run()
        assert result["asset_data"]["asset_structure"]["transcript_segments"] == []

    def test_asset_annotations_stay_default_no_fabrication(self):
        """brand/product/cta等は現行パイプラインで honest に検出できないため、デフォルトのまま"""
        annotations = self._run()["asset_data"]["asset_annotations"]
        assert annotations["brand_mentions"] == []
        assert annotations["product_mentions"] == []
        assert annotations["cta_candidates"] == []
        assert annotations["people_presence"] is None

    def test_evaluation_data_present_with_expected_shape(self):
        result = self._run()
        evaluation_data = result["evaluation_data"]
        assert evaluation_data is not None
        assert evaluation_data["evaluation_meta"]["evaluator_model"] == "gpt-4o"
        # _step_converter単体ではまだ実測処理時間が確定していないため0
        # （AnalysisOrchestrator.run()完了後にevaluation_meta.processing_time_msも
        # _metadata.processing_time_msと同じタイミングで上書きされる）
        assert evaluation_data["evaluation_meta"]["processing_time_ms"] == 0

    def test_evaluation_data_reuses_validated_diagnostics_performance_landing_page(self):
        result = self._run()
        evaluation_data = result["evaluation_data"]
        assert evaluation_data["diagnostics"] == result["diagnostics"]
        assert evaluation_data["performance"] == result["performance"]
        assert evaluation_data["landing_page_analysis"] == result["landing_page"]

    def test_asset_data_and_evaluation_data_are_json_serializable(self):
        """既知バグ回帰: datetimeフィールドを含むため、json.dumpsでこけないこと
        （_build_asset_evaluation_v0内部でjson.loads(model.json())を経由している）"""
        result = self._run()
        json.dumps(result["asset_data"])
        json.dumps(result["evaluation_data"])


class TestFileOnlyModeAssetEvaluationData:
    """file_onlyモード（landing_page/performanceがNone必須）でも asset_data/evaluation_data が生成されること"""

    def _run(self):
        service = ConverterService()
        return service.execute(
            mode="file_only",
            ingestion_result=_image_ingestion_result(),
            metadata_result={
                "asset_id": "asset_test_conv_0002",
                "width_pixels": 600,
                "height_pixels": 800,
            },
            lp_result=None,
            video_result={},
            ocr_result=_ocr_result(),
            llm_result=_llm_result(),
            kpi_result=None,
            video_cuts=None,
        )

    def test_asset_data_generated_for_image(self):
        result = self._run()
        assert result["asset_data"]["media_info"]["media_type"] == "image_static"
        assert result["asset_data"]["media_info"]["width"] == 600
        assert result["asset_data"]["media_info"]["height"] == 800
        assert result["asset_data"]["asset_structure"]["cuts"] == []
        assert result["asset_data"]["asset_structure"]["ocr_segments"] == []

    def test_evaluation_data_performance_and_landing_page_are_none(self):
        result = self._run()
        assert result["evaluation_data"]["performance"] is None
        assert result["evaluation_data"]["landing_page_analysis"] is None


class TestDimensionParsing:
    def test_prefers_width_height_pixels_when_present(self):
        service = ConverterService()
        width, height = service._parse_dimensions({"width_pixels": 100, "height_pixels": 200, "resolution": "9x9"})
        assert (width, height) == (100, 200)

    def test_falls_back_to_resolution_string(self):
        service = ConverterService()
        width, height = service._parse_dimensions({"resolution": "1920x1080"})
        assert (width, height) == (1920, 1080)

    def test_returns_none_when_unavailable(self):
        service = ConverterService()
        width, height = service._parse_dimensions({})
        assert (width, height) == (None, None)

    def test_returns_none_on_malformed_resolution(self):
        service = ConverterService()
        width, height = service._parse_dimensions({"resolution": "not-a-resolution"})
        assert (width, height) == (None, None)


class TestFailSoftGeneration:
    """asset_data/evaluation_data の生成失敗はspec_dataの返却をブロックしない"""

    def test_generation_failure_leaves_spec_data_intact(self, monkeypatch):
        service = ConverterService()

        def _boom(self, **kwargs):
            raise RuntimeError("synthetic failure")

        monkeypatch.setattr(ConverterService, "_build_asset_evaluation_v0", _boom)

        result = service.execute(
            mode="file_only",
            ingestion_result=_image_ingestion_result(),
            metadata_result={"asset_id": "asset_test_conv_0003"},
            lp_result=None,
            video_result={},
            ocr_result=_ocr_result(),
            llm_result=_llm_result(),
            kpi_result=None,
        )

        assert result["asset_data"] is None
        assert result["evaluation_data"] is None
        assert result["asset_meta"]["asset_id"] == "asset_test_conv_0003"
