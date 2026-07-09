"""
asset_data / evaluation_data → legacy spec_data の read adapter（Phase 2）。

設計の背景・変換方針は docs/plans/asset_evaluation_split_phase2_tasks.md を参照。

現状（2026-07-09、Phase 2 downcastバッチ4）:
- `resolve_spec_data()` の公開挙動は Phase 1 実装時から**変更していない**
  （asset_data/evaluation_data が非Noneでもfail-softにspec_dataへフォールバックする）。
  今回のバッチでもwiringは行わない（理由は下記「resolve_spec_data配線について」）。
- downcastバッチ1〜3（`_downcast_asset_meta`/`_downcast_input_metadata`/
  `_downcast_creative_core`/`_downcast_diagnostics`）に続き、バッチ4で
  `_downcast_performance()`・`_downcast_landing_page()`・`_downcast_views()`・
  `_downcast_metadata()`を追加した。これで`spec_data`の8ブロック**全て**の
  downcast部品が揃った（`asset_meta`/`input_metadata`/`creative_core`/
  `diagnostics`/`performance`/`landing_page`/`views`/`_metadata`）。
  ただし`_metadata.json_schema_version`のみ、legacy側の現行固定値`"v0.2"`を
  暫定的に踏襲しているだけで、正式な復元方法は未決定のまま（下記
  `_downcast_metadata`のdocstring参照）。
  詳細は docs/plans/asset_evaluation_split_phase2_tasks.md
  「🧩 残り5ブロックのlossless/近似/埋められない分類」参照。
- 8つの downcast 部品はいずれも**まだどこからも呼ばれない**（`resolve_spec_data()`
  からは呼び出していない）。単体テストのみで個別に検証している。全ブロックが
  揃ったため、次のバッチで`resolve_spec_data`への配線に着手する想定（このバッチでは
  まだ配線しない）。

### resolve_spec_data配線について（2026-07-09時点の判断）

今回のバッチで`spec_data`の8ブロック全てのdowncast部品が揃った。それでも
ユーザーの明示指示により**今回はまだ配線しない**（「全ブロックのdowncastが揃って
から、最後に配線バッチへ進む」という方針）:

- 8つの個別downcast関数は存在するが、それらを1つの`spec_data`互換dictへ
  組み立てる統合関数（`resolve_spec_data`の「新データ変換パス」本体に相当するもの）
  はまだ実装していない。配線バッチでは、この統合関数の実装と`resolve_spec_data`
  への実配線をあわせて行う想定。
- 検討したが採用しなかった代替案（バッチ2時点から変更なし）:
  - **フラグでの部分配線**: `resolve_spec_data(..., partial_downcast=True)`の
    ようなオプトインフラグを追加し、テスト用途限定で部分downcastを試せるように
    する案。→ `asset_data`/`evaluation_data`が実運用で非Noneになる経路がまだ無い
    ため、フラグを追加してもテストの利便性以上の価値が無く、APIの複雑化
    （恒久的に使われないパラメータが残るリスク）の方が上回ると判断し、見送った。
  - **既存コードのラップによる段階導入**: `resolve_spec_data`本体は変えず、
    新しいラッパー関数（例: `resolve_spec_data_preview()`）を用意して社内検証用に
    先出しする案。→ 用途が重複するモジュール公開関数が増えるだけで、
    最終的に必要になるのは「全ブロック揃った本配線」のみのため、中間ラッパーを
    作るコストに見合うメリットが無いと判断し、見送った。
  - 結論: **配線バッチを別途設け、統合関数の実装と`resolve_spec_data`への実配線を
    まとめて行う**方針を維持する。

Phase 1実装時点の状況（変更なし）:
- `AdInsight.asset_data`/`evaluation_data` カラムはDB上に実在する
  （backend/app/models/ad_insight.py、backend/alembic/）。
  `backend/app/schemas/asset_v0.py`/`evaluation_v0.py` にv0スキーマも実装済み。
- ただし dual-write（実際にこれらのカラムへ書き込むこと）はまだ実装していない
  （Phase 3）。そのため、このモジュールを呼ぶすべての実呼び出しにおいて
  `asset_data`/`evaluation_data` は常に `None` になる。

`resolve_spec_data()` の現時点でできること・できないこと:
- spec_data のみを渡した場合（現行の全レコードがこれに該当）: 無変換でそのまま返す。
  get_spec/list_specs が行っている `record.spec_data` の直接参照と完全に同じ結果になる。
- asset_data/evaluation_data に非Noneが渡された場合: 上記のとおり実際には発生しない想定だが、
  downcast変換ロジック自体がまだ実装されていないため、エラーにはせず spec_data 側へ
  fail-soft にフォールバックし、警告ログを出す（既存の「片方だけ値がある不整合ケース」と
  同じフォールバック方針を、「変換ロジック自体が未実装」なケースにも適用したもの）。

呼び出し箇所:
- backend/app/api/routes/specs.py の get_spec/list_specs から、
  `resolve_spec_data(record.spec_data, record.asset_data, record.evaluation_data)`
  として呼び出されている（配線済み）。`asset_data`/`evaluation_data` は常に`None`のため、
  実質的には無変換パススルーとして動作する。

asset_meta の正本についての方針:
- `app.schemas.ad_insight.AssetMeta`（"legacy asset_meta"、spec_data側）と
  `app.schemas.asset_v0.AssetMetaV0`（"v0 asset_meta"、asset_data側）は別クラス。
  `AssetMetaV0`はlegacy側の全フィールドを含むスーパーセットとして設計されているため、
  legacyが引き続き唯一の実効的な正本（asset_dataは常にNoneのため）。dual-write開始後、
  両者が実際に共存するようになった時点で、このモジュールにdowncastロジック
  （legacy側を優先するか、v0側を優先するかの判定を含む）を追加する。
"""
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def resolve_spec_data(
    spec_data: Dict[str, Any],
    asset_data: Optional[Dict[str, Any]] = None,
    evaluation_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    legacy spec_data 形状（ad_insight_spec v0.2 互換）の dict を返す。

    現行 main では asset_data/evaluation_data を生成する経路が存在しないため、
    通常の呼び出しは spec_data のみを渡すことを想定する（asset_data/evaluation_data は
    将来の拡張のためのフォワード互換パラメータ）。

    - asset_data/evaluation_data が両方 None: spec_data をそのまま返す（無変換）。
    - どちらか一方でも非 None: 変換ロジックが未実装のため、警告ログを出したうえで
      spec_data へ fail-soft にフォールバックする（例外は送出しない）。
    """
    if asset_data is not None or evaluation_data is not None:
        logger.warning(
            "resolve_spec_data received non-None asset_data/evaluation_data, but the "
            "asset_data+evaluation_data -> spec_data downcast is not implemented yet "
            "(dual-write is Phase 3; no current caller should produce non-None values here). "
            "Falling back to spec_data.",
            extra={
                "has_asset_data": asset_data is not None,
                "has_evaluation_data": evaluation_data is not None,
            },
        )

    return spec_data


# ===== asset_meta / input_metadata / creative_core downcast（Phase 2、未配線） =====
#
# resolve_spec_data() からはまだ呼ばれない（モジュールdocstring「resolve_spec_data
# 配線について」参照）。単体テストは backend/tests/test_asset_evaluation_adapter.py 参照。

# v0 asset_meta（asset_v0.AssetMetaV0）が legacy asset_meta（ad_insight.AssetMeta）の
# スーパーセットとして設計されているため、legacy側が持つキーだけを転記すればよい
# （オープン課題1の解決方針どおり、null埋めは発生しない）。
_LEGACY_ASSET_META_KEYS = (
    "asset_id",
    "asset_name",
    "platform",
    "ad_account_id",
    "campaign_name",
    "adset_name",
    "ad_name",
    "analysis_period",
    "external_ids",
)


def _downcast_asset_meta(asset_meta_v0: Dict[str, Any]) -> Dict[str, Any]:
    """
    asset_data.asset_meta（AssetMetaV0形状のdict）から、legacy spec_data.asset_meta
    （AssetMeta形状のdict）を再構築する。

    AssetMetaV0はlegacy AssetMetaの全フィールドを含むスーパーセットとして設計されて
    いるため、v0専用フィールド（source_type/source_ref/created_at/analysis_version）
    を除いた残りをそのまま転記するだけでよい。値の変換・マッピングは発生しない。

    v0側に無いキー（legacy AssetMetaのキーだが asset_meta_v0 に含まれない場合）は
    出力にも含めない。呼び出し側でNone/欠損の扱いはlegacy AssetMeta側のOptional性に
    委ねる。
    """
    return {
        key: asset_meta_v0[key]
        for key in _LEGACY_ASSET_META_KEYS
        if key in asset_meta_v0
    }


def _downcast_input_metadata(asset_meta_v0: Dict[str, Any]) -> Dict[str, Any]:
    """
    asset_data.asset_meta（AssetMetaV0形状のdict）から、legacy spec_data.input_metadata
    （InputMetadata形状のdict）を再構築する。

    入力は`_downcast_asset_meta`と同じ`asset_meta_v0`dict（asset_data.asset_meta）。
    出力先のspec_dataトップレベルキーが異なるだけで、変換元は共通（docs/plans/
    asset_evaluation_split_phase2_tasks.md「🗂 6項目の保存方針比較」で確定した
    mode/file_paths=AssetMetaV0拡張という方針どおり）。

    - mode: そのまま転記（AssetMetaV0.modeは必須フィールド）
    - source_type: そのまま転記
    - input_timestamp: asset_meta_v0.created_at を転記（意味的に同じ役割）
    - file_paths: そのまま転記（無ければNone）
    - api_source: 常にNone（legacy側でも現行実装では常にNoneのため、対応する
      v0フィールドを持たない。docs/plans/asset_evaluation_split_phase2_tasks.md
      「オープン課題4・5 詳細調査」の分類③参照）
    """
    return {
        "mode": asset_meta_v0.get("mode"),
        "source_type": asset_meta_v0.get("source_type"),
        "input_timestamp": asset_meta_v0.get("created_at"),
        "file_paths": asset_meta_v0.get("file_paths"),
        "api_source": None,
    }


def _downcast_creative_core(
    media_info_v0: Dict[str, Any],
    asset_structure_v0: Dict[str, Any],
    creative_core_llm: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    asset_data.media_info + asset_data.asset_structure + evaluation_data.creative_core
    （CreativeCoreSchema形状のdict、Noneの場合あり）から、legacy spec_data.creative_core
    （CreativeCore形状のdict）を再構築する。

    - format: media_info_v0.media_type をそのまま転記（既存FormatEnumを共有しているため変換不要）
    - duration_seconds: media_info_v0.duration_seconds をそのまま転記
    - primary_text/headline/body_text/call_to_action/platform_specific: 常にNone。
      legacy側の現行実装（converter_service.py::_populate_creative_core）でも
      これらは常にNone（未実装のため）であり、downcast後もNoneのままで現行挙動と
      一致する（docs/plans/asset_evaluation_split_phase2_tasks.md
      「オープン課題4・5 詳細調査」の分類③参照）。
    - visuals/tone/ai_labels: creative_core_llm（CreativeCoreSchema形状）から転記。
      creative_core_llmがNone（evaluation_data.creative_core未設定）の場合は
      legacy側のデフォルト値に合わせる（visuals/toneはNone、ai_labelsは空リスト）。
    - ocr_extracted_text: asset_structure_v0.ocr_extracted_text を転記
      （ocr_segmentsとは別データ。asset_v0.pyのモジュールdocstring参照）。
    """
    creative_core_llm = creative_core_llm or {}
    return {
        "format": media_info_v0.get("media_type"),
        "duration_seconds": media_info_v0.get("duration_seconds"),
        "primary_text": None,
        "headline": None,
        "body_text": None,
        "call_to_action": None,
        "visuals": creative_core_llm.get("visuals"),
        "tone": creative_core_llm.get("tone"),
        "ai_labels": creative_core_llm.get("ai_labels", []),
        "platform_specific": None,
        "ocr_extracted_text": asset_structure_v0.get("ocr_extracted_text", ""),
    }


# ===== diagnostics downcast（Phase 2 downcastバッチ3、未配線） =====


def _downcast_diagnostics(
    diagnostics_v0: Dict[str, Any],
    cuts_v0: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    evaluation_data.diagnostics（Diagnostics形状のdict、既存Diagnostics型をそのまま
    再利用している）から、legacy spec_data.diagnostics を再構築する。

    Diagnosticsは型そのものが legacy と共通のため、video_cuts内の
    start_seconds/end_seconds を除く全フィールドは無変換で転記できる
    （qualitative/quantitative/improvements/improvements_error/decision_support/
    decision_support_error/llm_model/llm_success/llm_retry_count/llm_error/
    video_cutsのcut_id・role_tag・summary等）。

    video_cuts.video_cuts[].start_seconds/end_secondsのみ、evaluation_data側では
    意図的にNoneのまま保持する設計（オープン課題2の解決方針）のため、
    asset_data.asset_structure.cuts（CutSpan形状、cuts_v0引数）から cut_id で
    突き合わせて補完する。

    - diagnostics_v0.video_cutsがNone、または video_cuts.video_cuts が空の場合:
      補完対象がないためそのまま返す。
    - cut_idが cuts_v0 内に見つかった場合: start_seconds/end_secondsを
      CutSpan.start_sec/end_secで上書きする。
    - cut_idが cuts_v0 内に見つからない場合: 補完せず既存値（Noneのはず）のまま
      残す（fail-soft。架空の時間範囲を捏造しない）。

    入力dict（diagnostics_v0・cuts_v0の各要素）は変更しない（新しいdictを構築して返す）。
    """
    cuts_v0 = cuts_v0 or []
    cuts_by_id = {cut["cut_id"]: cut for cut in cuts_v0 if "cut_id" in cut}

    result = dict(diagnostics_v0)
    video_cuts_block = result.get("video_cuts")
    if not video_cuts_block or not video_cuts_block.get("video_cuts"):
        return result

    merged_cuts = []
    for cut in video_cuts_block["video_cuts"]:
        merged_cut = dict(cut)
        matched_cut = cuts_by_id.get(merged_cut.get("cut_id"))
        if matched_cut is not None:
            merged_cut["start_seconds"] = matched_cut.get("start_sec")
            merged_cut["end_seconds"] = matched_cut.get("end_sec")
        merged_cuts.append(merged_cut)

    result["video_cuts"] = {**video_cuts_block, "video_cuts": merged_cuts}
    return result


# ===== performance / landing_page / views / _metadata downcast（Phase 2 downcastバッチ4、未配線） =====


def _downcast_performance(performance_v0: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    evaluation_data.performance（Performance形状のdict、既存Performance型をそのまま
    再利用している）から、legacy spec_data.performance を再構築する。

    `EvaluationJsonV0.performance`は`app.schemas.ad_insight.Performance`をそのまま
    再利用しているため、変換ロジックは不要な恒等写像（identity）。Noneの場合も
    legacy側がOptionalのため、そのままNoneを返す。
    """
    return performance_v0


def _downcast_landing_page(landing_page_v0: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    evaluation_data.landing_page_analysis（LandingPage形状のdict、既存LandingPage型を
    そのまま再利用している）から、legacy spec_data.landing_page を再構築する。

    `EvaluationJsonV0.landing_page_analysis`は`app.schemas.ad_insight.LandingPage`を
    そのまま再利用しているため、変換ロジックは不要な恒等写像（identity）。
    出力先のspec_dataトップレベルキー名が`landing_page_analysis`→`landing_page`と
    変わるだけで、値自体は無変換。
    """
    return landing_page_v0


def _downcast_views() -> Dict[str, Any]:
    """
    legacy spec_data.views を再構築する。

    **重要**: `views`はasset_data/evaluation_dataいずれの実データも必要としない。
    現行legacyパイプライン（`converter_service.py::_populate_views`）を実地調査した
    結果（docs/plans/asset_evaluation_split_phase2_tasks.md「🧩 残り5ブロックの
    lossless/近似/埋められない分類」参照）、ほぼ全フィールドがハードコードされた
    固定値であることが判明した（`status_label`は常に`"Good"`、`status_color`は常に
    `"#FFAA00"`等）。唯一動的に見える`recommended_actions_display`も
    `llm_result.get("recommendations", [])`を参照するが、そのキーをどのサービスも
    実際には設定していないため常に空リストになる。

    このため本関数は引数を取らず、legacy側の現行出力と完全に一致する固定値dictを
    返すだけでよい。

    **注意（将来のメンテナンス）**: `converter_service.py::_populate_views`の実装が
    将来変更された場合（例: `recommended_actions_display`が実データ化される等）、
    この関数も追従して更新する必要がある。追従を忘れると、legacy書き込みパス
    （dual-write実装後）とこのdowncast関数の出力が乖離する。
    """
    return {
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


def _downcast_metadata(
    asset_meta_v0: Dict[str, Any],
    evaluation_meta_v0: Dict[str, Any],
) -> Dict[str, Any]:
    """
    asset_data.asset_meta + evaluation_data.evaluation_meta から、
    legacy spec_data._metadata を再構築する（オープン課題3の解決方針: 取り込み時に
    確定する情報はasset_meta側、評価実行時に確定する情報はevaluation_meta側から
    復元する）。

    - generated_at: asset_meta_v0.created_at から転記
    - data_source: asset_meta_v0.source_type から転記
    - input_mode: asset_meta_v0.mode から転記（Phase 2バッチ2で解決済み）
    - ai_model_version: evaluation_meta_v0.evaluator_model から転記
    - processing_time_ms / validation_status / validation_notes / analysis_tools_used:
      evaluation_meta_v0 からそのまま転記

    **json_schema_version は未決（このブロックで唯一の残課題）**: legacy側は
    `converter_service.py::_populate_metadata`で常に固定値`"v0.2"`を書き込んでいる
    （動的に決定されるロジックは無い）。本関数も現時点ではその固定値をそのまま
    踏襲し、legacy側の現行出力と一致させている。ただしこれは正式なスキーマ
    バージョニング戦略ではなく、暫定対応である。将来的に`asset_data`/
    `evaluation_data`側でスキーマバージョンを独自に管理するようになった場合
    （例: `AssetMetaV0.analysis_version`から導出する等）は、この固定値を見直す
    必要がある。
    """
    return {
        "generated_at": asset_meta_v0.get("created_at"),
        "data_source": asset_meta_v0.get("source_type"),
        "ai_model_version": evaluation_meta_v0.get("evaluator_model"),
        "json_schema_version": "v0.2",  # 未決、上記docstring参照
        "input_mode": asset_meta_v0.get("mode"),
        "analysis_tools_used": evaluation_meta_v0.get("analysis_tools_used"),
        "processing_time_ms": evaluation_meta_v0.get("processing_time_ms"),
        "validation_status": evaluation_meta_v0.get("validation_status"),
        "validation_notes": evaluation_meta_v0.get("validation_notes"),
    }
