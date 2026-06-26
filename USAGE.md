# Ad-Insight-Spec v1.0.0-mvp 使用方法ガイド

## 🚀 起動方法

### **前提条件**
- Python 3.9+
- 外部ツール: Tesseract-OCR, FFmpeg (初回のみインストール)
- API キー: OpenAI (OPENAI_API_KEY), Google Gemini (GEMINI_API_KEY)

### **ステップ 1: リポジトリクローン・セットアップ**
```bash
git clone https://github.com/nario0715masa0619-create/ad-insight-spec.git
cd ad-insight-spec/backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### **ステップ 2: 環境変数設定**
`backend/.env` ファイルを作成し、以下を設定：

```env
OPENAI_API_KEY=sk-...
GEMINI_API_KEY=AIza...
LLM_MODEL=gpt  # または gemini
DATABASE_URL=sqlite:///./ad_insight.db
DEBUG=False
LOG_LEVEL=INFO
```

### **ステップ 3: FastAPI バックエンド起動**
```bash
cd backend
uvicorn app.main:app --host 127.0.0.1 --port 8000
```
✅ `INFO: Uvicorn running on http://127.0.0.1:8000` と表示されたら起動完了

### **ステップ 4: Streamlit UI 起動（別ターミナルで）**
```bash
cd ad-insight-spec  # ルートディレクトリ
streamlit run frontend/streamlit_app.py
```
✅ ブラウザが自動的に `http://localhost:8501` で開く

---

## 📥 インプット情報（何を与えるか）

### 必須入力
#### 1. メディアファイル（必須）
| 項目 | 要件 | 例 |
|---|---|---|
| ファイル形式 | PNG, JPG, JPEG, MP4, MOV | ad_campaign.png, product_video.mp4 |
| ファイルサイズ | 推奨 100MB 以下 | 小～中サイズの画像・動画 |
| フレーム情報 | 動画の場合、3 フレーム（先頭・中盤・末尾）を自動抽出 | - |

#### 2. 入力モード（必須）
Streamlit UI で以下から選択：

| モード | 説明 | 使用場面 |
|---|---|---|
| file_only | クリエイティブファイルのみ分析 | 初期評価、クリエイティブの単体品質確認 |
| file_plus_lp | クリエイティブ + LP URL/HTML を分析 | クリエイティブと LP のメッセージ一貫性確認 |
| file_plus_lp_plus_manual_kpi | クリエイティブ + LP + KPI 情報を分析 | フル分析、定量・定性の統合評価 |

### オプション入力
#### 3. ランディングページ（file_plus_lp 以上で必須）
| 形式 | 入力方法 |
|---|---|
| URL | `https://example.com/lp` を Streamlit で入力 |
| HTML ファイル | ローカルの HTML ファイルをアップロード |

#### 4. KPI 情報（file_plus_lp_plus_manual_kpi で必須）
```json
{
  "impressions": 45000,
  "clicks": 1350,
  "spend": 180000,
  "conversions": 45,
  "conversion_value": 450000
}
```
| フィールド | 説明 | 例 |
|---|---|---|
| impressions | インプレッション数 | 45000 |
| clicks | クリック数 | 1350 |
| spend | 広告費（円/ドル） | 180000 |
| conversions | コンバージョン数 | 45 |
| conversion_value | コンバージョン総額 | 450000 |

---

## 📤 アウトプット情報（何が得られるか）

### 出力形式
すべての分析結果は JSON 形式 (`AdInsightSpec v0.2`) で返却されます。

### アウトプット構成
```json
{
  "input_metadata": {
    "mode": "file_only",
    "source_type": "local_file",
    "input_timestamp": "2026-06-25T15:30:00Z"
  },
  "asset_meta": {
    "asset_id": "asset_image_abc123...",
    "version": 1,
    "platform": "unknown",
    "format": "image"
  },
  "creative_core": {
    "visuals": {
      "dominant_colors": ["blue", "white"],
      "composition": "centered product display",
      "style": "modern minimalist",
      "clarity": "高"
    },
    "tone": {
      "primary_tone": ["professional", "trustworthy"],
      "emotional_appeal": "論理的",
      "call_to_action": "強"
    },
    "ai_labels": ["finance", "trust", "innovation", "security"],
    "ocr_extracted_text": "Special Offer\n50% OFF\nCall Now",
    "llm_model": "gpt-4o",
    "llm_success": true,
    "llm_retry_count": 0,
    "llm_error": null
  },
  "landing_page": {
    "primary_headline": "Secure Your Financial Future",
    "cta_text": "Get Started Today",
    "structure_analysis": {},
    "message_consistency": 0.92
  },
  "performance": {
    "ctr": 0.03,
    "cvr": 0.0333,
    "cpa": 4000,
    "roas": 2.5,
    "reach": 1000
  },
  "diagnostics": {
    "qualitative": {
      "creative_fatigue_risk": "low",
      "message_clarity_score": 0.95,
      "lp_message_match_risk": 0.08
    },
    "quantitative": {
      "performance_status": "good",
      "ctr_assessment": "平均以上",
      "cvr_assessment": "平均",
      "roas_assessment": "優秀",
      "efficiency_score": 0.88
    }
  }
}
```

### 各フィールドの意味

#### input_metadata
- `mode`: 実行した分析モード
- `source_type`: ファイルソース（local_file）
- `input_timestamp`: 分析実行時刻

#### asset_meta
- `asset_id`: クリエイティブの一意識別子（SHA-256 ハッシュベース）
- `version`: 同一 asset_id の再分析時にインクリメント（1, 2, 3...）
- `platform`: 広告配信プラットフォーム（未実装）
- `format`: メディア形式（image, video 等）

#### creative_core ⭐ 最重要
- **visuals**: 画像の視覚的特性
  - `dominant_colors`: 主要色
  - `composition`: 構図
  - `style`: デザインスタイル
  - `clarity`: 視認性（高/中/低）
- **tone**: メッセージング・トーン
  - `primary_tone`: 主要なトーン（professional, energetic 等）
  - `emotional_appeal`: 感情的訴求 vs 論理的訴求
  - `call_to_action`: CTA の強度（強/中/弱）
- **ai_labels**: LLM が認識したキーワード（最大 15 個）
- **ocr_extracted_text**: 画像/動画フレームから抽出されたテキスト（Tesseract-OCR による自動抽出。複数フレームの場合、改行で結合）
- **llm_model**: 使用した LLM モデル（gpt-4o / gemini-2.0-flash）
- **llm_success**: LLM 分析の成功判定（true/false）
- **llm_retry_count**: リトライ回数（0～3）

#### landing_page (file_plus_lp 以上で出力)
- `primary_headline`: LP の主見出し
- `cta_text`: CTA テキスト
- `message_consistency`: クリエイティブと LP のメッセージ一貫性スコア（0.0～1.0）
- `structure_analysis`: LP の構造分析（セクション数、要素の配置等）

#### performance (file_plus_lp_plus_manual_kpi で出力)
- `ctr`: Click-Through Rate（クリック率）= clicks / impressions
- `cvr`: Conversion Rate（コンバージョン率）= conversions / clicks
- `cpa`: Cost Per Acquisition（顧客獲得単価）= spend / conversions
- `roas`: Return on Ad Spend（広告費対効果）= conversion_value / spend
- `reach`: 推定リーチ（推定値）

#### diagnostics 🔍 分析診断
- **qualitative**: 定性指標
  - `creative_fatigue_risk`: クリエイティブ疲弊リスク（low/medium/high）
  - `message_clarity_score`: メッセージの明確さ（0.0～1.0）
  - `lp_message_match_risk`: LP とのメッセージ不一致リスク（0.0～1.0）
- **quantitative**: 定量指標（KPI がある場合のみ）
  - `performance_status`: パフォーマンス判定（excellent/good/fair/poor）
  - `ctr_assessment`: CTR の評価
  - `cvr_assessment`: CVR の評価
  - `roas_assessment`: ROAS の評価
  - `efficiency_score`: 総合効率スコア（0.0～1.0）

---

## ✨ 改善コメント表示機能（v1.0.0+P0）

### 利用方法
1. 分析実行後、同画面の「✨ 改善提案」セクションを確認
2. 優先度ラベル（🔴P0/🟠P1）と1行要約で、最初に対応すべき項目を判断
3. 「詳細を見る」で展開し、根拠とアクションを確認

### 表示内容
- **優先度**: P0（必須） / P1（強く推奨） / P2（参考）
- **1行要約**: 改善内容の簡潔な説明
- **根拠**: 改善の理由（数値・ユーザー行動等）
- **アクション**: 実施手順

### fail-soft時の表示
LLM API が一時的に利用できない場合、UI上に以下が表示されます：
`⚠️ 改善コメント生成に失敗しました (Error: VALIDATION_FAILED)`

この場合でも、分析結果（JSON全体）は保存され、後で確認可能です。

---

## 📊 UI での使用例

### シナリオ 1: file_only（クリエイティブのみ評価）
**入力:**
1. Analyze タブで `ad_image.png` をアップロード
2. Mode: `file_only` を選択
3. 「🚀 分析実行」をクリック

**出力:**
- Visuals（色、構図、スタイル、視認性）
- Tone（トーン、感情訴求、CTA 強度）
- AI Labels（識別ラベル）
- OCR テキスト（あれば）
- LLM メタデータ（モデル、成功判定、リトライ回数）

### シナリオ 2: file_plus_lp（クリエイティブ + LP 一貫性確認）
**入力:**
1. `campaign_image.png` をアップロード
2. Mode: `file_plus_lp` を選択
3. LP URL: `https://example.com/lp` を入力（または HTML ファイルアップロード）
4. 「🚀 分析実行」をクリック

**出力:**
- Scenario 1 のすべて +
- Landing Page セクション（見出し、CTA テキスト）
- message_consistency スコア: クリエイティブと LP のメッセージ一貫性（0.0～1.0）
- LP 構造分析

### シナリオ 3: file_plus_lp_plus_manual_kpi（フル分析）
**入力:**
1. `video_ad.mp4` をアップロード
2. Mode: `file_plus_lp_plus_manual_kpi` を選択
3. LP URL をご指定
4. KPI JSON を入力：
```json
{
  "impressions": 100000,
  "clicks": 3000,
  "spend": 250000,
  "conversions": 150,
  "conversion_value": 1500000
}
```
5. 「🚀 分析実行」をクリック

**出力:**
- Scenario 2 のすべて +
- Performance セクション:
  - CTR: 3.0%
  - CVR: 5.0%
  - CPA: ¥1,667
  - ROAS: 6.0x
- 定量診断:
  - performance_status: "excellent"
  - 各 KPI の評価
  - efficiency_score: 0.92

---

## 💾 データ保存・取得

### DB に保存されるもの
- すべての分析結果（JSON 全体）
- `asset_id` + `version` で管理
- 論理削除対応（削除済みデータも履歴として保持）

### API での取得
- **一覧取得**:
```bash
curl http://127.0.0.1:8000/api/v1/specs?skip=0&limit=10
```
- **単件取得**:
```bash
curl http://127.0.0.1:8000/api/v1/specs/asset_image_abc123?version=1
```

### UI での確認:
- **List タブ**: 全分析履歴を一覧表示
- **Detail タブ**: `asset_id` を指定して詳細確認、version 選択も可能

---

## ⚠️ 注意点・制限事項

| 項目 | 詳細 |
|---|---|
| LLM API コスト | 毎回の分析で OpenAI / Google API を呼び出すため課金対象。テスト環境では注意 |
| 処理時間 | 同期実行のため、大きな動画は 30～60 秒以上かかる可能性あり |
| OCR 言語 | 英語+日本語固定（他言語は抽出精度低下） |
| 動画フレーム | 3 フレーム（先頭・中盤・末尾）のみ処理 |
| Tesseract 依存 | OCR 利用にはシステムに Tesseract-OCR がインストール済みであること必須 |

---

## 📚 参考ドキュメント

- `README.md`: プロジェクト概要、API エンドポイント
- `docs/ARCHITECTURE.md`: システム設計、技術スタック
- `docs/OPERATIONS.md`: 開発・本番環境ガイド
- `docs/DEPLOYMENT.md`: 本番デプロイチェックリスト

---

## 🔮 Phase 4 以降の改善予定（Roadmap）

### **課題: KPI の手動入力は自動化の障害**

現在、`file_plus_lp_plus_manual_kpi` モードでは **KPI 実績値を手動入力** する必要があります。これは自動化ツールとしては非効率であり、以下の改善が必須です。

### **Phase 4 実装予定項目**

#### **1. Meta Ads Manager API 連携**
- Meta 広告アカウントから実績値を自動取得
- キャンペーン ID / 広告セット ID で検索・分析
- 日次自動更新対応

#### **2. Google Ads API 連携**
- Google 広告アカウント対応
- 複数アカウント管理
- リアルタイム同期

#### **3. インプレッション・マネージャー統合**
- スプレッドシート連携（Google Sheets）
- ダッシュボード上での KPI 自動同期
- 複数キャンペーンの一括分析

#### **4. 定期的な自動再分析**
- スケジュール実行（日次 / 週次）
- トレンド監視・異常検知
- パフォーマンス劣化時のアラート

#### **5. ワークフロー自動化**
- API 連携により、手動入力が完全に不要に
- クリエイティブをアップロード → 自動で実績値を取得 → 分析実行 → 結果提示

### **実装後のユースケース**

**Before（現在）:**
```
クリエイティブアップロード → LP 入力 → KPI を手動で入力（面倒） → 分析実行 → 結果確認
```

**After（Phase 4）:**
```
クリエイティブアップロード + キャンペーン ID 指定 → システムが Meta/Google から自動取得 → 分析自動実行 → 結果確認 → （オプション）定期的に再分析
```

### **優先度**
1. **高**: Meta Ads API 連携（市場での使用例が多い）
2. **高**: Google Ads API 連携
3. **中**: スプレッドシート統合
4. **中**: 定期的な自動再分析
5. **低**: アラート・ダッシュボード機能

---

このロードマップにより、Ad-Insight-Spec は **真の自動化ツール** へと進化します。

Happy analyzing! 🚀
