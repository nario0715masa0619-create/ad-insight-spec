import requests
import json
import time

API_BASE_URL = "http://127.0.0.1:8000/api/v1/specs"
SAMPLE_IMAGE = "backend/sample_data/test_image.png"

def test_llm_integration_gpt():
    """Test 7: LLM 統合（GPT）"""
    print("\n=== Test 7: LLM 統合（GPT） ===")
    
    with open(SAMPLE_IMAGE, 'rb') as f:
        files = {"input_file": f}
        data = {"mode": "file_only"}
        response = requests.post(f"{API_BASE_URL}/analyze", files=files, data=data)
    
    if response.status_code != 200:
        print(f"❌ FAILED: {response.status_code}")
        print(response.text)
        return False
    
    result = response.json()
    
    # CreativeCore 検証
    creative_core = result.get("creative_core", {})
    if not creative_core.get("visuals") or not creative_core.get("tone"):
        print("❌ FAILED: CreativeCore missing")
        return False
    
    # LLM メタデータ検証
    diagnostics = result.get("diagnostics", {})
    if not diagnostics.get("llm_model") or not diagnostics.get("llm_success"):
        print("❌ FAILED: LLM metadata missing")
        return False
    
    print(f"✅ PASSED")
    print(f"   Model: {diagnostics['llm_model']}")
    print(f"   Success: {diagnostics['llm_success']}")
    print(f"   Retries: {diagnostics['llm_retry_count']}")
    return True

def test_llm_integration_gemini():
    """Test 8: LLM 統合（Gemini）"""
    print("\n=== Test 8: LLM 統合（Gemini） ===")
    
    # 環境変数で Gemini に切り替え
    import os
    os.environ["LLM_MODEL"] = "gemini"
    
    with open(SAMPLE_IMAGE, 'rb') as f:
        files = {"input_file": f}
        data = {"mode": "file_only"}
        response = requests.post(f"{API_BASE_URL}/analyze", files=files, data=data)
    
    if response.status_code != 200:
        print(f"❌ FAILED: {response.status_code}")
        print(response.text)
        return False
    
    result = response.json()
    
    # CreativeCore 検証
    creative_core = result.get("creative_core", {})
    if not creative_core.get("visuals") or not creative_core.get("tone"):
        print("❌ FAILED: CreativeCore missing")
        return False
    
    # LLM メタデータ検証
    diagnostics = result.get("diagnostics", {})
    if not diagnostics.get("llm_model") or not diagnostics.get("llm_success"):
        print("❌ FAILED: LLM metadata missing")
        return False
    
    print(f"✅ PASSED")
    print(f"   Model: {diagnostics['llm_model']}")
    print(f"   Success: {diagnostics['llm_success']}")
    print(f"   Retries: {diagnostics['llm_retry_count']}")
    
    # 環境変数をリセット
    os.environ["LLM_MODEL"] = "gpt"
    return True

def test_json_quality():
    """Test 9: JSON 品質確認"""
    print("\n=== Test 9: JSON 品質確認 ===")
    
    with open(SAMPLE_IMAGE, 'rb') as f:
        files = {"input_file": f}
        data = {"mode": "file_only"}
        response = requests.post(f"{API_BASE_URL}/analyze", files=files, data=data)
    
    if response.status_code != 200:
        print(f"❌ FAILED: {response.status_code}")
        print(response.text)
        return False
    
    result = response.json()
    
    # 必須フィールド検証
    required_fields = [
        "input_metadata", "asset_meta", "creative_core", 
        "landing_page", "performance", "diagnostics"
    ]
    
    for field in required_fields:
        if field not in result:
            print(f"❌ FAILED: Missing field {field}")
            return False
    
    # CreativeCore 構造検証
    cc = result["creative_core"]
    if not all(k in cc for k in ["visuals", "tone", "ai_labels"]):
        print("❌ FAILED: CreativeCore structure invalid")
        return False
    
    if not all(k in cc["visuals"] for k in ["dominant_colors", "composition", "style", "clarity"]):
        print("❌ FAILED: Visuals structure invalid")
        return False
    
    if not all(k in cc["tone"] for k in ["primary_tone", "emotional_appeal", "call_to_action"]):
        print("❌ FAILED: Tone structure invalid")
        return False
    
    print(f"✅ PASSED")
    print(f"   Required fields: 6/6 ✓")
    print(f"   CreativeCore structure: valid ✓")
    print(f"   Visuals fields: 4/4 ✓")
    print(f"   Tone fields: 3/3 ✓")
    return True

if __name__ == "__main__":
    print("=" * 60)
    print("Phase 2c-3 E2E テスト（LLM 統合）")
    print("=" * 60)
    
    results = []
    results.append(("Test 7: LLM 統合（GPT）", test_llm_integration_gpt()))
    time.sleep(2)
    results.append(("Test 8: LLM 統合（Gemini）", test_llm_integration_gemini()))
    time.sleep(2)
    results.append(("Test 9: JSON 品質確認", test_json_quality()))
    
    print("\n" + "=" * 60)
    print("テスト結果サマリー")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{name}: {status}")
    
    print(f"\n合計: {passed}/{total} PASSED")
    
    if passed == total:
        print("\n🎉 All tests passed!")
        exit(0)
    else:
        print(f"\n⚠️ {total - passed} test(s) failed")
        exit(1)
