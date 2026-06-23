# Ad-Insight-Spec 📊

Web広告とランディングページの統合分析・診断システム

## 🎯 プロジェクト概要

**Ad-Insight-Spec** は、ダウンロード済みの広告素材（動画・画像・テキスト）とランディングページ、KPI データから、構造化された診断 JSON を生成するシステムです。

**Version**: v0.2 (Phase 1 Complete)  
**Status**: ✅ **Phase 1 完了・凍結** → Phase 2a (Persistence & API) へ移行予定  
**Last Updated**: 2026-06-23

---

## 📊 Phase 1 ステータス

### ✅ 完了内容

| 項目 | 状況 |
|------|------|
| **7つのコアサービス** | ✅ 実装 + テスト完了（75+ tests） |
| **Pydantic v0.2 スキーマ** | ✅ 定義・検証機能完成 |
| **3つの入力モード** | ✅ file_only / file_plus_lp / file_plus_lp_plus_manual_kpi |
| **CLI インターフェース** | ✅ Click ベース実装 |
| **E2E 検証テスト** | ✅ 3/3 モード PASSED |
| **ドキュメント整備** | ✅ スキーマ・アーキテクチャ・完了レポート |

### ❌ Phase 2a へ延期した項目

- データベース永続化（SQLAlchemy + PostgreSQL）
- FastAPI エンドポイント実装
- LLMService 本実装（Gemini 2.0 Flash 統合）
- OCRService 本実装（Tesseract / Google Vision API）
- UI（Streamlit / Vue.js）
- Meta/Google/TikTok API 統合

---

## 🏗️ クイックスタート

### インストール

```bash
# リポジトリをクローン
git clone https://github.com/nario0715masa0619-create/ad-insight-spec.git
cd ad-insight-spec

# バックエンド環境構築
cd backend
pip install -r requirements.txt
```

### 基本的な使い方

```bash
# file_only モード（素材分析のみ）
python -m app.cli.main analyze --input image.png --mode file_only

# file_plus_lp モード（素材 + LP 整合性分析）
python -m app.cli.main analyze \
  --input image.png \
  --lp lp.html \
  --mode file_plus_lp

# file_plus_lp_plus_manual_kpi モード（完全診断）
python -m app.cli.main analyze \
  --input video.mp4 \
  --lp https://example.com/lp \
  --kpi kpi.json \
  --mode file_plus_lp_plus_manual_kpi \
  --output result.json
```

### E2E 検証テスト実行

```powershell
$env:PYTHONPATH="C:\NewProjects\ad-insight-spec\backend"
python scripts/e2e_validation.py
```

**期待される結果:**
```text
✅ Test 1: file_only mode: PASSED
✅ Test 2: file_plus_lp mode: PASSED
✅ Test 3: file_plus_lp_plus_manual_kpi mode: PASSED

🎉 All tests passed!
```

---

## 📦 システム構成

### 7つのコアサービス

```text
Input Files (Video/Image/Text, LP, KPI)
         ↓
    [IngestionService]        ← ファイル形式検証
         ↓
    [MetadataService]         ← asset_id 生成
         ↓
  [Content Analysis Layer]
   ├─ [VideoService]          ← フレーム抽出
   ├─ [LPService]             ← LP 解析
   └─ [OCRService]            ← テキスト抽出（モック）
         ↓
    [LLMService]              ← 定性分析（モック）
         ↓
  [ConverterService]          ← Pydantic v0.2 変換・検証
         ↓
    Output JSON               ← ad_insight_spec v0.2
```

### サービス詳細

| サービス | 責務 | テスト | 状態 |
|---|---|---|---|
| IngestionService | ファイル形式検証、モード判定 | 27 ✅ | 本実装 |
| MetadataService | asset_id 生成、メタデータ抽出 | 28 ✅ | 本実装 |
| LPService | LP 解析、FV コピー・CTA 抽出 | 20 ✅ | 本実装 |
| VideoService | フレーム抽出（FFmpeg） | 15 ✅ | 本実装 |
| OCRService | テキスト抽出（Tesseract/Vision） | - | モック |
| LLMService | 定性分析（Hook/Tone/Pain points） | - | モック |
| ConverterService | JSON 変換・Pydantic 検証 | ✅ | 本実装 |

---

## 📋 入力モードと出力仕様

### モード 1: file_only
**入力**: 素材ファイル（画像・動画・テキスト）のみ

**出力フィールド**:
- `asset_meta`: 素材メタデータ
- `creative_core`: 素材内容分析
- `diagnostics.qualitative`: 定性診断
- `landing_page`: null
- `performance`: null
- `diagnostics.quantitative`: null

**使用例**:
```bash
python -m app.cli.main analyze --input ad_video.mp4 --mode file_only --output analysis.json
```

### モード 2: file_plus_lp
**入力**: 素材ファイル + ランディングページ（URL or HTML）

**追加出力フィールド**:
- `landing_page`: LP 分析結果
- `landing_page.message_consistency`: メッセージ整合性スコア（0.0～1.0）
- `diagnostics.qualitative.lp_message_match_risk`: LP 整合性リスク評価

**使用例**:
```bash
python -m app.cli.main analyze \
  --input ad_image.png \
  --lp landing_page.html \
  --mode file_plus_lp \
  --output analysis.json
```

### モード 3: file_plus_lp_plus_manual_kpi
**入力**: 素材ファイル + LP + KPI（手動入力 JSON）

**KPI JSON フォーマット例**:
```json
{
  "impressions": 45000,
  "clicks": 1350,
  "spend": 180000,
  "conversions": 45,
  "conversion_value": 450000
}
```

**自動計算されるメトリクス**:
- `ctr`: clicks / impressions
- `cvr`: conversions / clicks
- `cpa`: spend / conversions
- `roas`: conversion_value / spend
- `frequency`: impressions / reach

**追加出力フィールド**:
- `performance`: KPI + 計算メトリクス
- `diagnostics.quantitative`: 定量診断（パフォーマンス評価）
  - `performance_status`: excellent / good / fair / poor
  - `ctr_assessment`: CTR の相対評価
  - `cvr_assessment`: CVR の相対評価
  - `roas_assessment`: ROAS の相対評価
  - `efficiency_score`: 総合効率スコア（0.0～1.0）

**使用例**:
```bash
python -m app.cli.main analyze \
  --input campaign_video.mp4 \
  --lp https://example.com/lp \
  --kpi kpi.json \
  --mode file_plus_lp_plus_manual_kpi \
  --output complete_analysis.json
```

---

## 📊 出力例（JSON）

### file_only モード出力例
```json
{
  "input_metadata": {
    "mode": "file_only",
    "source_type": "local_file",
    "input_timestamp": "2026-06-23T15:30:00Z"
  },
  "asset_meta": {
    "asset_id": "asset_20260623_153000_local_abc123",
    "asset_name": "Summer Campaign Video v2",
    "platform": "unknown"
  },
  "creative_core": {
    "format": "video_static",
    "duration_seconds": 30,
    "primary_text": "あなたの時間を取り戻す。簡単LP作成で成約率2倍。",
    "headline": "あなたの時間を取り戻す",
    "ai_labels": {
      "hook_type": "benefit",
      "appeal_type": "emotional",
      "identified_benefits": ["saves_time", "high_conversion"]
    }
  },
  "landing_page": null,
  "performance": null,
  "diagnostics": {
    "qualitative": {
      "creative_fatigue_risk": "low",
      "creative_fatigue_basis": "フック『成約率2倍』は具体的で新規性あり。",
      "message_clarity_score": 0.95
    },
    "quantitative": null
  },
  "_metadata": {
    "generated_at": "2026-06-23T15:30:05Z",
    "data_source": "local_file",
    "ai_model_version": "gemini-2.0-flash-mock",
    "json_schema_version": "v0.2",
    "input_mode": "file_only"
  }
}
```

詳細な出力例は以下を参照：
- `sample_data/sample_file_only.json`
- `sample_data/sample_file_plus_lp.json`
- `sample_data/sample_file_plus_lp_plus_manual_kpi.json`

---

## 📂 プロジェクト構造

```text
ad-insight-spec/
├── README.md                           ← このファイル
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── schemas/
│   │   │   └── ad_insight.py           (Pydantic v0.2 モデル)
│   │   ├── services/
│   │   │   ├── base_service.py
│   │   │   ├── ingestion_service.py
│   │   │   ├── metadata_service.py
│   │   │   ├── lp_service.py
│   │   │   ├── video_service.py
│   │   │   ├── ocr_service.py
│   │   │   ├── llm_service.py
│   │   │   ├── converter_service.py
│   │   │   └── analysis_orchestrator.py
│   │   └── cli/
│   │       └── main.py                 (Click CLI)
│   ├── requirements.txt
│   └── tests/
│       ├── test_ingestion_service.py   (27 tests)
│       ├── test_metadata_service.py    (28 tests)
│       ├── test_lp_service.py          (20 tests)
│       └── test_video_service.py       (15 tests)
├── scripts/
│   └── e2e_validation.py              (E2E 検証, 3 tests)
├── docs/
│   ├── specs/
│   │   └── ad_insight_json_schema_v0_2.md
│   ├── architecture/
│   │   └── phase1_file_first_strategy.md
│   ├── implementation/
│   │   └── service_interface_design.md
│   ├── plans/
│   │   ├── implementation_phase_plan.md
│   │   └── phase2a_backlog.md           (Phase 2a 計画)
│   └── phase1_completion_report.md      (詳細な完了レポート)
└── sample_data/
    ├── sample_file_only.json
    ├── sample_file_plus_lp.json
    ├── sample_file_plus_lp_plus_manual_kpi.json
    ├── test_image.png
    ├── test_lp.html
    └── test_kpi.json
```

---

## 📚 ドキュメント

### 仕様書・設計
| ドキュメント | 概要 |
|---|---|
| `ad_insight_json_schema_v0_2.md` | JSON スキーマ完全仕様（13セクション） |
| `phase1_file_first_strategy.md` | Phase 1 アーキテクチャ・ファイルファースト戦略 |
| `service_interface_design.md` | 7つのサービス インターフェース定義 |

### 計画・レポート
| ドキュメント | 概要 |
|---|---|
| `phase1_completion_report.md` | Phase 1 詳細な完了レポート（テスト結果・既知制限） |
| `phase2a_backlog.md` | Phase 2a（DB・API）の設計論点・タスク |
| `implementation_phase_plan.md` | 全体フェーズ計画（Phase 0～3） |

---

## 🧪 テスト

### ユニットテスト
```bash
cd backend
python -m pytest tests/ -v
```

**テスト結果**:
- IngestionService: 27/27 ✅
- MetadataService: 28/28 ✅
- LPService: 20/20 ✅
- VideoService: 15/15 ✅
- **総計: 90 テストケース 全 PASSED**

### E2E 検証テスト
```powershell
cd backend
$env:PYTHONPATH="C:\NewProjects\ad-insight-spec\backend"
python ..\scripts\e2e_validation.py
```

**テスト項目**:
- **Test 1**: file_only → landing_page=null, performance=null を確認 ✅
- **Test 2**: file_plus_lp → message_consistency スコア計算を確認 ✅
- **Test 3**: file_plus_lp_plus_manual_kpi → CTR/CVR/ROAS 自動計算を確認 ✅

---

## ⚙️ 環境要件

| 項目 | バージョン |
|---|---|
| Python | 3.9+ |
| Pydantic | 1.x or 2.x (互換モード) |
| FFmpeg | 4.0+ |
| BeautifulSoup4 | 4.9+ |

### インストール
```bash
cd backend
pip install -r requirements.txt
```

**requirements.txt の主要パッケージ**:
- `pydantic >= 1.10` (v0.2 互換)
- `beautifulsoup4 >= 4.9`
- `click >= 8.0` (CLI)
- `pytest` (テスト)

---

## 🚫 既知の制限と制約

### 実装上の制限
| 項目 | 制限内容 | 対応予定 |
|---|---|---|
| LLMService | モック実装（固定値返却） | Phase 2: Gemini 統合 |
| OCRService | モック実装（未統合） | Phase 2: Tesseract/Vision API |
| VideoService | フレーム抽出のみ | Phase 2: 高度な分析 |
| DB 永続化 | なし（JSON のみ出力） | Phase 2a: SQLAlchemy 統合 |
| LP 解析 | 静的 HTML のみ（JavaScript 非対応） | Phase 2: Selenium 統合 |
| asset_id 再現性 | UUID 使用で同入力でも異なる | 仕様通り |

### 設計上の制限
- **モード検証**: CLI 側のみ（API 側未実装）
- **external_ids**: オプショナル（Phase 2 で Meta/Google ID 連携予定）
- **エラーハンドリング**: 基本的なバリデーションエラーのみ
- **ファイルサイズ上限**: 100MB（Phase 2 で拡張予定）

詳細は `phase1_completion_report.md` を参照してください。

---

## 🔄 次フェーズ（Phase 2a）

Phase 2a では以下を実装予定です：

**主要な設計決定**（詳細は `docs/plans/phase2a_backlog.md` を参照）
1. **Persistence Policy**
   - asset_id と external_ids の扱い（ユニーク制約など）
   - DB スキーマ設計（JSONB vs 正規化）
   - 履歴管理・バージョニング方針
2. **SQLAlchemy モデル実装**
   - AdInsight テーブル設計
   - インデックス・外部キー定義
   - Alembic マイグレーション
3. **FastAPI 基盤実装**
   - `POST /analyze` エンドポイント（file upload）
   - `GET /specs/{asset_id}` エンドポイント（取得）
   - `PATCH /specs/{asset_id}` エンドポイント（更新）

**Phase 2a の着手順**（最初の3タスク）
詳細は `docs/plans/phase2a_backlog.md` を参照してください。

---

## 🤝 参考資料

本プロジェクトの設計思想は以下を参考にしています：
- `video-insight-spec`: YouTube 動画分析システムのアーキテクチャ
- **Pydantic v0.2**: スキーマ駆動開発
- **File-First 戦略**: API 依存を最小化し、ローカルファイル処理で高速開発を実現

## 📄 License

TBD

## 📞 Contact & Support

- Project Lead: nario0715masa0619-create
- Status: ✅ Phase 1 Complete → Phase 2a Planning
- Last Updated: 2026-06-23

Happy analyzing! 🚀
