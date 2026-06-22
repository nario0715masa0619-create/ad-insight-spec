# ADR-0001: FastAPI + Vue.js 分離構成の採用

**Status**: ACCEPTED  
**Date**: 2026-06-22  
**Authors**: Architecture Team

## Context（文脈）

Ad-Insight-Spec は、既存の video-insight-spec（VIS）の設計思想を活用しながら、Web広告分析サービスとして新規に構築される。フロントエンドの実装パターンについて、以下の選択肢が検討された：

### 選択肢

1. **Streamlit のみ** (VIS 同様)
   - ✅ 迅速なプロトタイピング
   - ❌ UI カスタマイズ性が低い
   - ❌ 本番向けUIでは限界

2. **FastAPI + Vue.js 分離** (提案)
   - ✅ フロントエンド/バックエンド の責務分離
   - ✅ UI カスタマイズ性が高い
   - ✅ API を複数クライアント（Web, Mobile等）で再利用可能
   - ✅ チーム分割・並行開発が容易

3. **FastAPI + Jinja2 (Traditional Server-Rendered)**
   - ✅ シンプル
   - ❌ インタラクティブな分析UIに不向き
   - ❌ リアルタイムデータ更新が弱い

4. **React / Next.js**
   - ✅ エコシステムが豊富
   - ❌ チーム学習コスト（Vue.js より若干高）
   - ❌ バンドルサイズが大きい

## Decision（決定）

**FastAPI + Vue.js の分離構成を採用する。**

理由：
- VIS の設計思想（バックエンド/UI の責務分離）を踏襲しつつ、本番レベルのフロントエンド柔軟性を実現
- マーケター向けのダッシュボード（複数タブ、インタラクティブなフィルタリング、リアルタイムチャート）に最適
- チーム規模（初期 2-3 名）で、バックエンド/フロントエンド の並行開発が可能
- Vue.js + Pinia は学習曲線が緩く、中小チームに適している

## Consequences（影響）

### ポジティブ

✅ **責務の明確化**
- バックエンド: FastAPI REST API、ビジネスロジック、データベース
- フロントエンド: Vue.js UI、ユーザーインタラクション、状態管理

✅ **開発効率の向上**
- フロント/バック の開発を並行実施可能
- API仕様を先に決定し、Mock API で両者が独立開発可能

✅ **再利用性**
- REST API を複数クライアント（Web、Mobile App、外部パートナー）で利用可能
- Streamlit ダッシュボードも同じAPI を消費

✅ **テスト戦略の向上**
- ユニットテスト (pytest)、E2E テスト (Cypress/Playwright) の分離
- API テスト、UI テスト の独立実行

### ネガティブ

❌ **デプロイの複雑化**
- バックエンド/フロントエンド の 2つのデプロイメント管理
- 対策: Docker + docker-compose で開発環境を一元化、GitHub Actions で自動デプロイ

❌ **初期開発コスト**
- Streamlit のみと比較すると、セットアップに時間がかかる
- 対策: Phase 0 で開発基盤を整備し、Phase 1 以降の効率を確保

❌ **CORS / セキュリティ設定**
- フロント/バック の同一オリジン問題、認証トークン管理が必要
- 対策: FastAPI の CORS ミドルウェア設定、JWT トークン導入

## Implementation（実装方針）

### ディレクトリ構造

ad-insight-spec/ ├── backend/ # FastAPI + PostgreSQL │ ├── app/ │ │ ├── api/ # エンドポイント │ │ ├── models/ # ORM │ │ ├── schemas/ # Pydantic スキーマ │ │ ├── services/ # ビジネスロジック │ │ └── db/ # DB接続 │ ├── tests/ # pytest │ └── requirements.txt ├── frontend/ # Vue.js 3 + Pinia │ ├── src/ │ │ ├── components/ # UI コンポーネント │ │ ├── views/ # ページビュー │ │ ├── stores/ # Pinia ストア │ │ ├── services/ # API クライアント │ │ └── router/ # Vue Router │ ├── package.json │ └── vite.config.js ├── docker-compose.yml # 開発環境構築 └── docs/

Copy
### 開発ワークフロー

**Phase 0: API仕様決定**
\\\
1. JSON スキーマ確定
2. FastAPI エンドポイント仕様書 作成
3. Mock API (JSON レスポンス) を提供
\\\

**Phase 1: バックエンド実装**
\\\
1. FastAPI ルーター実装
2. ビジネスロジック (Converter, LLM連携) 実装
3. pytest でテスト
\\\

**Phase 2: フロントエンド実装**
\\\
1. Vue.js 環境構築
2. UI コンポーネント実装
3. Pinia ストア実装
4. API クライアント実装
5. E2E テスト
\\\

**開発環境起動**
\\\ash
docker-compose up
# バックエンド: http://localhost:8000
# フロントエンド: http://localhost:5173
# PostgreSQL: localhost:5432
\\\

### API設計原則

- **REST 標準に準拠**: GET/POST/PUT/DELETE の明確な使い分け
- **バージョニング**: /api/v1/ プリフィックス
- **エラーレスポンス**: 標準化されたエラーフォーマット
- **ペイジング**: Large データセットはオフセット/リミット対応
- **ドキュメント**: OpenAPI (Swagger) 自動生成

### フロントエンド設計原則

- **コンポーネント志向**: UI を小さな再利用可能な単位に分割
- **Pinia ストア**: 複数コンポーネント間での状態共有
- **Vue Router**: ページ遷移管理
- **Composition API**: ロジック再利用性向上

## Alternatives Rejected（検討したがやめた選択肢）

### ❌ Streamlit のみ継続
**理由**: 本番レベルのUIカスタマイズができず、マーケター向けのプロフェッショナルなダッシュボードに限界がある。ただし、初期 PoC には Streamlit を併用してもよい。

### ❌ Next.js (React フレームワーク)
**理由**: 学習曲線が Vue.js より急で、小規模チームの効率が落ちる。ただし、将来的に大規模なSPA 化が必要な場合は再検討の余地あり。

## References（参考資料）

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Vue.js 3 Documentation](https://vuejs.org/)
- [Pinia Documentation](https://pinia.vuejs.org/)
- VIS アーキテクチャドキュメント（参考資産）
