#!/usr/bin/env python3
import sys
import logging

# PYTHONPATH を通して実行されることを前提とする
try:
    from app.config import get_settings
except ImportError:
    print("Error: 'app' module not found. Make sure to run this script from the project root or with PYTHONPATH=backend", file=sys.stderr)
    sys.exit(1)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

def mask_value(val: str, show_chars: int = 4) -> str:
    """機密情報の平文出力を防ぐためのマスク処理"""
    if not val:
        return "<Not Set or Empty>"
    val_str = str(val)
    if len(val_str) <= show_chars:
        return "***"
    return val_str[:show_chars] + "*" * (len(val_str) - show_chars)

def run_smoke_test():
    """環境変数および設定の Smoke Test を実行する"""
    logger.info("Starting Environment Smoke Test...")
    
    try:
        settings = get_settings()
    except Exception as e:
        logger.error(f"Failed to load settings: {e}")
        sys.exit(1)

    errors = []

    # --- 1. 絶対必須項目のチェック ---
    required_keys = ["OPENAI_API_KEY"]
    for key in required_keys:
        val = getattr(settings, key, None)
        if not val:
            errors.append(f"Missing required environment variable: {key}")
        else:
            logger.info(f"[OK] {key} is set (Value: {mask_value(val)})")

    # --- 2. 任意/条件付き項目のチェック ---
    optional_keys = ["GEMINI_API_KEY", "DATABASE_URL"]
    for key in optional_keys:
        val = getattr(settings, key, None)
        status = "Present" if val else "Not Set (Optional)"
        logger.info(f"[INFO] {key}: {status} (Value: {mask_value(val)})")

    # 結果判定
    if errors:
        logger.error("Environment Smoke Test FAILED with the following errors:")
        for err in errors:
            logger.error(f"  - {err}")
        sys.exit(1)
    
    logger.info("Environment Smoke Test PASSED. All required settings are properly configured.")
    sys.exit(0)

if __name__ == "__main__":
    run_smoke_test()
