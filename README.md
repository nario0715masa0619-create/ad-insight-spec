# Ad-Insight-Spec

Web広告（Meta）とランディングページの統合分析・レポートサービス

## 📋 プロジェクト概要

本プロジェクトは、既存の YouTube 動画分析システム「video-insight-spec」のアーキテクチャを流用し、Web広告領域へ拡張するものです。

**現在の状態**: リポジトリ scaffold のみ（フル実装は TODO）

## 🛠 採用技術スタック

- **Backend**: FastAPI + PostgreSQL + SQLAlchemy
- **Frontend**: Vue.js + Pinia
- **Infrastructure**: Docker + docker-compose
- **Documentation**: Markdown

## 📂 ディレクトリ構成

\\\
ad-insight-spec/
├── backend/                      # FastAPI アプリケーション
│   ├── app/
│   │   ├── api/                 # エンドポイント定義（TODO）
│   │   ├── core/                # 設定・定数
│   │   ├── models/              # SQLAlchemy モデル（TODO）
│   │   ├── schemas/             # Pydantic スキーマ
│   │   ├── services/            # ビジネスロジック（TODO）
│   │   ├── repositories/        # DB アクセス層（TODO）
│   │   └── db/                  # DB 接続・セッション管理
│   └── tests/                   # テストコード（TODO）
├── frontend/                     # Vue.js + Pinia フロントエンド
│   ├── src/
│   │   ├── components/          # UI コンポーネント（TODO）
│   │   ├── views/               # ページコンポーネント（TODO）
│   │   ├── stores/              # Pinia ストア（TODO）
│   │   ├── router/              # Vue Router 設定（TODO）
│   │   └── services/            # API クライアント（TODO）
│   └── public/                  # 静的ファイル
├── docs/                        # 設計・実装ドキュメント
│   ├── architecture/            # システムアーキテクチャ
│   ├── specs/                   # 仕様書・JSON スキーマ
│   ├── product/                 # プロダクト定義書
│   ├── plans/                   # 実装計画・チェックリスト
│   └── decisions/               # アーキテクチャ決定記録（ADR）
├── infra/                       # インフラストラクチャ
│   ├── docker/                  # Dockerfile・docker-compose
│   └── sql/                     # DDL・マイグレーション定義
├── scripts/                     # ユーティリティスクリプト
├── sample_data/                 # テスト用サンプルデータ
├── .github/workflows/           # GitHub Actions
├── .env.example                 # 環境変数テンプレート
├── .gitignore
├── .editorconfig
├── docker-compose.yml
└── README.md
\\\

## 📅 実装フェーズ概要

- **Phase 0**: スキーマ・アーキテクチャ設計（現在地）
- **Phase 1**: Meta広告 + LP 単体分析コアの実装
- **Phase 2**: UI/レポート基盤の移植と連携
- **Phase 3**: クロスプラットフォーム化準備（Google/TikTok等）

詳細は \docs/plans/implementation_phase_plan.md\ を参照してください。

## 🔗 参考資産

本プロジェクトは \ideo-insight-spec\ の設計思想を参考にしています。
- 設計思想・レポート構成の流用
- AI言語化パイプラインの転用
- YouTube依存コードは破棄・新規実装

## 📝 主要ドキュメント

| ドキュメント | 用途 |
|-----------|------|
| \docs/product/project_overview.md\ | プロダクト定義・背景・スコープ |
| \docs/specs/ad_insight_json_schema_draft.md\ | JSON スキーマ仕様書 |
| \docs/architecture/system_overview.md\ | システムアーキテクチャ全体図 |
| \docs/plans/implementation_phase_plan.md\ | フェーズごとの実装計画 |
| \docs/decisions/ADR-0001-project-structure.md\ | アーキテクチャ決定記録 |

## 🚀 クイックスタート

\\\ash
# バックエンド環境構築
cd backend
pip install -r requirements.txt
# TODO: FastAPI アプリケーション実装

# フロントエンド環境構築
cd ../frontend
npm install
npm run dev
# TODO: Vue.js アプリケーション実装
\\\

## 🔧 環境変数の設定

実際の \.env\ ファイルは以下に配置してください：

\\\
C:\Users\nario\.ad-insight-spec\.env
\\\

本リポジトリの \.env.example\ をテンプレートとして、必要に応じて修正してください。

## 📋 セットアップチェックリスト

完了状況は \docs/plans/repository_bootstrap_checklist.md\ を参照してください。

## ✨ 次に決めるべき論点

1. 評価KPIの優先順位（CPA vs ROAS）
2. LLM による診断の粒度
3. 広告とLP の結合ルール
4. データ取得の自動化範囲
5. 媒体抽象化のレベル
6. 初期PoC のキラー機能

詳細は \docs/product/project_overview.md\ の「次に決めるべき論点」セクションを参照。

---

**Status**: 🔨 Scaffolding Phase
