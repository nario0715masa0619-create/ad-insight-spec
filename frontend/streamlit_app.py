import streamlit as st
import requests
import json
from datetime import datetime

# ページ設定
st.set_page_config(page_title="Ad-Insight-Spec UI", layout="wide")
st.title("📊 Ad-Insight-Spec")

# API ベース URL（環境に応じて変更可）
API_BASE_URL = "http://127.0.0.1:8000/api/v1/specs"

# タブ 4 つ
tab1, tab2, tab3, tab4 = st.tabs(["📤 Analyze", "📋 List", "🔍 Detail", "🗑️ Delete"])

# ============ TAB 1: Analyze ============
with tab1:
    st.header("ファイル分析")
    uploaded_file = st.file_uploader("画像またはビデオをアップロード", type=["png", "jpg", "jpeg", "mp4", "mov"])
    mode = st.selectbox("モード選択", ["file_only", "file_plus_lp", "file_plus_lp_plus_manual_kpi"])
    
    if st.button("🚀 分析実行"):
        if uploaded_file:
            st.info("🔄 分析中...")
            try:
                files = {"input_file": uploaded_file}
                data = {"mode": mode}
                response = requests.post(f"{API_BASE_URL}/analyze", files=files, data=data, timeout=30)
                
                if response.status_code == 200:
                    result = response.json()
                    st.success("✅ 分析完了！")
                    st.json(result)
                    st.download_button(
                        label="📥 結果をダウンロード",
                        data=json.dumps(result, indent=2, ensure_ascii=False),
                        file_name=f"analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                        mime="application/json"
                    )
                else:
                    st.error(f"❌ エラー: {response.status_code}\n{response.text}")
            except Exception as e:
                st.error(f"❌ API 呼び出しエラー: {str(e)}")
        else:
            st.warning("⚠️ ファイルをアップロードしてください")

# ============ TAB 2: List ============
with tab2:
    st.header("分析結果一覧")
    col1, col2 = st.columns(2)
    with col1:
        skip = st.number_input("Skip", min_value=0, value=0, step=10)
    with col2:
        limit = st.number_input("Limit", min_value=1, value=10, step=5)
    
    if st.button("📊 一覧取得"):
        try:
            response = requests.get(f"{API_BASE_URL}/?skip={skip}&limit={limit}")
            if response.status_code == 200:
                results = response.json()
                st.success(f"✅ {len(results.get('items', []))} 件取得")
                for item in results.get('items', []):
                    st.write(f"**Asset ID:** `{item.get('asset_meta', {}).get('asset_id')}`")
                    st.write(f"Format: {item.get('creative_core', {}).get('format')} | ")
                    st.divider()
            else:
                st.error(f"❌ エラー: {response.status_code}")
        except Exception as e:
            st.error(f"❌ API 呼び出しエラー: {str(e)}")

# ============ TAB 3: Detail ============
with tab3:
    st.header("詳細表示")
    asset_id = st.text_input("Asset ID を入力")
    version = st.number_input("Version (オプション)", min_value=1, value=1, step=1)
    
    if st.button("🔍 詳細取得"):
        if asset_id:
            try:
                url = f"{API_BASE_URL}/{asset_id}?version={version}"
                response = requests.get(url)
                if response.status_code == 200:
                    detail = response.json()
                    st.success("✅ 詳細取得完了")
                    st.json(detail)
                else:
                    st.error(f"❌ エラー: {response.status_code}\n{response.text}")
            except Exception as e:
                st.error(f"❌ API 呼び出しエラー: {str(e)}")
        else:
            st.warning("⚠️ Asset ID を入力してください")

# ============ TAB 4: Delete ============
with tab4:
    st.header("削除")
    asset_id_del = st.text_input("削除対象の Asset ID")
    
    if st.button("🗑️ 削除実行", type="secondary"):
        if asset_id_del:
            confirm = st.checkbox("⚠️ 削除してもよろしいですか？")
            if confirm and st.button("🔴 確定削除"):
                try:
                    response = requests.delete(f"{API_BASE_URL}/{asset_id_del}")
                    if response.status_code == 200:
                        st.success("✅ 削除完了（論理削除）")
                    else:
                        st.error(f"❌ エラー: {response.status_code}\n{response.text}")
                except Exception as e:
                    st.error(f"❌ API 呼び出しエラー: {str(e)}")
        else:
            st.warning("⚠️ Asset ID を入力してください")

# ============ フッター ============
st.divider()
st.caption("Phase 2b Minimum UI | Ad-Insight-Spec v0.2")
