# Phase 2a バックログ - Persistence & API Foundation

**対象フェーズ**: Phase 2a (DB・API基盤)  
**期間**: 2026-06-24 ～ (予定)  
**ステータス**: 🔵 Planning  
**前フェーズ**: Phase 1 Complete ✅

---

## 📋 概要

Phase 2a は、Phase 1 で実装した CLI ベースのパイプラインを**API 化**し、**データベースに永続化**する基盤を整備するフェーズです。

### ゴール

- ✅ PostgreSQL / SQLite にデータを永続化
- ✅ FastAPI で CRUD エンドポイント実装
- ✅ `/analyze` エンドポイント（ファイル POST）
- ✅ 複数件管理・検索機能
- ✅ API ベースの仕様管理（Phase 2c への布石）

### スコープ外（Phase 2b 以降）

- UI（Streamlit / Vue.js）
- LLMService 本実装（Gemini 統合）
- Meta/Google/TikTok API 統合
- エンタープライズグレード機能（権限管理・監査ログ）

---

## 🎯 Phase 2a の主要な設計論点

### 論点 1: Persistence Policy（永続化ポリシー）

#### Q1.1: asset_id のユニーク性と履歴管理

**現在の状況**: 
- Phase 1 では `asset_id` は UUID を含むため、同じ入力でも毎回異なる ID が生成される
- UUID は timestamp + random で構成される形式

**決定すべき項目**:

| 項目 | 選択肢 | 影響 |
|------|--------|------|
| **asset_id 再生成** | A) 毎回新規生成<br>B) 素材ファイルのハッシュに基づく固定化 | A: 複数分析・比較困難<br>B: 同素材の同一性を保証 |
| **DB 上のユニーク制約** | A) `asset_id` に UNIQUE<br>B) `(creative_hash, source_type)` の複合キー | A: シンプル<br>B) 柔軟（同素材の複数分析対応） |
| **履歴管理** | A) 上書き（最新のみ保持）<br>B) バージョニング（全履歴保持）<br>C) タイムスタンプの soft-delete | A: シンプル<br>B: 追跡可能<br>C: 復元可能 |

**推奨案**: 
- **asset_id**: B（ハッシュベース）で固定化
- **DB 制約**: B（複合キー）で同素材複数分析に対応
- **履歴**: B（バージョニング）で分析内容の比較・トレーサビリティ確保

---

#### Q1.2: external_ids の扱い

**現在の状況**:
```python
class ExternalIds(BaseModel):
    meta_ad_id: Optional[str] = None
    google_ad_id: Optional[str] = None
    tiktok_ad_id: Optional[str] = None
```

**決定すべき項目**:

| 項目 | 選択肢 | 影響 |
|---|---|---|
| **DB カラム設計** | A) JSONB 列（スキーマ柔軟）<br>B) 正規化テーブル（ads_external_id） | A: クエリ困難<br>B: 検索効率↑ |
| **外部 ID のユニーク制約** | A) 各 ID は全体でユニーク<br>B) プラットフォーム内でのみユニーク<br>C) 制約なし（重複許可） | A: 厳格（キー衝突防止）<br>B: 標準的<br>C: 柔軟 |
| **外部 ID から逆参照** | A) 対応なし<br>B) インデックス作成（クエリ性能↑） | A: シンプル<br>B: 複数素材の横断検索可能 |

**推奨案**:
- カラム設計: B（正規化テーブル）で検索効率向上
- ユニーク制約: B（プラットフォーム内）で Phase 2c API 統合に対応
- 逆参照: B（インデックス）で横断検索可能化

### 論点 2: DB スキーマ設計

#### Q2.1: 永続化粒度（何をどのテーブルに保存するか）

**オプション A: JSONB 単一テーブル**
```text
Table: ad_insights
├─ id (PK)
├─ asset_id (UK, indexed)
├─ created_at
├─ updated_at
├─ spec_data (JSONB)  ← ad_insight_spec v0.2 全体
└─ metadata
```
**メリット**:
- スキーマ柔軟性（v0.2 → v0.3 移行が容易）
- 実装シンプル
- JSON 検索の爆発的な組み合わせに対応

**デメリット**:
- JSON 検索が遅い（大規模データセット）
- 複数条件フィルタリング困難（例: `ctr > 0.05 AND tone = "emotional"` ）

**オプション B: 正規化テーブル群**
```text
Table: ad_insights (メインテーブル)
├─ id (PK)
├─ asset_id (UK)
├─ format (enum)
├─ created_at
└─ updated_at

Table: asset_metadata
├─ asset_id (FK)
├─ campaign_name
├─ platform
└─ ...

Table: creative_core
├─ asset_id (FK)
├─ primary_text
├─ duration_seconds
├─ ai_labels (JSONB)
└─ ...

Table: landing_pages
├─ asset_id (FK)
├─ url
├─ fv_copy
├─ message_consistency_score
└─ ...

Table: performance_kpi
├─ asset_id (FK)
├─ impressions
├─ clicks
├─ conversions
└─ ...

Table: diagnostics
├─ asset_id (FK)
├─ fatigue_risk (enum)
├─ clarity_score
├─ efficiency_score
└─ ...
```
**メリット**:
- クエリ性能（B-tree インデックス活用）
- 複合条件フィルタリング可能
- データ整合性（外部キー制約）

**デメリット**:
- 実装複雑（JOIN 多数）
- スキーマ変更時の手間（マイグレーション）

**推奨案: ハイブリッド**
- `ad_insights` メインテーブル + `spec_data` JSONB（全体バックアップ）
- 頻繁にクエリされるフィールドは別テーブルで正規化（asset_meta, performance）
- 複雑な構造（ai_labels など）は JSONB 保持

```text
Table: ad_insights
├─ id (PK)
├─ asset_id (UK, indexed)
├─ format (enum, indexed)
├─ created_at (indexed)
├─ updated_at
├─ version (int)  ← バージョニング用
├─ spec_data (JSONB)  ← v0.2 全体
└─ status (enum: draft/published/archived)

Table: asset_metadata
├─ asset_id (FK -> ad_insights)
├─ campaign_name (indexed)
├─ platform (indexed)
├─ ad_account_id
└─ ...

Table: performance_kpi
├─ asset_id (FK)
├─ impressions (indexed)
├─ clicks (indexed)
├─ ctr (indexed)  ← 頻出クエリ対応
├─ conversions
├─ cvr
├─ roas (indexed)
└─ ...
```

#### Q2.2: バージョニング・履歴管理

**決定すべき項目**:

| 項目 | 選択肢 | 影響 |
|---|---|---|
| **旧バージョン保持** | A) 上書き<br>B) ad_insights_history テーブル<br>C) version カラム + soft-delete | A: シンプル<br>B: 分離管理<br>C: 復元可能 |
| **バージョン番号** | A) 自動採番<br>B) timestamp<br>C) semantic version | A: 簡潔<br>B: 時系列追跡可<br>C: 明示的 |

**推奨案: C（version + soft-delete）**
- `version INT` (1, 2, 3, ...)
- `deleted_at TIMESTAMP NULL`
- 同じ `asset_id` の複数 version を保持→比較分析可能

```text
Table: ad_insights
├─ id (PK)
├─ asset_id
├─ version (int)
├─ (asset_id, version) -> UNIQUE constraint
├─ created_at
├─ deleted_at (NULL = active)
└─ spec_data (JSONB)
```

### 論点 3: CRUD エンドポイント範囲

#### Q3.1: 対応すべき操作

| 操作 | エンドポイント | 必須? | 優先度 |
|---|---|---|---|
| **新規分析実行** | `POST /analyze` | ✅ | P0 |
| **取得（単件）** | `GET /specs/{asset_id}` | ✅ | P0 |
| **一覧取得** | `GET /specs` | ✅ | P0 |
| **削除（論理）** | `DELETE /specs/{asset_id}` | ✅ | P1 |
| **更新（診断部分）** | `PATCH /specs/{asset_id}` | ⚠️ | P2 |
| **バージョン比較** | `GET /specs/{asset_id}/versions` | - | P2 |
| **複数削除** | `DELETE /specs?asset_id=a&asset_id=b` | - | P3 |

**推奨の Phase 2a スコープ**:
- ✅ `POST /analyze` (file upload + orchestrator 実行)
- ✅ `GET /specs/{asset_id}` (最新 version 取得)
- ✅ `GET /specs` (一覧・フィルタリング)
- ✅ `DELETE /specs/{asset_id}` (論理削除)
- ⏳ `PATCH /specs/{asset_id}` (Phase 2b で検討)

#### Q3.2: /analyze エンドポイントの入力形式

**オプション A: multipart/form-data (ファイルアップロード)**
```python
@app.post("/analyze")
async def analyze(
    input_file: UploadFile,
    lp_file: Optional[UploadFile] = None,
    kpi_file: Optional[UploadFile] = None,
    mode: str = "file_plus_lp_plus_manual_kpi"
) -> Dict[str, Any]:
    """ファイルをアップロードして分析"""
    pass
```
**メリット**: Web UI との親和性、ブラウザから直接アップロード可
**デメリット**: 大ファイル対応（100MB+ ）への工夫必要

**オプション B: JSON リクエストボディ + base64**
```python
@app.post("/analyze")
async def analyze(
    request: AnalyzeRequest
) -> Dict[str, Any]:
    """
    {
      "input_file": "base64_encoded_data",
      "input_filename": "video.mp4",
      "lp_url": "https://example.com/lp",
      "kpi": {...},
      "mode": "file_plus_lp_plus_manual_kpi"
    }
    """
    pass
```
**メリット**: 非同期実行（job queue）との相性良好、API からの呼び出し容易
**デメリット**: base64 エンコーディングのオーバーヘッド（データ量 +33%）

**推奨案: A（multipart/form-data）**
- Phase 2b で Web UI 実装時に自然な流れ
- Flask/FastAPI の標準実装で簡潔
- 大ファイル対応は後続タスク

#### Q3.3: レスポンス形式

**同期実行 (ファイル小～中規模対応)**:
```python
# 実行時間 < 30秒を想定
@app.post("/analyze")
async def analyze(...) -> AdInsightSpec:
    """即座に結果を返す"""
    spec = orchestrator.run()
    save_to_db(spec)
    return spec
```

**非同期実行 (ファイル大規模対応)**:
```python
# 実行時間 > 30秒を想定
@app.post("/analyze")
async def analyze(...) -> Dict[str, str]:
    """job_id を返し、ポーリングで結果取得"""
    job_id = submit_job(...)
    return {"job_id": job_id, "status_url": f"/jobs/{job_id}"}

@app.get("/jobs/{job_id}")
async def get_job_status(job_id: str) -> Dict[str, Any]:
    """ジョブステータス確認"""
    return get_job(job_id)
```

**推奨案: 同期実行（Phase 2a）**
- ファイル < 100MB 想定（処理時間 < 30秒）
- 実装シンプル
- 非同期化は Phase 2c で（Celery or Apache Airflow）

### 論点 4: /analyze エンドポイントの責務

#### Q4.1: ファイル保存と管理

**決定すべき項目**:

| 項目 | 選択肢 | 影響 |
|---|---|---|
| **入力ファイル保存** | A) 保存しない（分析後削除）<br>B) ローカルストレージ保存<br>C) S3/クラウドストレージ | A: ディスク圧迫なし<br>B: 実装簡潔<br>C: スケール対応 |
| **入力ファイル参照** | A) ファイルなし（JSON のみ）<br>B) asset_id で参照可能 | A: 単純<br>B) 再分析・監査可能 |
| **ファイル削除ポリシー** | A) 手動削除<br>B) 自動削除（30日後）<br>C) 無期限保持 | A: 手作業<br>B: ストレージ圧迫防止<br>C: 監査性↑ |

**推奨案 (Phase 2a): B（ローカルストレージ保存）+ 手動削除**
- ローカル開発環境での実装簡潔
- `backend/uploads/` ディレクトリに保存
- 自動削除ポリシーは Phase 2c で検討（S3 移行時に自動実装）

```text
backend/
└── uploads/
    ├── {asset_id}/
    │   ├── input.mp4
    │   ├── lp.html
    │   └── kpi.json
    └── ...
```

#### Q4.2: 分析パイプラインの実行位置

**決定すべき項目**:

| 位置 | 実装方式 | 利点 | 欠点 |
|---|---|---|---|
| **API で実行** | `orchestrator.run()` 直呼び出し | 実装シンプル | 重い処理で timeout リスク |
| **バックグラウンド非同期** | Task queue (Celery) | 並列処理・UI 非ブロック | インフラ複雑化 |
| **CLI を再利用** | `subprocess` で CLI 呼び出し | 既存コード再利用 | プロセス分離のオーバーヘッド |

**推奨案 (Phase 2a): API で直実行**
- ファイル < 100MB で処理時間 < 30秒
- 実装が最もシンプル
- 非同期化は Phase 2c で（スケーリング時）

#### Q4.3: エラーハンドリング

**決定すべき項目**:

| エラータイプ | 対応 | HTTP Status |
|---|---|---|
| **入力ファイル形式エラー** | 詳細なメッセージ + 解決方法ガイド | 400 Bad Request |
| **モード検証エラー** | モード仕様の説明 + 例示 | 400 Bad Request |
| **LLMService エラー** | graceful degradation（モック値を返す） | 200 OK（警告付き） |
| **DB 保存エラー** | トランザクション rollback | 500 Internal Server Error |
| **未対応フォーマット** | 対応フォーマット一覧を返す | 415 Unsupported Media Type |

**推奨案: 上記の対応 + ErrorResponse モデル統一**
```python
class ErrorResponse(BaseModel):
    error_code: str  # "INVALID_INPUT_FORMAT"
    message: str
    details: Optional[Dict[str, Any]]  # { "reason": "...", "suggestion": "..." }
    timestamp: datetime
```

---

## 📝 Phase 2a タスク分解

### タスク グループ 1: 設計・準備（1-2 日）
- **T1.1: Persistence Policy 決定ドキュメント作成**
  - 上記論点 1-4 の決定を `docs/plans/phase2a_design_decisions.md` にまとめる
  - 最終決定内容を記録
- **T1.2: SQLAlchemy モデル設計書**
  - テーブル定義（CREATE TABLE）
  - インデックス・制約
  - リレーション図
  - マイグレーション戦略（Alembic）
- **T1.3: FastAPI エンドポイント仕様書**
  - 各エンドポイントの入出力仕様
  - エラーコード一覧
  - リクエスト/レスポンス例

### タスク グループ 2: 実装（3-5 日）
- **T2.1: SQLAlchemy モデル実装（`backend/app/models/`）**
  - AdInsight メインモデル
  - AssetMetadata モデル
  - PerformanceKpi モデル
  - リレーション・バリデーション
- **T2.2: Alembic マイグレーション初期化**
  - `alembic init`
  - 初期マイグレーション作成
  - dev/prod 環境 DB 構築
- **T2.3: FastAPI 基盤実装**
  - `backend/app/api/routes/specs.py`
  - `/analyze` POST エンドポイント
  - `/specs` GET エンドポイント
  - `/specs/{asset_id}` GET/DELETE エンドポイント
- **T2.4: DB Repository 層実装**
  - `backend/app/repositories/spec_repository.py`
  - CRUD 操作の統一インターフェース
  - クエリビルダー（フィルタリング）
- **T2.5: テスト実装**
  - SQLAlchemy モデルテスト（factories 活用）
  - FastAPI エンドポイントテスト（`pytest-asyncio`）
  - DB トランザクション・ロールバックテスト

### タスク グループ 3: 統合・検証（1-2 日）
- **T3.1: エンドツーエンド統合テスト**
  - POST `/analyze` → DB 保存 → GET `/specs/{asset_id}` の一連フロー
  - 複数ファイル形式での動作確認
- **T3.2: 負荷テスト・性能調査**
  - 大ファイル（> 50MB）での処理時間計測
  - DB クエリの最適化（インデックス効果測定）
- **T3.3: ドキュメント・デプロイガイド作成**
  - API ドキュメント（Swagger）自動生成
  - DB セットアップ手順
  - 本番環境への展開ガイド

---

## 🎯 Phase 2a の最初の 3 タスク（着手順）

### 📌 Task 1: Persistence Policy 最終決定ドキュメント作成
**ファイル**: `docs/plans/phase2a_design_decisions.md`

**内容**:
```markdown
# Phase 2a 設計決定（Design Decisions）

## 1. Persistence Policy

### 1.1 asset_id 戦略
**決定**: asset_id = MD5(file_content) で固定化
**理由**: 同素材の分析再実行時の同一性確保
**実装**: MetadataService に `generate_deterministic_asset_id()` メソッド追加

### 1.2 external_ids 管理
**決定**: 正規化テーブル `ads_external_ids` で管理
**理由**: Meta/Google/TikTok API との連携時にインデックス検索が必須
**実装**: (id, platform, external_id) の複合ユニーク制約

### 1.3 履歴管理
**決定**: version + soft-delete で全履歴保持
**理由**: 分析内容の比較・監査が必要
**実装**: (asset_id, version) 複合ユニーク制約

## 2. DB スキーマ

### テーブル一覧
- ad_insights（メイン）
- asset_metadata
- performance_kpi
- ads_external_ids

...（詳細テーブル定義）

## 3. API エンドポイント設計

### 優先実装 (Phase 2a)
- POST /analyze
- GET /specs
- GET /specs/{asset_id}
- DELETE /specs/{asset_id}

...（詳細仕様）
```
**期間**: 1 日
**アウトプット**: 決定済みドキュメント + チェックリスト

### 📌 Task 2: SQLAlchemy モデル実装
**ファイル**:
- `backend/app/models/__init__.py` (新規)
- `backend/app/models/ad_insight.py` (新規)
- `backend/app/models/base.py` (新規 - BaseModel)

**主要な実装**:
```python
# backend/app/models/ad_insight.py
from sqlalchemy import Column, String, Integer, DateTime, Text, JSON, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime

class AdInsight(Base):
    __tablename__ = "ad_insights"
    
    id: int = Column(Integer, primary_key=True)
    asset_id: str = Column(String(100), nullable=False, index=True)
    version: int = Column(Integer, default=1)
    format: str = Column(String(50), nullable=False, index=True)
    created_at: datetime = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at: datetime = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    deleted_at: Optional[datetime] = Column(DateTime, nullable=True)
    spec_data: dict = Column(JSON, nullable=False)  # JSONB
    
    # FK リレーション
    asset_metadata = relationship("AssetMetadata", uselist=False, back_populates="ad_insight")
    performance = relationship("PerformanceKpi", uselist=False, back_populates="ad_insight")
    
    __table_args__ = (
        UniqueConstraint('asset_id', 'version', name='uq_asset_version'),
    )
```
**期間**: 2 日
**アウトプット**: SQLAlchemy モデル + ユニットテスト

### 📌 Task 3: FastAPI 基盤実装（エンドポイント骨組み）
**ファイル**:
- `backend/app/api/__init__.py` (新規)
- `backend/app/api/routes/__init__.py` (新規)
- `backend/app/api/routes/specs.py` (新規)
- `backend/app/main.py` (新規 - FastAPI app)

**主要なエンドポイント骨組み**:
```python
# backend/app/api/routes/specs.py
from fastapi import APIRouter, File, UploadFile, Query, HTTPException
from typing import List, Optional
from app.schemas.ad_insight import AdInsightSpec
from app.services.analysis_orchestrator import AnalysisOrchestrator

router = APIRouter(prefix="/api/v1/specs", tags=["specs"])

@router.post("/analyze")
async def analyze(
    input_file: UploadFile,
    lp_file: Optional[UploadFile] = None,
    kpi_file: Optional[UploadFile] = None,
    mode: str = "file_plus_lp_plus_manual_kpi"
) -> AdInsightSpec:
    """ファイルをアップロードして分析を実行"""
    # T2.3 で実装
    pass

@router.get("/")
async def list_specs(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    asset_id: Optional[str] = None,
    format: Optional[str] = None,
    created_after: Optional[str] = None
) -> Dict[str, Any]:
    """分析結果一覧取得（フィルタリング対応）"""
    pass

@router.get("/{asset_id}")
async def get_spec(asset_id: str, version: Optional[int] = None) -> AdInsightSpec:
    """分析結果取得（特定 asset_id）"""
    pass

@router.delete("/{asset_id}")
async def delete_spec(asset_id: str) -> Dict[str, str]:
    """分析結果削除（論理削除）"""
    pass
```
**期間**: 2 日
**アウトプット**: FastAPI ルーター + テスト

---

## 📊 Phase 2a のマイルストーン

```text
Week 1:
├─ Day 1-2: 設計決定ドキュメント完成
├─ Day 3-4: SQLAlchemy モデル実装・テスト
└─ Day 5: FastAPI 基盤実装開始

Week 2:
├─ Day 1-2: FastAPI エンドポイント実装
├─ Day 3: Repository 層実装
├─ Day 4: E2E テスト・統合
└─ Day 5: デプロイガイド作成・Phase 2b へ移行
```

**Go-Live**: 2026-06-30（予定）  
**Phase 2b 開始**: 2026-07-01（予定）

---

## 🔗 関連ドキュメント
- Phase 1 完了レポート: `docs/phase1_completion_report.md`
- 実装計画: `docs/plans/implementation_phase_plan.md`
- API 仕様（詳細）: TBD (T1.3 で作成)
- DB スキーマ（詳細）: TBD (T1.2 で作成)

---

## ⚠️ 注意・リスク
| リスク | 対策 |
|---|---|
| **DB マイグレーション複雑化** | Alembic で段階的なマイグレーション作成、dev で十分テスト |
| **大ファイル対応（100MB+）** | 同期実行で timeout リスク → 非同期化は Phase 2c で |
| **JSON クエリ性能** | PostgreSQL の JSONB インデックス活用、必要に応じて正規化 |
| **外部 ID 衝突** | `(platform, external_id)` 複合ユニーク制約で防止 |

---
**Status**: 🔵 Planning Phase  
**Last Updated**: 2026-06-23  
**Next Review**: Phase 2a Kickoff (2026-06-24)
