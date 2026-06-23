"""
Ad-Insight-Spec v0.2 - End-to-End Validation
Validates the complete pipeline for the three main input modes.
"""

import sys
import os
from pathlib import Path
from datetime import datetime
import json

# Add backend to path
backend_path = Path(__file__).parent.parent / "backend"
sys.path.append(str(backend_path))

from app.services.analysis_orchestrator import AnalysisOrchestrator
from app.schemas.ad_insight import InputModeEnum

# Sample data paths
SAMPLE_DATA_DIR = Path(__file__).parent.parent / "sample_data"
TEST_IMAGE = str(SAMPLE_DATA_DIR / "test_image.png")
TEST_LP = str(SAMPLE_DATA_DIR / "test_lp.html")
TEST_KPI = str(SAMPLE_DATA_DIR / "test_kpi.json")


def print_header(title):
    print("=" * 80)
    print(title)
    print("=" * 80)


def run_e2e_tests():
    print_header("Ad-Insight-Spec v0.2 - End-to-End Validation")
    start_time = datetime.now()
    print(f"Start: {start_time.isoformat()}")
    
    passed_tests = 0
    total_tests = 3
    
    # Test 1: file_only
    print_header("Test 1: file_only mode")
    print(f"Input: {TEST_IMAGE}")
    print("Mode: file_only")
    print("Expected: landing_page=null, performance=null\n")
    
    try:
        orch_1 = AnalysisOrchestrator(
            input_path=TEST_IMAGE,
            mode="file_only"
        )
        spec_1 = orch_1.run()
        
        # Validation
        assert spec_1["input_metadata"]["mode"] == "file_only"
        assert spec_1.get("landing_page") is None
        assert spec_1.get("performance") is None
        assert spec_1["diagnostics"]["qualitative"] is not None
        assert spec_1["diagnostics"]["quantitative"] is None
        
        print("✅ PASSED")
        print(f"   Asset ID: {spec_1['asset_meta']['asset_id']}")
        print(f"   Mode: {spec_1['input_metadata']['mode']}")
        print("   Landing Page: None")
        print("   Performance: None\n")
        passed_tests += 1
    except Exception as e:
        print(f"❌ FAILED: {str(e)}\n")
        import traceback
        traceback.print_exc()

    # Test 2: file_plus_lp
    print_header("Test 2: file_plus_lp mode")
    print(f"Input: {TEST_IMAGE}")
    print(f"LP: {TEST_LP}")
    print("Mode: file_plus_lp")
    print("Expected: landing_page populated, performance=null\n")
    
    try:
        orch_2 = AnalysisOrchestrator(
            input_path=TEST_IMAGE,
            lp_input=TEST_LP,
            mode="file_plus_lp"
        )
        spec_2 = orch_2.run()
        
        # Validation
        assert spec_2["input_metadata"]["mode"] == "file_plus_lp"
        assert spec_2.get("landing_page") is not None
        assert spec_2["landing_page"]["message_consistency"]["match_score"] is not None
        assert spec_2.get("performance") is None
        assert spec_2["diagnostics"]["quantitative"] is None
        
        print("✅ PASSED")
        print(f"   Asset ID: {spec_2['asset_meta']['asset_id']}")
        print(f"   Mode: {spec_2['input_metadata']['mode']}")
        print(f"   Landing Page: {spec_2['landing_page']['url']}")
        print(f"   Message Consistency Score: {spec_2['landing_page']['message_consistency']['match_score']}\n")
        passed_tests += 1
    except Exception as e:
        print(f"❌ FAILED: {str(e)}\n")
        import traceback
        traceback.print_exc()

    # Test 3: file_plus_lp_plus_manual_kpi
    print_header("Test 3: file_plus_lp_plus_manual_kpi mode")
    print(f"Input: {TEST_IMAGE}")
    print(f"LP: {TEST_LP}")
    print(f"KPI: {TEST_KPI}")
    print("Mode: file_plus_lp_plus_manual_kpi")
    print("Expected: landing_page + performance populated + quantitative diagnostics\n")
    
    try:
        orch_3 = AnalysisOrchestrator(
            input_path=TEST_IMAGE,
            lp_input=TEST_LP,
            kpi_path=TEST_KPI,
            mode="file_plus_lp_plus_manual_kpi"
        )
        spec_3 = orch_3.run()
        
        # Validation
        assert spec_3["input_metadata"]["mode"] == "file_plus_lp_plus_manual_kpi"
        assert spec_3.get("landing_page") is not None
        assert spec_3.get("performance") is not None
        assert spec_3["performance"]["ctr"] is not None
        assert spec_3["diagnostics"]["quantitative"] is not None
        assert spec_3["diagnostics"]["quantitative"]["performance_status"] is not None
        
        print("✅ PASSED")
        print(f"   Asset ID: {spec_3['asset_meta']['asset_id']}")
        print(f"   Mode: {spec_3['input_metadata']['mode']}")
        print(f"   Impressions: {spec_3['performance'].get('impressions')}")
        print(f"   Clicks: {spec_3['performance'].get('clicks')}")
        print(f"   CTR: {spec_3['performance'].get('ctr')}")
        print(f"   Conversions: {spec_3['performance'].get('conversions')}")
        print(f"   Performance Status: {spec_3['diagnostics']['quantitative']['performance_status']}\n")
        passed_tests += 1
    except Exception as e:
        print(f"❌ FAILED: {str(e)}\n")
        import traceback
        traceback.print_exc()

    # Summary
    print_header("SUMMARY")
    print(f"Total Tests: {total_tests}")
    print(f"Passed: {passed_tests}")
    print(f"Failed: {total_tests - passed_tests}")
    
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    print(f"Duration: {duration:.2f}s\n")
    
    if passed_tests == total_tests:
        print("🎉 All tests passed!")
    else:
        print("⚠️ Some tests failed.")
        sys.exit(1)
    
    print(f"End: {end_time.isoformat()}")
    print("=" * 80)

if __name__ == "__main__":
    run_e2e_tests()
