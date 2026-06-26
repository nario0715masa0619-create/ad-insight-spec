# PostgreSQL マイグレーションガイド

Ad-Insight-Spec において、本番環境で SQLite から PostgreSQL へ移行する手順を説明します。

## 0. 前提条件
- 本番 PostgreSQL サーバが稼働中であること
- データベースとユーザーが作成済みであること
- バックアップツール（`pg_dump` 等）が利用可能であること

## 1. バックアップ
まずは既存の SQLite データベースのバックアップを取得します。
```bash
# SQLite のバックアップ
cp ad_insight.db ad_insight.db.backup.$(date +%Y%m%d_%H%M%S)
```

## 2. PostgreSQL 接続先変更
アプリケーションが PostgreSQL に接続するよう、環境変数を変更します。
```bash
# .env の DATABASE_URL を更新
DATABASE_URL="postgresql://user:password@localhost:5432/ad_insight"
```

## 3. Alembic による初期化（または SQL 直実行）
PostgreSQL に必要なテーブルを作成します。
```bash
# テーブル初期化スクリプトを実行
psql -U user -d ad_insight -f scripts/init_postgres.sql
```
※ 将来的に Alembic が導入された場合は `alembic upgrade head` を実行します。

## 4. SQLite → PostgreSQL データ移行（オプション）
既存のデータを引き継ぐ場合は、スクリプト等を用いて移行します。
SQLite 側のデータを JSON 形式でエクスポートし、PostgreSQL 側にインポートすることを推奨します。
```python
# 例: 移行スクリプトを実行
# python scripts/migrate_sqlite_to_pg.py --source ad_insight.db --dest postgresql://...
```

## 5. 接続確認・動作テスト
移行が完了したら、FastAPI バックエンドを起動してヘルスチェックを行います。
```bash
# 本番環境で FastAPI を起動してヘルスチェック
curl http://localhost:8000/health
```
