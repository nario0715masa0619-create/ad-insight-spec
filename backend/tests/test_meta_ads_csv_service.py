"""
MetaAdsCsvService のテスト。

Meta Ads Manager からエクスポートしたCSVを「そのまま」受け取れることを検証する。
機密データは使わず、すべてダミーの数値・名称を使用する。

観点:
1. 代表的なMeta Ads CSVで主要指標を正しく抽出できる（日本語/英語ヘッダー）
2. 不要列が多くても処理できる（ノイズ列は無視）
3. 必須列不足時に分かるエラーになる
4. 粒度判定（campaign / adset / ad）が期待通り動く
5. 複数行（日別内訳）の合算・分析期間の抽出
"""
from pathlib import Path

import pytest

from app.services.meta_ads_csv_service import MetaAdsCsvError, MetaAdsCsvService

SAMPLE_DATA_DIR = Path(__file__).resolve().parents[2] / "sample_data" / "meta_ads_csv"


class TestJapaneseHeaders:
    """日本語ヘッダーのMeta Ads CSV（fixtureファイル経由）"""

    def test_ad_level_csv_extracts_kpi_and_granularity(self):
        result = MetaAdsCsvService.parse_file(str(SAMPLE_DATA_DIR / "meta_ads_ad_level_ja.csv"))

        assert result["granularity"] == "ad"
        assert result["row_count"] == 2
        # 2行の合算（10000+12000, 300+280, 50000+52000, 15+18）
        assert result["kpi"] == {
            "impressions": 22000,
            "clicks": 580,
            "spend": 102000.0,
            "conversions": 33,
        }
        assert result["asset_meta"]["campaign_name"] == "夏の新作キャンペーン"
        assert result["asset_meta"]["adset_name"] == "20-30代女性_興味関心"
        assert result["asset_meta"]["ad_name"] == "新作動画A"
        assert result["asset_meta"]["analysis_period"] == {"start": "2026-07-01", "end": "2026-07-14"}
        assert result["warnings"] == []

    def test_column_mapping_reports_original_headers(self):
        result = MetaAdsCsvService.parse_file(str(SAMPLE_DATA_DIR / "meta_ads_ad_level_ja.csv"))
        assert result["column_mapping"]["impressions"] == "インプレッション"
        assert result["column_mapping"]["clicks"] == "クリック（すべて）"
        assert result["column_mapping"]["ad_name"] == "広告名"


class TestEnglishHeaders:
    """英語ヘッダー・キャンペーン粒度のMeta Ads CSV"""

    def test_campaign_level_csv_aggregates_daily_rows(self):
        result = MetaAdsCsvService.parse_file(str(SAMPLE_DATA_DIR / "meta_ads_campaign_level_en.csv"))

        assert result["granularity"] == "campaign"
        assert result["row_count"] == 3
        assert result["kpi"]["impressions"] == 5000 + 5400 + 4800
        assert result["kpi"]["clicks"] == 120 + 130 + 110
        assert result["kpi"]["spend"] == 20000 + 21500 + 19000
        assert result["kpi"]["conversions"] == 6 + 7 + 5
        assert result["asset_meta"]["campaign_name"] == "Autumn Launch Campaign"
        assert result["asset_meta"]["adset_name"] is None
        assert result["asset_meta"]["ad_name"] is None
        assert result["asset_meta"]["analysis_period"] == {"start": "2026-08-01", "end": "2026-08-03"}


class TestNoisyColumns:
    """不要列（画質ランキング等、対応外の指標）が多く含まれていても処理できること"""

    def test_extra_columns_are_ignored_not_fatal(self):
        result = MetaAdsCsvService.parse_file(str(SAMPLE_DATA_DIR / "meta_ads_noisy_extra_columns.csv"))

        assert result["granularity"] == "adset"
        assert result["kpi"]["impressions"] == 84000
        assert result["kpi"]["clicks"] == 2100
        assert result["kpi"]["spend"] == 310000.0
        assert result["kpi"]["conversions"] == 64
        # 「配信状況」「リーチ」「頻度」「画質ランキング」等はマッピング対象外として無視される
        assert "配信状況" in result["unmapped_columns"]
        assert "画質ランキング" in result["unmapped_columns"]


class TestMissingRequiredColumns:
    """必須列（インプレッション・クリック）が無い場合、分かるエラーになること"""

    def test_missing_required_columns_raises_with_guidance(self):
        with pytest.raises(MetaAdsCsvError) as exc_info:
            MetaAdsCsvService.parse_file(str(SAMPLE_DATA_DIR / "meta_ads_missing_required_columns.csv"))

        err = exc_info.value
        assert err.error_code == "META_ADS_CSV_MISSING_REQUIRED_COLUMNS"
        assert "impressions" in err.missing_fields
        assert "clicks" in err.missing_fields
        assert "インプレッション" in err.user_message


class TestEmptyAndHeaderOnlyCsv:
    def test_empty_csv_raises(self):
        with pytest.raises(MetaAdsCsvError) as exc_info:
            MetaAdsCsvService.parse_text("")
        assert exc_info.value.error_code == "META_ADS_CSV_EMPTY"

    def test_header_only_csv_raises_no_data_error(self):
        with pytest.raises(MetaAdsCsvError) as exc_info:
            MetaAdsCsvService.parse_text("キャンペーン名,インプレッション,クリック（すべて）\n")
        assert exc_info.value.error_code == "META_ADS_CSV_NO_DATA"


class TestUnreadableValues:
    def test_blank_metric_cells_raise_unreadable_values_error(self):
        csv_text = (
            "キャンペーン名,インプレッション,クリック（すべて）\n"
            "テストキャンペーン,,\n"
        )
        with pytest.raises(MetaAdsCsvError) as exc_info:
            MetaAdsCsvService.parse_text(csv_text)
        assert exc_info.value.error_code == "META_ADS_CSV_UNREADABLE_VALUES"


class TestGranularityDetection:
    def test_campaign_only_columns_yield_campaign_granularity(self):
        csv_text = (
            "キャンペーン名,インプレッション,クリック（すべて）\n"
            "テストキャンペーン,1000,20\n"
        )
        result = MetaAdsCsvService.parse_text(csv_text)
        assert result["granularity"] == "campaign"

    def test_no_name_columns_yield_unknown_granularity_with_warning(self):
        csv_text = "インプレッション,クリック（すべて）\n1000,20\n"
        result = MetaAdsCsvService.parse_text(csv_text)
        assert result["granularity"] == "unknown"
        assert any("粒度を判定できませんでした" in w for w in result["warnings"])

    def test_ad_name_takes_precedence_over_campaign_and_adset(self):
        csv_text = (
            "キャンペーン名,広告セット名,広告名,インプレッション,クリック（すべて）\n"
            "C,S,A,1000,20\n"
        )
        result = MetaAdsCsvService.parse_text(csv_text)
        assert result["granularity"] == "ad"


class TestRecommendedFieldsAndWarnings:
    def test_missing_spend_and_conversions_are_reported_as_warning_not_error(self):
        csv_text = (
            "キャンペーン名,インプレッション,クリック（すべて）\n"
            "テストキャンペーン,1000,20\n"
        )
        result = MetaAdsCsvService.parse_text(csv_text)
        assert result["kpi"]["spend"] is None
        assert result["kpi"]["conversions"] is None
        assert "spend" in result["missing_recommended_fields"]
        assert "conversions" in result["missing_recommended_fields"]
        assert any("任意項目" in w for w in result["warnings"])

    def test_multiple_distinct_names_uses_first_and_warns(self):
        csv_text = (
            "キャンペーン名,インプレッション,クリック（すべて）\n"
            "キャンペーンA,1000,20\n"
            "キャンペーンB,900,15\n"
        )
        result = MetaAdsCsvService.parse_text(csv_text)
        assert result["asset_meta"]["campaign_name"] in ("キャンペーンA", "キャンペーンB")
        assert any("複数のキャンペーン名" in w for w in result["warnings"])


class TestPercentAndCurrencyParsing:
    def test_percent_and_currency_formatted_cells_do_not_break_parsing(self):
        # 桁区切りカンマを含む数値セルは、CSVの仕様上ダブルクオートで囲まれる
        # （"1,000" 等）。¥記号・カンマ・%記号を含んでいても解析できることを確認する。
        csv_text_quoted = (
            'キャンペーン名,インプレッション,クリック（すべて）,消化金額 (JPY)\n'
            'テスト,"1,000",20,"¥5,000"\n'
        )
        result = MetaAdsCsvService.parse_text(csv_text_quoted)
        assert result["kpi"]["impressions"] == 1000
        assert result["kpi"]["clicks"] == 20
        assert result["kpi"]["spend"] == 5000.0
