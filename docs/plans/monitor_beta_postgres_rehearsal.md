# モニターベータ PR #91 Postgres 適用リハーサル

## このドキュメントの位置づけ

[monitor_beta_post_merge_runbook.md](./monitor_beta_post_merge_runbook.md) でSQLiteに対して
実施した「post-merge runbook」のリハーサルを、**Postgres環境に対して**実施した記録です。
目的は本番作業ではなく、**本番（Postgres想定）へ適用する前に、Postgres固有の詰まりどころが
無いかを事前に洗い出すこと**です。

- 日常のアカウント運用手順そのものは [MONITOR_ACCOUNT_MANAGEMENT.md](../MONITOR_ACCOUNT_MANAGEMENT.md)
  を参照してください。本ドキュメントは「その手順がPostgresでも同じように通るか」の検証記録です。
- 本番適用の全体フロー（Phase 1〜4）は [monitor_beta_post_merge_runbook.md](./monitor_beta_post_merge_runbook.md)
  を参照してください。本ドキュメントの内容はそのPhase 2（本番適用前チェック）を
  Postgres観点で補強するものです。

## 検証環境

本番・開発中のPostgres（`.env`が指す既存の接続先）には**一切接続していません**。
理由: 接続を試みたところ資格情報が一致せず認証エラーになり、それ以上の追跡は
「既存の開発用DBに触れる」リスクを伴うため中断し、代わりに以下の方式に切り替えました。

- ローカルにインストール済みのPostgreSQL 16のバイナリ（`initdb`/`pg_ctl`/`psql`）を使い、
  **既存のPostgresサービスとは完全に別の、新規データディレクトリ・別ポート（5544）**で
  使い捨てのPostgresクラスタを一時的に起動
  （データディレクトリはリポジトリ外の一時スクラッチ領域。作業後に停止済み・
  データは残置しても実害のない使い捨て）
- 既存のPostgresサービス（ポート5432、`.env`の`DATABASE_URL`が指す方）には**起動確認以外
  一切接続していません**（接続を一度試みてパスワード不一致で失敗した時点で中断し、
  以降はこの隔離クラスタのみを使用）
- 検証用クラスタ内に新規データベース`monitor_beta_pg_rehearsal`を作成し、そこに対してのみ
  migration・CLI操作を実行
- 接続文字列・パスワードは一切docsやコミットに含めていません（作業用の一時ファイルに
  留め、リハーサル終了後もリポジトリには残していません）

## 実施した手順と結果

[monitor_beta_post_merge_runbook.md](./monitor_beta_post_merge_runbook.md)の
「リハーサル実施記録」と同じ12項目を、`DATABASE_URL`をPostgres向けに変えただけで
実行しました。

| # | 手順 | 結果 |
|---|---|---|
| 1 | `alembic upgrade head`（baseline→3リビジョン） | 成功。エラーなし |
| 2 | `seed-plans --dry-run` → `seed-plans` → `list-plans` | 成功。5プランとも正しい値で投入 |
| 3 | `seed-plans` 再実行（冪等性確認） | 成功。5件とも`updated`、重複作成なし |
| 4 | 管理用会社・最初のadmin作成 | 成功 |
| 5 | モニター1社目作成（`--limit`省略）→ plan割当 → ユーザー招待 | 成功。`list-usage`で`plan:monitor, 0/100` |
| 6 | override設定・解除 | 成功。`override, 0/150` → `plan:monitor, 0/100` |
| 7 | 0クレジット設定・解除 | 成功。`override, 0/0` → `plan:monitor, 0/100` |
| 8 | 実際の認証情報でのログイン→`/me`→ログアウト→トークン失効 | 成功。SQLite版と同じ挙動・同じレスポンス形状 |
| 9 | 誤パスワード・存在しないメールアドレスでの401確認 | 成功（タイミング差対策の経路も通過） |
| 10 | 0クレジット時の`usage.limit_reached=true`確認 | 成功 |
| 11 | `alembic downgrade base` → `alembic upgrade head` | 成功。エラーなし |
| 12 | ダウングレード時の`monthly_credit_limit`のNULL埋め戻し（`b7e2f4a1c3d5`のdowngrade） | 成功（他社データが無い状態での確認のため、実データでの再検証は本番適用前に推奨） |

**日本語文字列（会社名・プラン名・マーケティング文言）もPostgres上で正しくUTF-8のまま
保存・取得できることを確認済みです**（`initdb -E UTF8`で作成したクラスタ。表示上一部
文字化けして見えた箇所がありましたが、いずれもWindowsコンソール側の表示問題であり、
FastAPI経由でJSONとして取得した値は正しいことを別途確認済みです）。

## SQLiteとの差分

**結論: 今回確認した範囲では、SQLiteとPostgresでスキーマ適用結果・アプリケーションの
挙動に機能的な差分は見つかりませんでした。** `batch_alter_table`を使っている3箇所
（カラム追加、nullable化、カラムrename）はいずれもSQLite向けの機構ですが、Postgresでは
Alembicが自動的に通常の`ALTER TABLE`として実行するため、素通りしています。

一点、**SQLite・Postgres共通の（Postgres固有ではない）軽微な冗長性**を見つけました。

- `monitor_sessions.token_hash`と`monitor_companies.slug`は、それぞれ
  「`sa.UniqueConstraint(...)`によるテーブル制約」と「`op.create_index(..., unique=True)`
  による明示的なユニークインデックス」の**2つの一意性制約が同じ列に重複して存在**します
  （`f3a1c9d2e8b0`のテーブル作成時から）。
  - Postgresでは`monitor_sessions_token_key`（制約由来）と`ix_monitor_sessions_token_hash`
    （インデックス由来）という2つの名前を持つオブジェクトとして確認できます。
  - SQLiteでも同様に、`sqlite_autoindex_monitor_companies_N`（制約由来、無名）と
    `ix_monitor_companies_slug`（インデックス由来、命名済み）の2つが存在することを確認しました。
  - **機能的には無害です**（書き込み時のインデックス更新が僅かに二重になるだけで、
    データ不整合やクエリ結果への影響はありません）。PR #91のスコープ外の既存設計であり、
    今回のPostgresリハーサルで新たに問題化したものではないため、本タスクでは修正して
    いません。将来的なスキーマクリーンアップの候補として記録するに留めます。

## Postgres特有の注意点（本番適用前に確認・意識すべきこと）

- **`psycopg2-binary`は`backend/requirements.txt`に既存で含まれています**
  （`psycopg2-binary==2.9.9`）。Postgresへの接続に追加の依存パッケージインストールは
  不要です（今回のリハーサルで新規に追加した依存はありません）。
- **`DATABASE_URL`の書式**: `postgresql://<user>:<password>@<host>:<port>/<dbname>`。
  `app/db/session.py`の`build_connect_args()`は非SQLiteの場合`connect_args={}`を返す
  ため、SSL等の追加オプションが必要な場合は`DATABASE_URL`のクエリ文字列
  （例: `?sslmode=require`）で指定する想定です（本番のGCP VM上でPostgresへどう接続する
  予定か次第。今回はローカル接続のみ検証しており、SSL接続自体は未検証です）。
- **`lc_messages`（サーバーメッセージの言語）**: 検証中、日本語ロケールのPostgresエラー
  メッセージがWindows側のツール（psycopg2の一部エラーパス）でUTF-8前提のデコードに
  失敗し例外になる事象に遭遇しました（`UnicodeDecodeError`）。これは接続自体の失敗では
  なく、**エラーメッセージの表示層でのみ**発生する問題で、実際のクエリ実行やデータの
  正しさには影響しません。本番のLinux環境（本番はGCP VM上のDebian Linux想定、
  CLAUDE.md参照）ではロケール設定が異なるため再現しない可能性が高いですが、Windows上の
  開発機でPostgresのエラー内容を直接確認したい場合は、`psql`（Postgresネイティブ
  クライアント）を使うか、接続時に`PGOPTIONS="-c lc_messages=C"`を設定することを推奨します。
- **文字コード**: クラスタ自体を`UTF8`エンコーディングで作成する必要があります
  （`initdb -E UTF8`。今回のローカル既存Postgresサービスのエンコーディングは未確認のため、
  本番適用前に本番Postgres側のエンコーディングが`UTF8`であることを確認してください）。
- **DB作成権限**: 今回はクラスタの初期スーパーユーザーで`CREATE DATABASE`しました。
  本番適用時に使う接続ユーザーがデータベース作成権限を持っているか（あるいは、
  DBは事前に別途作成済みで、アプリ用ユーザーはそのDB内でのテーブル作成・DML権限のみ
  持てば足りるのか）は、本番のPostgres運用ポリシー次第のため、**要確認事項**として
  残します。
- **CLI実行時の`PYTHONPATH`/インタプリタ依存はPostgresでもSQLiteと同じ**です
  （Postgres固有の追加事項なし。[monitor_beta_post_merge_runbook.md](./monitor_beta_post_merge_runbook.md)
  記載の注意点がそのまま当てはまります）。

## 本番適用前チェック項目（Postgres観点の追加分）

[monitor_beta_post_merge_runbook.md](./monitor_beta_post_merge_runbook.md)の
「Phase 2: 本番適用前チェック」に対して、Postgres固有の観点として以下を追加してください。

- [ ] 本番Postgresの実体・接続方式を確認する（同一VM内のUnixソケット接続か、
  ネットワーク越しのTCP接続か。CLAUDE.mdの直アクセス経路に関する既知の注意と同様、
  接続経路自体のセキュリティも別途確認する）
- [ ] 本番Postgresのエンコーディングが`UTF8`であることを確認する
  （`SHOW server_encoding;`または`psql -l`で確認）
- [ ] マイグレーション・seedを実行する接続ユーザーの権限を確認する
  （テーブル作成・ALTER・INDEX作成権限が必要。DB作成権限が必要かは運用方針次第）
- [ ] SSL接続が必要な運用か確認する（必要な場合、`DATABASE_URL`にオプションを追加する
  想定だが、今回は未検証）
- [ ] 本番Postgresの既存データ（`ad_insights`テーブル等）の件数・内容を確認する
  （[monitor_beta_post_merge_runbook.md](./monitor_beta_post_merge_runbook.md)の
  「既存データ確認」と同じ観点。Postgres固有の追加リスクは今回の検証では見つかっていません）
- [ ] バックアップ手段が`pg_dump`等、Postgres向けの方式で確立していることを確認する
  （SQLiteのファイルコピー方式とは異なる。`docs/POSTGRES_MIGRATION.md`に既存の
  記載があれば参照する）

## 未実施事項（本タスクの範囲外・今後の課題）

- **本番相当のネットワーク経由（TCP、SSL）でのPostgres接続検証**: 今回はローカルホスト内の
  接続のみで検証しました。本番相当（別ホスト・SSL必須）の接続経路は未検証です。
- **実データ量でのダウングレード検証**: `monthly_credit_limit`のNULL埋め戻し
  （`b7e2f4a1c3d5`のdowngrade）は、今回複数社のテストデータがある状態で成功を確認しましたが、
  本番規模のデータ量・同時実行環境での検証ではありません。
- **本番Postgresサーバーの実際の設定（照合順序、タイムゾーン設定等）との整合性**:
  今回作成した検証用クラスタは`--locale=C`で初期化しており、本番Postgresの実際の
  ロケール設定とは異なる可能性があります。文字列比較・ソート順に依存するロジックが
  今回のスコープには無いため実害は無いと考えていますが、本番導入前に本番側の設定を
  確認することを推奨します。
- **既存のローカルPostgresサービス（`.env`が指す接続先）そのものの認証情報不整合**:
  今回、既存の開発用Postgresサービスへの接続を試みたところパスワード認証に失敗しました。
  これは本タスクの対象外（本タスクは隔離環境での検証が目的）のため深追いしていませんが、
  もし今後この既存サービスをローカル開発で使う予定があるなら、`.env`の資格情報が
  現在のサービス設定と一致しているか別途確認が必要です。
