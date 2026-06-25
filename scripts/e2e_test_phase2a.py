"""
E2E Test Suite for Phase 2a API
"""
import subprocess
import json
import requests
import time
import sqlite3
from pathlib import Path

# テスト用 URL
BASE_URL = "http://127.0.0.1:8000"
TEST_IMAGE = "sample_data/test_image.png"
TEST_LP = "sample_data/test_lp.html"
TEST_KPI = "sample_data/test_kpi.json"

def log_test(test_num, name, status, details=""):
    print(f"\n[Test {test_num}] {name}")
    print(f"Status: {status}")
    if details:
        print(f"Details: {details}")

def check_db(asset_id, expected_is_deleted=False, expected_version=None):
    """DB 状態確認"""
    conn = sqlite3.connect("backend/ad_insight.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT version, is_deleted FROM ad_insights WHERE asset_id = ?",
        (asset_id,)
    )
    rows = cursor.fetchall()
    conn.close()
    
    if expected_is_deleted:
        is_deleted_records = [r for r in rows if r[1] == 1]
        return len(is_deleted_records) > 0
    elif expected_version:
        versions = [r[0] for r in rows]
        return expected_version in versions
    else:
        return len(rows) > 0

def test_1_post_analyze():
    """Test 1: POST → DB 保存"""
    try:
        with open(TEST_IMAGE, "rb") as f:
            files = {"input_file": f}
            response = requests.post(
                f"{BASE_URL}/api/v1/specs/analyze",
                files=files,
                data={"mode": "file_only"}
            )
        
        if response.status_code == 200:
            data = response.json()
            asset_id = data.get("asset_meta", {}).get("asset_id")
            
            # DB 確認
            if check_db(asset_id):
                log_test(1, "POST → DB 保存", "✅ PASSED", f"asset_id={asset_id}")
                return True, asset_id
            else:
                log_test(1, "POST → DB 保存", "❌ FAILED", "DB に保存されていない")
                return False, None
        else:
            log_test(1, "POST → DB 保存", "❌ FAILED", f"Status: {response.status_code}")
            return False, None
    except Exception as e:
        log_test(1, "POST → DB 保存", "❌ FAILED", str(e))
        return False, None

def test_2_get_list(asset_id):
    """Test 2: GET 一覧"""
    try:
        response = requests.get(f"{BASE_URL}/api/v1/specs?skip=0&limit=10")
        
        if response.status_code == 200:
            data = response.json()
            items = data.get("items", [])
            
            # POST したレコードが含まれるか確認
            found = any(item.get("asset_meta", {}).get("asset_id") == asset_id for item in items)
            
            if found:
                log_test(2, "GET 一覧", "✅ PASSED", f"total={data.get('total')}, items={len(items)}")
                return True
            else:
                log_test(2, "GET 一覧", "❌ FAILED", "POST したレコードが一覧に含まれない")
                return False
        else:
            log_test(2, "GET 一覧", "❌ FAILED", f"Status: {response.status_code}")
            return False
    except Exception as e:
        log_test(2, "GET 一覧", "❌ FAILED", str(e))
        return False

def test_3_get_single(asset_id):
    """Test 3: GET 単件"""
    try:
        response = requests.get(f"{BASE_URL}/api/v1/specs/{asset_id}")
        
        if response.status_code == 200:
            data = response.json()
            retrieved_asset_id = data.get("asset_meta", {}).get("asset_id")
            
            if retrieved_asset_id == asset_id:
                log_test(3, "GET 単件", "✅ PASSED", f"asset_id match")
                return True
            else:
                log_test(3, "GET 単件", "❌ FAILED", "asset_id が一致しない")
                return False
        else:
            log_test(3, "GET 単件", "❌ FAILED", f"Status: {response.status_code}")
            return False
    except Exception as e:
        log_test(3, "GET 単件", "❌ FAILED", str(e))
        return False

def test_4_delete(asset_id):
    """Test 4: DELETE"""
    try:
        response = requests.delete(f"{BASE_URL}/api/v1/specs/{asset_id}")
        
        if response.status_code == 200:
            # DB 確認: is_deleted = True
            if check_db(asset_id, expected_is_deleted=True):
                log_test(4, "DELETE", "✅ PASSED", "論理削除成功")
                return True
            else:
                log_test(4, "DELETE", "❌ FAILED", "DB で is_deleted=True に設定されていない")
                return False
        else:
            log_test(4, "DELETE", "❌ FAILED", f"Status: {response.status_code}")
            return False
    except Exception as e:
        log_test(4, "DELETE", "❌ FAILED", str(e))
        return False

def test_5_after_delete_access(asset_id):
    """Test 5: 削除後アクセス"""
    try:
        response = requests.get(f"{BASE_URL}/api/v1/specs/{asset_id}")
        
        if response.status_code == 404:
            log_test(5, "削除後アクセス", "✅ PASSED", "404 返却 (削除済み除外)")
            return True
        else:
            log_test(5, "削除後アクセス", "❌ FAILED", f"Status: {response.status_code} (404 期待)")
            return False
    except Exception as e:
        log_test(5, "削除後アクセス", "❌ FAILED", str(e))
        return False

def test_6_reanalyze(asset_id_1):
    """Test 6: 削除後再分析（条件付き実施）"""
    try:
        # 同一ファイルで再度 POST
        with open(TEST_IMAGE, "rb") as f:
            files = {"input_file": f}
            response = requests.post(
                f"{BASE_URL}/api/v1/specs/analyze",
                files=files,
                data={"mode": "file_only"}
            )
        
        if response.status_code == 200:
            data = response.json()
            asset_id_2 = data.get("asset_meta", {}).get("asset_id")
            
            if asset_id_1 == asset_id_2:
                # 同一 asset_id → version +1 テスト可能
                if check_db(asset_id_1, expected_version=2):
                    log_test(6, "削除後再分析 (version +1)", "✅ PASSED", f"version=2 確認")
                    return True, "PASSED", "asset_id がハッシュベース → version +1 成立"
                else:
                    log_test(6, "削除後再分析 (version +1)", "❌ FAILED", "version=2 が見つからない")
                    return False, "FAILED", "version ロジック未実装または bug"
            else:
                # 異なる asset_id → テスト未成立
                log_test(6, "削除後再分析 (version +1)", "⚠️  SKIPPED", 
                        f"asset_id 異なる: {asset_id_1} → {asset_id_2}")
                return None, "SKIPPED", "asset_id が UUID ベース → テスト6 成立不可"
        else:
            log_test(6, "削除後再分析", "❌ FAILED", f"Status: {response.status_code}")
            return False, "FAILED", "再分析リクエスト失敗"
    except Exception as e:
        log_test(6, "削除後再分析", "❌ FAILED", str(e))
        return False, "FAILED", str(e)

def main():
    print("="*80)
    print("E2E Test Suite - Phase 2a API")
    print("="*80)
    
    # サーバー起動確認
    print("\n[Setup] サーバー疎通確認...")
    try:
        response = requests.get(f"{BASE_URL}/health")
        if response.status_code == 200:
            print("✅ サーバー起動確認")
        else:
            print("❌ サーバーに接続できません")
            return
    except:
        print("❌ サーバーに接続できません")
        return
    
    # Test 1: POST → DB 保存
    test1_pass, asset_id = test_1_post_analyze()
    if not test1_pass:
        print("\n❌ Test 1 失敗のため中止")
        return
    
    # Test 2: GET 一覧
    test2_pass = test_2_get_list(asset_id)
    
    # Test 3: GET 単件
    test3_pass = test_3_get_single(asset_id)
    
    # Test 4: DELETE
    test4_pass = test_4_delete(asset_id)
    
    # Test 5: 削除後アクセス
    test5_pass = test_5_after_delete_access(asset_id)
    
    # Test 6: 削除後再分析（条件付き）
    test6_pass, test6_status, test6_reason = test_6_reanalyze(asset_id)
    
    # 結果サマリー
    print("\n" + "="*80)
    print("テスト結果サマリー")
    print("="*80)
    print(f"Test 1 (POST → DB 保存): {'✅ PASSED' if test1_pass else '❌ FAILED'}")
    print(f"Test 2 (GET 一覧): {'✅ PASSED' if test2_pass else '❌ FAILED'}")
    print(f"Test 3 (GET 単件): {'✅ PASSED' if test3_pass else '❌ FAILED'}")
    print(f"Test 4 (DELETE): {'✅ PASSED' if test4_pass else '❌ FAILED'}")
    print(f"Test 5 (削除後アクセス): {'✅ PASSED' if test5_pass else '❌ FAILED'}")
    print(f"Test 6 (削除後再分析): {test6_status} - {test6_reason}")
    
    passed = sum([test1_pass, test2_pass, test3_pass, test4_pass, test5_pass])
    print(f"\n合計: {passed}/5 PASSED (Test 6: {test6_status})")

if __name__ == "__main__":
    main()
