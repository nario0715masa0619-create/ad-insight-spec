import logging

from app.services.asset_evaluation_adapter import (
    resolve_spec_data,
    _downcast_asset_meta,
    _downcast_input_metadata,
    _downcast_creative_core,
    _downcast_diagnostics,
    _downcast_performance,
    _downcast_landing_page,
    _downcast_views,
    _downcast_metadata,
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


class TestDowncastDiagnostics:
    """_downcast_diagnostics 単体テスト（Phase 2 downcastバッチ3）。
    Diagnosticsは既存型をそのまま再利用しているためvideo_cuts以外はlossless、
    video_cuts.video_cuts[].start_seconds/end_secondsのみasset_data.asset_structure.cuts
    からcut_idで突き合わせて補完する（オープン課題2の解決方針）。"""

    def _make_diagnostics_v0(self, **overrides):
        data = {
            "qualitative": {
                "creative_fatigue_risk": "low",
                "creative_fatigue_basis": "テスト用の根拠テキストです",
            },
            "llm_model": "gpt-4o",
            "llm_success": True,
            "llm_retry_count": 0,
            "llm_error": None,
        }
        data.update(overrides)
        return data

    def test_non_video_cuts_fields_pass_through_unchanged(self):
        """qualitative/llm_model等、video_cuts以外は無変換で転記される（lossless）"""
        diagnostics_v0 = self._make_diagnostics_v0()
        result = _downcast_diagnostics(diagnostics_v0)
        assert result["qualitative"] == diagnostics_v0["qualitative"]
        assert result["llm_model"] == "gpt-4o"
        assert result["llm_success"] is True

    def test_none_video_cuts_returns_unchanged(self):
        """video_cutsがNone（画像フォーマット等）の場合、補完対象がないためそのまま返す"""
        diagnostics_v0 = self._make_diagnostics_v0(video_cuts=None)
        result = _downcast_diagnostics(diagnostics_v0)
        assert result["video_cuts"] is None

    def test_empty_video_cuts_list_returns_unchanged(self):
        diagnostics_v0 = self._make_diagnostics_v0(
            video_cuts={
                "schema_version": "1.0",
                "generation_status": {"status": "not_attempted", "error_code": None},
                "video_summary": None,
                "video_cuts": [],
            }
        )
        result = _downcast_diagnostics(diagnostics_v0)
        assert result["video_cuts"]["video_cuts"] == []

    def test_cut_id_match_fills_start_end_seconds(self):
        diagnostics_v0 = self._make_diagnostics_v0(
            video_cuts={
                "schema_version": "1.0",
                "generation_status": {"status": "success", "error_code": None},
                "video_summary": {"total_duration_seconds": 15.9, "cut_count": 1},
                "video_cuts": [
                    {
                        "cut_id": "cut_1",
                        "start_seconds": None,
                        "end_seconds": None,
                        "role_tag": "hook",
                        "summary": "画面内容の要約テキスト",
                        "improvement_suggestion": "具体的な改善提案テキスト",
                    }
                ],
            }
        )
        cuts_v0 = [{"cut_id": "cut_1", "start_sec": 0.0, "end_sec": 8.1}]
        result = _downcast_diagnostics(diagnostics_v0, cuts_v0)
        merged_cut = result["video_cuts"]["video_cuts"][0]
        assert merged_cut["start_seconds"] == 0.0
        assert merged_cut["end_seconds"] == 8.1
        # 他のフィールドは無変換のまま
        assert merged_cut["role_tag"] == "hook"
        assert merged_cut["summary"] == "画面内容の要約テキスト"

    def test_cut_id_no_match_leaves_start_end_none_fail_soft(self):
        """cut_idがcuts_v0に見つからない場合、架空の時間範囲を捏造せずNoneのまま残す"""
        diagnostics_v0 = self._make_diagnostics_v0(
            video_cuts={
                "schema_version": "1.0",
                "generation_status": {"status": "success", "error_code": None},
                "video_summary": {"total_duration_seconds": 8.1, "cut_count": 1},
                "video_cuts": [
                    {
                        "cut_id": "cut_unknown",
                        "start_seconds": None,
                        "end_seconds": None,
                        "role_tag": "hook",
                        "summary": "画面内容の要約テキスト",
                        "improvement_suggestion": "具体的な改善提案テキスト",
                    }
                ],
            }
        )
        cuts_v0 = [{"cut_id": "cut_1", "start_sec": 0.0, "end_sec": 8.1}]
        result = _downcast_diagnostics(diagnostics_v0, cuts_v0)
        merged_cut = result["video_cuts"]["video_cuts"][0]
        assert merged_cut["start_seconds"] is None
        assert merged_cut["end_seconds"] is None

    def test_missing_cuts_v0_argument_defaults_to_no_match(self):
        diagnostics_v0 = self._make_diagnostics_v0(
            video_cuts={
                "schema_version": "1.0",
                "generation_status": {"status": "success", "error_code": None},
                "video_summary": {"total_duration_seconds": 8.1, "cut_count": 1},
                "video_cuts": [
                    {
                        "cut_id": "cut_1",
                        "start_seconds": None,
                        "end_seconds": None,
                        "role_tag": "hook",
                        "summary": "画面内容の要約テキスト",
                        "improvement_suggestion": "具体的な改善提案テキスト",
                    }
                ],
            }
        )
        result = _downcast_diagnostics(diagnostics_v0)
        assert result["video_cuts"]["video_cuts"][0]["start_seconds"] is None

    def test_does_not_mutate_input_dicts(self):
        """入力のdiagnostics_v0/cuts_v0は変更されない（新しいdictを構築して返す）"""
        original_cut = {
            "cut_id": "cut_1",
            "start_seconds": None,
            "end_seconds": None,
            "role_tag": "hook",
            "summary": "画面内容の要約テキスト",
            "improvement_suggestion": "具体的な改善提案テキスト",
        }
        diagnostics_v0 = self._make_diagnostics_v0(
            video_cuts={
                "schema_version": "1.0",
                "generation_status": {"status": "success", "error_code": None},
                "video_summary": {"total_duration_seconds": 8.1, "cut_count": 1},
                "video_cuts": [original_cut],
            }
        )
        cuts_v0 = [{"cut_id": "cut_1", "start_sec": 0.0, "end_sec": 8.1}]
        _downcast_diagnostics(diagnostics_v0, cuts_v0)
        assert original_cut["start_seconds"] is None
        assert original_cut["end_seconds"] is None


class TestDowncastPerformance:
    """_downcast_performance 単体テスト（Phase 2 downcastバッチ4）。
    Performance型はEvaluationJsonV0でそのまま再利用されているため恒等写像。"""

    def test_identity_passthrough(self):
        performance_v0 = {"impressions": 10000, "clicks": 500, "ctr": 0.05}
        assert _downcast_performance(performance_v0) == performance_v0

    def test_none_stays_none(self):
        assert _downcast_performance(None) is None


class TestDowncastLandingPage:
    """_downcast_landing_page 単体テスト（Phase 2 downcastバッチ4）。
    LandingPage型はEvaluationJsonV0.landing_page_analysisでそのまま再利用されているため恒等写像。"""

    def test_identity_passthrough(self):
        landing_page_v0 = {"url": "https://example.com/lp", "fv_copy": "テストコピー"}
        assert _downcast_landing_page(landing_page_v0) == landing_page_v0

    def test_none_stays_none(self):
        assert _downcast_landing_page(None) is None


class TestDowncastViews:
    """_downcast_views 単体テスト（Phase 2 downcastバッチ4）。
    converter_service.py::_populate_viewsの現行固定値出力と完全に一致することを検証する
    （実データを一切必要としない）。"""

    def test_matches_current_legacy_hardcoded_output(self):
        """converter_service.py::_populate_viewsが返す現行の固定値と1バイトも違わないこと"""
        result = _downcast_views()
        assert result == {
            "dashboard_summary": {
                "status_label": "Good",
                "key_metric_highlight": "Analysis complete",
                "status_color": "#FFAA00",
            },
            "performance_ranking": "Average",
            "trend_indicator": None,
            "creative_fatigue_visual": "● Low",
            "lp_match_visual": "✓ Aligned",
            "recommended_actions_display": [],
        }

    def test_takes_no_arguments(self):
        """viewsはasset_data/evaluation_dataの実データを一切必要としないため、
        引数なしで呼び出せることを確認する"""
        import inspect
        sig = inspect.signature(_downcast_views)
        assert len(sig.parameters) == 0


class TestDowncastMetadata:
    """_downcast_metadata 単体テスト（Phase 2 downcastバッチ4、オープン課題3の続き）"""

    def test_full_roundtrip_from_asset_and_evaluation_meta(self):
        asset_meta_v0 = {
            "asset_id": "asset_meta_test_0001",
            "created_at": "2026-07-09T12:00:00",
            "source_type": "local_file",
            "mode": "file_plus_lp_plus_manual_kpi",
        }
        evaluation_meta_v0 = {
            "evaluated_at": "2026-07-09T12:30:00",
            "evaluator_model": "gpt-4o",
            "processing_time_ms": 4200,
            "validation_status": "passed",
            "validation_notes": ["LLM analysis: gpt-4o (success)"],
            "analysis_tools_used": {"ocr_engine": "tesseract"},
        }
        result = _downcast_metadata(asset_meta_v0, evaluation_meta_v0)
        assert result == {
            "generated_at": "2026-07-09T12:00:00",
            "data_source": "local_file",
            "ai_model_version": "gpt-4o",
            "json_schema_version": "v0.2",
            "input_mode": "file_plus_lp_plus_manual_kpi",
            "analysis_tools_used": {"ocr_engine": "tesseract"},
            "processing_time_ms": 4200,
            "validation_status": "passed",
            "validation_notes": ["LLM analysis: gpt-4o (success)"],
        }

    def test_json_schema_version_matches_current_legacy_fixed_value(self):
        """json_schema_versionは未決だが、現時点ではlegacy側の固定値"v0.2"
        （converter_service.py::_populate_metadata）と一致させている"""
        result = _downcast_metadata({}, {})
        assert result["json_schema_version"] == "v0.2"

    def test_missing_fields_become_none(self):
        result = _downcast_metadata({}, {})
        assert result["generated_at"] is None
        assert result["data_source"] is None
        assert result["input_mode"] is None
        assert result["ai_model_version"] is None
