# Phase 2a 設計判断 (Persistence & API)

> ⚠️ **Historical planning doc（2026-06-23頃の記録）**
> この文書は Phase 2a 着手時点の設計決定記録であり、その後の実装状況を反映していません。
> **現在の実装状況は [README.md](../../README.md) と現行コードを参照してください。**
> README.md記載のとおり、Phase 2a は既に完了済みです。本文書が決定した「JSON正本主義」
> （`AdInsight.spec_data`を単一JSON正本とする方針）は実際に採用され、
> `backend/app/models/ad_insight.py` / `backend/app/api/routes/specs.py` /
> `backend/app/repositories/ad_insight_repository.py` として実装・本番稼働中です。

## 1. 永続化方針
- **JSON正本主義**: `ad_insight_spec` 全体の解析結果などを JSON（または JSONB 相当）の正本データとして保持する。
- **検索用項目**: 一覧表示や検索で利用する最低限の項目（`asset_id`, 作成日時など）のみ、独立したカラムとして冗長保持する。
- **履歴管理**: `asset_id` と `version` を用いた履歴管理案を優先する。
- **削除処理**: 論理削除（`is_deleted` フラグ等）を優先し、物理削除は行わない。

## 2. データベース選定と拡張性
- **DB選定**: まずは **SQLite** で動く最小形を実装する。
- **拡張性**: 将来的な PostgreSQL への移行余地を残すため、Repository パターンを導入し、DB操作の詳細を隠蔽する。
- **マイグレーション**: 本格的な Alembic 整備は後回しとし、まずは SQLAlchemy の `create_all` 等で最小限のテーブル作成を行う。

## 3. 実装の制約と互換性
- Phase 1 の CLI フローや、構築済みの `AnalysisOrchestrator` の再利用を最優先とし、破壊的変更は避ける。
- 既存の Pydantic スキーマとの整合性を保つ。

## 4. API実装のスコープ
- **対象**:
  - FastAPI エントリーポイントの整備 (`main.py`)
  - API ルーターの追加
  - `POST /api/v1/analyze`
  - `GET /api/v1/specs`
  - `GET /api/v1/specs/{asset_id}`
  - `DELETE /api/v1/specs/{asset_id}`
- **対象外**:
  - 認証認可、Meta API連携、LLM/OCR本実装、UI実装、本格的なDBマイグレーション
