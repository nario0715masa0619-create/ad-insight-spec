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


def init_session_state():
    # 新規分析 / 保存済み結果 の画面遷移は st.tabs() ではなく session_state で管理する。
    # st.tabs() は「新規分析」「保存済み結果」という大区分の切り替えにのみ使う。
    defaults = {
        "current_view": "list",  # 保存済み結果タブ内での "list" | "detail"
        "selected_asset_id": None,
        "selected_version": None,
        "list_items": [],
        "analysis_result": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def render_asset_detail(tab_key: str, detail: dict, asset_id: str, on_delete_success=None):
    """
    分析結果1件分の詳細表示（CreativeCore / 改善提案 / JSON / ダウンロード / 削除）。

    「新規分析」完了直後の結果表示と、「保存済み結果」からの詳細表示の両方で使う共通描画関数。
    tab_key は widget key の名前空間分離用（呼び出し元ごとにユニークにする）。
    """
    asset_meta = detail.get("asset_meta", {}) or {}
    creative_core = detail.get("creative_core", {}) or {}
    diagnostics = detail.get("diagnostics", {}) or {}
    improvements = diagnostics.get("improvements")
    improvements_error = diagnostics.get("improvements_error")

    st.write(
        f"**🆔 Asset ID**: {asset_meta.get('asset_id', asset_id)}"
        f"（`{creative_core.get('format', 'N/A')}`）"
    )

    if improvements and improvements.get("summary"):
        st.write(f"**📝 1行要約**: {improvements['summary']}")

    visuals = creative_core.get("visuals", {}) or {}
    tone = creative_core.get("tone", {}) or {}
    ai_labels = creative_core.get("ai_labels", []) or []
    if visuals or tone or ai_labels:
        st.markdown("### 🎨 CreativeCore 分析結果")
        colors = "、".join(visuals.get("dominant_colors", []) or []) or "情報なし"
        st.write(
            f"**🖼️ ビジュアル**: 色調は{colors}。"
            f"構図は{visuals.get('composition', 'N/A')}。"
            f"スタイルは{visuals.get('style', 'N/A')}。"
            f"視認性は{visuals.get('clarity', 'N/A')}。"
        )
        tones = "、".join(tone.get("primary_tone", []) or []) or "情報なし"
        st.write(
            f"**🎭 トーン**: {tones}を基調とし、"
            f"訴求は{tone.get('emotional_appeal', 'N/A')}型。"
            f"CTAの強さは{tone.get('call_to_action', 'N/A')}。"
        )
        if ai_labels:
            st.write(f"**🏷️ AIラベル**: {', '.join(ai_labels)}")

        with st.expander(
            "🔧 Visuals / Tone / Labels（JSON・デバッグ用）",
            expanded=False,
            key=widget_key(tab_key, "expander_visuals_tone_labels", asset_id),
        ):
            st.json({"visuals": visuals, "tone": tone, "ai_labels": ai_labels})

    st.markdown("### ✨ 改善提案")
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
                key=widget_key(tab_key, "expander_comment", asset_id, i),
            ):
                st.write(f"**対象箇所**: {c.get('target_scope', 'N/A')}")
                st.write(f"**根拠**: {c.get('evidence', 'N/A')}")
                st.write(f"**次にやること**: {c.get('recommended_action', 'N/A')}")
    else:
        st.info("改善コメントはありません。")

    with st.expander(
        "🔧 完全な分析結果（JSON・デバッグ用）",
        expanded=False,
        key=widget_key(tab_key, "expander_full_result", asset_id),
    ):
        st.json(detail)

    st.download_button(
        label="📥 結果をダウンロード",
        data=json.dumps(detail, indent=2, ensure_ascii=False),
        file_name=f"analysis_{asset_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
        mime="application/json",
        key=widget_key(tab_key, "download_result", asset_id),
    )

    with st.expander("⚠️ 削除", expanded=False, key=widget_key(tab_key, "expander_delete", asset_id)):
        confirm = st.checkbox(
            "この Asset を削除してもよろしいですか？（論理削除）",
            key=widget_key(tab_key, "delete_confirm", asset_id),
        )
        if confirm and st.button("🔴 削除実行", key=widget_key(tab_key, "delete_execute", asset_id)):
            try:
                response = requests.delete(f"{API_BASE_URL}/{asset_id}")
                if response.status_code == 200:
                    st.success("✅ 削除完了（論理削除）")
                    if on_delete_success:
                        on_delete_success()
                    st.rerun()
                else:
                    st.error(f"❌ エラー: {response.status_code}\n{response.text}")
            except Exception as e:
                st.error(f"❌ API 呼び出しエラー: {str(e)}")


# ページ設定
st.set_page_config(page_title="Ad-Insight-Spec UI", layout="wide")
st.title("📊 Ad-Insight-Spec")

# API ベース URL（環境に応じて変更可）
API_BASE_URL = "http://localhost:8000/api/v1/specs"

init_session_state()

# 上位ナビゲーションは「新規分析」「保存済み結果」の2区分のみ。
# 詳細表示への遷移は st.tabs() ではなく session_state（current_view 等）で管理する。
tab_new, tab_saved = st.tabs(["📤 新規分析", "📂 保存済み結果"])

# ============ 新規分析 ============
with tab_new:
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
                    result = response.json()
                    st.session_state["analysis_result"] = result
                else:
                    add_log(f"❌ エラー: {response.status_code}")
                    try:
                        err_json = response.json()
                    except Exception:
                        err_json = None

                    st.session_state["analysis_result"] = None

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

    # 分析結果は session_state に永続化し、ボタン判定の外側（毎rerun）で描画する。
    # こうしておかないと、結果内の削除チェックボックス等を操作した瞬間の rerun で
    # 「🚀 分析実行」の if ブロックが False に戻り、結果表示ごと消えてしまう。
    if st.session_state.get("analysis_result"):
        result = st.session_state["analysis_result"]
        result_asset_id = result.get("asset_meta", {}).get("asset_id", "unknown")

        st.success("✅ 分析完了！")

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

        def _clear_analysis_result():
            st.session_state["analysis_result"] = None

        render_asset_detail("analyze", result, result_asset_id, on_delete_success=_clear_analysis_result)

# ============ 保存済み結果 ============
with tab_saved:
    if st.session_state["current_view"] == "detail" and st.session_state.get("selected_asset_id"):
        # --- 詳細表示 ---
        asset_id = st.session_state["selected_asset_id"]
        st.header("詳細表示")

        if st.button("← 一覧へ戻る", key=widget_key("saved_detail", "back_to_list")):
            st.session_state["current_view"] = "list"
            st.session_state["selected_asset_id"] = None
            st.session_state["selected_version"] = None
            st.rerun()

        version = st.number_input(
            "Version（未指定/1のままなら選択時点の最新版を取得）",
            min_value=1,
            value=st.session_state.get("selected_version") or 1,
            step=1,
            key=widget_key("saved_detail", "version", asset_id),
        )

        try:
            url = f"{API_BASE_URL}/{asset_id}?version={version}"
            response = requests.get(url)
            if response.status_code == 200:
                detail = response.json()

                def _back_to_list():
                    st.session_state["current_view"] = "list"
                    st.session_state["selected_asset_id"] = None
                    st.session_state["selected_version"] = None

                render_asset_detail("saved_detail", detail, asset_id, on_delete_success=_back_to_list)
            else:
                try:
                    err_json = response.json()
                except Exception:
                    err_json = None
                if err_json:
                    st.error(f"❌ 詳細取得に失敗しました: {err_json.get('error', 'Unknown error')}")
                else:
                    st.error(f"❌ 詳細取得に失敗しました（HTTP {response.status_code}）")
                with st.expander(
                    "🔧 エラー詳細（デバッグ用）",
                    expanded=False,
                    key=widget_key("saved_detail", "expander_error_detail", asset_id),
                ):
                    st.json(err_json if err_json else {"raw_response": response.text})
        except Exception as e:
            st.error(f"❌ API 呼び出しエラー: {str(e)}")

    else:
        # --- 一覧表示 ---
        st.header("分析結果一覧")
        st.caption("ℹ️ asset_id ごとの最新版のみを表示します。")
        col1, col2 = st.columns(2)
        with col1:
            skip = st.number_input("Skip", min_value=0, value=0, step=10, key=widget_key("saved_list", "skip"))
        with col2:
            limit = st.number_input("Limit", min_value=1, value=10, step=5, key=widget_key("saved_list", "limit"))

        if st.button("📊 一覧取得", key=widget_key("saved_list", "fetch")):
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

        # 一覧APIはデフォルトで asset_id ごとの最新版のみを返すが、念のため
        # ループ index は残しておく（unknown フォールバック等での widget key 衝突防止）。
        for idx, item in enumerate(st.session_state.get("list_items", [])):
            item_asset_id = item.get("asset_meta", {}).get("asset_id", "unknown")
            item_format = item.get("creative_core", {}).get("format", "N/A")
            item_diag = item.get("diagnostics", {}) or {}
            item_improvements = item_diag.get("improvements")
            item_summary = item_improvements.get("summary") if item_improvements else None
            item_comments = item_improvements.get("comments") if item_improvements else None
            item_first_comment = item_comments[0] if item_comments else None

            with st.container(border=True, key=widget_key("saved_list", "item_container", item_asset_id, idx)):
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
                if st.button("🔍 詳細を見る", key=widget_key("saved_list", "select_detail", item_asset_id, idx)):
                    st.session_state["current_view"] = "detail"
                    st.session_state["selected_asset_id"] = item_asset_id
                    st.session_state["selected_version"] = None
                    st.rerun()
                with st.expander(
                    "🔧 JSON（デバッグ用）",
                    expanded=False,
                    key=widget_key("saved_list", "expander_json", item_asset_id, idx),
                ):
                    st.json(item)
                st.divider()

# ============ フッター ============
st.divider()
st.caption("Phase 2b Minimum UI | Ad-Insight-Spec v0.2")
