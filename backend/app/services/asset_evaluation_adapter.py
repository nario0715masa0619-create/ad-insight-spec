"""
asset_data / evaluation_data → legacy spec_data の read adapter（Phase 2 最初のステップ）。

設計の背景は docs/plans/asset_evaluation_split_phase2_tasks.md を参照。ただし同ドキュメントは
「Phase 1（AdInsight.asset_data/evaluation_data カラム追加）が別ブランチで実装済み」という
前提で書かれている。そのPhase 1（Antigravity側のローカルPoC）は公式リポジトリには一切
反映しないことになったため、現行 main の `AdInsight` モデルには asset_data/evaluation_data
カラムは存在しない。

このモジュールは、その前提差分を踏まえて「まずは spec_data のみから legacy spec を組み立てる
インターフェース」を用意し、将来 asset_data/evaluation_data が実際に導入された時にそのまま
拡張できる形にすることを目的にする。

現時点でできること・できないこと:
- spec_data のみを渡した場合（現行の全レコードがこれに該当）: 無変換でそのまま返す。
  get_spec/list_specs が現在行っている `record.spec_data` の直接参照と完全に同じ結果になる。
- asset_data/evaluation_data を渡した場合: このリポジトリには変換元となる AssetJsonV0/
  EvaluationJsonV0 スキーマも、それらを生成する書き込みパスも存在しないため、実際の downcast
  変換はまだ実装しない。誤って非Noneが渡された場合はエラーにはせず、spec_data 側へ
  fail-soft にフォールバックし、警告ログを出す（既存の「片方だけ値がある不整合ケース」と
  同じフォールバック方針を、「変換ロジック自体が未実装」なケースにも適用したもの）。

呼び出し箇所についての方針:
- このコミットでは backend/app/api/routes/specs.py の get_spec/list_specs 側の呼び出しは
  まだ組み込まない（DBスキーマ・保存ロジックを変えないというPhase 2最初のコミットのスコープ
  制約のため）。将来組み込む際は、`record.spec_data` を直接使っている箇所を
  `resolve_spec_data(record.spec_data)` に置き換えるだけで、現状の全レコード（spec_dataのみ）
  については挙動が1バイトも変わらない。

asset_meta の正本についての方針:
- 現行 main には v0 系の AssetMeta（Antigravity PoC の `AssetMetaV0`）は存在しない。
  したがって `app.schemas.ad_insight.AssetMeta`（"legacy asset_meta"）が唯一の正本であり、
  このモジュールは asset_meta に関して何の変換も行わない。将来 asset_data が実際に導入され、
  legacy/v0 の2つの asset_meta 表現が共存するようになった時点で、どちらを正本とするかの
  判定ロジックをここに追加する。
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
            "(Phase 1 columns do not exist on this repo's AdInsight model). "
            "Falling back to spec_data.",
            extra={
                "has_asset_data": asset_data is not None,
                "has_evaluation_data": evaluation_data is not None,
            },
        )

    return spec_data
