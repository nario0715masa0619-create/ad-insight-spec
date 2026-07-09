"""
asset_data / evaluation_data → legacy spec_data の read adapter（Phase 2）。

設計の背景・変換方針は docs/plans/asset_evaluation_split_phase2_tasks.md を参照。

現状（2026-07-09、Phase 1実装後）:
- `AdInsight.asset_data`/`evaluation_data` カラムはDB上に実在する
  （backend/app/models/ad_insight.py、backend/alembic/）。
  `backend/app/schemas/asset_v0.py`/`evaluation_v0.py` にv0スキーマも実装済み。
- ただし dual-write（実際にこれらのカラムへ書き込むこと）はまだ実装していない
  （Phase 3）。そのため、このモジュールを呼ぶすべての実呼び出しにおいて
  `asset_data`/`evaluation_data` は常に `None` になる。
- このモジュール自体の downcast変換ロジック（`asset_data + evaluation_data → spec_data`）
  はまだ実装していない。dual-writeが始まり実際に非Noneの値が渡されるようになった時点で
  実装する。

現時点でできること・できないこと:
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
