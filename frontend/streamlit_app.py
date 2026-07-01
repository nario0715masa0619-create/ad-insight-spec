import streamlit as st
import requests
import json
import os
from datetime import datetime

# ページ設定
st.set_page_config(page_title="Ad-Insight-Spec UI", layout="wide")
st.title("📊 Ad-Insight-Spec")

# API ベース URL（環境に応じて変更可）
API_BASE_URL = "http://localhost:8000/api/v1/specs"

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
            
            log_container = st.container()
            with log_container:
                st.write("📋 処理ログ：")
                log_output = st.empty()
                logs = []
                
                def add_log(msg):
                    logs.append(f"- {msg}")
                    log_output.write("\n".join(logs))
                
                add_log("📤 API にファイルを送信中...")
                add_log("⏳ サーバーで処理中...（最大60秒）")

            try:
                files = {"input_file": uploaded_file}
                data = {"mode": mode}
                response = requests.post(f"{API_BASE_URL}/analyze", files=files, data=data, timeout=60)
                
                if response.status_code == 200:
                    add_log("✅ 分析完了")
                    add_log("📊 結果を処理中...")
                    result = response.json()
                    st.success("✅ 分析完了！")
                    
                    # LLM メタデータ表示
                    diagnostics = result.get("diagnostics", {})
                    if diagnostics:
                        st.markdown("### 📊 LLM 分析メタデータ")
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("Model", diagnostics.get("llm_model", "N/A"))
                        with col2:
                            st.metric("Success", "✅" if diagnostics.get("llm_success") else "❌")
                        with col3:
                            st.metric("Retries", diagnostics.get("llm_retry_count", 0))
                        
                        if diagnostics.get("llm_error"):
                            st.error(f"⚠️ エラー: {diagnostics['llm_error']}")
                    
                    # CreativeCore 結果表示
                    creative_core = result.get("creative_core", {})
                    if creative_core:
                        st.markdown("### 🎨 CreativeCore 分析結果")
                        with st.expander("Visuals"):
                            st.json(creative_core.get("visuals", {}))
                        with st.expander("Tone"):
                            st.json(creative_core.get("tone", {}))
                        with st.expander("AI Labels"):
                            st.write(creative_core.get("ai_labels", []))
                    
                    # 全体 JSON 表示 (既存)
                    # 改善提案 (P0 追加機能)
                    if diagnostics:
                        st.markdown("### ✨ 改善提案")
                        improvements_error = diagnostics.get("improvements_error")
                        improvements = diagnostics.get("improvements")
                        
                        if improvements_error:
                            st.warning(f"⚠️ 改善コメント生成に失敗しました (Error: {improvements_error.get('error_code', 'UNKNOWN')})")
                        elif improvements and improvements.get("comments"):
                            comments = improvements.get("comments", [])
                            for i, c in enumerate(comments[:3]):
                                priority = c.get("priority", "N/A")
                                if priority == "P0":
                                    badge = "🔴 **P0 (必須)**"
                                elif priority == "P1":
                                    badge = "🟠 **P1 (強く推奨)**"
                                elif priority == "P2":
                                    badge = "🟡 **P2 (推奨)**"
                                else:
                                    badge = f"🔵 **{priority}**"
                                
                                st.write(f"{badge} | **{c.get('issue_summary', 'No summary')}**")
                                with st.expander("詳細を見る"):
                                    st.write(f"**対象箇所**: {c.get('target_scope', 'N/A')}")
                                    st.write(f"**根拠**: {c.get('evidence', 'N/A')}")
                                    st.write(f"**アクション**: {c.get('actionable_advice', 'N/A')}")
                        elif not improvements:
                            st.info("改善コメントはありません。")
                    
                    # 全体 JSON 表示

                    st.markdown("### 📄 完全な分析結果（JSON）")
                    st.json(result)
                    
                    st.download_button(
                        label="📥 結果をダウンロード",
                        data=json.dumps(result, indent=2, ensure_ascii=False),
                        file_name=f"analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                        mime="application/json"
                    )
                else:
                    add_log(f"❌ エラー: {response.status_code}")
                    st.error(f"❌ エラー: {response.status_code}\n{response.text}")
            except Exception as e:
                add_log(f"❌ エラー内容: {str(e)}")
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
