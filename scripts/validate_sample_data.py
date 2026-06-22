"""
Validate sample data against Pydantic schemas.

Usage:
    python scripts/validate_sample_data.py
"""
import json
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.schemas.ad_insight import AdInsight


def validate_sample_file(filepath: str) -> dict:
    """
    Validate a single JSON sample file.
    
    Args:
        filepath: Path to JSON file
    
    Returns:
        dict with keys: filename, valid, data (if valid), errors (if invalid)
    """
    filepath = Path(filepath)
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Validate with Pydantic
        validated = AdInsight(**data)
        
        return {
            "filename": filepath.name,
            "valid": True,
            "data": validated,
            "errors": None
        }
    
    except FileNotFoundError:
        return {
            "filename": filepath.name,
            "valid": False,
            "errors": f"File not found: {filepath}"
        }
    
    except json.JSONDecodeError as e:
        return {
            "filename": filepath.name,
            "valid": False,
            "errors": f"JSON parse error: {str(e)}"
        }
    
    except Exception as e:
        return {
            "filename": filepath.name,
            "valid": False,
            "errors": f"Validation error: {str(e)}"
        }


def main():
    """Run validation on all sample data files."""
    sample_dir = Path(__file__).parent.parent / "sample_data"
    
    if not sample_dir.exists():
        print(f"❌ sample_data directory not found: {sample_dir}")
        return 1
    
    # Find all JSON files
    json_files = list(sample_dir.glob("*.json"))
    
    if not json_files:
        print(f"⚠️  No JSON files found in {sample_dir}")
        return 0
    
    print(f"🔍 Validating {len(json_files)} sample files...\n")
    
    results = []
    for json_file in sorted(json_files):
        result = validate_sample_file(str(json_file))
        results.append(result)
        
        status = "✅" if result["valid"] else "❌"
        print(f"{status} {result['filename']}")
        
        if not result["valid"]:
            print(f"   Error: {result['errors']}\n")
        else:
            print(f"   ✓ Valid AdInsight (ad_id: {result['data'].asset_meta.ad_id})\n")
    
    # Summary
    valid_count = sum(1 for r in results if r["valid"])
    total_count = len(results)
    
    print("-" * 60)
    print(f"📊 Summary: {valid_count}/{total_count} files valid")
    
    if valid_count == total_count:
        print("✅ All sample data is valid!")
        return 0
    else:
        print(f"❌ {total_count - valid_count} file(s) failed validation")
        return 1


if __name__ == "__main__":
    sys.exit(main())
