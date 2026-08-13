# lp_url フェッチのredirect経由SSRF対策 follow-up整理

## この文書について

[PR #93](https://github.com/nario0715masa0619-create/ad-insight-spec/pull/93)（主入力の再定義:
Meta Ads CSV + 広告クリエイティブ + LP）で、`lp_url`パラメータに対する最低限のSSRF対策
（初期URLのホスト検証）を追加しました。その再レビュー中に、**redirect（HTTP 3xx）を
追従した先のホストは再検証していない**という残論点が新たに見つかりました。

本ドキュメントは、この残論点を実装を広げずに独立した設計論点として整理し、次の
安全化対応（fast followまたは別スプリント）へつなげるためのものです。

**関連Issue**: [#97 security: harden lp_url fetch against redirect-based SSRF](https://github.com/nario0715masa0619-create/ad-insight-spec/issues/97)

## 背景: PR #93で何を防いだか

CampaignPilotの主入力再定義の一環で、`/api/v1/specs/analyze`に`lp_url`フォーム
パラメータを追加しました。これは`LPService`（元々URL/ローカルファイルの両方に対応
していたが、API層に配線されていなかった）を、認証済みユーザーが指定した任意のURLで
呼び出せるようにするものです。

`LPService._fetch_html()`（[backend/app/services/lp_service.py:182](../../backend/app/services/lp_service.py)）は、
`requests.get(lp_input, timeout=self.timeout)`でサーバー側からURLへGETリクエストを
行います。認証済みユーザーが指定した任意のURLをサーバー側からフェッチするという構造
そのものが、本番環境（GCP、CLAUDE.md記載の静的IP `34.84.24.83`）上でのSSRF
（Server-Side Request Forgery）の攻撃面になりえます。

PR #93では、この面に対する**最低限の防御**として、`backend/app/api/routes/specs.py::
_is_unsafe_lp_host()`を追加しました。

## 現状の防御範囲（PR #93で対応済み）

`_is_unsafe_lp_host()`は、`/analyze`エンドポイントに渡された**入力URLそのもの**の
ホストを検証し、以下に該当する場合は422で拒否します。

- 明示的に禁止したホスト名（`localhost`、`metadata.google.internal`、`metadata`）
- `socket.getaddrinfo()`でホスト名を解決した結果が、以下のいずれかに該当するIPアドレス
  - loopback（127.0.0.0/8、::1）
  - link-local（169.254.0.0/16、fe80::/10 — GCPメタデータエンドポイント
    `169.254.169.254`を含む）
  - RFC1918プライベートIP（10.0.0.0/8、172.16.0.0/12、192.168.0.0/16）とIPv6の
    ユニークローカルアドレス（fc00::/7）
  - reserved / multicast / unspecified

これは**「ユーザーが直接指定したURLの検証」**であり、`LPService`が実際にHTTPリクエストを
発行する時点までの間にホストが変わらないことを前提にしています。

## 残っているリスク: redirectを追従した先の再検証がない

`LPService._fetch_html()`の`requests.get(lp_input, timeout=self.timeout)`は、
`allow_redirects`を明示的に指定していないため、`requests`ライブラリのデフォルト値
（GETでは`True`）が適用され、**HTTP 3xxリダイレクトを自動的に追従します**。

`_is_unsafe_lp_host()`による検証は`/analyze`エンドポイントで受け取った**入力時点の
URL**に対してのみ行われ、`requests`が内部で追従するリダイレクト先のホストは
一切再検証されません。そのため、以下が成立します。

- 入力URL自体は公開インターネット上の一見安全なホスト（例: `https://safe-looking-cdn.example/`）
- そのホストが302/301等で内部向けアドレス（例: `http://169.254.169.254/computeMetadata/v1/`）
  へリダイレクトを返す
- `_is_unsafe_lp_host()`は入力URL（`safe-looking-cdn.example`）しか見ないため通過する
- `requests.get()`がリダイレクトを追従し、実際には内部アドレスへリクエストが飛ぶ

**この手法は、DNS rebindingのようにTTLやDNSインフラを操作する高度な手法を必要とせず、
攻撃者が制御する外部Webサーバー1台（302を返すだけ）で成立します。** 攻撃者が
外部から自由にWebサーバーを立てられる前提（招待制ベータの認証済みユーザーであれば
十分に可能）では、現実的に悪用しうる経路です。

## 想定攻撃シナリオ

1. 攻撃者（招待制ベータの認証済みユーザー、または悪用されたアカウント）が、自身の
   管理下にある外部ドメイン（例: `https://attacker-controlled.example/redirect`）を用意する
2. このURLは`_is_unsafe_lp_host()`のチェックを通過する（一般的な公開ホストのため）
3. `lp_url=https://attacker-controlled.example/redirect`を指定して`/analyze`を実行する
4. `LPService`がこのURLへGETリクエストを送ると、攻撃者のサーバーが
   `Location: http://169.254.169.254/computeMetadata/v1/instance/service-accounts/default/token`
   （GCPメタデータのアクセストークン取得エンドポイント等）への302を返す
5. `requests`がこのリダイレクトを自動追従し、CampaignPilotのバックエンドプロセスが
   GCPインスタンスのメタデータ（サービスアカウントトークン等の機密情報を含みうる）を
   取得してしまう
6. レスポンス本文（メタデータのJSON）は`LPService`によって「LPのHTML」としてパース
   されようとするため、`BeautifulSoup`のパース結果自体は無意味な値になる可能性が高いが、
   `raw_text_excerpt`（本文先頭500文字）等が分析結果やエラーメッセージ、ログに
   混入し、間接的に漏洩する可能性がある

## 対応案の比較

### 案A: `requests.get(..., allow_redirects=False)`

- **実装コスト**: 最小（1行変更）
- **メリット**: リダイレクト追従自体を止めるため、この攻撃経路は完全に塞がれる
- **デメリット**: 実際のLPは正規の理由でリダイレクトを使うことが珍しくない
  （`http://` → `https://`への正規化、`example.com` → `www.example.com`への
  正規化、CDN経由の配信、キャンペーン用の短縮URL等）。`allow_redirects=False`に
  すると、これらの**正当なLPが軒並み取得失敗（3xxレスポンスをHTMLとして誤ってパース
  しようとするか、`raise_for_status()`で例外）になる**リスクが高く、機能的な
  リグレッションになりかねない。安易に採用すべきではない。

### 案B: redirectを1 hopずつ追跡し、毎回ホスト/IPを再検証する（推奨）

- **実装コスト**: 中程度
- **メリット**: 正当なリダイレクト（1〜数hop程度）は許容しつつ、各hop先のホストが
  内部アドレスでないことを`_is_unsafe_lp_host()`相当のロジックで都度検証できる。
  「LPが普通に使えること」と「SSRF対策」を両立できる、最もバランスが良い案。
- **実装イメージ**:
  1. `LPService`（または新しい共通フェッチヘルパー）で`allow_redirects=False`に
     設定した上で自前のループを書く
  2. レスポンスが3xxの場合、`Location`ヘッダーのURLを取り出し、
     `_is_unsafe_lp_host()`相当のチェックを再度通す
  3. 安全であれば次のリクエストを送る。安全でなければ`ProcessingError`として
     失敗させる
  4. 最大hop数（例: 5）を設けて無限リダイレクトを防ぐ
- **留意点**: `_is_unsafe_lp_host()`は現状`backend/app/api/routes/specs.py`に
  閉じている（API層の入力バリデーション用）。redirect先の再検証は`LPService`
  （`backend/app/services/lp_service.py`）側で行う必要があるため、このチェック
  ロジック自体をAPI層とservice層の両方から使える共通モジュールへ切り出す
  リファクタリングが前提になる。

### 案C: HTTPクライアントラッパ/共通フェッチ層での統一hardening

- **実装コスト**: 大
- **メリット**: 将来`LPService`以外にもサーバー側フェッチを行う機能（例:
  Meta Marketing API連携等）が増えた場合、SSRF対策を1箇所に集約できる。
  再利用性・保守性が最も高い。
- **デメリット**: 現時点でサーバー側フェッチを行っているのは`LPService`のみであり、
  共通層を今作る便益はまだ小さい。今回のスコープを超える設計変更になる。

## 推奨方針

**案Bを推奨します。** 理由:

1. 案Aは実装コストが最小な反面、正当なLP（http→https正規化、www正規化、CDN経由等）
   を壊すリスクが高く、「安全だが使い物にならない」状態になりかねない。今回のような
   ユーザー向け機能の防御策として不適切。
2. 案Cは方向性としては正しいが、現時点でサーバー側フェッチを行う機能が`LPService`
   のみである以上、共通層を新設する投資対効果がまだ低い。将来同種の機能
   （Meta Marketing API連携等、[csv_only_mode_followup.md](./csv_only_mode_followup.md)
   参照）が増えたタイミングで案Cへ格上げする方が合理的。
3. 案Bは「LPが普通に使える」という機能要件と「内部アドレスへの到達を防ぐ」という
   安全要件を両立でき、実装コストも現実的な範囲に収まる。

ただし、案Bの実装には`_is_unsafe_lp_host()`のロジックをAPI層（`specs.py`）と
service層（`lp_service.py`）の両方から呼べる形へ切り出すリファクタリングが
前提になるため、**「小さな1行修正」では完結しない**点は着手前に認識しておく
必要があります。

## 非対象（本follow-up整理のスコープ外）

- redirect経由SSRF対策の実際の実装（本ドキュメントは論点整理のみ）
- `allow_redirects=False`の即時反映
- HTTPクライアント全体の刷新（案C）
- `LPService`以外のフェッチ経路の監査（現時点で該当機能なし）

## 受け入れ条件（実装Issueとして着手する場合の目安）

- [ ] `_is_unsafe_lp_host()`相当のロジックがAPI層・service層の両方から再利用できる
      形に切り出されている
- [ ] `LPService`が3xxレスポンスを受け取った際、リダイレクト先URLのホストを
      都度再検証してから追従する
- [ ] 最大リダイレクトhop数の上限が設けられている
- [ ] 正当なLP（http→https正規化、www正規化等の一般的なリダイレクトパターン）が
      引き続き取得できることを回帰テストで確認している
- [ ] 内部アドレスへのリダイレクトを返す悪意あるサーバーを模したテスト
      （`responses`等でモック）で、途中hopでの内部アドレスが拒否されることを確認している
