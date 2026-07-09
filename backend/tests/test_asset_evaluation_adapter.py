import logging

from app.services.asset_evaluation_adapter import resolve_spec_data


SAMPLE_SPEC_DATA = {
    "asset_meta": {"asset_id": "asset_meta_test_0001", "asset_name": "test"},
    "diagnostics": {
        "qualitative": {
            "creative_fatigue_risk": "low",
            "creative_fatigue_basis": "テスト用の根拠テキストです",
        }
    },
}


class TestResolveSpecDataPassthrough:
    """asset_data/evaluation_data が存在しない現行 main の唯一のパス（spec_dataのみ）の検証"""

    def test_spec_data_only_returns_unchanged(self):
        result = resolve_spec_data(SAMPLE_SPEC_DATA)
        assert result == SAMPLE_SPEC_DATA

    def test_spec_data_only_is_identity_not_a_copy(self):
        """既存のget_spec/list_specsと同じ挙動（そのまま返す）であることを明示する。
        将来ここでdeep copyに変えるとしても、呼び出し側の期待を崩さないことをテストで固定する。"""
        result = resolve_spec_data(SAMPLE_SPEC_DATA)
        assert result is SAMPLE_SPEC_DATA

    def test_explicit_none_asset_and_evaluation_data_does_not_break(self):
        result = resolve_spec_data(SAMPLE_SPEC_DATA, asset_data=None, evaluation_data=None)
        assert result == SAMPLE_SPEC_DATA


class TestResolveSpecDataForwardCompatibility:
    """asset_data/evaluation_data は現行DBに存在しないカラムのためのフォワード互換パラメータ。
    渡された場合でも例外を送出せず、spec_dataへfail-softにフォールバックすること。"""

    def test_non_none_asset_data_falls_back_to_spec_data(self, caplog):
        with caplog.at_level(logging.WARNING):
            result = resolve_spec_data(
                SAMPLE_SPEC_DATA,
                asset_data={"asset_meta": {"asset_id": "asset_meta_test_0001"}},
            )
        assert result == SAMPLE_SPEC_DATA
        assert any("not implemented" in record.message for record in caplog.records)

    def test_non_none_evaluation_data_falls_back_to_spec_data(self, caplog):
        with caplog.at_level(logging.WARNING):
            result = resolve_spec_data(
                SAMPLE_SPEC_DATA,
                evaluation_data={"diagnostics": {}},
            )
        assert result == SAMPLE_SPEC_DATA
        assert any("not implemented" in record.message for record in caplog.records)

    def test_both_non_none_falls_back_to_spec_data_without_raising(self, caplog):
        with caplog.at_level(logging.WARNING):
            result = resolve_spec_data(
                SAMPLE_SPEC_DATA,
                asset_data={"asset_meta": {}},
                evaluation_data={"diagnostics": {}},
            )
        assert result == SAMPLE_SPEC_DATA
