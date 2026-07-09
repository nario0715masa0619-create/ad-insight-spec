"""
asset_data / evaluation_data → legacy spec_data の read adapter（Phase 2）。

設計の背景・変換方針は docs/plans/asset_evaluation_split_phase2_tasks.md を参照。

現状（2026-07-09、Phase 2 downcast第一バッチ）:
- `resolve_spec_data()` の公開挙動は Phase 1 実装時から変更していない
  （asset_data/evaluation_data が非Noneでもfail-softにspec_dataへフォールバックする）。
- 完全な downcast（`asset_data + evaluation_data → spec_data`）はまだ実装できない。
  `AssetJsonV0`/`EvaluationJsonV0`（asset_v0.py/evaluation_v0.py）には、legacy
  `spec_data.input_metadata`・`spec_data.creative_core`の自由文/分析系フィールド
  （primary_text/headline/body_text/call_to_action/visuals/tone/ai_labels/
  platform_specific/ocr_extracted_text等）に対応する変換元データが存在しない
  （docs/plans/asset_evaluation_split_phase2_tasks.md の「オープン課題4・5」参照）。
  これらの住み処が決まるまで、完全なdowncastの実装・`resolve_spec_data`への配線は
  行わない（一気に全wiringはしない、というスコープ制約）。
- 今回追加したのは、変換元データが完全に揃っている部分（`asset_meta`）のみを
  対象にした、**まだどこからも呼ばれない**独立した downcast 部品
  `_downcast_asset_meta()` のみ。`resolve_spec_data()`からは呼び出していない
  （呼び出すには他のキー、特に`input_metadata`/`creative_core`が埋まらないと
  中途半端な`spec_data`になってしまうため）。

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


# ===== asset_meta downcast（Phase 2 downcast第一バッチ、未配線） =====
#
# 変換元データが完全に揃っている asset_meta のみを対象にした最小の downcast 部品。
# resolve_spec_data() からはまだ呼ばれない（モジュールdocstring参照）。
# 単体テストは backend/tests/test_asset_evaluation_adapter.py 参照。

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
