"""
AdInsightSpec.validate_mode_requirements() のテスト。

主入力の再定義（CSV + クリエイティブ + LP、docs/plans/primary_input_redesign.md）に
伴い追加した file_plus_kpi モード（クリエイティブ + KPI、LPなし）が、既存の3モードと
同じバリデーション契約（landing_page/performanceのnull/必須ルール）に従うことを検証する。
既存3モードの挙動が変わっていないことも合わせて確認する（回帰防止）。
"""
import pytest
from pydantic.v1 import ValidationError

from app.schemas.ad_insight import AdInsightSpec


def _base_spec(mode: str, landing_page=None, performance=None) -> dict:
    return {
        "input_metadata": {
            "mode": mode,
            "source_type": "local_file",
            "input_timestamp": "2026-08-10T00:00:00Z",
        },
        "asset_meta": {"asset_id": f"asset_{mode}_test"},
        "creative_core": {"format": "image_static"},
        "landing_page": landing_page,
        "performance": performance,
        "diagnostics": {
            "qualitative": {
                "creative_fatigue_risk": "low",
                "creative_fatigue_basis": "テスト用の根拠テキストです",
            },
        },
        "views": None,
        "_metadata": {
            "generated_at": "2026-08-10T00:00:00Z",
            "data_source": "local_file",
            "ai_model_version": "gpt-4o",
            "input_mode": mode,
        },
    }


_SAMPLE_PERFORMANCE = {"impressions": 1000, "clicks": 10}
_SAMPLE_LANDING_PAGE = {"url": "https://example.com/lp"}


class TestFilePlusKpiMode:
    """新規追加した file_plus_kpi（クリエイティブ + KPI、LPなし）モード"""

    def test_accepts_performance_without_landing_page(self):
        spec = AdInsightSpec(**_base_spec("file_plus_kpi", performance=_SAMPLE_PERFORMANCE))
        assert spec.performance.impressions == 1000
        assert spec.landing_page is None

    def test_rejects_missing_performance(self):
        with pytest.raises(ValidationError, match="performance is required in file_plus_kpi mode"):
            AdInsightSpec(**_base_spec("file_plus_kpi"))

    def test_rejects_landing_page_present(self):
        with pytest.raises(ValidationError, match="landing_page must be null in file_plus_kpi mode"):
            AdInsightSpec(**_base_spec(
                "file_plus_kpi",
                landing_page=_SAMPLE_LANDING_PAGE,
                performance=_SAMPLE_PERFORMANCE,
            ))


class TestExistingModesUnchanged:
    """既存3モードのバリデーション契約が、新モード追加後も変わっていないことの回帰確認"""

    def test_file_only_rejects_landing_page(self):
        with pytest.raises(ValidationError, match="landing_page must be null in file_only mode"):
            AdInsightSpec(**_base_spec("file_only", landing_page=_SAMPLE_LANDING_PAGE))

    def test_file_only_rejects_performance(self):
        with pytest.raises(ValidationError, match="performance must be null in file_only mode"):
            AdInsightSpec(**_base_spec("file_only", performance=_SAMPLE_PERFORMANCE))

    def test_file_only_accepts_neither(self):
        spec = AdInsightSpec(**_base_spec("file_only"))
        assert spec.landing_page is None
        assert spec.performance is None

    def test_file_plus_lp_requires_landing_page(self):
        with pytest.raises(ValidationError, match="landing_page is required in file_plus_lp mode"):
            AdInsightSpec(**_base_spec("file_plus_lp"))

    def test_file_plus_lp_rejects_performance(self):
        with pytest.raises(ValidationError, match="performance must be null in file_plus_lp mode"):
            AdInsightSpec(**_base_spec(
                "file_plus_lp", landing_page=_SAMPLE_LANDING_PAGE, performance=_SAMPLE_PERFORMANCE
            ))

    def test_file_plus_lp_plus_manual_kpi_requires_both(self):
        with pytest.raises(ValidationError, match="landing_page is required in file_plus_lp_plus_manual_kpi mode"):
            AdInsightSpec(**_base_spec("file_plus_lp_plus_manual_kpi"))
        with pytest.raises(ValidationError, match="performance is required in file_plus_lp_plus_manual_kpi mode"):
            AdInsightSpec(**_base_spec("file_plus_lp_plus_manual_kpi", landing_page=_SAMPLE_LANDING_PAGE))

    def test_file_plus_lp_plus_manual_kpi_accepts_both(self):
        spec = AdInsightSpec(**_base_spec(
            "file_plus_lp_plus_manual_kpi",
            landing_page=_SAMPLE_LANDING_PAGE,
            performance=_SAMPLE_PERFORMANCE,
        ))
        assert spec.landing_page.url == "https://example.com/lp"
        assert spec.performance.impressions == 1000
