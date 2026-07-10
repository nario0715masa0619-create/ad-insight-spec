"""
AnalysisOrchestrator.run() レベルでの asset_data/evaluation_data 配線テスト
（Phase 2 P1: 生成ロジック実装）。

ConverterService単体の生成ロジック自体は test_converter_service.py で検証済み。
ここでは、AnalysisOrchestrator側の配線（self.video_cutsがConverterServiceへ
渡ること、_metadata.processing_time_msと同じ実測値がevaluation_meta側にも
上書きされること）を確認する。実I/Oを伴う_step_ingest/_step_metadata/
_step_content_analysis/_step_llmはmonkeypatchで置き換え、_step_converter()と
run()末尾の後処理は実コードをそのまま通す。
"""
import json

from app.services.analysis_orchestrator import AnalysisOrchestrator


def _make_orchestrator_with_stubbed_steps(monkeypatch, mode="file_only"):
    orch = AnalysisOrchestrator(input_path="/tmp/input.mp4", lp_input=None, kpi_path=None, mode=mode)

    def _fake_ingest():
        orch.ingested_asset = {"format": "video_static", "file_path": "/tmp/input.mp4"}

    def _fake_metadata():
        orch.metadata = {
            "asset_id": "asset_test_run_0001",
            "duration_seconds": 12.0,
            "resolution": "640x480",
        }

    def _fake_content_analysis():
        orch.video_result = {}
        orch.ocr_result = {"success": True, "ocr_extracted_text": "", "confidence": 0.0}
        orch.lp_result = {}
        orch.video_cuts = [
            {
                "cut_id": "cut_1",
                "start_seconds": 0.0,
                "end_seconds": 4.0,
                "frame_path": "/tmp/f.jpg",
                "ocr_text": "テロップ",
            },
        ]

    def _fake_llm():
        orch.llm_result = {
            "creative_core": {
                "visuals": {},
                "tone": {},
                "ai_labels": ["x"],
                "llm_model": "gpt-4o",
                "llm_success": True,
                "llm_retry_count": 0,
                "llm_error": None,
            },
            "recommendations": [],
            "video_cuts": None,
        }

    monkeypatch.setattr(orch, "_step_ingest", _fake_ingest)
    monkeypatch.setattr(orch, "_step_metadata", _fake_metadata)
    monkeypatch.setattr(orch, "_step_content_analysis", _fake_content_analysis)
    monkeypatch.setattr(orch, "_step_llm", _fake_llm)
    return orch


class TestVideoCutsWiredIntoAssetData:
    def test_run_passes_video_cuts_through_to_asset_structure(self, monkeypatch):
        orch = _make_orchestrator_with_stubbed_steps(monkeypatch)
        result = orch.run()

        cuts = result["asset_data"]["asset_structure"]["cuts"]
        assert cuts == [{"cut_id": "cut_1", "start_sec": 0.0, "end_sec": 4.0}]

        ocr_segments = result["asset_data"]["asset_structure"]["ocr_segments"]
        assert len(ocr_segments) == 1
        assert ocr_segments[0]["text"] == "テロップ"


class TestProcessingTimeMsPatchedOnBothMetadataBlocks:
    def test_evaluation_meta_processing_time_matches_metadata_processing_time(self, monkeypatch):
        orch = _make_orchestrator_with_stubbed_steps(monkeypatch)
        result = orch.run()

        legacy_processing_time = result["_metadata"]["processing_time_ms"]
        v0_processing_time = result["evaluation_data"]["evaluation_meta"]["processing_time_ms"]

        assert legacy_processing_time == v0_processing_time
        assert legacy_processing_time >= 0
        # _step_converter直後の暫定値(0)ではなく、run()完了後の実測値で
        # 上書きされていることを確認する（0秒未満の経過は通常あり得ないため、
        # ここでは「上書き処理が実際に走ったこと」を型と非負性で担保する）
        assert isinstance(v0_processing_time, int)


class TestOrchestratorRunOutputIsJsonSerializable:
    """CLIはorchestrator.run()の戻り値をそのままjson.dump(..., default=str)するため、
    asset_data/evaluation_data追加後もJSON直列化できることを確認する。

    spec_data側（input_metadata.input_timestamp等）はConverterServiceが
    spec.dict()で組み立てているため生のdatetimeオブジェクトが残る（既存の
    仕様、P1のスコープ外）。CLI側のdefault=strはその保険であり、ここでは
    CLIと同じ呼び出し方（default=str）でJSON化できることを確認する。
    新規追加したasset_data/evaluation_data自体は_build_asset_evaluation_v0内で
    json.loads(model.json())を経由済みのため、default=strに頼らずとも
    素のjson.dumpsで直列化できることを別途確認する。"""

    def test_full_result_is_json_dumpable_with_cli_style_default_str(self, monkeypatch):
        orch = _make_orchestrator_with_stubbed_steps(monkeypatch)
        result = orch.run()
        json.dumps(result, default=str)

    def test_asset_evaluation_data_alone_need_no_default_str_fallback(self, monkeypatch):
        orch = _make_orchestrator_with_stubbed_steps(monkeypatch)
        result = orch.run()
        json.dumps(result["asset_data"])
        json.dumps(result["evaluation_data"])
