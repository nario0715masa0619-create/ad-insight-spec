import streamlit as st
import requests
import json
import os
import threading
import time
import html as html_module
from datetime import datetime


def render_api_exception(e: Exception):
    # requests.exceptions.ConnectionError（backend未起動・落ちている等）や
    # Timeout（サーバー処理が長引いている等）は、生の urllib3 スタックトレース
    # 文字列をそのまま出すとユーザーには「壊れた」ように見えるため、原因と
    # 次のアクションが分かる穏当なメッセージに差し替える。
    # 注意: requests.exceptions.ConnectTimeout は Timeout と ConnectionError の
    # 両方を継承しているため、Timeout の判定を ConnectionError より先に行う。
    if isinstance(e, requests.exceptions.Timeout):
        st.error("⏱️ タイムアウトしました。サーバーからの応答に時間がかかりすぎています。")
        st.write("**次のアクション**: もう一度お試しください。繰り返し発生する場合は、ファイルサイズやサーバーの状態をご確認ください。")
    elif isinstance(e, requests.exceptions.ConnectionError):
        st.error(
            f"❌ バックエンドAPI（{API_BASE_URL}）に接続できません。"
            "バックエンドサーバーが起動しているか確認してください。"
        )
    else:
        st.error(f"❌ API 呼び出しエラー: {str(e)}")


# ===== 分析実行中の進捗表示 =====
# バックエンドの /analyze は単一の同期APIで、内部の各処理ステップ（OCR/LLM等）の
# 実況はサーバー側から取得できない。そのため、リクエストはバックグラウンド
# スレッドで実行し、メインスレッド側は経過時間をもとにした見込みステップを
# 一定間隔で描画し続けることで「止まっているように見える」問題を解消する。
# ステップの厳密な完了検知ではなく、体感的な進行表示であることに注意。
ANALYZE_PROGRESS_STEPS = [
    "ファイルアップロード完了",
    "API送信中…",
    "サーバーで解析中…",
    "AIが5軸を分析中…",
    "結果を表示中…",
]
# 各ステップに到達したとみなす経過秒数の目安（実測値ベースの経験則）
ANALYZE_PROGRESS_THRESHOLDS = [0, 0, 2, 8]
# リクエスト自体のタイムアウト（秒）。5軸診断生成（generate_decision_support）は
# 実測で1回あたり約20〜25秒、improvements/decision_support とも最大3回リトライ
# し得るため、直列実行だと理論上の最大待ち時間は100秒を超える。バックエンド側で
# improvements と decision_support を並列実行するよう変更した後も、リトライが
# 重なった場合に備えて十分な余裕を持たせる。
ANALYZE_REQUEST_TIMEOUT_SECONDS = 150
# この秒数を超えたら「通常より時間がかかっています」という案内に切り替える
# （リクエスト自体のタイムアウトとは別の、体感メッセージ用のしきい値）
ANALYZE_SLOW_WARNING_SECONDS = 60


def run_analyze_with_progress(files: dict, data: dict):
    """
    /analyze へのリクエストをバックグラウンドスレッドで実行しつつ、
    メインスレッド側でステップ進行・経過時間・プログレスバーを更新し続ける。

    Streamlit の st.* 呼び出しはメインスレッドからのみ行う必要があるため、
    バックグラウンドスレッドは requests.post の実行と結果の受け渡しのみ行う。

    Returns:
        (response, exception): 成功時は (Response, None)、例外時は (None, Exception)
    """
    result = {"response": None, "exception": None}

    def _worker():
        try:
            result["response"] = requests.post(
                f"{API_BASE_URL}/analyze", files=files, data=data, timeout=ANALYZE_REQUEST_TIMEOUT_SECONDS
            )
        except Exception as e:
            result["exception"] = e

    thread = threading.Thread(target=_worker, daemon=True)
    status_area = st.empty()
    progress_bar = st.progress(0)
    elapsed_area = st.empty()

    start_time = time.time()
    thread.start()
    while thread.is_alive():
        elapsed = time.time() - start_time

        current_step = 0
        for i, threshold in enumerate(ANALYZE_PROGRESS_THRESHOLDS):
            if elapsed >= threshold:
                current_step = i
        lines = []
        for i, step_label in enumerate(ANALYZE_PROGRESS_STEPS[:-1]):
            if i < current_step:
                lines.append(f"✅ {step_label}")
            elif i == current_step:
                lines.append(f"▶️ **{step_label}**")
            else:
                lines.append(f"⬜ {step_label}")
        status_area.markdown("\n\n".join(lines))

        # 正確な割合は取得できないため、経過時間から漸近的に近づける
        # （100%には到達させず、処理中であることが視覚的に分かる程度で十分）
        progress_bar.progress(min(0.92, elapsed / 90))

        if elapsed > ANALYZE_SLOW_WARNING_SECONDS:
            elapsed_area.warning(f"⏳ 経過時間: {int(elapsed)}秒 - 通常より時間がかかっていますが、処理は継続中です")
        else:
            elapsed_area.caption(f"⏳ 経過時間: {int(elapsed)}秒")

        time.sleep(0.5)

    thread.join()

    if result["exception"] is None:
        status_area.markdown(
            "\n\n".join(f"✅ {s}" for s in ANALYZE_PROGRESS_STEPS)
        )
        progress_bar.progress(1.0)
        elapsed_area.caption(f"⏳ 経過時間: {int(time.time() - start_time)}秒")
    else:
        status_area.empty()
        progress_bar.empty()
        elapsed_area.empty()

    return result["response"], result["exception"]


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
    """
    axes形式の decision_support の結論サマリー。

    読む順序を明確にするため、上から
    1. 結論（短い見出し）
    2. 短い補足説明（1〜2文）
    3. 総合ランク / 総合スコア / 判断（余白を取ったサマリーカード）
    の順で表示する。st.columns は狭い画面幅では自動的に縦積みになる。
    """
    summary = decision_support.get("summary", {}) or {}
    headline = summary.get("headline") or "結論サマリー"
    decision = summary.get("decision")
    rationale = summary.get("rationale")
    overall_rank = decision_support.get("overall_rank")
    overall_score = decision_support.get("overall_score")

    with st.container(border=True):
        # 第一優先: 結論
        st.markdown(f"### 🧭 {headline}")

        # 第二優先: 短い補足説明（結論と重複しない前提の1〜2文）
        if rationale:
            st.write(rationale)

        st.divider()

        # 第三優先: ランク / スコア / 判断（十分な余白を取ったサマリー表示）
        col_rank, col_score, col_decision = st.columns(3)
        with col_rank:
            st.caption("総合ランク")
            st.markdown(f"#### {rank_badge(overall_rank)}")
        with col_score:
            st.caption("総合スコア")
            st.markdown(f"#### {overall_score:.1f} / 5" if overall_score is not None else "#### —")
        with col_decision:
            st.caption("判断")
            st.markdown(f"#### {DECISION_LABELS.get(decision, decision) if decision else '—'}")


def render_evidence(evidence: dict):
    """
    判断根拠を項目ごとに分けた構造化表示にする（1行詰め込み表示にしない）。
    「評価」を最も目立たせ、「根拠」は補足として弱い見た目にする。
    """
    if not evidence:
        return
    with st.container(border=True):
        st.caption("対象箇所")
        st.write(evidence.get("location", "N/A"))

        st.caption("観点")
        st.write(evidence.get("viewpoint", "N/A"))

        st.caption("評価")
        st.markdown(f"**{evidence.get('evaluation', 'N/A')}**")

        st.caption("根拠")
        st.caption(evidence.get("rationale", "N/A"))


def render_axis_block(tab_key: str, asset_id: str, axis: dict, expanded: bool = False):
    """
    1軸分（強み・弱み・改善提案の3点セット必須）の表示。

    ヘッダー（軸名・スコア・改善余地の一言サマリ）は常時表示し、詳細
    （強み/弱み/改善提案の本文）はst.expanderでクリック開閉するアコーディオン
    にする（縦に長くなりすぎる診断結果画面の一覧性を上げるため）。
    """
    axis_id = axis.get("axis")
    score = axis.get("score")
    strength = axis.get("strength", {}) or {}
    weakness = axis.get("weakness", {}) or {}
    recommendation = axis.get("recommendation", {}) or {}

    weakness_aspect = weakness.get("aspect")
    header = f"{axis_label(axis_id)}　{score_stars(score)}（{score if score is not None else '?'}/5）"
    if weakness_aspect:
        header += f"　—　改善余地: {weakness_aspect}"

    with st.expander(header, expanded=expanded, key=widget_key(tab_key, "expander_axis", asset_id, axis_id)):
        strength_aspect = strength.get("aspect")
        st.markdown(f"**🟢 強み（{strength_aspect}）**" if strength_aspect else "**🟢 強み**")
        st.write(f"対象: {strength.get('target_element', 'N/A')}")
        st.write(strength.get("description", ""))
        reason = strength.get("reason")
        if reason:
            st.caption(f"💡 理由: {reason}")
        keep_reason = strength.get("keep_reason")
        if keep_reason:
            st.caption(f"🔒 維持すべき理由: {keep_reason}")
        render_evidence(strength.get("evidence"))

        st.markdown(f"**🔴 弱み（{weakness_aspect}）**" if weakness_aspect else "**🔴 弱み**")
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


def render_decision_support_axes(tab_key: str, asset_id: str, decision_support: dict):
    """axes形式の decision_support 本体（5軸を固定順で表示）"""
    render_overall_score_card(decision_support)
    axes_by_id = {a.get("axis"): a for a in decision_support.get("axes", []) or []}

    # デフォルトはすべて折りたたみ。ただし最もスコアが低い軸（同点はAXIS_ORDER先頭を優先）
    # だけ初期状態で開いておき、最初に見るべき箇所を自然に示す。
    lowest_axis_id = None
    lowest_score = None
    for axis_id in AXIS_ORDER:
        axis = axes_by_id.get(axis_id)
        if axis and axis.get("score") is not None:
            if lowest_score is None or axis["score"] < lowest_score:
                lowest_score = axis["score"]
                lowest_axis_id = axis_id

    for axis_id in AXIS_ORDER:
        axis = axes_by_id.get(axis_id)
        if axis:
            render_axis_block(tab_key, asset_id, axis, expanded=(axis_id == lowest_axis_id))


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


# ===== 5軸診断が生成できなかった場合の理由説明 =====
# バックエンドの decision_support_error.error_code は内部向けの技術用語
# （バリデーション失敗・抽象語検知・時間予算超過 等）なので、そのままUIに
# 出さず、ユーザーに伝わる自然な日本語（理由 + 次のアクション）に翻訳する。
DECISION_SUPPORT_ERROR_EXPLANATIONS = {
    "ITEM_VALIDATION_FAILED": {
        "reason": "生成された分析結果が、社内の品質基準を満たさなかったためです。",
        "action": "別のクリエイティブで再度お試しいただくか、時間をおいてもう一度実行してみてください。",
    },
    "AXIS_COVERAGE_INVALID": {
        "reason": "生成された分析結果が、社内の品質基準を満たさなかったためです。",
        "action": "別のクリエイティブで再度お試しいただくか、時間をおいてもう一度実行してみてください。",
    },
    "MAX_RETRIES_EXCEEDED": {
        "reason": "生成された分析結果が、社内の品質基準を満たさなかったためです。",
        "action": "別のクリエイティブで再度お試しいただくか、時間をおいてもう一度実行してみてください。",
    },
    "TIME_BUDGET_EXCEEDED": {
        "reason": "映像・画像の内容が抽象的で、診断に必要な具体的な情報（訴求内容やテキストなど）が十分に読み取れなかった可能性があります。",
        "action": "訴求やテキストがより明確なクリエイティブで再分析してみてください。",
    },
    "JSON_PARSE_ERROR": {
        "reason": "分析結果を生成する過程で、一時的な不具合が発生しました。",
        "action": "時間をおいてもう一度実行してみてください。",
    },
    "LLM_ERROR": {
        "reason": "分析結果を生成する過程で、一時的な不具合が発生しました。",
        "action": "時間をおいてもう一度実行してみてください。",
    },
    "API_KEY_MISSING": {
        "reason": "システム側の設定により、分析機能を一時的にご利用いただけない状態でした。",
        "action": "時間をおいて再度お試しいただき、解決しない場合は管理者にご確認ください。",
    },
    "INSUFFICIENT_TEXT_SOURCE": {
        "reason": "明示的なメッセージ（テロップやナレーション）がほぼ無いため、現在の5軸診断では十分な精度で評価できませんでした。",
        "action": "テロップを追加するか、ナレーション音声を含む動画で再度お試しください。",
    },
}
DECISION_SUPPORT_ERROR_EXPLANATION_DEFAULT = {
    "reason": "分析結果を生成する過程で、想定外の問題が発生しました。",
    "action": "時間をおいてもう一度実行してみてください。",
}

CREATIVE_FORMAT_LABELS = {
    "video_static": "動画",
    "image_static": "画像",
}


def render_decision_support_missing_notice(
    tab_key: str, asset_id: str, creative_format: str, decision_support_error: dict
):
    """
    5軸診断（decision_support）が生成できなかった場合の理由説明ボックス。

    「新規分析」「保存済み結果」どちらの詳細画面でも render_asset_detail 経由で
    共通して使われるため、表示ルールは自動的に両方に適用される。
    """
    format_label = CREATIVE_FORMAT_LABELS.get(creative_format, "クリエイティブ")
    error_code = (decision_support_error or {}).get("error_code")
    explanation = DECISION_SUPPORT_ERROR_EXPLANATIONS.get(error_code, DECISION_SUPPORT_ERROR_EXPLANATION_DEFAULT)

    with st.container(border=True):
        st.markdown(f"### ℹ️ この{format_label}では5軸診断を生成できませんでした")
        st.write(f"**理由**: {explanation['reason']}")
        st.write(f"**次にお試しいただきたいこと**: {explanation['action']}")

        internal_reason = (decision_support_error or {}).get("reason")
        if internal_reason:
            with st.expander(
                "詳細理由を見る",
                expanded=False,
                key=widget_key(tab_key, "expander_decision_support_error", asset_id),
            ):
                st.caption("品質基準を満たさなかった項目の概要（社内向け詳細情報）:")
                st.code(internal_reason, language=None)

    st.caption("以下は、従来形式での改善コメントです（参考情報）。")


# ===== カット別分析（video_cuts、動画のみ） =====
VIDEO_CUTS_ERROR_EXPLANATIONS = {
    "CUT_COVERAGE_INVALID": {
        "reason": "生成された分析結果が、社内の品質基準を満たさなかったためです。",
        "action": "時間をおいてもう一度実行してみてください。",
    },
    "ITEM_VALIDATION_FAILED": {
        "reason": "生成された分析結果が、社内の品質基準を満たさなかったためです。",
        "action": "時間をおいてもう一度実行してみてください。",
    },
    "TIME_BUDGET_EXCEEDED": {
        "reason": "動画の内容からカットごとの判断材料を十分に読み取れず、分析に時間がかかりすぎました。",
        "action": "訴求やテキストがより明確なカット構成の動画で再度お試しください。",
    },
    "JSON_PARSE_ERROR": {
        "reason": "分析結果を生成する過程で、一時的な不具合が発生しました。",
        "action": "時間をおいてもう一度実行してみてください。",
    },
    "LLM_ERROR": {
        "reason": "分析結果を生成する過程で、一時的な不具合が発生しました。",
        "action": "時間をおいてもう一度実行してみてください。",
    },
    "API_KEY_MISSING": {
        "reason": "システム側の設定により、分析機能を一時的にご利用いただけない状態でした。",
        "action": "時間をおいて再度お試しいただき、解決しない場合は管理者にご確認ください。",
    },
    "NO_CUTS": {
        "reason": "動画からカット（シーンの区切り）を検出できませんでした。",
        "action": "別の動画で再度お試しください。",
    },
    "NO_FRAMES": {
        "reason": "カットの代表フレームを取得できませんでした。",
        "action": "時間をおいてもう一度実行してみてください。",
    },
}
VIDEO_CUTS_ERROR_EXPLANATION_DEFAULT = {
    "reason": "分析結果を生成する過程で、想定外の問題が発生しました。",
    "action": "時間をおいてもう一度実行してみてください。",
}


def render_video_cuts_missing_notice(tab_key: str, asset_id: str, error_code: str, internal_reason: str = None):
    """
    カット別分析が生成できなかった場合の理由説明ボックス（decision_supportと同じトーン）。

    error_code/internal_reason は新形式（generation_status.error_code、reasonは無し）
    ・旧形式（video_cuts_error.error_code/.reason）のどちらから来てもよいよう、
    呼び出し側で正規化してから渡す。
    """
    explanation = VIDEO_CUTS_ERROR_EXPLANATIONS.get(error_code, VIDEO_CUTS_ERROR_EXPLANATION_DEFAULT)

    with st.container(border=True):
        st.markdown("### ℹ️ カット別分析を生成できませんでした")
        st.write(f"**理由**: {explanation['reason']}")
        st.write(f"**次にお試しいただきたいこと**: {explanation['action']}")

        if internal_reason:
            with st.expander(
                "詳細理由を見る",
                expanded=False,
                key=widget_key(tab_key, "expander_video_cuts_error", asset_id),
            ):
                st.caption("品質基準を満たさなかった項目の概要（社内向け詳細情報）:")
                st.code(internal_reason, language=None)


def format_mmss(seconds) -> str:
    """秒数を MM:SS 形式にフォーマットする（人が読む表示用。内部では秒数のまま保持する）。"""
    if seconds is None:
        return "--:--"
    total = max(0, int(round(seconds)))
    m, s = divmod(total, 60)
    return f"{m:02d}:{s:02d}"


# ===== カットの役割タグ → 色・アイコンの対応 =====
# バックエンド側（llm_response.normalize_role_tag）で role_tag は内部語彙
# （hook/benefit/proof/trust/cta/other）へ正規化されてから保存される。
# 旧データはこの正規化を経ていない自由記述（例:「証拠・信頼形成」）のままなので、
# ここでも部分一致によるフォールバックマッピングを残す（後方互換）。
# 色は dataviz スキルの検証済みカテゴリカルパレットから採用し、
# light/dark 両方で node scripts/validate_palette.js による検証を通過済み。
ROLE_TAG_STYLES = {
    "hook": {"label": "Hook", "icon": "🪝", "light": "#2a78d6", "dark": "#3987e5"},
    "benefit": {"label": "ベネフィット提示", "icon": "💡", "light": "#1baf7a", "dark": "#199e70"},
    "proof": {"label": "証拠提示", "icon": "🧾", "light": "#eda100", "dark": "#c98500"},
    "trust": {"label": "信頼形成", "icon": "🤝", "light": "#4a3aa7", "dark": "#9085e9"},
    "cta": {"label": "CTA", "icon": "📣", "light": "#008300", "dark": "#008300"},
    "other": {"label": "その他", "icon": "⬜", "light": "#898781", "dark": "#898781"},
}


def _role_tag_style_key(role_tag) -> str:
    t = (role_tag or "").strip().lower()
    if t in ROLE_TAG_STYLES:
        # 新形式: バックエンドで正規化済みの内部語彙がそのまま入っている
        return t
    # 旧データ・自由記述からのフォールバックマッピング（後方互換）
    if "hook" in t:
        return "hook"
    if "ベネフィット" in t or "benefit" in t:
        return "benefit"
    if "証拠" in t or "proof" in t:
        return "proof"
    if "信頼" in t or "trust" in t:
        return "trust"
    if "cta" in t:
        return "cta"
    return "other"


def render_video_composition_header(cuts: list, video_summary: dict = None):
    """
    動画の尺・カット数・Hook位置を一目で把握できるヘッダー。
    タイムラインバーは各カットの長さに比例した幅・役割タグ別の色分けで構成する。
    目的はテンポ・構成の把握であり、再生機能は持たない。

    video_summary（新形式のみ存在）があればそちらの値を優先する
    （カットが未整列・非連続でも表示側で再計算が不要になるため）。
    """
    if not cuts:
        return

    total_duration = (video_summary or {}).get("total_duration_seconds")
    if total_duration is None:
        total_duration = max((c.get("end_seconds") or 0) for c in cuts)
    cut_count = (video_summary or {}).get("cut_count") or len(cuts)
    hook_cut = next(
        (c for c in cuts if _role_tag_style_key(c.get("role_tag")) == "hook"),
        cuts[0],
    )
    hook_start = hook_cut.get("start_seconds")
    hook_within_3s = hook_start is not None and hook_start < 3.0

    col1, col2, col3 = st.columns(3)
    with col1:
        st.caption("動画の長さ")
        st.markdown(f"#### {format_mmss(total_duration)}")
    with col2:
        st.caption("カット数")
        st.markdown(f"#### {cut_count}")
    with col3:
        st.caption("Hookの位置")
        hook_range = f"{format_mmss(hook_start)}〜{format_mmss(hook_cut.get('end_seconds'))}"
        st.markdown(f"#### {'✅' if hook_within_3s else '⚠️'} {hook_range}")
        if not hook_within_3s:
            st.caption("冒頭3秒を超えています")

    # ===== タイムラインバー =====
    segment_tags = []
    for c in cuts:
        start = c.get("start_seconds") or 0
        end = c.get("end_seconds") or start
        duration = max(end - start, 0.1)
        style_key = _role_tag_style_key(c.get("role_tag"))
        style = ROLE_TAG_STYLES[style_key]
        tooltip = html_module.escape(
            f"{c.get('cut_id', '')}: {format_mmss(start)}〜{format_mmss(end)}（{style['label']}）",
            quote=True,
        )
        segment_tags.append(
            f'<div class="video-timeline-segment" '
            f'style="flex: {duration} 0 0; background: var(--role-{style_key});" '
            f'title="{tooltip}">{style["icon"]}</div>'
        )

    light_vars = "; ".join(f"--role-{k}: {v['light']}" for k, v in ROLE_TAG_STYLES.items())
    dark_vars = "; ".join(f"--role-{k}: {v['dark']}" for k, v in ROLE_TAG_STYLES.items())

    st.markdown(
        f"""
        <style>
        .video-timeline-wrap {{ {light_vars} }}
        @media (prefers-color-scheme: dark) {{
            .video-timeline-wrap {{ {dark_vars} }}
        }}
        .video-timeline-bar {{
            display: flex;
            width: 100%;
            height: 32px;
            border-radius: 6px;
            overflow: hidden;
            gap: 2px;
        }}
        .video-timeline-segment {{
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-size: 14px;
            min-width: 4px;
        }}
        </style>
        <div class="video-timeline-wrap">
          <div class="video-timeline-bar">{''.join(segment_tags)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # 凡例（登場した役割タグのみ、正規化後の日本語ラベルで表示）
    seen = set()
    legend_parts = []
    for c in cuts:
        key = _role_tag_style_key(c.get("role_tag"))
        if key in seen:
            continue
        seen.add(key)
        legend_parts.append(f"{ROLE_TAG_STYLES[key]['icon']} {ROLE_TAG_STYLES[key]['label']}")
    st.caption("　".join(legend_parts))


def render_video_cut_card(tab_key: str, asset_id: str, cut: dict):
    """
    カット1件分のカード表示。

    ヘッダー（カット番号・時間範囲・役割）は常時表示し、詳細（要約・評価・
    根拠・改善提案）はst.expanderでクリック開閉するアコーディオンにする
    （カット数が多い動画でもヘッダー一覧をスクロールしながら気になるカット
    だけ開けるようにするため）。
    """
    start = cut.get("start_seconds")
    end = cut.get("end_seconds")
    has_range = start is not None and end is not None
    time_range = f"{format_mmss(start)}〜{format_mmss(end)}" if has_range else "時間範囲不明"
    duration_text = f"（{end - start:.1f}秒）" if has_range else ""
    # 最初の3秒以内から始まるカットは Hook として視覚的に強調する
    is_hook = start is not None and start < 3.0
    title_prefix = "🔥 " if is_hook else ""
    style = ROLE_TAG_STYLES[_role_tag_style_key(cut.get("role_tag"))]
    cut_id = cut.get("cut_id", "カット")

    header = f"{title_prefix}{cut_id}　{time_range}{duration_text}　{style['icon']} {style['label']}"

    with st.expander(header, expanded=False, key=widget_key(tab_key, "expander_cut", asset_id, cut_id)):
        st.write(cut.get("summary", ""))
        # strength_or_issue は「強み」「問題点」のどちらか一方が入るフィールド（JSON構造は不変）。
        # 表示側では「強み/問題点」という曖昧なラベルをやめ、内容がポジティブ/ネガティブ
        # どちらでも違和感のない「このカットの評価」に統一する。
        strength_or_issue = cut.get("strength_or_issue")
        if strength_or_issue:
            st.caption(f"💡 このカットの評価: {strength_or_issue}")
        st.write(f"**改善提案**: {cut.get('improvement_suggestion', 'N/A')}")
        # evidence は単独の「根拠」だと何に対する根拠か伝わらないため、
        # 直前の評価（このカットの評価）に対する根拠であることが一読でわかるようにする。
        evidence = cut.get("evidence")
        if evidence:
            st.caption(f"🔍 この評価の根拠: {evidence}")


def render_video_cuts(tab_key: str, asset_id: str, cuts: list, video_summary: dict = None):
    """カット別分析セクション全体（動画分析結果の下部に表示）。cutsは正規化済みカットのリスト。"""
    if not cuts:
        return
    st.markdown("### 🎬 カット別分析")
    st.caption("シーン切り替え・構図変化を目安にした、ざっくりしたカット単位の分析です。")
    render_video_composition_header(cuts, video_summary)
    st.divider()
    for cut in cuts:
        render_video_cut_card(tab_key, asset_id, cut)


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
        render_decision_support_axes(tab_key, asset_id, decision_support)
        render_decision_support_diff(diagnostics.get("decision_support_diff"))
    elif decision_support:
        render_decision_summary(decision_support.get("summary", {}) or {})
        render_strengths(decision_support.get("strengths", []) or [])
        weaknesses = decision_support.get("weaknesses", []) or []
        render_weaknesses(weaknesses)
        render_recommendations(decision_support.get("recommendations", []) or [], weaknesses)
    else:
        if decision_support_error:
            render_decision_support_missing_notice(
                tab_key, asset_id, creative_core.get("format"), decision_support_error
            )
        else:
            st.caption("ℹ️ この結果は意思決定支援UIの追加前に作成されたため、従来形式で表示しています。")
        render_legacy_improvements(tab_key, asset_id, improvements, improvements_error)

    # ===== カット別分析（video_cuts、動画のみ） =====
    # diagnostics.video_cuts は新形式（v1.0、schema_version/generation_status/
    # video_summary/video_cutsを1ブロックにまとめたもの）と旧形式
    # （{"cuts": [...]} 単体 + 別フィールドの video_cuts_error）の両方があり得る
    # （旧レコードはGET時に新スキーマへ再検証されないため、後方互換として両対応する）。
    #
    # 現時点では schema_version は "1.0" の1種類しかなく、ここでは
    # 「generation_status キーを持つか(=新形式)/持たないか(=旧形式)」だけで
    # 分岐している。将来 schema_version を上げる変更をする場合は、
    # この判定を video_cuts_raw.get("schema_version") の値による分岐へ拡張すること
    # （新形式が2種類以上に増えた時点で、キーの有無だけの判定は破綻する）。
    # 詳細: docs/specs/video_cuts_json_schema_v1_0.md
    if creative_core.get("format") == "video_static":
        video_cuts_raw = diagnostics.get("video_cuts")
        if isinstance(video_cuts_raw, dict) and "generation_status" in video_cuts_raw:
            status = (video_cuts_raw.get("generation_status") or {}).get("status")
            error_code = (video_cuts_raw.get("generation_status") or {}).get("error_code")
            cuts = video_cuts_raw.get("video_cuts") or []
            if status == "success" and cuts:
                render_video_cuts(tab_key, asset_id, cuts, video_cuts_raw.get("video_summary"))
            elif status == "failed":
                render_video_cuts_missing_notice(tab_key, asset_id, error_code)
            # not_attempted: カット別分析自体が未実施のため何も表示しない
        elif isinstance(video_cuts_raw, dict) and video_cuts_raw.get("cuts"):
            render_video_cuts(tab_key, asset_id, video_cuts_raw.get("cuts") or [])
        else:
            video_cuts_error = diagnostics.get("video_cuts_error")
            if video_cuts_error:
                render_video_cuts_missing_notice(
                    tab_key,
                    asset_id,
                    video_cuts_error.get("error_code"),
                    video_cuts_error.get("reason"),
                )

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
                        render_api_exception(e)

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
            files = {"input_file": uploaded_file}
            if lp_file_upload:
                files["lp_file"] = lp_file_upload
            if kpi_file_upload:
                files["kpi_file"] = kpi_file_upload
            data = {"mode": mode}
            if asset_name_input:
                data["asset_name"] = asset_name_input

            response, exception = run_analyze_with_progress(files, data)

            if exception is not None:
                # 前回成功時の analysis_result が残ったままだと、今回のエラー
                # メッセージの下に古い分析結果（5軸診断の全パネル）が
                # そのまま居座り、「エラーなのに結果が出ている」矛盾した画面になる。
                # URL の query params（result_asset_id/result_version）も、失敗した
                # この試行を指したまま残さないようクリアする。
                st.session_state["analysis_result"] = None
                clear_analysis_result_query_params()
                render_api_exception(exception)
            elif response.status_code == 200:
                st.success("✅ 分析完了")
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
            render_api_exception(e)

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
                    render_api_exception(e)

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
