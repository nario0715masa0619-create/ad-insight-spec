from typing import Optional

from app.config import Settings, get_settings

# /analyze の mode パラメータ（既存の3モード）を、クレジット消費の3段階
# （Light/Standard/Heavy）にそのまま対応させる。この分析ツールでは
# クリエイティブ単体の分析が常に発生し、LP・KPIが追加の層として乗る構造の
# ため、「入力が増えるほど処理・提供価値が増す」という設計方針
# （campaignpilot_credit_billing_design参照）を、追加される入力の数でそのまま
# 表現できる。将来、比較分析等の新モードが増えた場合はここに追記する。
_MODE_TO_TIER = {
    "file_only": "light",
    "file_plus_lp": "standard",
    # LPなし・クリエイティブ+KPI(CSV/JSON)のみの「広告面分析」。file_plus_lpと
    # 同じく「クリエイティブに1層追加」の構成のためstandard扱いとする。
    "file_plus_kpi": "standard",
    "file_plus_lp_plus_manual_kpi": "heavy",
}

_DEFAULT_TIER = "light"

# /analyze が受け付ける既知のmode一覧（credit_cost_for_mode()の対応表と同じ
# ソースから導出し、二重管理を避ける）。呼び出し側(specs.py)がリクエストの
# mode を早期に検証する際の判定に使う。credit_cost_for_mode() 自体は
# 未知のmodeに対して例外を投げず light 扱いにフォールバックする設計を維持する
# （このモジュールは「costを引く」ことだけに責務を絞り、"未知のmodeを拒否する"
# というAPI入力バリデーションの責務は境界であるspecs.py側に置く）。
VALID_ANALYZE_MODES = frozenset(_MODE_TO_TIER.keys())


def credit_cost_for_mode(mode: str, settings: Optional[Settings] = None) -> int:
    """
    分析モードに応じた消費クレジット数を返す。

    値そのものはハードコードせず app.config.Settings（環境変数
    CREDIT_COST_LIGHT/STANDARD/HEAVY）から都度読む。運用中に消費量を
    調整したい場合、コード変更・再デプロイなしで環境変数の変更のみで
    対応できる（管理画面はまだ用意していないため、今回はこの粒度に留める）。

    未知のmodeは例外を投げずLightティア扱いにフォールバックする
    （呼び出し側で未知のmodeを弾きたい場合は VALID_ANALYZE_MODES を使うこと。
    例: backend/app/api/routes/specs.py::analyze()）。
    """
    settings = settings or get_settings()
    tier = _MODE_TO_TIER.get(mode, _DEFAULT_TIER)
    return {
        "light": settings.CREDIT_COST_LIGHT,
        "standard": settings.CREDIT_COST_STANDARD,
        "heavy": settings.CREDIT_COST_HEAVY,
    }[tier]
