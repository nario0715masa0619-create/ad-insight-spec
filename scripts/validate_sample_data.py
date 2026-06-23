"""
Sample Data Validation Script
3つのサンプルJSONが Pydantic v0.2 スキーマに準拠しているか検証
"""

import json
import sys
from pathlib import Path
from datetime import datetime

# Pydantic モデルをインポート（実装後）
try:
    from app.schemas.ad_insight import AdInsightSpec, InputModeEnum
except ImportError:
    print("❌ Error: app.schemas.ad_insight not found. Install backend dependencies first.")
    sys.exit(1)


def validate_sample(file_path: str, expected_mode: str) -> bool:
    """サンプルJSONを検証"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Pydantic バリデーション (alias _metadata is automatically parsed)
        spec = AdInsightSpec(**data)

        # モード確認
        actual_mode = spec.input_metadata.mode.value
        if actual_mode != expected_mode:
            print(f"❌ Mode mismatch: expected {expected_mode}, got {actual_mode}")
            return False

        print(f"✅ {file_path}")
        print(f"   Mode: {actual_mode}")
        print(f"   Generated: {spec.metadata.generated_at}")
        print(f"   Asset ID: {spec.asset_meta.asset_id}")
        print(f"   Creative Fatigue: {spec.diagnostics.qualitative.creative_fatigue_risk}")
        if spec.diagnostics.quantitative:
            print(f"   Performance Status: {spec.diagnostics.quantitative.performance_status}")
        print()
        return True

    except Exception as e:
        print(f"❌ {file_path}")
        print(f"   Error: {str(e)}")
        print()
        return False


def main():
    """メイン検証処理"""
    base_path = Path(__file__).parent.parent / "sample_data"

    samples = [
        (
            base_path / "file_only" / "sample_file_only.json",
            "file_only"
        ),
        (
            base_path / "file_plus_lp" / "sample_file_plus_lp.json",
            "file_plus_lp"
        ),
        (
            base_path / "file_plus_lp_plus_manual_kpi" / "sample_file_plus_lp_plus_manual_kpi.json",
            "file_plus_lp_plus_manual_kpi"
        ),
    ]

    print("=" * 80)
    print("Ad-Insight-Spec v0.2 Sample Data Validation")
    print("=" * 80)
    print()

    results = []
    for file_path, expected_mode in samples:
        if not file_path.exists():
            print(f"⚠️  {file_path} not found (skipped)")
            results.append(False)
        else:
            results.append(validate_sample(str(file_path), expected_mode))

    print("=" * 80)
    print(f"Results: {sum(results)}/{len(results)} passed")
    print("=" * 80)

    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
