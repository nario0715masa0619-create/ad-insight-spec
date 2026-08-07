"""
AnalysisOrchestrator の Meta Ads CSV 取り込み配線のテスト。

観点:
1. kpi_path が .csv の場合、MetaAdsCsvService経由でパースされ、.jsonの場合は
   従来通り json.load される（回帰なし）こと。
2. CSV取り込み結果（campaign_name/adset_name/ad_name/analysis_period/
   granularity）が self.metadata にマージされること。手入力KPI(JSON)フローでは
   何もマージされない（既存動作を維持）こと。
3. MetaAdsCsvError は run() で ProcessingError に包まれず、そのまま伝播すること
   （API層で専用の分かりやすいエラーメッセージを出すための前提）。
"""
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from app.services.analysis_orchestrator import AnalysisOrchestrator
from app.services.base_service import ProcessingError
from app.services.meta_ads_csv_service import MetaAdsCsvError


def _write_temp_file(tmp_path: Path, name: str, content: str) -> str:
    file_path = tmp_path / name
    file_path.write_text(content, encoding="utf-8")
    return str(file_path)


class TestStepLoadKpiRouting:
    def test_csv_extension_routes_through_meta_ads_csv_service(self, tmp_path):
        csv_content = (
            "キャンペーン名,インプレッション,クリック（すべて）\n"
            "テストキャンペーン,1000,50\n"
        )
        kpi_path = _write_temp_file(tmp_path, "kpi.csv", csv_content)

        orch = AnalysisOrchestrator(input_path="dummy.png", kpi_path=kpi_path)
        orch._step_load_kpi()

        assert orch.kpi_data == {"impressions": 1000, "clicks": 50, "spend": None, "conversions": None}
        assert orch.csv_import_result is not None
        assert orch.csv_import_result["granularity"] == "campaign"

    def test_json_extension_still_loads_as_plain_json_unchanged(self, tmp_path):
        """既存の手入力KPI(JSON)フローに回帰がないことの確認"""
        kpi_path = _write_temp_file(
            tmp_path, "kpi.json", json.dumps({"impressions": 10000, "clicks": 500, "ctr": 0.05, "conversions": 10})
        )

        orch = AnalysisOrchestrator(input_path="dummy.png", kpi_path=kpi_path)
        orch._step_load_kpi()

        assert orch.kpi_data == {"impressions": 10000, "clicks": 500, "ctr": 0.05, "conversions": 10}
        assert orch.csv_import_result is None

    def test_invalid_csv_raises_meta_ads_csv_error_not_processing_error(self, tmp_path):
        kpi_path = _write_temp_file(tmp_path, "kpi.csv", "キャンペーン名,消化金額\nテスト,1000\n")

        orch = AnalysisOrchestrator(input_path="dummy.png", kpi_path=kpi_path)
        with pytest.raises(MetaAdsCsvError):
            orch._step_load_kpi()

    def test_invalid_json_still_raises_processing_error_unchanged(self, tmp_path):
        kpi_path = _write_temp_file(tmp_path, "kpi.json", "{not valid json")

        orch = AnalysisOrchestrator(input_path="dummy.png", kpi_path=kpi_path)
        with pytest.raises(ProcessingError):
            orch._step_load_kpi()


class TestMergeCsvImportIntoMetadata:
    def test_merges_campaign_adset_ad_name_and_granularity(self):
        orch = AnalysisOrchestrator(input_path="dummy.png")
        orch.metadata = {"asset_id": "asset_test_0001", "asset_name": "Original Name"}
        orch.csv_import_result = {
            "granularity": "ad",
            "row_count": 1,
            "column_mapping": {"impressions": "インプレッション"},
            "warnings": [],
            "asset_meta": {
                "campaign_name": "夏キャンペーン",
                "adset_name": "セットA",
                "ad_name": "広告A",
                "analysis_period": {"start": "2026-07-01", "end": "2026-07-07"},
            },
        }

        orch._merge_csv_import_into_metadata()

        assert orch.metadata["campaign_name"] == "夏キャンペーン"
        assert orch.metadata["adset_name"] == "セットA"
        assert orch.metadata["ad_name"] == "広告A"
        assert orch.metadata["analysis_period"] == {"start": "2026-07-01", "end": "2026-07-07"}
        assert orch.metadata["platform"] == "meta"
        assert orch.metadata["kpi_source"] == "meta_ads_csv"
        assert orch.metadata["kpi_granularity"] == "ad"
        # asset_name はCSV取り込みで上書きされない（既存の広告名/キャンペーン名入力を尊重）
        assert orch.metadata["asset_name"] == "Original Name"

    def test_manual_kpi_json_flow_leaves_metadata_untouched(self):
        """csv_import_result が None（手入力KPI(JSON)フロー）では何もマージしない"""
        orch = AnalysisOrchestrator(input_path="dummy.png")
        orch.metadata = {"asset_id": "asset_test_0002", "asset_name": "Original Name"}
        orch.csv_import_result = None

        orch._merge_csv_import_into_metadata()

        assert orch.metadata == {"asset_id": "asset_test_0002", "asset_name": "Original Name"}


class TestRunPropagatesMetaAdsCsvErrorUnwrapped:
    @patch("app.services.analysis_orchestrator.AnalysisOrchestrator._step_llm")
    @patch("app.services.analysis_orchestrator.AnalysisOrchestrator._step_content_analysis")
    @patch("app.services.analysis_orchestrator.AnalysisOrchestrator._step_metadata")
    @patch("app.services.analysis_orchestrator.AnalysisOrchestrator._step_ingest")
    def test_meta_ads_csv_error_is_not_wrapped_in_processing_error(
        self, mock_ingest, mock_metadata, mock_content, mock_llm, tmp_path
    ):
        kpi_path = _write_temp_file(tmp_path, "kpi.csv", "キャンペーン名,消化金額\nテスト,1000\n")

        orch = AnalysisOrchestrator(input_path="dummy.png", kpi_path=kpi_path, mode="file_plus_lp_plus_manual_kpi")
        orch.metadata = {"asset_id": "asset_test_0003"}
        orch.ingested_asset = {"format": "image_static", "file_path": "dummy.png"}
        orch.ocr_result = {"success": True, "ocr_extracted_text": "", "confidence": 0.0}
        orch.lp_result = {}
        orch.llm_result = {"creative_core": {}}

        with pytest.raises(MetaAdsCsvError):
            orch.run()
