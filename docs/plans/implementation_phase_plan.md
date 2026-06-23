# 実装フェーズ計画 - Ad-Insight-Spec（改訂版）

**Last Updated**: 2026-06-22  
**Strategy Shift**: Meta API-First → File-First

## 📌 戦略変更の背景

### 従来の方針（Meta API-First）
- Meta Graph API から広告データを取得
- リアルタイム連携を前提
- API 認証・レート制限が実装の複雑性

### 新しい方針（File-First Strategy）
- すでにダウンロード済みの素材ファイル（動画・画像）を入力
- LPスクレイピングまたはマニュアル指定
- 手入力KPI（optional）で診断を補強
- **MVP の高速実装** + **将来の API 連携と整合**

### なぜ File-First を優先するのか？

1. **実装速度**: API 認証・ライセンス・レート制限なしで即座に開発可能
2. **ユースケース**: マーケターが「既存広告素材の分析」を最初に求めている
3. **設計の汎用性**: ファイル取込 → 分析 → JSON は Meta/Google/TikTok 全媒体に共通
4. **運用効率**: 手元にある素材で検証でき、API 連携はその後に追加
5. **テスト性**: 固定入力データで deterministic な動作確認

---

## フェーズ再構成

### Phase 0: 基盤整備（✅ 完了）
- JSON スキーマ v0.1
- Pydantic + SQLAlchemy モデル
- 環境変数管理

### Phase 1: File-First Ingestion & Creative Analysis（新規ゴール）

**目的**: ファイル入力 → 構造化JSON生成 → 診断提示

**成果物**:
- Creative Analyzer（動画・画像からメタデータ抽出）
- Landing Page Analyzer（LP からテキスト・訴求抽出）
- Converter Service（raw data → ad_insight_spec JSON）
- CLI または FastAPI エンドポイント（file upload）
- sample input → ad_insight_spec 生成の完全フロー

**期間**: 2-3週間  
**優先度**: 🔴 最高

**入力**:
Copy
├─ Creative Asset（いずれか） │ ├─ 動画ファイル（.mp4, .mov等） │ ├─ 画像ファイル（.png, .jpg等） │ └─ テキスト（キャプション・見出し） ├─ Landing Page │ ├─ URL（スクレイピング）または │ └─ HTML/テキスト（マニュアル入力） └─ KPI（optional） ├─ impressions ├─ clicks ├─ conversions └─ spend

Copy
**出力**:
{ "asset_meta": { asset_id, platform, creative_type, ... }, "creative_core": { ... with LLM-extracted labels }, "landing_page": { ... with message consistency analysis }, "performance": { ... if provided, else null/defaults }, "diagnostics": { ... always generated }, "views": { ... dashboard summary }, "_metadata": { ... processing info } }

Copy
**チェックリスト**:
- [ ] Creative Asset の メタデータ抽出ロジック
- [ ] 動画・画像・テキストの 3 フォーマット対応
- [ ] LP スクレイピング & テキスト抽出
- [ ] Creative Core の LLM ラベル抽出（Hook/Appeal/Emotion等）
- [ ] LP Message Consistency スコア計算
- [ ] KPI なしでも成立する diagnostics 生成
- [ ] KPI 入力時の診断拡張ロジック
- [ ] CLI / FastAPI エンドポイント
- [ ] end-to-end テスト（sample input → JSON 出力）

---

### Phase 2: UI / Reporting & Dashboard

**目的**: JSON データの可視化・レポート生成

**成果物**:
- Streamlit ダッシュボード
- HTML/PDF レポート生成
- Vue.js フロントエンド

**期間**: 2-3週間

---

### Phase 3: API Integration & Multi-Platform

**目的**: Meta/Google/TikTok との API 連携

**成果物**:
- Meta Ads API クライアント
- Google Ads API クライアント
- TikTok Ads API クライアント（optional）
- 媒体抽象化レイヤー

**期間**: 3-4週間

---

## 全体タイムライン

| フェーズ | 期間 | 人員 | 成果 |
|---------|------|------|------|
| 0 | 1-2週 | 1-2名 | スキーマ確定、開発基盤 |
| **1** | **2-3週** | **2-3名** | **File-First 完全動作（サンプルから JSON 生成）** |
| 2 | 2-3週 | 2-3名 | UI / レポート完成 |
| 3 | 3-4週 | 1-2名 | マルチプラットフォーム検証 |
| **合計** | **8-12週** | **平均2名** | **完全な File-First MVP** |

---

## Phase 1 詳細設計

### Input Models

#### Creative Asset Input

\\\
asset_file: Union[VideoFile, ImageFile, TextFile]
  - VideoFile: .mp4, .mov, .avi（メタデータ抽出、フレーム抽出）
  - ImageFile: .png, .jpg, .webp（OCR、メタデータ）
  - TextFile: .txt, .json（キャプション・見出し・テキスト）

metadata:
  - filename (from file)
  - format (video/image/text, inferred)
  - size (bytes)
  - duration (for video)
  - dimensions (for image)
  - detected_text (from OCR or raw text)
\\\

#### Landing Page Input

\\\
lp_input: Union[LPUrl, LPHtml, LPText]
  - LPUrl: "https://example.com/sale" → スクレイピング
  - LPHtml: raw HTML → テキスト抽出
  - LPText: {fv_copy, offer, cta} → 直接入力

extracted:
  - url
  - fv_copy (first view text)
  - body_copy (main content)
  - cta_text (call-to-action)
  - offer_text (discount/offer description)
  - form_fields (detected form complexity)
\\\

#### KPI Input (Optional)

\\\
kpi_optional:
  - impressions: int
  - clicks: int
  - conversions: int
  - spend: float
  
  if all provided:
    ctr = clicks / impressions
    cvr = conversions / clicks
    cpa = spend / conversions
    roas = revenue / spend (if revenue provided)
  
  if partial:
    use provided values, leave others null
  
  if none provided:
    performance = null
    diagnostics generated based on creative/LP analysis only
\\\

---

## KPI なしでも成立する診断範囲

### Creative Analysis（KPI 不要）

**LLM が生成可能**:
- Hook Type（割引、ストーリー、UGC等）
- Appeal Axis（価格、品質、便利性等）
- Emotion（緊急性、楽しさ、信頼等）
- Tone（カジュアル、フォーマル等）
- Target Audience（推定ターゲット層）
- Creative Fatigue Risk（素材の陳腐度推定）

### LP Analysis（KPI 不要）

**テキスト解析で生成可能**:
- Message Consistency Score（広告と LP のメッセージズレ度）
- Form Difficulty（フォーム複雑度）
- CTA Clarity（CTA の明確さ）
- Offer Clarity（オファーの明確さ）

### Diagnostics（KPI 不要）

**生成可能な提案**:
- "Hook は効果的ですが、訴求軸が曖昧です"
- "LP と広告のメッセージがズレています"
- "フォームが複雑すぎる可能性があります"
- "CTA が不明確です"

### 制限事項

**生成不可**（KPI 必須）:
- CTR、CVR、CPA 実績値に基づく診断
- パフォーマンス比較（「業界平均より 20% 低い」等）
- ROAS の評価
- 過去トレンド分析

---

## KPI 入力時の拡張

\\\
if kpi provided:
  diagnostics += [
    "CPA ¥{cpa} は {benchmark_range} です",
    "CVR {cvr}% はターゲット {target_cvr}% に対して {status}",
    "予算効率：ROAS {roas} に基づき、{recommendation}"
  ]
  
  performance_status = evaluate(cpa, cvr, roas vs benchmarks)
else:
  diagnostics = creative + lp analysis only
  performance_status = "insufficient_data"
\\\

---

## File-First と API 連携の整合性

### 現在（Phase 1: File-First）

**入力源**:
- ローカルファイル（動画・画像・テキスト）
- LP URL またはテキスト
- 手入力 KPI

**パイプライン**:
File Upload → Metadata Extract → LLM Analyze → Converter → JSON

Copy
### 将来（Phase 3: API Integration）

**入力源追加**:
- Meta Graph API → 広告素材・KPI 自動取得
- Google Ads API → 広告データ自動取得
- TikTok Ads API → 広告データ自動取得

**パイプライン統合**:
[File Upload] ┐ [Meta API] ├→ Normalized Raw Data → Metadata Extract → LLM Analyze → Converter → JSON [Google API] ├→ [TikTok API] ┘

※ ファイル入力と API 入力の差別化なし （内部的には同じ Converter パイプラインを通す）

Copy
### 設計の汎用性

**Media-Agnostic**:
- asset_meta.platform（meta, google, tiktok等）で媒体を区別
- platform_specific で各媒体特有フィールドを保持
- 診断ロジックは platform に依存しない

**Input-Agnostic**:
- ファイル入力と API 入力の後段パイプラインが共通
- 同じ Converter → JSON 生成処理

---

## 次に決めるべき論点（Phase 1 時点）

1. **ビデオフレーム抽出**: 全フレーム vs サンプリング vs キーフレームのみ？
2. **OCR 精度**: Tesseract vs Google Vision API？
3. **LLM プロンプト設計**: 日本語・複数言語対応？
4. **LP スクレイピング**: Selenium vs Beautiful Soup vs Playwright？
5. **Performance Benchmark**: CPA/CVR/ROAS の「標準値」定義？
6. **CLI vs FastAPI**: 開発の優先順位？
