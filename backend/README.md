# Backend - Ad-Insight-Spec

FastAPI ベースのバックエンドアプリケーション

## 技術スタック

- **Framework**: FastAPI
- **Database**: PostgreSQL + SQLAlchemy
- **Language**: Python 3.9+
- **Testing**: pytest

## ディレクトリ構成

- \pp/api/\ - APIエンドポイント定義（TODO）
- \pp/core/\ - 設定・定数
- \pp/models/\ - SQLAlchemy ORM モデル（TODO）
- \pp/schemas/\ - Pydantic リクエスト/レスポンススキーマ
- \pp/services/\ - ビジネスロジック（TODO）
- \pp/repositories/\ - データアクセス層（TODO）
- \pp/db/\ - DB接続・セッション管理
- \	ests/\ - テストコード（TODO）

## セットアップ

\\\ash
python -m venv venv
source venv/bin/activate  # Windows: venv\\Scripts\\Activate.ps1
pip install -r requirements.txt
\\\

## 実装予定

- [ ] FastAPI アプリケーション初期化
- [ ] PostgreSQL 接続実装
- [ ] SQLAlchemy モデル定義
- [ ] Alembic マイグレーション設定
- [ ] API エンドポイント実装
- [ ] ビジネスロジック実装
- [ ] 認証・認可実装
- [ ] Meta Ads API 連携
