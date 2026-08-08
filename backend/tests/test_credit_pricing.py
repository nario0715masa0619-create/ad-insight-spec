"""
app/services/credit_pricing.py のテスト。

消費クレジット数はハードコードではなく Settings（環境変数）経由で調整可能に
している、という設計の要となる部分なので、デフォルト値とオーバーライドの
両方を検証する。
"""
from app.config import Settings
from app.services.credit_pricing import credit_cost_for_mode


def _settings(**overrides) -> Settings:
    defaults = {"CREDIT_COST_LIGHT": 1, "CREDIT_COST_STANDARD": 2, "CREDIT_COST_HEAVY": 3}
    defaults.update(overrides)
    return Settings(**defaults)


class TestDefaultTiers:
    def test_file_only_is_light_tier(self):
        assert credit_cost_for_mode("file_only", settings=_settings()) == 1

    def test_file_plus_lp_is_standard_tier(self):
        assert credit_cost_for_mode("file_plus_lp", settings=_settings()) == 2

    def test_file_plus_lp_plus_manual_kpi_is_heavy_tier(self):
        assert credit_cost_for_mode("file_plus_lp_plus_manual_kpi", settings=_settings()) == 3

    def test_unknown_mode_falls_back_to_light_tier(self):
        assert credit_cost_for_mode("some_future_mode", settings=_settings()) == 1


class TestCostsAreConfigurable:
    def test_overriding_settings_changes_cost_without_code_changes(self):
        settings = _settings(CREDIT_COST_LIGHT=5, CREDIT_COST_STANDARD=10, CREDIT_COST_HEAVY=20)
        assert credit_cost_for_mode("file_only", settings=settings) == 5
        assert credit_cost_for_mode("file_plus_lp", settings=settings) == 10
        assert credit_cost_for_mode("file_plus_lp_plus_manual_kpi", settings=settings) == 20

    def test_default_settings_singleton_matches_documented_defaults(self):
        """get_settings()経由(=環境変数未設定時)のデフォルトが設計どおり1/2/3であること"""
        from app.config import get_settings

        settings = get_settings()
        assert credit_cost_for_mode("file_only", settings=settings) == 1
        assert credit_cost_for_mode("file_plus_lp", settings=settings) == 2
        assert credit_cost_for_mode("file_plus_lp_plus_manual_kpi", settings=settings) == 3
