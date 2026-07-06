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


def refresh_saved_list():
    # 削除成功時などに「保存済み結果」一覧をサーバー側の最新状態へ揃えるための再取得。
    # skip/limit は一覧画面の number_input の現在値（widget state）をそのまま使う。
    # 失敗しても一覧遷移自体は継続し、既存の「一覧取得」ボタンで手動リトライできる。
    skip = st.session_state.get(widget_key("saved_list", "skip"), 0)
    limit = st.session_state.get(widget_key("saved_list", "limit"), 10)
    try:
        response = requests.get(f"{API_BASE_URL}/?skip={skip}&limit={limit}")
        if response.status_code == 200:
            st.session_state["list_items"] = response.json().get("items", [])
    except Exception:
        pass


def init_session_state():
    # 新規分析 / 保存済み結果 の画面遷移は st.tabs() ではなく session_state で管理する。
    # st.tabs() は「新規分析」「保存済み結果」という大区分の切り替えにのみ使う。
    defaults = {
        "current_view": "list",  # 保存済み結果タブ内での "list" | "detail"
        "selected_asset_id": None,
        "selected_version": None,
        "list_items": [],
        "analysis_result": None,
        # 詳細画面の Version widget (key="detail_version_input") が
        # 現在どの asset_id 向けに初期化済みかを覚えておくための追跡用。
        # widget 本体の値ではないので、rerun のたびに触らないこと。
        "detail_version_input_for_asset": None,
        # analysis_result の復元をこのセッションで既に試みたかどうか。
        # backend未起動時などに毎rerunで再試行してAPIを叩き続けないための一回性フラグ。
        "analysis_result_restore_attempted": False,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


# ===== 新規分析タブの analysis_result: いつ更新/クリアするか =====
# 通常のタブ切替や、他ウィジェット操作によるrerunでは analysis_result は
# 一切触らない（st.session_state に保持し続けるだけ）。以下の3ケースのみ
# 明示的に変更する:
#   1. 新規/再分析が成功した (200 OK) 時: 常に最新結果で上書きする
#      （set_analysis_result_query_params で URL にも asset_id/version を残す）
#   2. 新規/再分析が失敗した時: 直前の成功結果を残さない
#      （エラーの下に古い結果が居座る「矛盾した画面」を防ぐため None にする）
#   3. 表示中のアセットが削除された時: 削除されたものを表示し続けない
#
# ブラウザの完全リロードや、Streamlitセッション自体の再作成（サーバー再起動後の
# 再接続等）では session_state は失われるが、その場合は URL の query params
# （result_asset_id / result_version）を手がかりに backend から結果を再取得し、
# 同じ画面を復元する（restore_analysis_result_from_query_params）。
def set_analysis_result_query_params(asset_id, version):
    st.query_params["result_asset_id"] = str(asset_id)
    st.query_params["result_version"] = str(version)


def clear_analysis_result_query_params():
    st.query_params.pop("result_asset_id", None)
    st.query_params.pop("result_version", None)


def restore_analysis_result_from_query_params():
    # ページの完全リロード等で新しい Streamlit セッションが始まった直後だけ
    # 復元を試みる。analysis_result が既にある場合や、一度復元を試みた後
    # (backend未起動等で失敗した場合を含む) は毎rerunで再試行しない。
    if st.session_state.get("analysis_result"):
        return
    if st.session_state.get("analysis_result_restore_attempted"):
        return
    st.session_state["analysis_result_restore_attempted"] = True

    asset_id = st.query_params.get("result_asset_id")
    version = st.query_params.get("result_version")
    if not asset_id:
        return

    try:
        url = f"{API_BASE_URL}/{asset_id}"
        if version:
            url += f"?version={version}"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            result = response.json()
            st.session_state["analysis_result"] = result
            st.session_state["selected_asset_id"] = result.get("asset_meta", {}).get("asset_id")
            st.session_state["selected_version"] = result.get("version")
        else:
            # 対象アセットが削除済み等で見つからない場合は、URLの手がかりも消す。
            clear_analysis_result_query_params()
    except Exception:
        # backend未起動時などはここで静かに諦める（画面には何も出さない）。
        # 次にbackendが起動してからページを開き直せば復元される。
        pass


CATEGORY_LABELS = {
    "visual": "🎨 ビジュアル・構成",
    "message": "💬 メッセージ・トーン",
    "cta": "📣 CTA",
    "target": "🎯 ターゲット適合",
    "lp": "🔗 LP連動",
    "brand": "🏷️ ブランド",
}

PRIORITY_LABELS = {
    "P0": "🔴 P0（致命的）",
    "P1": "🟠 P1（改善推奨）",
    "P2": "🟡 P2（伸び代）",
}

PRIORITY_SORT_ORDER = {"P0": 0, "P1": 1, "P2": 2}

DECISION_LABELS = {
    "継続": "✅ 継続",
    "改修推奨": "🛠️ 改修推奨",
    "停止検討": "🛑 停止検討",
}


def category_label(category) -> str:
    if not category:
        return "🔸 その他"
    return CATEGORY_LABELS.get(category, f"🔸 {category}")


def priority_label(priority) -> str:
    if not priority:
        return "⚪ 優先度未設定"
    return PRIORITY_LABELS.get(priority, f"⚪ {priority}")


def sort_by_priority(items: list) -> list:
    return sorted(items, key=lambda item: PRIORITY_SORT_ORDER.get(item.get("priority"), 99))


def render_decision_summary(summary: dict):
    headline = summary.get("headline") or "結論サマリー"
    decision = summary.get("decision")
    rationale = summary.get("rationale")
    with st.container(border=True):
        st.markdown(f"## 🧭 {headline}")
        if decision:
            st.markdown(f"**判断: {DECISION_LABELS.get(decision, decision)}**")
        if rationale:
            st.write(rationale)


def render_strengths(strengths: list):
    st.markdown("### 🟢 強み（維持・再利用すべき勝ち要素）")
    if not strengths:
        st.info("特筆すべき強みは検出されませんでした。")
        return
    for s in strengths:
        with st.container(border=True):
            st.markdown(f"**{category_label(s.get('category'))} | {s.get('title', '（無題）')}**")
            st.write(s.get("description", ""))
            keep_reason = s.get("keep_reason")
            if keep_reason:
                st.caption(f"🔒 この要素は残すべき理由: {keep_reason}")
            evidence = s.get("evidence")
            if evidence:
                st.caption(f"🔍 判断根拠: {evidence}")


def render_weaknesses(weaknesses: list):
    st.markdown("### 🔴 弱み（成果を下げているボトルネック）")
    if not weaknesses:
        st.info("特筆すべき弱みは検出されませんでした。")
        return
    for w in sort_by_priority(weaknesses):
        with st.container(border=True):
            st.markdown(
                f"**{priority_label(w.get('priority'))} | "
                f"{category_label(w.get('category'))} | {w.get('title', '（無題）')}**"
            )
            st.write(w.get("description", ""))
            impact = w.get("impact")
            if impact:
                st.caption(f"⚠️ 放置した場合の影響: {impact}")
            evidence = w.get("evidence")
            if evidence:
                st.caption(f"🔍 判断根拠: {evidence}")


def render_recommendations(recommendations: list, weaknesses: list):
    st.markdown("### ✨ 改善提案（What / Why / How）")
    if not recommendations:
        st.info("改善提案はありません。")
        return
    weakness_title_by_id = {w.get("id"): w.get("title") for w in weaknesses if w.get("id")}
    for r in sort_by_priority(recommendations):
        with st.container(border=True):
            target_ids = r.get("target_weakness_ids") or []
            target_labels = [f"「{weakness_title_by_id.get(wid, wid)}」" for wid in target_ids]
            st.markdown(f"**{priority_label(r.get('priority'))} | {r.get('title', '（無題）')}**")
            if target_labels:
                st.caption(f"🔗 対応する弱み: {', '.join(target_labels)}")
            st.write(f"**What（何を変えるか）**: {r.get('what', 'N/A')}")
            st.write(f"**Why（なぜ変えるか）**: {r.get('why', 'N/A')}")
            st.write(f"**How（どう検証するか）**: {r.get('how', 'N/A')}")
            expected_effect = r.get("expected_effect")
            if expected_effect:
                st.caption(f"📈 期待効果: {expected_effect}")


# ===== 5軸構造化（axes）の表示: appeal/creative/cta/trust/target =====

AXIS_ORDER = ["appeal", "creative", "cta", "trust", "target"]

AXIS_ICON_LABELS = {
    "appeal": "🎯 訴求軸",
    "creative": "🎨 クリエイティブ",
    "cta": "📣 CTA",
    "trust": "🤝 信頼",
    "target": "🧑‍🤝‍🧑 ターゲット",
}

RANK_BADGES = {
    "A": "🥇 A（良好）",
    "B": "🥈 B（合格）",
    "C": "🥉 C（要改善）",
    "D": "⚠️ D（要対応）",
}


def axis_label(axis: str) -> str:
    return AXIS_ICON_LABELS.get(axis, axis)


def rank_badge(rank) -> str:
    if not rank:
        return "—"
    return RANK_BADGES.get(rank, rank)


def score_stars(score) -> str:
    if not isinstance(score, (int, float)):
        return "☆☆☆☆☆"
    filled = max(0, min(5, int(round(score))))
    return "★" * filled + "☆" * (5 - filled)


def render_overall_score_card(decision_support: dict):
    """axes形式の decision_support の結論サマリー（総合ランク/スコア付き）"""
    summary = decision_support.get("summary", {}) or {}
    headline = summary.get("headline") or "結論サマリー"
    decision = summary.get("decision")
    rationale = summary.get("rationale")
    overall_rank = decision_support.get("overall_rank")
    overall_score = decision_support.get("overall_score")
    with st.container(border=True):
        st.markdown(f"## 🧭 {headline}")
        cols = st.columns([1, 1, 2])
        with cols[0]:
            st.metric("総合ランク", rank_badge(overall_rank))
        with cols[1]:
            st.metric("総合スコア", f"{overall_score:.1f} / 5" if overall_score is not None else "—")
        with cols[2]:
            if decision:
                st.markdown(f"**判断: {DECISION_LABELS.get(decision, decision)}**")
        if rationale:
            st.write(rationale)


def render_evidence(evidence: dict):
    if not evidence:
        return
    st.caption(
        f"🔍 根拠 | 対象箇所: {evidence.get('location', 'N/A')} / "
        f"観点: {evidence.get('viewpoint', 'N/A')} / "
        f"評価: {evidence.get('evaluation', 'N/A')} / "
        f"根拠: {evidence.get('rationale', 'N/A')}"
    )


def render_axis_block(axis: dict):
    """1軸分（強み・弱み・改善提案の3点セット必須）の表示"""
    axis_id = axis.get("axis")
    score = axis.get("score")
    strength = axis.get("strength", {}) or {}
    weakness = axis.get("weakness", {}) or {}
    recommendation = axis.get("recommendation", {}) or {}

    with st.container(border=True):
        st.markdown(f"### {axis_label(axis_id)}　{score_stars(score)}（{score if score is not None else '?'}/5）")

        st.markdown("**🟢 強み**")
        st.write(f"対象: {strength.get('target_element', 'N/A')}")
        st.write(strength.get("description", ""))
        reason = strength.get("reason")
        if reason:
            st.caption(f"💡 理由: {reason}")
        keep_reason = strength.get("keep_reason")
        if keep_reason:
            st.caption(f"🔒 維持すべき理由: {keep_reason}")
        render_evidence(strength.get("evidence"))

        st.markdown("**🔴 弱み**")
        st.write(f"対象: {weakness.get('target_element', 'N/A')}")
        st.write(weakness.get("description", ""))
        w_reason = weakness.get("reason")
        if w_reason:
            st.caption(f"💡 理由: {w_reason}")
        impact = weakness.get("impact")
        if impact:
            st.caption(f"⚠️ 放置した場合の影響: {impact}")
        render_evidence(weakness.get("evidence"))

        st.markdown("**✨ 改善提案**")
        st.write(f"**What（何を変えるか）**: {recommendation.get('what', 'N/A')}")
        st.write(f"**Why（なぜ変えるか）**: {recommendation.get('why', 'N/A')}")
        st.write(f"**How（どう検証するか）**: {recommendation.get('how', 'N/A')}")
        expected_effect = recommendation.get("expected_effect")
        if expected_effect:
            st.caption(f"📈 期待効果: {expected_effect}")


def render_decision_support_axes(decision_support: dict):
    """axes形式の decision_support 本体（5軸を固定順で表示）"""
    render_overall_score_card(decision_support)
    axes_by_id = {a.get("axis"): a for a in decision_support.get("axes", []) or []}
    for axis_id in AXIS_ORDER:
        axis = axes_by_id.get(axis_id)
        if axis:
            render_axis_block(axis)


def render_decision_support_diff(diff: dict):
    """前回バージョンとの decision_support 差分（新形式同士の場合のみ渡される）"""
    if not diff:
        return
    with st.container(border=True):
        st.markdown(f"### 📊 前回分析（version {diff.get('previous_version', '?')}）との差分")
        previous_headline = diff.get("previous_headline")
        if previous_headline:
            st.caption(f"前回の結論: {previous_headline}")

        rank_delta = diff.get("overall_rank_delta")
        previous_rank = diff.get("previous_overall_rank")
        if rank_delta is not None:
            if rank_delta > 0:
                arrow = f"⬆️ 改善（{rank_badge(previous_rank)} → 今回）"
            elif rank_delta < 0:
                arrow = f"⬇️ 悪化（{rank_badge(previous_rank)} → 今回）"
            else:
                arrow = f"➡️ 変化なし（{rank_badge(previous_rank)}）"
            st.write(f"**総合ランク**: {arrow}")

        for ad in diff.get("axis_deltas", []) or []:
            delta = ad.get("delta", 0)
            arrow = "▲" if delta > 0 else ("▼" if delta < 0 else "→")
            st.write(
                f"- {ad.get('axis_label', ad.get('axis'))}: "
                f"{ad.get('previous_score')} → {ad.get('current_score')} ({arrow}{abs(delta)})"
            )


def render_legacy_improvements(tab_key: str, asset_id: str, improvements: dict, improvements_error: dict):
    """decision_support が無い（旧データ・生成失敗）場合の従来形式フォールバック表示。"""
    st.markdown("### ✨ 改善提案（従来形式）")
    if improvements_error:
        st.warning(f"⚠️ 改善コメント生成に失敗しました (Error: {improvements_error.get('error_code', 'UNKNOWN')})")
        reason = improvements_error.get("reason")
        if reason:
            st.write(f"**理由**: {reason}")
        st.write("**次のアクション**: 時間をおいて再度分析を実行するか、下記の CreativeCore 分析結果（トーン・ビジュアル）を参考に改善を検討してください。")
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


def render_asset_detail(tab_key: str, detail: dict, asset_id: str, on_delete_success=None):
    """
    分析結果1件分の詳細表示（意思決定支援 / 補助情報 / ダウンロード / 削除）。

    「新規分析」完了直後の結果表示と、「保存済み結果」からの詳細表示の両方で使う共通描画関数。
    tab_key は widget key の名前空間分離用（呼び出し元ごとにユニークにする）。
    """
    asset_meta = detail.get("asset_meta", {}) or {}
    creative_core = detail.get("creative_core", {}) or {}
    diagnostics = detail.get("diagnostics", {}) or {}
    improvements = diagnostics.get("improvements")
    improvements_error = diagnostics.get("improvements_error")
    decision_support = diagnostics.get("decision_support")
    decision_support_error = diagnostics.get("decision_support_error")

    st.write(
        f"**🆔 Asset ID**: {asset_meta.get('asset_id', asset_id)}"
        f"（`{creative_core.get('format', 'N/A')}`）"
    )

    # ===== 主画面: 意思決定支援 =====
    # 3分岐フォールバック:
    #   1. 新形式（axesあり）: 5軸 × 強み/弱み/改善提案の新UI
    #   2. 旧形式（axesなし、strengths/weaknessesあり）: 従来のフラット表示（データ移行不要）
    #   3. decision_support自体が無い: 従来の改善コメント表示
    if decision_support and decision_support.get("axes"):
        render_decision_support_axes(decision_support)
        render_decision_support_diff(diagnostics.get("decision_support_diff"))
    elif decision_support:
        render_decision_summary(decision_support.get("summary", {}) or {})
        render_strengths(decision_support.get("strengths", []) or [])
        weaknesses = decision_support.get("weaknesses", []) or []
        render_weaknesses(weaknesses)
        render_recommendations(decision_support.get("recommendations", []) or [], weaknesses)
    else:
        if decision_support_error:
            st.warning(
                "⚠️ 意思決定支援（強み・弱み・改善提案）の生成に失敗したため、"
                f"従来形式で表示しています (Error: {decision_support_error.get('error_code', 'UNKNOWN')})"
            )
        else:
            st.caption("ℹ️ この結果は意思決定支援UIの追加前に作成されたため、従来形式で表示しています。")
        render_legacy_improvements(tab_key, asset_id, improvements, improvements_error)

    # ===== 補助情報（折りたたみ）: CreativeCore / 改善コメント原文 / LLMメタデータ / 完全なJSON =====
    visuals = creative_core.get("visuals", {}) or {}
    tone = creative_core.get("tone", {}) or {}
    ai_labels = creative_core.get("ai_labels", []) or []
    with st.expander(
        "🔍 診断根拠データ（CreativeCore分析結果）",
        expanded=False,
        key=widget_key(tab_key, "expander_creative_core", asset_id),
    ):
        if visuals or tone or ai_labels:
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
            st.json({"visuals": visuals, "tone": tone, "ai_labels": ai_labels})
        else:
            st.info("CreativeCore分析結果はありません。")

        # decision_support がある場合、改善コメント原文（improvements）はここに参考情報として残す。
        if decision_support and improvements and improvements.get("comments"):
            st.markdown("##### 🗒️ 生成された改善コメント（原文・参考情報）")
            st.json(improvements)

    if diagnostics:
        with st.expander(
            "🤖 LLM分析メタデータ",
            expanded=False,
            key=widget_key(tab_key, "expander_llm_meta", asset_id),
        ):
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Model", diagnostics.get("llm_model", "N/A"))
            with col2:
                st.metric("Success", "✅" if diagnostics.get("llm_success") else "❌")
            with col3:
                st.metric("Retries", diagnostics.get("llm_retry_count", 0))
            if diagnostics.get("llm_error"):
                st.error(f"⚠️ エラー: {diagnostics['llm_error']}")

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

    # ===== 削除（st.dialog による確認モーダル） =====
    # 削除APIは asset_id 単位（DELETE /{asset_id}）であり、現在表示中の
    # version だけでなく、この asset_id の全バージョンをまとめて論理削除する。
    # モーダル内でその範囲を誤解しないよう、対象・粒度・削除後の挙動を明示する。
    displayed_version = detail.get("version")
    delete_dialog_open_key = widget_key(tab_key, "delete_dialog_open", asset_id)

    @st.dialog(f"⚠️ {asset_id} を削除しますか？")
    def _confirm_delete_dialog():
        st.caption(
            f"🆔 対象 Asset ID: `{asset_id}`"
            + (f"（現在表示中: version {displayed_version}）" if displayed_version else "")
        )
        st.write(
            "**削除の範囲**: version 単位ではなく、この asset_id に紐づく"
            "**全バージョン**が対象です。特定バージョンだけを消すことはできません。"
        )
        st.write(
            "**削除後**: 論理削除（データベース上は残り、管理者が必要なら復元可能）"
            "され、「保存済み結果」の一覧・詳細からは見えなくなります。不可逆な操作です。"
        )
        col_cancel, col_confirm = st.columns(2)
        with col_cancel:
            if st.button("キャンセル", key=widget_key(tab_key, "delete_cancel", asset_id)):
                st.session_state[delete_dialog_open_key] = False
                st.rerun()
        with col_confirm:
            if st.button(
                f"🔴 {asset_id} を削除する（全バージョン）",
                key=widget_key(tab_key, "delete_execute", asset_id),
            ):
                with st.spinner(f"🗑️ {asset_id} を削除中..."):
                    try:
                        response = requests.delete(f"{API_BASE_URL}/{asset_id}")
                        if response.status_code == 200:
                            st.session_state[delete_dialog_open_key] = False
                            if on_delete_success:
                                on_delete_success()
                            st.rerun()
                        else:
                            st.error(f"❌ エラー: {response.status_code}\n{response.text}")
                    except Exception as e:
                        st.error(f"❌ API 呼び出しエラー: {str(e)}")

    if st.button(
        f"🗑️ この分析結果を削除（{asset_id} の全バージョンが対象）",
        key=widget_key(tab_key, "delete_open", asset_id),
    ):
        st.session_state[delete_dialog_open_key] = True

    if st.session_state.get(delete_dialog_open_key):
        _confirm_delete_dialog()


# ページ設定
st.set_page_config(
    page_title="CampaignPilot",
    page_icon="📊",
    layout="wide",
    menu_items={
        "About": "CampaignPilot — 広告・LP・KPIを横断して診断し、改善アクションを判断するためのサービスです。",
    },
)
st.title("📊 CampaignPilot")

# API ベース URL（環境に応じて変更可）
API_BASE_URL = "http://localhost:8000/api/v1/specs"

init_session_state()
restore_analysis_result_from_query_params()

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

    asset_name_input = st.text_input(
        "広告名/キャンペーン名（任意・未入力時はアップロードファイル名を使用）",
        key=widget_key("analyze", "asset_name_input"),
    )

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
                if asset_name_input:
                    data["asset_name"] = asset_name_input
                response = requests.post(f"{API_BASE_URL}/analyze", files=files, data=data, timeout=60)

                if response.status_code == 200:
                    add_log("✅ 分析完了")
                    result = response.json()
                    st.session_state["analysis_result"] = result
                    # 「保存済み結果」タブへ移動した場合でも、直近に分析したこの
                    # asset/version が selected として引き継がれるようにする。
                    result_id = result.get("asset_meta", {}).get("asset_id")
                    result_version = result.get("version")
                    st.session_state["selected_asset_id"] = result_id
                    st.session_state["selected_version"] = result_version
                    # ページリロード等でセッションが失われても復元できるよう、
                    # URLにも同じ asset_id/version を残しておく。
                    set_analysis_result_query_params(result_id, result_version)
                else:
                    add_log(f"❌ エラー: {response.status_code}")
                    try:
                        err_json = response.json()
                    except Exception:
                        err_json = None

                    st.session_state["analysis_result"] = None
                    clear_analysis_result_query_params()

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
                st.session_state["analysis_result"] = None
                clear_analysis_result_query_params()
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
        # LLM分析メタデータは render_asset_detail 内の折りたたみ（補助情報）に統合済み。

        def _clear_analysis_result():
            st.session_state["analysis_result"] = None
            clear_analysis_result_query_params()

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
            st.session_state["detail_version_input_for_asset"] = None
            st.rerun()

        # widget の値は key="detail_version_input" が唯一の正とし、value= は渡さない
        # （value= と session_state の二重管理は Streamlit で警告・表示ズレの原因になりうる）。
        # selected_version はあくまで「遷移時の初期値ヒント」であり、
        # 表示中の asset_id が切り替わったタイミングだけ widget state に流し込む。
        # 同じ asset_id を見ている間にユーザーが手で変更した値は、次の rerun でも
        # 上書きされずそのまま尊重される。
        if st.session_state.get("detail_version_input_for_asset") != asset_id:
            st.session_state["detail_version_input"] = st.session_state.get("selected_version") or 1
            st.session_state["detail_version_input_for_asset"] = asset_id

        version = st.number_input(
            "Version（未指定/1のままなら選択時点の最新版を取得）",
            min_value=1,
            step=1,
            key="detail_version_input",
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
                    st.session_state["detail_version_input_for_asset"] = None
                    # 削除直後の一覧に削除済みカードが残らないよう、最新状態を取得し直す
                    refresh_saved_list()

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
            with st.spinner("📊 一覧を取得中..."):
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
        #
        # 注意: st.rerun() はループ/コンテナの内側から即座に呼ばない。ループ途中で
        # 画面がすでに部分的にフロントエンドへ送信された状態で rerun すると、
        # 直前まで描画されていた要素が新しい画面側に残留することがある
        # (実機検証で再現・特定済み)。クリックの意図はいったん変数で受け取り、
        # ループ完了・コンテナを抜けた後にまとめて反映する。
        navigate_to_asset_id = None
        navigate_to_version = None
        for idx, item in enumerate(st.session_state.get("list_items", [])):
            item_asset_meta = item.get("asset_meta", {}) or {}
            item_asset_id = item_asset_meta.get("asset_id", "unknown")
            item_name = item_asset_meta.get("asset_name") or item_asset_id
            item_format = item.get("creative_core", {}).get("format", "N/A")
            item_version = item.get("version")
            item_created_at = item.get("created_at")
            item_diag = item.get("diagnostics", {}) or {}
            item_decision_support = item_diag.get("decision_support")
            item_improvements = item_diag.get("improvements")

            with st.container(border=True):
                header_cols = st.columns([3, 1, 1])
                with header_cols[0]:
                    st.write(f"**📌 {item_name}**（`{item_format}`）")
                    st.caption(f"🆔 {item_asset_id}")
                with header_cols[1]:
                    if item_created_at:
                        st.caption(f"🗓️ {item_created_at[:19].replace('T', ' ')}")
                with header_cols[2]:
                    if item_decision_support and item_decision_support.get("overall_rank"):
                        st.write(f"**{rank_badge(item_decision_support.get('overall_rank'))}**")
                    else:
                        st.caption("ランク —")

                # 主要改善ポイント1〜2件: 新形式は軸weaknessをスコア昇順、
                # 旧データは従来の improvements 先頭コメントにフォールバック。
                if item_decision_support and item_decision_support.get("axes"):
                    worst_axes = sorted(
                        item_decision_support.get("axes", []),
                        key=lambda a: a.get("score", 99),
                    )[:2]
                    for axis in worst_axes:
                        weakness = axis.get("weakness", {}) or {}
                        st.write(
                            f"📝 {axis_label(axis.get('axis'))}: "
                            f"{weakness.get('description', weakness.get('target_element', 'N/A'))}"
                        )
                elif item_improvements and item_improvements.get("comments"):
                    first_comment = item_improvements["comments"][0]
                    st.write(
                        f"優先度: **{first_comment.get('priority', 'N/A')}** | "
                        f"次アクション: {first_comment.get('recommended_action', 'N/A')}"
                    )
                else:
                    st.write("📝 改善コメントはありません。")

                if st.button("🔍 詳細を見る", key=widget_key("saved_list", "select_detail", item_asset_id, idx)):
                    navigate_to_asset_id = item_asset_id
                    navigate_to_version = item_version
                with st.expander(
                    "🔧 JSON（デバッグ用）",
                    expanded=False,
                    key=widget_key("saved_list", "expander_json", item_asset_id, idx),
                ):
                    st.json(item)
                st.divider()

        if navigate_to_asset_id is not None:
            st.session_state["current_view"] = "detail"
            st.session_state["selected_asset_id"] = navigate_to_asset_id
            # 一覧カードの版（最新版）をそのまま詳細画面に引き継ぎ、
            # 「一覧は最新版、詳細はv1」という表示不整合を防ぐ。
            st.session_state["selected_version"] = navigate_to_version
            st.rerun()

# ============ フッター ============
st.divider()
st.caption("Phase 2b Minimum UI | CampaignPilot v0.2")
