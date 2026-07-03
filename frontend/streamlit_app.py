import streamlit as st
import requests
import json
import os
from datetime import datetime


def widget_key(tab: str, action: str, entity_id=None, idx=None) -> str:
    # Streamlit runs every `with tabX:` block on every rerun, so keys must be
    # unique across the whole app, not just within one tab or one loop.
    parts = [tab, action, str(entity_id) if entity_id is not None else "na"]
    if idx is not None:
        parts.append(str(idx))
    return "_".join(parts)


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
    mode = st.selectbox(
        "モード選択",
        ["file_only", "file_plus_lp", "file_plus_lp_plus_manual_kpi"],
        key=widget_key("analyze", "mode_select"),
    )

    mode_requirements = {
        "file_only": "必要な入力: 画像/動画ファイル",
        "file_plus_lp": "必要な入力: 画像/動画ファイル + LPファイル（HTML）",
        "file_plus_lp_plus_manual_kpi": "必要な入力: 画像/動画ファイル + LPファイル（HTML） + KPIファイル（JSON）",
    }
    st.caption(f"ℹ️ {mode_requirements[mode]}")

    uploaded_file = st.file_uploader(
        "画像またはビデオをアップロード",
        type=["png", "jpg", "jpeg", "mp4", "mov"],
        key=widget_key("analyze", "file_upload", "main"),
    )

    lp_file_upload = None
    kpi_file_upload = None
    if mode in ("file_plus_lp", "file_plus_lp_plus_manual_kpi"):
        lp_file_upload = st.file_uploader(
            "LPファイルをアップロード（HTML）",
            type=["html", "htm"],
            key=widget_key("analyze", "file_upload", "lp"),
        )
    if mode == "file_plus_lp_plus_manual_kpi":
        kpi_file_upload = st.file_uploader(
            "KPIファイルをアップロード（JSON）",
            type=["json"],
            key=widget_key("analyze", "file_upload", "kpi"),
        )

    missing_items = []
    if not uploaded_file:
        missing_items.append("画像/動画ファイル")
    if mode in ("file_plus_lp", "file_plus_lp_plus_manual_kpi") and not lp_file_upload:
        missing_items.append("LPファイル（HTML）")
    if mode == "file_plus_lp_plus_manual_kpi" and not kpi_file_upload:
        missing_items.append("KPIファイル（JSON）")

    if missing_items:
        st.warning(f"⚠️ 不足している入力: {'、'.join(missing_items)}。上記をアップロードすると分析を実行できます。")

    if st.button("🚀 分析実行", disabled=bool(missing_items), key=widget_key("analyze", "submit")):
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
                if lp_file_upload:
                    files["lp_file"] = lp_file_upload
                if kpi_file_upload:
                    files["kpi_file"] = kpi_file_upload
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
                        cc_visuals = creative_core.get("visuals", {}) or {}
                        cc_tone = creative_core.get("tone", {}) or {}
                        cc_ai_labels = creative_core.get("ai_labels", []) or []

                        cc_colors = "、".join(cc_visuals.get("dominant_colors", []) or []) or "情報なし"
                        st.write(
                            f"**🖼️ ビジュアル**: 色調は{cc_colors}。"
                            f"構図は{cc_visuals.get('composition', 'N/A')}。"
                            f"スタイルは{cc_visuals.get('style', 'N/A')}。"
                            f"視認性は{cc_visuals.get('clarity', 'N/A')}。"
                        )

                        cc_tones = "、".join(cc_tone.get("primary_tone", []) or []) or "情報なし"
                        st.write(
                            f"**🎭 トーン**: {cc_tones}を基調とし、"
                            f"訴求は{cc_tone.get('emotional_appeal', 'N/A')}型。"
                            f"CTAの強さは{cc_tone.get('call_to_action', 'N/A')}。"
                        )

                        if cc_ai_labels:
                            st.write(f"**🏷️ AIラベル**: {', '.join(cc_ai_labels)}")

                        with st.expander(
                            "🔧 Visuals / Tone / Labels（JSON・デバッグ用）",
                            expanded=False,
                            key=widget_key("analyze", "expander_visuals_tone_labels"),
                        ):
                            st.json({"visuals": cc_visuals, "tone": cc_tone, "ai_labels": cc_ai_labels})

                    # 改善提案 (P0 追加機能)
                    if diagnostics:
                        st.markdown("### ✨ 改善提案")
                        improvements_error = diagnostics.get("improvements_error")
                        improvements = diagnostics.get("improvements")

                        if improvements and improvements.get("summary"):
                            st.write(f"**📝 1行要約**: {improvements['summary']}")

                        if improvements_error:
                            st.warning(f"⚠️ 改善コメント生成に失敗しました (Error: {improvements_error.get('error_code', 'UNKNOWN')})")
                            reason = improvements_error.get("reason")
                            if reason:
                                st.write(f"**理由**: {reason}")
                            st.write("**次のアクション**: 時間をおいて再度分析を実行するか、上記 CreativeCore 分析結果（トーン・ビジュアル）を参考に改善を検討してください。")
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
                                with st.expander(
                                    "詳細を見る",
                                    key=widget_key("analyze", "expander_comment", idx=i),
                                ):
                                    st.write(f"**対象箇所**: {c.get('target_scope', 'N/A')}")
                                    st.write(f"**根拠**: {c.get('evidence', 'N/A')}")
                                    st.write(f"**次にやること**: {c.get('recommended_action', 'N/A')}")
                        elif not improvements:
                            st.info("改善コメントはありません。")
                    
                    # 全体 JSON 表示（デバッグ用・折りたたみ）

                    with st.expander(
                        "🔧 完全な分析結果（JSON・デバッグ用）",
                        expanded=False,
                        key=widget_key("analyze", "expander_full_result"),
                    ):
                        st.json(result)

                    st.download_button(
                        label="📥 結果をダウンロード",
                        data=json.dumps(result, indent=2, ensure_ascii=False),
                        file_name=f"analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                        mime="application/json",
                        key=widget_key("analyze", "download_result"),
                    )
                else:
                    add_log(f"❌ エラー: {response.status_code}")
                    try:
                        err_json = response.json()
                    except Exception:
                        err_json = None

                    if err_json and err_json.get("error_code") == "INSUFFICIENT_INPUT":
                        st.error(f"⚠️ {err_json.get('error', '分析に必要な情報が不足しています。')}")
                        st.write("**次のアクション**: 不足している情報（LPファイルやKPIファイル等）を追加して、再度分析を実行してください。")
                    elif err_json:
                        st.error(f"❌ 分析中にエラーが発生しました（{response.status_code}）: {err_json.get('error', 'Unknown error')}")
                        st.write("**次のアクション**: 入力内容を確認し、再度お試しください。解決しない場合は管理者にお問い合わせください。")
                    else:
                        st.error(f"❌ 分析中にエラーが発生しました（HTTP {response.status_code}）")

                    with st.expander(
                        "🔧 エラー詳細（デバッグ用）",
                        expanded=False,
                        key=widget_key("analyze", "expander_error_detail"),
                    ):
                        st.json(err_json if err_json else {"raw_response": response.text})
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
        skip = st.number_input("Skip", min_value=0, value=0, step=10, key=widget_key("list", "skip"))
    with col2:
        limit = st.number_input("Limit", min_value=1, value=10, step=5, key=widget_key("list", "limit"))

    if st.button("📊 一覧取得", key=widget_key("list", "fetch")):
        try:
            response = requests.get(f"{API_BASE_URL}/?skip={skip}&limit={limit}")
            if response.status_code == 200:
                results = response.json()
                st.session_state["list_items"] = results.get("items", [])
                st.success(f"✅ {len(results.get('items', []))} 件取得")
            else:
                st.error(f"❌ エラー: {response.status_code}")
        except Exception as e:
            st.error(f"❌ API 呼び出しエラー: {str(e)}")

    # List API は asset_id x version 単位で行を返すため、同じ asset_id が
    # 複数行にわたって出現しうる（"unknown" フォールバック時も同様）。
    # そのためループ index を必ずキーに含め、asset_id の重複だけでは
    # widget key が衝突しないようにする。
    for idx, item in enumerate(st.session_state.get("list_items", [])):
        item_asset_id = item.get("asset_meta", {}).get("asset_id", "unknown")
        item_format = item.get("creative_core", {}).get("format", "N/A")
        item_diag = item.get("diagnostics", {}) or {}
        item_improvements = item_diag.get("improvements")
        item_summary = item_improvements.get("summary") if item_improvements else None
        item_comments = item_improvements.get("comments") if item_improvements else None
        item_first_comment = item_comments[0] if item_comments else None

        with st.container(border=True, key=widget_key("list", "item_container", item_asset_id, idx)):
            st.write(f"**🆔 {item_asset_id}**（`{item_format}`）")
            if item_summary:
                st.write(f"📝 {item_summary}")
            else:
                st.write("📝 改善コメントはありません。")
            if item_first_comment:
                st.write(
                    f"優先度: **{item_first_comment.get('priority', 'N/A')}** | "
                    f"次アクション: {item_first_comment.get('recommended_action', 'N/A')}"
                )
            if st.button("🔍 Detail で見る", key=widget_key("list", "select_detail", item_asset_id, idx)):
                st.session_state["selected_asset_id"] = item_asset_id
                st.info("「🔍 Detail」タブに切り替えると、この Asset が選択された状態で表示されます。")
            with st.expander(
                "🔧 JSON（デバッグ用）",
                expanded=False,
                key=widget_key("list", "expander_json", item_asset_id, idx),
            ):
                st.json(item)
            st.divider()

# ============ TAB 3: Detail ============
with tab3:
    st.header("詳細表示")

    list_items = st.session_state.get("list_items", [])
    asset_options = [it.get("asset_meta", {}).get("asset_id", "unknown") for it in list_items]

    if asset_options:
        selected_default = st.session_state.get("selected_asset_id")
        default_index = asset_options.index(selected_default) if selected_default in asset_options else 0
        asset_id = st.selectbox(
            "Asset を選択",
            asset_options,
            index=default_index,
            key=widget_key("detail", "asset_select"),
        )
    else:
        st.info("先に「📋 List」タブで一覧を取得すると、ここで Asset を選択できるようになります。")
        asset_id = st.text_input(
            "Asset ID を直接入力（List 未取得時のフォールバック）",
            key=widget_key("detail", "asset_input_fallback"),
        )

    version = st.number_input("Version (オプション)", min_value=1, value=1, step=1, key=widget_key("detail", "version"))

    if st.button("🔍 詳細取得", key=widget_key("detail", "fetch")):
        if asset_id:
            try:
                url = f"{API_BASE_URL}/{asset_id}?version={version}"
                response = requests.get(url)
                if response.status_code == 200:
                    detail = response.json()
                    st.success("✅ 詳細取得完了")

                    detail_asset_meta = detail.get("asset_meta", {}) or {}
                    detail_creative_core = detail.get("creative_core", {}) or {}
                    detail_diag = detail.get("diagnostics", {}) or {}
                    detail_improvements = detail_diag.get("improvements")

                    st.write(
                        f"**🆔 Asset ID**: {detail_asset_meta.get('asset_id', asset_id)}"
                        f"（`{detail_creative_core.get('format', 'N/A')}`）"
                    )

                    if detail_improvements and detail_improvements.get("summary"):
                        st.write(f"**📝 1行要約**: {detail_improvements['summary']}")

                    detail_visuals = detail_creative_core.get("visuals", {}) or {}
                    detail_tone = detail_creative_core.get("tone", {}) or {}
                    detail_ai_labels = detail_creative_core.get("ai_labels", []) or []
                    if detail_visuals or detail_tone or detail_ai_labels:
                        detail_colors = "、".join(detail_visuals.get("dominant_colors", []) or []) or "情報なし"
                        st.write(
                            f"**🖼️ ビジュアル**: 色調は{detail_colors}。"
                            f"構図は{detail_visuals.get('composition', 'N/A')}。"
                            f"スタイルは{detail_visuals.get('style', 'N/A')}。"
                            f"視認性は{detail_visuals.get('clarity', 'N/A')}。"
                        )
                        detail_tones = "、".join(detail_tone.get("primary_tone", []) or []) or "情報なし"
                        st.write(
                            f"**🎭 トーン**: {detail_tones}を基調とし、"
                            f"訴求は{detail_tone.get('emotional_appeal', 'N/A')}型。"
                            f"CTAの強さは{detail_tone.get('call_to_action', 'N/A')}。"
                        )
                        if detail_ai_labels:
                            st.write(f"**🏷️ AIラベル**: {', '.join(detail_ai_labels)}")

                    if detail_improvements and detail_improvements.get("comments"):
                        st.markdown("### ✨ 改善ポイント")
                        for c in detail_improvements["comments"][:3]:
                            st.write(f"- **{c.get('priority', 'N/A')}** {c.get('issue_summary', 'No summary')}")
                            st.write(f"  根拠: {c.get('evidence', 'N/A')} | 次にやること: {c.get('recommended_action', 'N/A')}")
                    elif not detail_improvements:
                        st.info("改善コメントはありません。")

                    with st.expander(
                        "🔧 完全な分析結果（JSON・デバッグ用）",
                        expanded=False,
                        key=widget_key("detail", "expander_full_result"),
                    ):
                        st.json(detail)
                else:
                    try:
                        detail_err_json = response.json()
                    except Exception:
                        detail_err_json = None

                    if detail_err_json:
                        st.error(f"❌ 詳細取得に失敗しました: {detail_err_json.get('error', 'Unknown error')}")
                        st.write("**次のアクション**: Asset ID・バージョン指定を確認し、再度お試しください。")
                    else:
                        st.error(f"❌ 詳細取得に失敗しました（HTTP {response.status_code}）")

                    with st.expander(
                        "🔧 エラー詳細（デバッグ用）",
                        expanded=False,
                        key=widget_key("detail", "expander_error_detail"),
                    ):
                        st.json(detail_err_json if detail_err_json else {"raw_response": response.text})
            except Exception as e:
                st.error(f"❌ API 呼び出しエラー: {str(e)}")
        else:
            st.warning("⚠️ Asset ID を入力してください")

# ============ TAB 4: Delete ============
with tab4:
    st.header("削除")

    del_list_items = st.session_state.get("list_items", [])
    del_asset_options = [it.get("asset_meta", {}).get("asset_id", "unknown") for it in del_list_items]

    if del_asset_options:
        asset_id_del = st.selectbox(
            "削除対象の Asset を選択",
            del_asset_options,
            key=widget_key("delete", "asset_select"),
        )
    else:
        st.info("先に「📋 List」タブで一覧を取得すると、ここで Asset を選択できるようになります。")
        asset_id_del = st.text_input(
            "削除対象の Asset ID を直接入力（List 未取得時のフォールバック）",
            key=widget_key("delete", "asset_input_fallback"),
        )

    if st.button("🗑️ 削除実行", type="secondary", key=widget_key("delete", "request")):
        if asset_id_del:
            confirm = st.checkbox(
                "⚠️ 削除してもよろしいですか？",
                key=widget_key("delete", "confirm_checkbox", asset_id_del),
            )
            if confirm and st.button("🔴 確定削除", key=widget_key("delete", "confirm_button", asset_id_del)):
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
