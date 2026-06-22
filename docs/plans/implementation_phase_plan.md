# 実装フェーズ計画 - Ad-Insight-Spec

## 概要

本プロジェクトは4つのフェーズに分けて段階的に実装される。各フェーズの成果物と優先度は以下の通り。

---

## Phase 0: スキーマ・アーキテクチャ設計（基盤整備）

**目的**: 新JSONスキーマの確定とモジュール選定、開発基盤の構築

**期間**: 1-2週間

**成果物**:
- ✅ リポジトリ初期セットアップ（本スクリプトで完了）
- ✅ JSON スキーマドラフト（\docs/specs/ad_insight_json_schema_draft.md\）
- ✅ システムアーキテクチャ図（\docs/architecture/system_overview.md\）
- ✅ Python Pydantic モデル定義（backend/app/schemas）
- ⏳ PostgreSQL テーブル設計（backend/app/models）
- ⏳ GitHub Actions CI/CD 基本設定

**主要タスク**:
1. JSON スキーマの確定（ステークホルダーレビュー）
2. PostgreSQL テーブル DDL 作成
3. Pydantic リクエスト/レスポンススキーマ定義
4. FastAPI と Vue.js の環境構築スクリプト作成
5. Docker Compose の最小化（postgres + backend + frontend）

**優先度**: 🔴 最高

**チェックリスト**:
- [ ] JSON スキーマが全ステークホルダーで合意
- [ ] PostgreSQL DDL が作成・レビュー完了
- [ ] Pydantic モデルが実装可能な状態
- [ ] ローカル開発環境が docker-compose で起動可能

---

## Phase 1: Meta広告 + LP 単体分析コアの実装

**目的**: 1つのMeta広告とLPのデータを入力し、JSONを出力するバッチ処理の構築

**期間**: 2-3週間

**成果物**:
- ✅ ダミーデータジェネレータ（\sample_data/\ に複数シナリオ）
- ⏳ Meta Ads API クライアント実装
- ⏳ クリエイティブ要素分解 (Converter層)
  - Hook / Body / CTA の抽出
  - LLM プロンプト実装
- ⏳ LP スクレイピング & マッチング処理
- ⏳ JSON 出力機能
- ⏳ PostgreSQL への永続化（Repository パターン）
- ⏳ pytest によるユニットテスト一式

**主要実装ファイル**:
Copy
backend/ ├── app/ │ ├── api/ │ │ └── ads.py # 仮実装：/api/v1/ads エンドポイント │ ├── core/ │ │ └── config.py # LLM API Key、DB URL 設定 │ ├── models/ │ │ ├── ad.py # Ad ORM モデル │ │ └── ad_insight.py # AdInsight ORM モデル │ ├── schemas/ │ │ └── ad_insight.py # Pydantic: AdInsightSchema │ ├── services/ │ │ ├── meta_service.py # Meta API クライアント │ │ ├── converter_service.py # Converter層（要素抽出） │ │ ├── lp_service.py # LP スクレイピング │ │ └── llm_service.py # LLM プロンプト実行 │ ├── repositories/ │ │ └── ad_repository.py # Ad / AdInsight CRUD │ └── db/ │ ├── init.py │ ├── session.py # DB セッション管理 │ └── base.py # SQLAlchemy Base ├── tests/ │ ├── test_converter_service.py │ └── test_ad_repository.py └── requirements.txt # 依存ライブラリ（最小化）

Copy
**主要タスク**:
1. FastAPI 基本アプリケーション初期化（uvicorn サーバー）
2. PostgreSQL へのローカル接続確認
3. Meta Ads API 認証・クライアント実装
4. クリエイティブ要素分解ロジック（LLM プロンプト + 処理）
5. LP スクレイピング（Beautiful Soup / Selenium）
6. メッセージマッチスコア計算アルゴリズム
7. JSON シリアライズ & 永続化
8. エラーハンドリング・ロギング

**外部依存**:
- Meta Graph API クレデンシャル
- Gemini / OpenAI API クレデンシャル

**優先度**: 🔴 高

**チェックリスト**:
- [ ] Meta Ads API から1件のサンプル広告データを取得可能
- [ ] クリエイティブ要素分解（Hook/Body/CTA）の精度 > 80%
- [ ] LP スクレイピングが安定して動作
- [ ] JSON 生成・永続化のエンドツーエンドテストがGREEN
- [ ] ユニットテストカバレッジ > 70%

---

## Phase 2: UI/レポート基盤の移植と連携

**目的**: Phase 1のJSONを読み込み、可視化するダッシュボードと静的レポートの構築

**期間**: 2-3週間

**成果物**:
- ⏳ Streamlit ダッシュボード（VIS資産の移植）
  - 全体パフォーマンス タブ
  - クリエイティブ分析 タブ
  - LP一貫性診断 タブ
  - AI改善提案 タブ
- ⏳ HTML エグゼクティブサマリー レポート生成器
- ⏳ Vue.js フロントエンド基本実装
  - ページレイアウト
  - API クライアント実装
  - Pinia ストア基本設計
- ⏳ FastAPI ← → Vue.js の通信確認

**主要実装ファイル**:
streamlit_app/ ├── app.py # Streamlit メインアプリケーション ├── pages/ │ ├── performance.py # 全体パフォーマンス │ ├── creative_analysis.py # クリエイティブ分析 │ ├── lp_consistency.py # LP一貫性診断 │ └── ai_recommendations.py # AI改善提案 ├── components/ │ ├── charts.py # グラフコンポーネント │ └── cards.py # サマリーカード └── utils/ ├── data_loader.py # JSON ローダー └── styling.py # Streamlit スタイリング

backend/ ├── app/ │ └── api/ │ ├── ads.py # GET /api/v1/ads (JSON 取得) │ └── reports.py # POST /api/v1/reports/html (レポート生成)

frontend/ ├── src/ │ ├── components/ │ │ ├── PerformanceCard.vue │ │ ├── CreativeBreakdown.vue │ │ └── LPConsistencyChart.vue │ ├── views/ │ │ ├── DashboardView.vue │ │ └── DetailView.vue │ ├── stores/ │ │ ├── adStore.js # Pinia store: 広告データ │ │ └── filterStore.js # Pinia store: フィルタ状態 │ ├── services/ │ │ └── apiClient.js # Axios ラッパー │ └── App.vue ├── package.json └── vite.config.js

Copy
**主要タスク**:
1. Streamlit ページテンプレート作成
2. VIS の report_generator.py をWeb広告向けに改修
3. HTMLレポートテンプレート（CSS inline）設計
4. Vue.js 環境構築（Vite）
5. Pinia ストア設計（ad データ、フィルタ状態）
6. API クライアント実装
7. チャートライブラリ統合（Chart.js / ECharts）

**優先度**: 🟠 中

**チェックリスト**:
- [ ] Streamlit が localhost:8501 で起動可能
- [ ] 4つのタブすべてが基本機能を提供
- [ ] HTMLレポートが1枚ペラで出力可能
- [ ] Vue.js が localhost:5173 で起動可能
- [ ] FastAPI ← → Vue.js 間の通信が正常

---

## Phase 3: クロスプラットフォーム化準備（将来構想）

**目的**: Google広告等の別媒体データを同スキーマにマッピングする検証

**期間**: 3-4週間（今後）

**成果物**:
- ⏳ Google Ads API クライアント実装
- ⏳ TikTok Ads API クライアント実装（オプション）
- ⏳ 媒体抽象化レイヤー (Platform Adapter パターン)
- ⏳ 複数媒体による比較UI
- ⏳ ドキュメント更新（マルチプラットフォーム対応）

**主要タスク**:
1. Google Ads API 認証・クライアント実装
2. Google Ads データ → ad_insight_spec マッピング
3. Platform Adapter インターフェース設計
4. 共通KPI ダッシュボード（複数媒体比較）
5. E2E テスト（Meta + Google 両媒体）

**優先度**: 🟢 低（将来）

**チェックリスト**:
- [ ] Google Ads データが同じJSONスキーマに正規化可能
- [ ] Platform Adapter が拡張可能な設計
- [ ] 複数媒体のダッシュボード表示がリアルタイム対応

---

## 全体タイムライン

| フェーズ | 期間 | 人員 | 成果 |
|---------|------|------|------|
| 0 | 1-2週 | 1-2名 | スキーマ確定、開発基盤 |
| 1 | 2-3週 | 2-3名 | バッチ処理コア完成 |
| 2 | 2-3週 | 2-3名 | UI / レポート完成 |
| 3 | 3-4週 | 1-2名 | マルチプラットフォーム検証 |
| **合計** | **8-12週** | **平均2名** | **完全なMVP** |

---

## リスク・外部依存

### リスク

| リスク | 影響度 | 対策 |
|-------|--------|------|
| Meta API 変更 | 🔴 高 | API ドキュメント定期確認、サンドボックス環境での検証 |
| LLM API コスト増加 | 🟠 中 | キャッシング機構、バッチ処理最適化 |
| LP スクレイピング失敗率 | 🟠 中 | フォールバック処理、手動入力対応 |
| PostgreSQL パフォーマンス | 🟡 低 | インデックス設計、クエリ最適化 |

### 外部依存

- Meta Graph API クレデンシャル（Phase 1）
- Gemini / OpenAI API クレデンシャル（Phase 1）
- PostgreSQL 15+ のローカル/クラウドインスタンス
- Google Ads API クレデンシャル（Phase 3）
