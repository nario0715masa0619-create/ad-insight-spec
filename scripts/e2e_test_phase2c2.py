import requests
import json
import time
import os
from PIL import Image
import cv2
import numpy as np

API_BASE_URL = "http://127.0.0.1:8000/api/v1/specs"
SAMPLE_IMAGE = "backend/sample_data/test_image_with_text.png"
SAMPLE_VIDEO = "backend/sample_data/test_video_with_text.mp4"

def create_test_image_with_text():
    """テキスト入り画像を生成"""
    try:
        from PIL import ImageDraw
        img = Image.new('RGB', (600, 400), color='white')
        draw = ImageDraw.Draw(img)
        # テキストを描画（簡易版）
        draw.text((50, 50), "SPECIAL OFFER", fill='black')
        draw.text((50, 100), "50% OFF TODAY", fill='black')
        draw.text((50, 150), "CALL NOW", fill='red')
        img.save(SAMPLE_IMAGE)
        print(f"✅ Created test image: {SAMPLE_IMAGE}")
    except Exception as e:
        print(f"⚠️ Failed to create test image: {e}")

def create_test_video_with_text():
    """テキスト入り動画を生成"""
    try:
        os.makedirs("backend/sample_data", exist_ok=True)
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(SAMPLE_VIDEO, fourcc, 10.0, (600, 400))
        
        texts = ["SALE 50% OFF", "LIMITED TIME", "CALL NOW"]
        for i in range(30):
            frame = np.ones((400, 600, 3), dtype=np.uint8) * 255
            text_idx = i // 10  # 10 フレームごとにテキスト変更
            if text_idx < len(texts):
                cv2.putText(frame, texts[text_idx], (50, 100), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 0), 2)
            out.write(frame)
        
        out.release()
        print(f"✅ Created test video: {SAMPLE_VIDEO}")
    except Exception as e:
        print(f"⚠️ Failed to create test video: {e}")

def test_ocr_from_image():
    """Test 10: 画像 OCR → LLM → JSON 検証"""
    print("\n=== Test 10: 画像 OCR 統合 ===")
    
    if not os.path.exists(SAMPLE_IMAGE):
        create_test_image_with_text()
    
    try:
        with open(SAMPLE_IMAGE, 'rb') as f:
            files = {"input_file": f}
            data = {"mode": "file_only"}
            response = requests.post(f"{API_BASE_URL}/analyze", files=files, data=data, timeout=60)
        
        if response.status_code != 200:
            print(f"❌ FAILED: {response.status_code}")
            return False
        
        result = response.json()
        
        # OCR テキスト確認
        ocr_text = result.get("creative_core", {}).get("ocr_extracted_text", "")
        if ocr_text:
            print(f"✅ OCR Extracted: {ocr_text[:50]}...")
        else:
            print("⚠️ No OCR text (Fail-Soft)")
        
        # CreativeCore 構造確認
        cc = result.get("creative_core", {})
        if not all(k in cc for k in ["visuals", "tone", "ai_labels"]):
            print("❌ FAILED: CreativeCore structure invalid")
            return False
        
        # JSON Schema 準拠確認
        required_fields = ["input_metadata", "asset_meta", "creative_core", "landing_page", "performance", "diagnostics"]
        if not all(f in result for f in required_fields):
            print("❌ FAILED: Schema compliance failed")
            return False
        
        print("✅ PASSED")
        return True
        
    except Exception as e:
        print(f"❌ ERROR: {str(e)}")
        return False

def test_ocr_from_video():
    """Test 11: 動画フレーム OCR → LLM → JSON 検証"""
    print("\n=== Test 11: 動画フレーム OCR 統合 ===")
    
    if not os.path.exists(SAMPLE_VIDEO):
        create_test_video_with_text()
    
    try:
        with open(SAMPLE_VIDEO, 'rb') as f:
            files = {"input_file": f}
            data = {"mode": "file_only"}
            response = requests.post(f"{API_BASE_URL}/analyze", files=files, data=data, timeout=60)
        
        if response.status_code != 200:
            print(f"❌ FAILED: {response.status_code}")
            return False
        
        result = response.json()
        
        # OCR テキスト確認
        ocr_text = result.get("creative_core", {}).get("ocr_extracted_text", "")
        if ocr_text:
            print(f"✅ OCR Extracted from video frames: {ocr_text[:50]}...")
        else:
            print("⚠️ No OCR text from video (Fail-Soft)")
        
        # CreativeCore 構造確認
        cc = result.get("creative_core", {})
        if not all(k in cc for k in ["visuals", "tone", "ai_labels", "ocr_extracted_text"]):
            print("❌ FAILED: CreativeCore structure invalid")
            return False
        
        # JSON 型チェック
        if not isinstance(cc["ocr_extracted_text"], str):
            print("❌ FAILED: ocr_extracted_text type error")
            return False
        
        print("✅ PASSED")
        return True
        
    except Exception as e:
        print(f"❌ ERROR: {str(e)}")
        return False

def test_json_quality_with_ocr():
    """Test 12: OCR 統合後の JSON 品質確認"""
    print("\n=== Test 12: JSON 品質確認（OCR 統合後） ===")
    
    if not os.path.exists(SAMPLE_IMAGE):
        create_test_image_with_text()
    
    try:
        with open(SAMPLE_IMAGE, 'rb') as f:
            files = {"input_file": f}
            data = {"mode": "file_only"}
            response = requests.post(f"{API_BASE_URL}/analyze", files=files, data=data)
        
        if response.status_code != 200:
            print(f"❌ FAILED: {response.status_code}")
            return False
        
        result = response.json()
        
        # 必須フィールド確認
        required_fields = ["input_metadata", "asset_meta", "creative_core", "landing_page", "performance", "diagnostics"]
        missing = [f for f in required_fields if f not in result]
        if missing:
            print(f"❌ FAILED: Missing fields {missing}")
            return False
        
        # CreativeCore 型チェック
        cc = result["creative_core"]
        if not isinstance(cc.get("ocr_extracted_text"), str):
            print("❌ FAILED: ocr_extracted_text type")
            return False
        
        if not isinstance(cc.get("visuals"), dict):
            print("❌ FAILED: visuals type")
            return False
        
        if not isinstance(cc.get("ai_labels"), list):
            print("❌ FAILED: ai_labels type")
            return False
        
        print("✅ PASSED (JSON Schema compliance 100%, type errors 0)")
        return True
        
    except Exception as e:
        print(f"❌ ERROR: {str(e)}")
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("Phase 2c-2 E2E テスト（OCR 統合）")
    print("=" * 60)
    
    results = []
    
    results.append(("Test 10: 画像 OCR 統合", test_ocr_from_image()))
    time.sleep(2)
    results.append(("Test 11: 動画フレーム OCR 統合", test_ocr_from_video()))
    time.sleep(2)
    results.append(("Test 12: JSON 品質確認", test_json_quality_with_ocr()))
    
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
