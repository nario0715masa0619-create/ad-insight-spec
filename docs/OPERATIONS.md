# 運用・オペレーションガイド

本ドキュメントでは、Ad-Insight-Spec の開発環境と本番環境におけるセットアップ、運用手順、およびトラブルシューティングについて解説します。

---

## 1. 開発環境前提

### 推奨スペック
- **OS**: Windows, macOS, Linux いずれでも動作可能
- **CPU**: 最低 2 コア
- **メモリ**: 8GB 以上推奨（動画処理を行う場合はより多くのメモリが必要です）

### インストール手順

1. **Python 環境の構築**
   ```bash
   git clone https://github.com/nario0715masa0619-create/ad-insight-spec.git
   cd ad-insight-spec/backend
   python -m venv venv
   source venv/bin/activate  # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **外部依存ツールのインストール**
   - **Tesseract-OCR**: 
     - Windows: インストーラーをダウンロードし、環境変数 `TESSERACT_PATH` にパスを設定してください。
     - macOS: `brew install tesseract`
     - Linux: `sudo apt-get install tesseract-ocr`
   - **FFmpeg** (動画フレーム抽出用):
     - OS パッケージマネージャ経由でインストールし、システムパスが通っていることを確認してください。

### 開発用 .env 設定
`backend/.env` を作成し、以下を設定します。
```env
OPENAI_API_KEY=your_openai_api_key_here
GEMINI_API_KEY=your_gemini_api_key_here
LLM_MODEL=gpt
# TESSERACT_PATH=C:\Program Files\Tesseract-OCR\tesseract.exe  # Windows の場合のみ
```

### 開発起動手順
- **バックエンド**
  ```bash
  cd backend
  uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
  ```
- **フロントエンド**
  ```bash
  streamlit run frontend/streamlit_app.py
  ```

### 開発テスト実行
```bash
cd backend
python -m pytest tests/ -v
# または E2E テスト
python ../scripts/e2e_test_phase2c2.py
```

### 開発環境での注意点
- `uvicorn --reload` を使用すると、コード変更時に自動的にサーバーが再起動します。
- SQLite DB (`ad_insight.db`) はローカルにファイルとして生成されます。

---

## 2. 本番環境前提

### 推奨スペック
- **OS**: Linux (Ubuntu 22.04 LTS 等) 推奨
- **CPU**: 4 コア以上
- **メモリ**: 16GB 以上（同時リクエスト数や動画処理頻度に依存）

### 本番環境チェックリスト（2.1～2.10）

1. **インフラストラクチャ**: リバースプロキシでの SSL/TLS 通信の適用、不要なポートのファイアウォール遮断。
2. **ツール・依存関係**: Tesseract, FFmpeg をシステムパッケージとして本番サーバーにインストール。
3. **データベース**: 本番稼働時は SQLite ではなく **PostgreSQL** への移行と定期バックアップ戦略の導入を推奨。
4. **API キー・シークレット管理**: `.env` での直接管理は避け、AWS Secrets Manager 等の機密情報管理サービスを推奨。
5. **アプリケーション設定**: デバッグモード無効化 (`DEBUG=False`)、ログレベルの適切な設定 (`LOG_LEVEL=INFO`)。
6. **ロギング・監視**: アプリケーションログの CloudWatch または ELK スタックへの転送とモニタリング。
7. **デプロイ・起動**: Gunicorn 等の WSGI/ASGI サーバーを使用し、Nginx などを前段に置く。Systemd 等での自動再起動設定。
8. **セキュリティ**: CORS の適切な制限設定、API レート制限の設定。
9. **バックアップ・災害対応**: DB 定期バックアップおよびスナップショットの取得。
10. **パフォーマンス**: タイムアウト設定、非同期タスクキュー（Celery 等）の導入、コネクションプーリングの設定。

### 本番環境用 .env 例
```env
ENVIRONMENT=production
DEBUG=False
LOG_LEVEL=INFO
DATABASE_URL=postgresql://user:password@host/dbname
OPENAI_API_KEY=...
LLM_MODEL=gpt
```

### 本番環境起動
Gunicorn + Uvicorn 構成での起動例:
```bash
gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

---

## 3. 共通：テスト実行
本番デプロイ前には必ず以下のテストを実行し、すべて通過することを確認してください。
- ユニットテスト: `pytest tests/`
- E2E テスト: 定義されたシナリオスクリプトを実行し、システムの結合状態を確認。

---

## 4. 共通：トラブルシューティング

- **Q: LLM からのレスポンスがエラーになる**
  - A: API キーが正しく設定されているか、または API の利用限度額に達していないか確認してください。
- **Q: OCR のテキスト抽出が空になる**
  - A: Tesseract のインストールパスが間違っていないか、また言語データ (eng+jpn) がインストールされているか確認してください。Fail-Soft によりシステムは停止しません。
- **Q: DB ロックエラーが発生する (SQLite)**
  - A: 並行アクセスにより SQLite がロックされることがあります。本番環境では PostgreSQL への移行を検討してください。

---

## 5. 共通：ログ出力設定
標準の Python `logging` を使用し、処理のステップごとに情報を出力しています。
本番では `logger.error` を中心に監視アラートを設定することを推奨します。

---

## 6. 本番環境への移行チェックリスト
- [ ] Tesseract, FFmpeg パッケージのインストール
- [ ] リバースプロキシ / SSL 化の完了
- [ ] シークレット情報のセキュアな配置
- [ ] PostgreSQL へのデータ移行（今後の拡張）
- [ ] 自動起動（systemd）と Gunicorn サーバー設定の完了
