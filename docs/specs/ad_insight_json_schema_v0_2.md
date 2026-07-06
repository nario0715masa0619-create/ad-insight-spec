# JSON Schema - Ad-Insight-Spec v0.2

**Version**: 0.2  
**Date**: 2026-06-22  
**Status**: APPROVED (Phase 1 - File-First Strategy)  
**Milestone**: MVP定義完了、Pydantic v0.2実装準備完了

---

## 📋 変更概要：v0.1 → v0.2

### 主な変更点

| 項目 | v0.1 | v0.2 | 理由 |
|------|------|------|------|
| **戦略** | Meta API-First | File-First | MVP高速化、ローカル開発重視 |
| **asset_meta** | ad_id一般向け | asset_id + 日時ベース一意性 | ダウンロード済み素材を起点にする |
| **external_ids** | strict | optional | API連携はPhase 2以降 |
| **performance** | always strict | mode依存で optional化 | KPIなし診断を必須化 |
| **creative_core** | 基本的なフィールドのみ | テキスト・ビジュアル分析強化 | 素材ファイルから直接抽出対応 |
| **landing_page** | message_match_score optional | consistency_basis 追加 | LLM根拠を記録 |
| **diagnostics** | flat | qualitative / quantitative分離 | KPI有無での分析体系分離 |

---

## 🎯 File-First Strategy の背景

### 採択理由

1. **Meta API の複雑性を回避**
   - OAuth認可フロー不要（ローカルファイル入力で即分析開始）
   - API rate limit対策不要（開発初期段階）
   - Graph APIのバージョン変更に依存しない

2. **MVP開発を2-3週間で完結**
   - ローカルファイル（動画/画像/HTML）を入力
   - LLM分析で Creative Fatigue / LP Match を診断
   - KPI不要な診断パスを最優先

3. **将来のマルチプラットフォーム対応を準備**
   - File-First パイプライン（ファイル → メタ抽出 → 診断 → JSON）は
   - Meta / Google / TikTok API との統合と矛盾しない
   - `input_mode` フィールドで入力源の記録

4. **実装者の負荷低減**
   - API認証・キー管理を後回し
   - ローカルテスト環境で完結
   - CI/CDパイプライン構築が簡単

---

## 📐 トップレベル構造

```json
// 現場の分析タスクに対応する各ブロックの役割は以下の通りです。同一スキーマでありながら、入力ソース（自社/競合/トレンドなど）に応じて文脈を切り替えて扱える設計としています。
{
  "input_metadata": { ... },      // どのモードで入力されたか。（※現行スキーマでは入力ソース（自社/競合/トレンド）を直接表現するフィールドは未定義であるが、将来的な拡張候補として ad_category などの追加を検討する）
  "asset_meta": { ... },          // 診断対象素材の一意な識別子（asset_id）等の管理情報
  "creative_core": { ... },       // 素材の形式・訴求・トーン・視覚要素・ペインポイント等を構造化し、自社・競合のクリエイティブ構造を比較可能にするブロック
  "landing_page": { ... },        // LPのメッセージ・CTA・フォーム負荷を抽出し、広告との整合性や摩擦ポイントを評価するブロック
  "performance": { ... },         // 広告のKPI実績を記録するブロック
  "diagnostics": {                // 定性・定量の評価理由と、根拠付きの改善アクションを言語化する診断ブロック
    "qualitative": { ... },       
    "quantitative": { ... }       
  },
  "views": { ... },               // UIダッシュボード表示用の整形済みデータ
  "_metadata": { ... }
}
```

🔧 セクション詳細設計
1. input_metadata（新規：Phase 1で必須）
用途: 入力モード・ソースの追跡
strict / optional 定義

フィールド	型	strict	説明
mode	string	strict	file_only / file_plus_lp / file_plus_lp_plus_manual_kpi / api_import_ready
source_type	string	strict	local_file / api / hybrid
input_timestamp	string	strict	ISO 8601 (ファイル入力時刻)
file_paths	object	optional	入力ファイルへのパス（ローカル開発用）
api_source	string	optional	meta / google / tiktok （Phase 3以降）
例:

```json
{
  "mode": "file_plus_lp_plus_manual_kpi",
  "source_type": "local_file",
  "input_timestamp": "2026-06-22T14:30:00Z",
  "file_paths": {
    "creative_video": "/downloads/ad_001_video.mp4",
    "creative_images": ["/downloads/ad_001_img_1.png"],
    "landing_page_html": "/downloads/lp_snapshot.html"
  }
}
```

2. asset_meta（File-First再設計）
用途: 素材の一意識別・期間管理
`asset_id` は診断対象素材の一意な識別子であり、`version`（※DB仕様）は同一 `asset_id` に対する再診断の履歴管理用です。
UI上では、原則として「最新版の診断結果を1件」として扱う前提とし、内部仕様として履歴は保持するものの、ユーザー向けには必ずしも全 version を露出しない方針とします。

strict / optional 定義

フィールド	型	strict	説明	Validation
asset_id	string	strict	asset_YYYYMMDD_HHmmss_platform_uuid	パターン: asset_20260622_143000_local_a1b2c3
asset_name	string	optional	ユーザー指定の素材名	最大255文字
platform	string	optional	meta / google / tiktok / unknown	不明な場合は「unknown」
ad_account_id	string	optional	Meta Ad Account ID	Phase 2以降（API連携）
campaign_name	string	optional	キャンペーン名	手動入力可
adset_name	string	optional	アドセット名	手動入力可
ad_name	string	optional	広告名	手動入力可
analysis_period.start	string	optional	ISO 8601 (YYYY-MM-DD)	手動KPI入力時のみ必須
analysis_period.end	string	optional	ISO 8601 (YYYY-MM-DD)	手動KPI入力時のみ必須
external_ids	object	optional	外部ID連携用	{ "meta_ad_id": "...", "google_ad_id": "..." }
例:

```json
{
  "asset_id": "asset_20260622_143000_local_a1b2c3",
  "asset_name": "Summer Campaign Video v2",
  "platform": "unknown",
  "campaign_name": "Summer 2026 Promo",
  "adset_name": "Awareness - 18-35 JP",
  "ad_name": "Summer Promo - 30s Video",
  "analysis_period": {
    "start": "2026-06-01",
    "end": "2026-06-22"
  },
  "external_ids": null
}
```

3. creative_core（File-First対応：強化版）
用途: 素材ファイルから直接抽出したテキスト・ビジュアル分析
strict / optional 定義

フィールド	型	strict	説明
format	string	strict	video_static / image_static / image_carousel / text_only / mixed
duration_seconds	number	optional	動画の場合の長さ（秒）
primary_text	string	optional	広告文・キャプション（OCR/LLM抽出）
headline	string	optional	見出し（広告文の冒頭15-20文字）
body_text	string	optional	本文（OCR/LLM抽出）
call_to_action	string	optional	CTA（"Learn More"等）
visual_elements	object	strict（format=image系）	ビジュアル分析結果
visual_elements.dominant_colors	array[string]	optional	配色分析結果（例: ["#FF5733", "#3366FF"]）
visual_elements.detected_objects	array[string]	optional	画像内の物体検出（LLM/Vision分析）
visual_elements.text_overlay_detected	boolean	optional	テキストオーバーレイの有無
visual_elements.brand_elements	boolean	optional	ブランド要素（ロゴ等）の有無
tone_and_emotion	object	optional	LLMが推定したトーン・感情
tone_and_emotion.primary_tone	string	optional	professional / casual / humorous / urgent / inspirational / etc.
tone_and_emotion.detected_emotion	array[string]	optional	["excitement", "trust", "happiness"]
tone_and_emotion.target_audience_inferred	string	optional	LLMが推定したターゲット層
ai_labels	object	optional	LLM分析タグ（Hook/Appeal/Pain Point等）
ai_labels.hook_type	string	optional	curiosity / pain_point / benefit / social_proof / scarcity / etc.
ai_labels.appeal_type	string	optional	emotional / rational / hybrid
ai_labels.identified_pain_points	array[string]	optional	["time_consuming", "complex_setup"]
ai_labels.identified_benefits	array[string]	optional	["saves_time", "high_conversion"]
platform_specific	object	optional	プラットフォーム固有メタ（将来拡張）
例:

```json
{
  "format": "video_static",
  "duration_seconds": 30,
  "primary_text": "あなたの時間を取り戻す。簡単LP作成で成約率2倍。",
  "headline": "あなたの時間を取り戻す",
  "body_text": "簡単LP作成で成約率2倍。今なら30日無料トライアル。",
  "call_to_action": "今すぐ始める",
  "visual_elements": {
    "dominant_colors": ["#FF6B6B", "#FFFFFF"],
    "detected_objects": ["laptop", "person_working", "checkmark"],
    "text_overlay_detected": true,
    "brand_elements": true
  },
  "tone_and_emotion": {
    "primary_tone": "inspirational",
    "detected_emotion": ["excitement", "trust"],
    "target_audience_inferred": "18-35, SaaS entrepreneurs, time-conscious"
  },
  "ai_labels": {
    "hook_type": "benefit",
    "appeal_type": "emotional",
    "identified_pain_points": ["time_consuming", "complex_setup"],
    "identified_benefits": ["saves_time", "high_conversion"]
  }
}
```

4. landing_page（File-First対応：根拠記録強化）
用途: LP分析（スクレイピング/ローカルHTML/URL入力）
strict / optional 定義

フィールド	型	strict	説明
url	string	optional	LP URL（入力時のみ）
fv_copy	string	optional	FV（First View）のコピー（スクレイピング/HTML解析）
fv_headline	string	optional	FV見出し
offer	string	optional	オファー内容
form_difficulty	string	optional	low / medium / high（フォーム項目数を分析）
form_field_count	number	optional	フォーム項目数（自動抽出）
cta_button_text	string	optional	CTAボタンテキスト
message_consistency	object	optional	広告文とLP FVコピーの整合性分析
message_consistency.match_score	number	optional	0.0～1.0
message_consistency.consistency_basis	string	optional	LLM分析結果（なぜマッチしているのか）
message_consistency.key_alignment_points	array[string]	optional	一致している主要ポイント
message_consistency.mismatch_areas	array[string]	optional	ズレている部分（あれば）
message_consistency.analyzed_at	string	optional	ISO 8601（分析時刻）
lp_page_structure	object	optional	ページ構成分析
lp_page_structure.has_hero_section	boolean	optional	
lp_page_structure.has_social_proof	boolean	optional	
lp_page_structure.has_faq_section	boolean	optional	
lp_page_structure.estimated_scroll_depth_for_form	string	optional	above_fold / mid_page / below_fold
例:

```json
{
  "url": "https://example.com/lp/summer-promo",
  "fv_copy": "簡単LP作成ツール。2分で成約率2倍のLPが作れる。",
  "fv_headline": "簡単LP作成ツール",
  "offer": "30日間無料トライアル",
  "form_difficulty": "low",
  "form_field_count": 3,
  "cta_button_text": "今すぐ始める",
  "message_consistency": {
    "match_score": 0.92,
    "consistency_basis": "広告文の『成約率2倍』と、LP FVの『成約率2倍』が完全一致。『簡単』というトーンも統一。",
    "key_alignment_points": [
      "成約率向上（両方で言及）",
      "簡単・手軽（両方で言及）",
      "無料トライアル（両方で言及）"
    ],
    "mismatch_areas": [],
    "analyzed_at": "2026-06-22T14:30:00Z"
  },
  "lp_page_structure": {
    "has_hero_section": true,
    "has_social_proof": true,
    "has_faq_section": true,
    "estimated_scroll_depth_for_form": "above_fold"
  }
}
```

5. performance（mode依存でoptional化）
用途: KPI管理（手動入力 or API連携）
strict / optional 定義

フィールド	型	strict	説明	必須モード
impressions	integer	optional	-	file_plus_lp_plus_manual_kpi / api_import_ready
clicks	integer	optional	-	file_plus_lp_plus_manual_kpi / api_import_ready
ctr	number	optional	0.0～1.0（自動計算可）	file_plus_lp_plus_manual_kpi / api_import_ready
spend	number	optional	通貨単位（JPY推定）	file_plus_lp_plus_manual_kpi / api_import_ready
conversions	integer	optional	-	file_plus_lp_plus_manual_kpi / api_import_ready
conversion_value	number	optional	総売上等	file_plus_lp_plus_manual_kpi / api_import_ready
cpa	number	optional	自動計算：spend / conversions	file_plus_lp_plus_manual_kpi / api_import_ready
cvr	number	optional	conversions / clicks	file_plus_lp_plus_manual_kpi / api_import_ready
roas	number	optional	conversion_value / spend	file_plus_lp_plus_manual_kpi / api_import_ready
reach	integer	optional	-	api_import_ready
frequency	number	optional	impressions / reach	api_import_ready
例:

```json
{
  "impressions": 45000,
  "clicks": 1350,
  "ctr": 0.03,
  "spend": 180000,
  "conversions": 45,
  "conversion_value": 450000,
  "cpa": 4000,
  "cvr": 0.0333,
  "roas": 2.5,
  "reach": 35000,
  "frequency": 1.29
}
```

モード別 必須度:

file_only: すべてNULL（省略可）
file_plus_lp: すべてNULL（省略可）
file_plus_lp_plus_manual_kpi: impressions, clicks, spend, conversions 必須
api_import_ready: 全フィールド必須（API側で提供）

6. diagnostics（定性/定量で分離）
用途: 診断結果（qualitative は KPI不要、quantitative は KPI必須）

6.1 diagnostics.qualitative（KPI不要で必ず実施）
フィールド	型	strict	説明
creative_fatigue_risk	string	strict	low / medium / high
creative_fatigue_basis	string	strict	LLM分析の根拠・説明
creative_fatigue_indicators	array[string]	optional	["overused_hook", "generic_cta", "low_contrast"]
message_clarity_score	number	optional	0.0～1.0（メッセージ明確性）
message_clarity_basis	string	optional	LLM分析根拠
lp_message_match_risk	string	optional	low / medium / high（LP入力時のみ）
lp_message_match_basis	string	optional	整合性分析の根拠
form_usability_concern	string	optional	low / medium / high（LP入力時のみ）
form_usability_basis	string	optional	フォーム項目数・配置の評価
audience_relevance_concern	string	optional	low / medium / high
audience_relevance_basis	string	optional	ターゲット層との適合度
recommended_creative_improvements	array[string]	optional	LLMが提案する改善案
例:

```json
{
  "creative_fatigue_risk": "low",
  "creative_fatigue_basis": "フック（『成約率2倍』）が具体的で新規性あり。ビジュアルは高コントラスト。一般的すぎる表現はなし。",
  "creative_fatigue_indicators": [],
  "message_clarity_score": 0.95,
  "message_clarity_basis": "FV→本文→CTAの流れが一貫性あり。3つのポイント（簡単・成果・無料）が明確。",
  "lp_message_match_risk": "low",
  "lp_message_match_basis": "広告文『成約率2倍』とLP『成約率2倍』が完全一致。トーンも統一。",
  "form_usability_concern": "low",
  "form_usability_basis": "フォーム項目が3つ（名前・メール・企業名）。Above the fold。",
  "audience_relevance_concern": "low",
  "audience_relevance_basis": "ターゲット『18-35, SaaS entrepreneur』と『簡単・短時間・成果』の訴求が合致。",
  "recommended_creative_improvements": [
    "社会証明（導入企業数や顧客満足度）を追加するとCTR向上の可能性",
    "動画の最後に『30日無料』というオファーを明示するとCVR向上の可能性"
  ]
}
```

6.1.1 diagnostics.decision_support（optional、新規分析結果の意思決定支援ブロック）
用途: 「強み・弱み・改善提案」を意思決定用に構造化する。既存の diagnostics.improvements（フラットな改善コメント）とは独立した並存フィールドで、旧データや生成失敗時は null（欠落）を許容する後方互換フィールドである。

フィールド	型	strict	説明
summary.headline	string	optional	一言結論（画面最上部カード用）
summary.decision	string	optional	継続 / 改修推奨 / 停止検討 等の短い判断ラベル
summary.rationale	string	optional	判断理由（強み・弱みの要約）
strengths[].id	string	optional	weakness/recommendationから参照する識別子（例: "s1"）
strengths[].category	string	optional	visual / message / cta / target / lp / brand
strengths[].title	string	optional	要素名
strengths[].description	string	optional	何が良いかの具体説明
strengths[].keep_reason	string	optional	今後も維持・再利用すべき理由（「よかった点」ではなく勝ち要素として表現する）
weaknesses[].id	string	optional	recommendation.target_weakness_ids から参照される識別子（例: "w1"）
weaknesses[].priority	string	optional	P0（致命的）/ P1（改善推奨）/ P2（伸び代）
weaknesses[].category	string	optional	visual / message / cta / target / lp / brand
weaknesses[].title	string	optional	問題名
weaknesses[].description	string	optional	何が問題かの具体説明
weaknesses[].impact	string	optional	放置した場合の成果への影響
recommendations[].id	string	optional	識別子（例: "r1"）
recommendations[].priority	string	optional	P0 / P1 / P2
recommendations[].target_weakness_ids	array[string]	optional	対応する weakness の id（最低1件、必ずどの弱みへの対応かを明示する）
recommendations[].title	string	optional	提案名
recommendations[].what	string	optional	何を変えるか
recommendations[].why	string	optional	なぜ変えるか（対応する弱みへの言及を含む）
recommendations[].how	string	optional	どう検証するか
recommendations[].expected_effect	string	optional	期待される効果

例:

```json
{
  "decision_support": {
    "summary": {
      "headline": "LPとの連動は強いが、動画冒頭のフックが弱くCTRで機会損失",
      "decision": "改修推奨",
      "rationale": "LP整合性は高いが、フックの抽象さが視聴維持率を下げている"
    },
    "strengths": [
      {
        "id": "s1",
        "category": "lp",
        "title": "LPとの完全一致",
        "description": "広告文とLPのファーストビューが『成約率2倍』で完全一致している",
        "keep_reason": "この整合性は信頼感とCVRに直結するため、今後の改修でも必ず維持すること"
      }
    ],
    "weaknesses": [
      {
        "id": "w1",
        "priority": "P1",
        "category": "message",
        "title": "冒頭フックの抽象さ",
        "description": "動画冒頭3秒のテキストが抽象的で、視聴維持につながっていない",
        "impact": "スクロール離脱が増え、視聴完了率・CTRの両方を下げている"
      }
    ],
    "recommendations": [
      {
        "id": "r1",
        "priority": "P1",
        "target_weakness_ids": ["w1"],
        "title": "冒頭ペインポイント訴求への変更",
        "what": "動画0〜3秒に『〜でお悩みですか？』というペインポイント訴求のテキストを大きく配置する",
        "why": "弱み『冒頭フックの抽象さ』を解消し、視聴維持率を上げるため",
        "how": "既存クリエイティブとABテストし、3秒視聴率とCTRを3日間比較する",
        "expected_effect": "3秒視聴率+10%、CTR改善を見込む"
      }
    ]
  }
}
```

後方互換:
- decision_support は Optional。存在しない（旧データ・生成失敗時）場合、UIは decision_support_error の有無に応じて警告を出しつつ、従来の diagnostics.improvements ベースの表示にフォールバックする。
- decision_support_error は diagnostics.improvements_error と同様の fail-soft エラー情報（success/error_code/reason）を持つ。

6.2 diagnostics.quantitative（KPI必須）
フィールド	型	strict	説明	必須モード
performance_status	string	optional	excellent / good / fair / poor	file_plus_lp_plus_manual_kpi / api_import_ready
performance_status_basis	string	optional	ステータス判定の根拠	file_plus_lp_plus_manual_kpi / api_import_ready
ctr_assessment	string	optional	excellent / good / fair / poor	file_plus_lp_plus_manual_kpi / api_import_ready
ctr_benchmark_comparison	string	optional	業界ベンチマークとの比較	file_plus_lp_plus_manual_kpi / api_import_ready
cvr_assessment	string	optional	excellent / good / fair / poor	file_plus_lp_plus_manual_kpi / api_import_ready
cvr_benchmark_comparison	string	optional	業界ベンチマークとの比較	file_plus_lp_plus_manual_kpi / api_import_ready
roas_assessment	string	optional	excellent / good / fair / poor	file_plus_lp_plus_manual_kpi / api_import_ready
roas_benchmark_comparison	string	optional	業界ベンチマークとの比較	file_plus_lp_plus_manual_kpi / api_import_ready
efficiency_score	number	optional	0.0～1.0（CPA効率評価）	file_plus_lp_plus_manual_kpi / api_import_ready
recommended_optimizations	array[string]	optional	KPI基づく改善案	file_plus_lp_plus_manual_kpi / api_import_ready
例:

```json
{
  "performance_status": "good",
  "performance_status_basis": "CTR 3.0%（業界平均1.5%の2倍）、CVR 3.33%（良好）、ROAS 2.5倍（目標達成）",
  "ctr_assessment": "excellent",
  "ctr_benchmark_comparison": "業界平均 1.5% に対し 3.0% → 2倍高い",
  "cvr_assessment": "good",
  "cvr_benchmark_comparison": "業界平均 2.5% に対し 3.33% → 33%高い",
  "roas_assessment": "good",
  "roas_benchmark_comparison": "目標 2.0x に対し 2.5x → 125%達成",
  "efficiency_score": 0.82,
  "recommended_optimizations": [
    "CTRが高い → このクリエイティブをスケールして予算増",
    "CVRが伸び代あり → LP最適化（フォーム簡略化）で さらに向上",
    "ROAS目標達成 → キープしつつ、類似オーディエンスへ展開"
  ]
}
```

7. views（UI表示用・生成版）
用途: Dashboard / Report 生成用のプリフォーマットデータ
strict / optional 定義

フィールド	型	strict	説明
dashboard_summary.status_label	string	optional	Excellent / Good / Fair / Poor
dashboard_summary.key_metric_highlight	string	optional	主要成果を1行で
dashboard_summary.status_color	string	optional	#00AA00 (green) / #FFAA00 (orange) / #FF0000 (red)
performance_ranking	string	optional	"Top 10%" / "Average" / "Bottom 30%"
trend_indicator	string	optional	"+15%" / "-58%"
creative_fatigue_visual	string	optional	● Low / ◐ Medium / ◯ High
lp_match_visual	string	optional	✓ Aligned / ⚠ Partial / ✗ Misaligned
recommended_actions_display	array[object]	optional	UI表示用の改善案リスト（優先度付き）
recommended_actions_display[].priority	string	optional	high / medium / low
recommended_actions_display[].action	string	optional	改善案テキスト
recommended_actions_display[].expected_impact	string	optional	CTR向上予想: +5～10%
例:

```json
{
  "dashboard_summary": {
    "status_label": "Good",
    "key_metric_highlight": "CTR 3.0% (2x industry avg) | ROAS 2.5x | CVR 3.33%",
    "status_color": "#FFAA00"
  },
  "performance_ranking": "Top 10%",
  "trend_indicator": "+15%",
  "creative_fatigue_visual": "● Low",
  "lp_match_visual": "✓ Aligned",
  "recommended_actions_display": [
    {
      "priority": "high",
      "action": "スケール：このクリエイティブで予算を30%増",
      "expected_impact": "ROAS維持＋リーチ向上"
    },
    {
      "priority": "medium",
      "action": "LP最適化：フォーム項目を2つに削減",
      "expected_impact": "CVR +5～10%"
    },
    {
      "priority": "low",
      "action": "類似オーディエンス展開テスト",
      "expected_impact": "新規リーチ +20%"
    }
  ]
}
```

8. _metadata（ファイル生成・バージョン管理）
用途: スキーマ・分析バージョン・生成タイムスタンプの記録
strict / optional 定義

フィールド	型	strict	説明
generated_at	string	strict	ISO 8601 (YYYY-MM-DDTHH:MM:SSZ)
data_source	string	strict	local_file / meta_api / google_api / tiktok_api / manual_input / hybrid
ai_model_version	string	strict	gemini-2.0-flash / gpt-4o / claude-opus / other
json_schema_version	string	strict	v0.2
input_mode	string	strict	file_only / file_plus_lp / file_plus_lp_plus_manual_kpi / api_import_ready
analysis_tools_used	object	optional	使用したツール・ライブラリ
analysis_tools_used.ocr_engine	string	optional	tesseract / google_vision / aws_textract
analysis_tools_used.video_frame_extractor	string	optional	opencv / ffmpeg
analysis_tools_used.web_scraper	string	optional	beautifulsoup / selenium
processing_time_ms	number	optional	処理時間（ミリ秒）
validation_status	string	optional	passed / warnings / failed
validation_notes	array[string]	optional	バリデーション時の警告・メモ
例:

```json
{
  "generated_at": "2026-06-22T14:35:00Z",
  "data_source": "local_file",
  "ai_model_version": "gemini-2.0-flash",
  "json_schema_version": "v0.2",
  "input_mode": "file_plus_lp_plus_manual_kpi",
  "analysis_tools_used": {
    "ocr_engine": "google_vision",
    "video_frame_extractor": "ffmpeg",
    "web_scraper": "beautifulsoup"
  },
  "processing_time_ms": 3200,
  "validation_status": "passed",
  "validation_notes": [
    "Creative video duration 30s (within limits)",
    "LP form fields 3 (low friction, good)",
    "Manual KPI provided: all required fields present"
  ]
}
```

📥 入力モード（input_metadata.mode）定義と診断深度
各入力モードは、入力情報の量に応じて「診断深度」が変わるように設計されています。

- `file_only`: 素材単体に対するクリエイティブの定性診断を行う。
- `file_plus_lp`: 素材とLPのメッセージ整合性やLP構造の診断を含む。
- `file_plus_lp_plus_manual_kpi`: 過去の実績KPIを踏まえたパフォーマンス診断と、予算調整・改善アクションの提案まで含むフル診断を行う。

1. file_only
説明: 素材ファイルのみ入力、KPIなし

入力: 動画/画像 → File Drop

実施される分析:

✓ Creative Fatigue Risk
✓ Message Clarity
✓ Tone & Emotion
✗ LP Consistency
✗ Performance Assessment
✗ ROAS/CVR Assessment
出力: qualitative diagnostics のみ

使用例: 「素材だけ評価してほしい」「LP未定」

2. file_plus_lp
説明: 素材ファイル + LP URL/HTML入力、KPIなし

入力: 動画/画像 + LP URL

実施される分析:

✓ Creative Fatigue Risk
✓ Message Clarity
✓ LP Message Consistency
✓ Form Usability
✗ Performance Assessment
✗ ROAS/CVR Assessment
出力: qualitative diagnostics のみ（LP含む）

使用例: 「素材とLPの整合性を確認したい」「数値は未定」

3. file_plus_lp_plus_manual_kpi
説明: 素材 + LP + 手動KPI入力（30日間の実績値等）

入力: 動画/画像 + LP URL + 手動KPI（impressions, clicks, spend, conversions等）

実施される分析:

✓ Creative Fatigue Risk
✓ Message Clarity
✓ LP Message Consistency
✓ Performance Assessment (CTR, CVR, CPA, ROAS)
✓ Benchmark Comparison
✓ Recommended Optimizations
出力: qualitative + quantitative diagnostics

使用例: 「過去30日の実績をもとに改善案を提案してほしい」MVP版で最頻用

4. api_import_ready
説明: Meta Ads API / Google Ads API から取得したデータ形式（Phase 2以降）

入力: API response （JSON形式）

実施される分析: file_plus_lp_plus_manual_kpi と同じ + APIメタデータ

出力: 完全な diagnostics （qualitative + quantitative）

使用例: Phase 3で Meta / Google 連携時に使用

✅ KPI不要で成立する診断範囲
Qualitative Diagnostics（これだけで価値を提供）
Creative Fatigue Risk Assessment

Hook の新規性（「成約率2倍」は具体的か？一般的か？）
ビジュアルのコントラスト・色彩の新規性
CTAのバリエーション度
テキストの汎用性
Message Clarity & Structure

FV → 本文 → CTA の論理性
主訴求ポイント（3つ以上？不足？）
文字量（多すぎないか）
LP Message Consistency（LP入力時）

広告文とLP FVコピーのキーワード一致度
トーン・ニュアンスの整合性
分析根拠を記録（「なぜ92%なのか」を説明）
Form Usability（LP入力時）

フォーム項目数の評価
配置位置（above fold?）
フィールドの必須度
Audience Relevance

推定ターゲット層の特定
訴求内容とのマッチ
📈 KPIあり で追加される診断範囲
Quantitative Diagnostics（KPI必須）
Performance Status

CTR / CVR / ROAS / CPA の判定
業界ベンチマークとの比較
Efficiency Assessment

費用効率スコア（0.0～1.0）
CPAの妥当性
Optimization Recommendations

スケール提案
LP最適化の優先度付け
予算配分改善
📄 完全サンプル JSON（file_plus_lp_plus_manual_kpi モード）
```json
{
  "input_metadata": {
    "mode": "file_plus_lp_plus_manual_kpi",
    "source_type": "local_file",
    "input_timestamp": "2026-06-22T14:30:00Z",
    "file_paths": {
      "creative_video": "/downloads/ad_001_video.mp4",
      "creative_images": null,
      "landing_page_html": "/downloads/lp_snapshot.html"
    }
  },
  "asset_meta": {
    "asset_id": "asset_20260622_143000_local_a1b2c3",
    "asset_name": "Summer Campaign Video v2",
    "platform": "unknown",
    "campaign_name": "Summer 2026 Promo",
    "adset_name": "Awareness - 18-35 JP",
    "ad_name": "Summer Promo - 30s Video",
    "analysis_period": {
      "start": "2026-06-01",
      "end": "2026-06-22"
    },
    "external_ids": null
  },
  "creative_core": {
    "format": "video_static",
    "duration_seconds": 30,
    "primary_text": "あなたの時間を取り戻す。簡単LP作成で成約率2倍。",
    "headline": "あなたの時間を取り戻す",
    "body_text": "簡単LP作成で成約率2倍。今なら30日無料トライアル。",
    "call_to_action": "今すぐ始める",
    "visual_elements": {
      "dominant_colors": ["#FF6B6B", "#FFFFFF"],
      "detected_objects": ["laptop", "person_working", "checkmark"],
      "text_overlay_detected": true,
      "brand_elements": true
    },
    "tone_and_emotion": {
      "primary_tone": "inspirational",
      "detected_emotion": ["excitement", "trust"],
      "target_audience_inferred": "18-35, SaaS entrepreneurs, time-conscious"
    },
    "ai_labels": {
      "hook_type": "benefit",
      "appeal_type": "emotional",
      "identified_pain_points": ["time_consuming", "complex_setup"],
      "identified_benefits": ["saves_time", "high_conversion"]
    }
  },
  "landing_page": {
    "url": "https://example.com/lp/summer-promo",
    "fv_copy": "簡単LP作成ツール。2分で成約率2倍のLPが作れる。",
    "fv_headline": "簡単LP作成ツール",
    "offer": "30日間無料トライアル",
    "form_difficulty": "low",
    "form_field_count": 3,
    "cta_button_text": "今すぐ始める",
    "message_consistency": {
      "match_score": 0.92,
      "consistency_basis": "広告文の『成約率2倍』と、LP FVの『成約率2倍』が完全一致。『簡単』というトーンも統一。",
      "key_alignment_points": [
        "成約率向上（両方で言及）",
        "簡単・手軽（両方で言及）",
        "無料トライアル（両方で言及）"
      ],
      "mismatch_areas": [],
      "analyzed_at": "2026-06-22T14:30:00Z"
    },
    "lp_page_structure": {
      "has_hero_section": true,
      "has_social_proof": true,
      "has_faq_section": true,
      "estimated_scroll_depth_for_form": "above_fold"
    }
  },
  "performance": {
    "impressions": 45000,
    "clicks": 1350,
    "ctr": 0.03,
    "spend": 180000,
    "conversions": 45,
    "conversion_value": 450000,
    "cpa": 4000,
    "cvr": 0.0333,
    "roas": 2.5,
    "reach": 35000,
    "frequency": 1.29
  },
  "diagnostics": {
    "qualitative": {
      "creative_fatigue_risk": "low",
      "creative_fatigue_basis": "フック（『成約率2倍』）が具体的で新規性あり。ビジュアルは高コントラスト。一般的すぎる表現はなし。",
      "creative_fatigue_indicators": [],
      "message_clarity_score": 0.95,
      "message_clarity_basis": "FV→本文→CTAの流れが一貫性あり。3つのポイント（簡単・成果・無料）が明確。",
      "lp_message_match_risk": "low",
      "lp_message_match_basis": "広告文『成約率2倍』とLP『成約率2倍』が完全一致。トーンも統一。",
      "form_usability_concern": "low",
      "form_usability_basis": "フォーム項目が3つ（名前・メール・企業名）。Above the fold。",
      "audience_relevance_concern": "low",
      "audience_relevance_basis": "ターゲット『18-35, SaaS entrepreneur』と『簡単・短時間・成果』の訴求が合致。",
      "recommended_creative_improvements": [
        "社会証明（導入企業数や顧客満足度）を追加するとCTR向上の可能性",
        "動画の最後に『30日無料』というオファーを明示するとCVR向上の可能性"
      ]
    },
    "quantitative": {
      "performance_status": "good",
      "performance_status_basis": "CTR 3.0%（業界平均1.5%の2倍）、CVR 3.33%（良好）、ROAS 2.5倍（目標達成）",
      "ctr_assessment": "excellent",
      "ctr_benchmark_comparison": "業界平均 1.5% に対し 3.0% → 2倍高い",
      "cvr_assessment": "good",
      "cvr_benchmark_comparison": "業界平均 2.5% に対し 3.33% → 33%高い",
      "roas_assessment": "good",
      "roas_benchmark_comparison": "目標 2.0x に対し 2.5x → 125%達成",
      "efficiency_score": 0.82,
      "recommended_optimizations": [
        "CTRが高い → このクリエイティブをスケールして予算増",
        "CVRが伸び代あり → LP最適化（フォーム簡略化）で さらに向上",
        "ROAS目標達成 → キープしつつ、類似オーディエンスへ展開"
      ]
    }
  },
  "views": {
    "dashboard_summary": {
      "status_label": "Good",
      "key_metric_highlight": "CTR 3.0% (2x industry avg) | ROAS 2.5x | CVR 3.33%",
      "status_color": "#FFAA00"
    },
    "performance_ranking": "Top 10%",
    "trend_indicator": "+15%",
    "creative_fatigue_visual": "● Low",
    "lp_match_visual": "✓ Aligned",
    "recommended_actions_display": [
      {
        "priority": "high",
        "action": "スケール：このクリエイティブで予算を30%増",
        "expected_impact": "ROAS維持＋リーチ向上"
      },
      {
        "priority": "medium",
        "action": "LP最適化：フォーム項目を2つに削減",
        "expected_impact": "CVR +5～10%"
      },
      {
        "priority": "low",
        "action": "類似オーディエンス展開テスト",
        "expected_impact": "新規リーチ +20%"
      }
    ]
  },
  "_metadata": {
    "generated_at": "2026-06-22T14:35:00Z",
    "data_source": "local_file",
    "ai_model_version": "gemini-2.0-flash",
    "json_schema_version": "v0.2",
    "input_mode": "file_plus_lp_plus_manual_kpi",
    "analysis_tools_used": {
      "ocr_engine": "google_vision",
      "video_frame_extractor": "ffmpeg",
      "web_scraper": "beautifulsoup"
    },
    "processing_time_ms": 3200,
    "validation_status": "passed",
    "validation_notes": [
      "Creative video duration 30s (within limits)",
      "LP form fields 3 (low friction, good)",
      "Manual KPI provided: all required fields present"
    ]
  }
}
```

🔮 将来拡張ポイント
Phase 2: 複数プラットフォーム対応予定
platform_specific の拡張

external_ids.meta_ad_id / external_ids.google_ad_id の利用
プラットフォーム固有メタデータの取得
API Import Ready Mode

Meta Graph API 連携
Google Ads API 連携
TikTok Ads API 連携
Benchmark Database

業界別ベンチマーク（SaaS, EC, 金融等）
クリエイティブタイプ別（動画 vs 画像）
プラットフォーム別（Meta vs Google）
Phase 3: マルチテナント化
User & Account Management

ユーザーごとの診断履歴
アカウント別のプリセット管理
Custom Benchmarks

ユーザー自身のベンチマーク設定
過去実績を基準にした比較
✨ v0.1 互換性メモ
v0.1 との主な違い
v0.1 要素	v0.2 での扱い	互換性
ad_id	→ asset_id に改名（ファイル起点へ）	後方互換性あり（マイグレーション可能）
external_ids	optional化（API連携は Phase 2以降）	後方互換性あり
performance (全 strict)	mode依存で optional化	破壊的変更 - マイグレーション必要
creative_core	テキスト・ビジュアル分析強化	後方互換性あり（拡張）
landing_page	message_consistency_basis 追加	後方互換性あり（拡張）
diagnostics	qualitative / quantitative 分離	破壊的変更 - スキーマ変更
v0.1 JSON → v0.2 への変換スクリプト
v0.1 JSON 形式のデータを v0.2 へ移行する場合は以下ロジックで変換：

```python
def migrate_v01_to_v02(v01_json):
    v02 = {
        "input_metadata": {
            "mode": "api_import_ready" if v01_json.get("external_ids") else "file_plus_lp_plus_manual_kpi",
            "source_type": "api" if v01_json.get("external_ids") else "local_file",
            "input_timestamp": v01_json["_metadata"]["generated_at"]
        },
        "asset_meta": {
            "asset_id": generate_asset_id(v01_json["asset_meta"]["ad_id"]),
            **{k: v for k, v in v01_json["asset_meta"].items() if k != "ad_id"}
        },
        # ... 以下同様にマッピング
    }
    return v02
```

📋 実装チェックリスト（Pydantic v0.2 作成用）
 InputMetadataModel クラス作成（input_metadata）
 AssetMetaModel クラス改修（asset_id 中心、external_ids optional）
 CreativeCoreModel クラス拡張（visual_elements, tone_and_emotion 詳細化）
 LandingPageModel クラス拡張（message_consistency_basis 追加）
 PerformanceModel クラス改修（全フィールド optional 化）
 DiagnosticsModel クラス再構成（qualitative / quantitative 分離）
 ViewsModel クラス（unchanged）
 MetadataModel クラス改修（input_mode, analysis_tools_used 追加）
 Validator: input_mode に基づいて strict / optional を動的に切り替え
 サンプルデータ3種類（file_only, file_plus_lp, file_plus_lp_plus_manual_kpi）作成
 ドキュメント: Pydantic v0.2 実装ガイド（backend 向け）
🔗 関連ドキュメント
実装計画書: docs/plans/implementation_phase_plan.md
アーキテクチャ（File-First）: docs/architecture/phase1_file_first_strategy.md （次作成予定）
既存 v0.1 スキーマ: docs/specs/ad_insight_json_schema_v0_1.md
最終更新: 2026-06-22
ステータス: APPROVED for Phase 1 Implementation
