# API エンドポイント仕様書（確定版）

## 1. 理想仕様

### 1.1 エンドポイント一覧
- POST /api/v1/specs/analyze
- GET /api/v1/specs
- GET /api/v1/specs/{asset_id}
- DELETE /api/v1/specs/{asset_id}

### 1.2 論理削除ルール
- 削除済みレコード（is_deleted=True）は一覧・単件取得から除外される
- 削除済みレコードへのアクセスは 404 を返す

### 1.3 Version 管理ルール
- version は「同一 asset_id に対する再分析時のみ加算される」
- 前提: 同一ファイル → 同一 asset_id が生成される

### 1.4 ページング仕様
- パラメータ: skip (デフォルト 0), limit (デフォルト 10, 最大 100)
- レスポンス形式:
  ```json
  {
    "items": [...],
    "total": N,
    "skip": 0,
    "limit": 10
  }
  ```

### 1.5 詳細エンドポイント仕様
- **POST /api/v1/specs/analyze**
  - 入力: multipart/form-data (input_file, lp_file?, kpi_file?, mode?)
  - 出力: ad_insight_spec v0.2 JSON
  - 処理: ファイル保存 → Orchestrator 実行 → Pydantic 検証 → DB 保存
  - エラー: 400 (形式エラー), 500 (分析エラー)
- **GET /api/v1/specs**
  - クエリ: skip, limit, asset_id (filter), format (filter)
  - 出力: { items, total, skip, limit }
  - エラー: 500 (DB エラー)
- **GET /api/v1/specs/{asset_id}**
  - オプション: version (未指定で最新版)
  - 出力: ad_insight_spec v0.2 JSON
  - エラー: 404 (レコードなし), 500 (DB エラー)
- **DELETE /api/v1/specs/{asset_id}**
  - 処理: 論理削除（is_deleted=True, deleted_at 設定）
  - 出力: { message: "Deleted N record(s) successfully" }
  - エラー: 404 (レコードなし), 500 (DB エラー)

## 2. 現行実装確認結果

### 2.1 asset_id 生成方式
- **確認項目**: asset_id は UUID ベースか、ハッシュベースか。
- **確認結果**: UUIDベース（ランダム生成）である。`MetadataService._generate_asset_id` 内で現在時刻と `uuid.uuid4()` を組み合わせて生成しているため、同一ファイルを再分析しても常に異なる asset_id が生成される。

### 2.2 version +1 ロジックの実装状態
- **確認項目**: Repository.create() で既存 asset_id 検出時に version を +1 するロジックがあるか。
- **確認結果**: Repository 層の `create` メソッドには +1 する自動ロジックはないが、API ルーター層（`specs.py` の `analyze` 内）において、保存直前に `get_latest_by_asset_id` で最新バージョンを取得し `version = latest.version + 1` と計算して登録するロジックが実装されている。

### 2.3 テスト 6（削除後再分析）の成立条件
- **確認結果**: 未成立。
- **未成立理由**: asset_id が UUID ベースであり、同一ファイルを入力しても常に異なる ID が生成されるため。同一 asset_id を持つ前提での version +1 の自動発火フローを E2E テストとして成立させることはできない。

## 3. エラーコード一覧
- 200: 成功
- 400: リクエスト形式エラー
- 404: リソースなし
- 500: サーバーエラー
