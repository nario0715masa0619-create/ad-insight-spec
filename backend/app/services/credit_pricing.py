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
    "file_plus_lp_plus_manual_kpi": "heavy",
}

_DEFAULT_TIER = "light"


def credit_cost_for_mode(mode: str, settings: Optional[Settings] = None) -> int:
    """
    分析モードに応じた消費クレジット数を返す。

    値そのものはハードコードせず app.config.Settings（環境変数
    CREDIT_COST_LIGHT/STANDARD/HEAVY）から都度読む。運用中に消費量を
    調整したい場合、コード変更・再デプロイなしで環境変数の変更のみで
    対応できる（管理画面はまだ用意していないため、今回はこの粒度に留める）。
    """
    settings = settings or get_settings()
    tier = _MODE_TO_TIER.get(mode, _DEFAULT_TIER)
    return {
        "light": settings.CREDIT_COST_LIGHT,
        "standard": settings.CREDIT_COST_STANDARD,
        "heavy": settings.CREDIT_COST_HEAVY,
    }[tier]
