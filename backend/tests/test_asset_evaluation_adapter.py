import logging

from app.services.asset_evaluation_adapter import (
    resolve_spec_data,
    _downcast_asset_meta,
    _downcast_input_metadata,
    _downcast_creative_core,
)


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


class TestDowncastAssetMetaNotWired:
    """_downcast_asset_meta はPhase 2 downcast第一バッチの部品だが、resolve_spec_data
    からはまだ呼ばれない（input_metadata/creative_coreの変換元が無いため、resolve_spec_data
    は引き続き既存のfail-soft挙動のまま）ことを固定する。"""

    def test_resolve_spec_data_does_not_call_downcast_asset_meta(self, caplog):
        """asset_dataにasset_metaを含めて渡しても、resolve_spec_dataの戻り値は
        依然としてspec_dataへのfail-softフォールバックのままであること
        （_downcast_asset_metaの出力に置き換わっていないこと）を確認する。"""
        with caplog.at_level(logging.WARNING):
            result = resolve_spec_data(
                SAMPLE_SPEC_DATA,
                asset_data={
                    "asset_meta": {
                        "asset_id": "asset_meta_test_9999",
                        "platform": "meta",
                        "source_type": "local_file",
                    }
                },
            )
        assert result == SAMPLE_SPEC_DATA
        assert result["asset_meta"]["asset_id"] == "asset_meta_test_0001"


class TestDowncastAssetMeta:
    """_downcast_asset_meta 単体テスト（オープン課題1の解決: AssetMetaV0はlegacy AssetMetaの
    スーパーセットのため、legacy側のキーをそのまま転記するだけでよいことを検証する）"""

    def test_legacy_fields_are_copied_through_unchanged(self):
        asset_meta_v0 = {
            "asset_id": "asset_meta_test_0001",
            "asset_name": "テスト素材",
            "platform": "meta",
            "ad_account_id": "act_123",
            "campaign_name": "テストキャンペーン",
            "adset_name": "テストアドセット",
            "ad_name": "テスト広告",
            "analysis_period": {"start": "2026-07-01", "end": "2026-07-31"},
            "external_ids": {"meta_ad_id": "1234567890"},
            # v0専用フィールド（legacyには存在しないため出力から除外されるはず）
            "source_type": "local_file",
            "source_ref": "/tmp/input.mp4",
            "created_at": "2026-07-09T12:00:00",
            "analysis_version": "v0",
        }
        result = _downcast_asset_meta(asset_meta_v0)
        assert result == {
            "asset_id": "asset_meta_test_0001",
            "asset_name": "テスト素材",
            "platform": "meta",
            "ad_account_id": "act_123",
            "campaign_name": "テストキャンペーン",
            "adset_name": "テストアドセット",
            "ad_name": "テスト広告",
            "analysis_period": {"start": "2026-07-01", "end": "2026-07-31"},
            "external_ids": {"meta_ad_id": "1234567890"},
        }

    def test_v0_only_fields_are_dropped(self):
        result = _downcast_asset_meta({
            "asset_id": "asset_meta_test_0001",
            "source_type": "local_file",
            "source_ref": "/tmp/input.mp4",
            "created_at": "2026-07-09T12:00:00",
            "analysis_version": "v0",
        })
        assert "source_type" not in result
        assert "source_ref" not in result
        assert "created_at" not in result
        assert "analysis_version" not in result

    def test_missing_optional_legacy_fields_are_omitted_not_null_padded(self):
        """asset_meta_v0側に無いキーは、None埋めせず出力からも省く
        （欠損の扱いはlegacy AssetMeta側のOptional性に委ねる方針）"""
        result = _downcast_asset_meta({"asset_id": "asset_meta_test_0001"})
        assert result == {"asset_id": "asset_meta_test_0001"}
        assert "platform" not in result
        assert "campaign_name" not in result

    def test_empty_input_returns_empty_dict(self):
        assert _downcast_asset_meta({}) == {}


class TestDowncastInputMetadata:
    """_downcast_input_metadata 単体テスト（Phase 2 downcastバッチ2、
    docs/plans/asset_evaluation_split_phase2_tasks.md「🗂 6項目の保存方針比較」で
    確定した推奨案: mode/file_pathsはAssetMetaV0拡張、source_type/created_atは
    既存v0フィールドの転記で埋める）"""

    def test_full_roundtrip_from_asset_meta_v0(self):
        asset_meta_v0 = {
            "asset_id": "asset_meta_test_0001",
            "source_type": "local_file",
            "created_at": "2026-07-09T12:00:00",
            "mode": "file_plus_lp_plus_manual_kpi",
            "file_paths": {
                "creative_video": "/tmp/input.mp4",
                "creative_images": None,
                "landing_page_html": None,
            },
        }
        result = _downcast_input_metadata(asset_meta_v0)
        assert result == {
            "mode": "file_plus_lp_plus_manual_kpi",
            "source_type": "local_file",
            "input_timestamp": "2026-07-09T12:00:00",
            "file_paths": {
                "creative_video": "/tmp/input.mp4",
                "creative_images": None,
                "landing_page_html": None,
            },
            "api_source": None,
        }

    def test_api_source_is_always_none(self):
        """api_sourceは現行システムに実データが存在しない項目
        （オープン課題4・5詳細調査の分類③）のため、常にNoneを返す"""
        result = _downcast_input_metadata({"asset_id": "asset_meta_test_0001"})
        assert result["api_source"] is None

    def test_missing_file_paths_becomes_none(self):
        result = _downcast_input_metadata({"asset_id": "asset_meta_test_0001"})
        assert result["file_paths"] is None
        assert result["mode"] is None
        assert result["source_type"] is None
        assert result["input_timestamp"] is None


class TestDowncastCreativeCore:
    """_downcast_creative_core 単体テスト（Phase 2 downcastバッチ2、
    media_info + asset_structure + evaluation_data.creative_core の3ソースから
    legacy spec_data.creative_core を再構築する）"""

    def test_full_roundtrip_with_llm_data(self):
        media_info_v0 = {"media_type": "video_static", "duration_seconds": 15.9}
        asset_structure_v0 = {"ocr_extracted_text": "今だけ限定セール"}
        creative_core_llm = {
            "visuals": {
                "dominant_colors": ["#FF6B6B"],
                "composition": "中央寄せ",
                "style": "モダン",
                "clarity": "高",
            },
            "tone": {
                "primary_tone": ["professional"],
                "emotional_appeal": "論理的",
                "call_to_action": "強",
            },
            "ai_labels": ["finance", "trust"],
        }
        result = _downcast_creative_core(media_info_v0, asset_structure_v0, creative_core_llm)
        assert result["format"] == "video_static"
        assert result["duration_seconds"] == 15.9
        assert result["ocr_extracted_text"] == "今だけ限定セール"
        assert result["visuals"]["clarity"] == "高"
        assert result["tone"]["emotional_appeal"] == "論理的"
        assert result["ai_labels"] == ["finance", "trust"]

    def test_always_none_fields_match_current_legacy_behavior(self):
        """primary_text/headline/body_text/call_to_action/platform_specificは、
        legacy側の現行実装でも常にNone（オープン課題4・5詳細調査の分類③）のため、
        downcast後もNoneのままで現行挙動と一致する"""
        result = _downcast_creative_core({}, {}, None)
        assert result["primary_text"] is None
        assert result["headline"] is None
        assert result["body_text"] is None
        assert result["call_to_action"] is None
        assert result["platform_specific"] is None

    def test_creative_core_llm_none_falls_back_to_legacy_defaults(self):
        """evaluation_data.creative_core未設定（None）時は、legacy側のデフォルト値
        （visuals/toneはNone、ai_labelsは空リスト）に合わせる"""
        result = _downcast_creative_core({}, {}, None)
        assert result["visuals"] is None
        assert result["tone"] is None
        assert result["ai_labels"] == []

    def test_missing_ocr_extracted_text_defaults_to_empty_string(self):
        result = _downcast_creative_core({}, {}, None)
        assert result["ocr_extracted_text"] == ""
