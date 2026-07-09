"""
asset_data / evaluation_data → legacy spec_data の read adapter（Phase 2）。

設計の背景・変換方針は docs/plans/asset_evaluation_split_phase2_tasks.md を参照。

現状（2026-07-09、Phase 2 downcastバッチ2）:
- `resolve_spec_data()` の公開挙動は Phase 1 実装時から**変更していない**
  （asset_data/evaluation_data が非Noneでもfail-softにspec_dataへフォールバックする）。
  今回のバッチでもwiringは行わない（理由は下記「resolve_spec_data配線について」）。
- downcast第一バッチ（`_downcast_asset_meta`）に続き、バッチ2で
  `_downcast_input_metadata()`・`_downcast_creative_core()`を追加した。
  これでカバーされるのは`spec_data`の`asset_meta`/`input_metadata`/`creative_core`の
  3ブロック（オープン課題4・5で特定した6つの真のブロッカー全て：mode/file_paths/
  visuals/tone/ai_labels/ocr_extracted_text を含む）。
  ただし`diagnostics`（video_cutsのcut_id補完含む）/`performance`/`landing_page`/
  `views`/`_metadata`のdowncastロジックはまだ実装していないため、**依然として
  完全なdowncastはできない**。
- 3つの downcast 部品はいずれも**まだどこからも呼ばれない**（`resolve_spec_data()`
  からは呼び出していない）。単体テストのみで個別に検証している。

### resolve_spec_data配線について（2026-07-09時点の判断）

今回のバッチで新たに3ブロック分（asset_meta/input_metadata/creative_core）の
downcastが揃ったが、`spec_data`の残り5ブロック（diagnostics/performance/
landing_page/views/_metadata）はまだdowncastできない。そのため:

- **配線しない**: 仮に今`resolve_spec_data`に配線すると、`asset_data`/
  `evaluation_data`が非Noneの場合に「一部のキーだけ埋まった不完全な`spec_data`」
  を返すことになる。これは現行のfail-softフォールバック（`spec_data`をそのまま
  返す）よりも危険（呼び出し側が「diagnosticsが無い＝分析未実施」等の誤判定を
  する可能性がある）。全ブロックのdowncastが揃うまでは、配線しない方が安全。
- 検討したが採用しなかった代替案:
  - **フラグでの部分配線**: `resolve_spec_data(..., partial_downcast=True)`の
    ようなオプトインフラグを追加し、テスト用途限定で部分downcastを試せるように
    する案。→ 現時点では`asset_data`/`evaluation_data`が実運用で非Noneになる
    経路が無いため、フラグを追加してもテストの利便性以上の価値が無く、
    APIの複雑化（恒久的に使われないパラメータが残るリスク）の方が上回ると判断し、
    見送った。
  - **既存コードのラップによる段階導入**: `resolve_spec_data`本体は変えず、
    新しいラッパー関数（例: `resolve_spec_data_preview()`）を用意して社内検証用に
    先出しする案。→ 用途が重複するモジュール公開関数が増えるだけで、
    最終的に必要になるのは「全ブロック揃った本配線」のみのため、中間ラッパーを
    作るコストに見合うメリットが無いと判断し、見送った。
  - 結論: **全ブロックのdowncastが揃った時点で、一度にresolve_spec_dataへ配線する**
    方針を維持する（既存の「一気に全wiringはしない」制約は、downcast部品の実装
    バッチ単位についての制約であり、配線自体は完全性が確認できてから一括で行う）。

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
from typing import Any, Dict, Optional

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
