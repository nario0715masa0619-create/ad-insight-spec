# CLAUDE.md

## このファイルの目的
このファイルは、CampaignPilot / Ad-Insight-Spec リポジトリで Claude Code が安定して安全に作業するための運用ルールです。

毎回の会話で同じ前提説明を繰り返さずに済むように、以下を固定します。
- このプロジェクトの現在地
- 何を優先すべきか
- 何をしてよくて、何を慎重に扱うべきか
- 変更後に何を確認すべきか

このファイルは「長い一般論」ではなく、このプロジェクトで実際に守るべきルールを簡潔にまとめることを目的にします。

## プロジェクトの基本情報
- 公開名: CampaignPilot
- 正式公開URL: https://campaignpilot.luvira.co.jp
- 旧名称 / 内部名称: Ad-Insight-Spec
- repo / コード / service 名には `ad-insight-spec` や `ad-insight-*` が残っている

このプロジェクトは、広告・LP・KPIを横断して診断し、改善アクションを判断するための本番稼働中のサービスです。

## いまの前提
- すでに HTTPS で本番公開済み
- FastAPI / Streamlit / Nginx は稼働済み
- `/health` は確認済み
- WebSocket 疎通も確認済み
- docs はかなり main に反映済み

この repo は新規立ち上げ中の未整備プロジェクトではありません。
「すでに動いている本番サービス」を前提に扱ってください。

## 最優先の考え方
今の最優先は、新機能を急いで足すことではありません。
優先順位は次の通りです。

1. 本番の安定運用を維持する
2. 運用を整理して事故を減らす
3. 直アクセス経路や firewall など公開経路を引き締める
4. docs / infra / 実体の整合を保つ
5. そのうえで機能改善を進める

## Claude Code の権限方針
Claude Code は、このプロジェクトで本番に関わる作業まで触ってよい前提です。
これ自体は意図された運用です。

ただし「本番を触ってよい」は「何でも無条件に変えてよい」ではありません。
以下の原則を守ってください。

- できるだけ小さく安全な変更単位で進める
- ただし細かすぎる承認往復は増やさず、論理的にまとまった単位で実行する
- 変更前に依存関係を確認する
- 変更後は検証する
- 何を変えたか、何を確認したか、何が未確認かを明確に報告する

## このプロジェクトでのツール分担
### Claude Code
主担当:
- コード調査
- 修正
- テスト
- リファクタリング
- VM作業
- systemd / nginx / TLS / デプロイ関連作業
- 本番反映作業
- 技術的変更の PR 作成

### Antigravity
向いている作業:
- Git / GitHub の軽い操作
- docs 更新
- markdown 整形
- 軽量PRの整理やマージ
- 状況整理
- 小さく安全な修正

### 検索・戦略担当AI
使う場面:
- 要件整理
- 影響範囲整理
- リスク洗い出し
- 優先順位付け
- 他AIに渡すための指示文設計

### Genspark
使う場面:
- 長文ドキュメント
- 提案書
- 運用ガイド
- LP / スライド / 研修資料の初稿

## 本番構成の理解
### 正式な公開先
- UI: https://campaignpilot.luvira.co.jp
- Health: https://campaignpilot.luvira.co.jp/health

### 直アクセス経路
- Streamlit: http://34.84.24.83:8501
- FastAPI: http://34.84.24.83:8000

注意:
- `:8000` は外部 firewall 未開放の既知ギャップがある
- 直アクセス経路は現時点ではまだ残っている
- 閉鎖や縮小は別タスクとして慎重に扱う

### 構成の要点
- Nginx が 80 / 443 の前段
- API 系は FastAPI にルーティング
- UI 系は Streamlit にルーティング
- app プロセスは systemd 管理

### 実際の systemd service 名
- `ad-insight-fastapi.service`
- `ad-insight-streamlit.service`

### repo 上の canonical source
- `infra/systemd/fastapi.service.template`
- `infra/systemd/streamlit.service.template`
- `infra/sudoers/ais-ops.template`
- `infra/nginx/ais.conf.template`

## 既知の重要事実
- 正式公開名は CampaignPilot だが、内部名称は ad-insight 系が残っている
- 静的IP は `34.84.24.83`
- DNS権威は Cloud DNS ではなく Xserver
- wildcard DNS が存在していたため、`campaignpilot` は個別Aレコードで上書きした
- 直アクセス経路は暫定的に残っている
- `google_sudoers` 側の広範権限は既知だが、このプロジェクトの管理境界外

## 現在の優先順位
### 高
1. HTTPS 本番運用の安定維持
2. 直アクセス経路を残すか閉じるかの判断
3. firewall 整理
4. certbot 自動更新確認手順の明文化

### 中
1. CampaignPilot への表示・ブランド統一
2. repo 名や内部名称の rename 要否判断
3. SaaS用の認証 / 課金 / 顧客管理 / LP 設計

### 長期
1. `*.luvira.co.jp` 命名ガイドの策定
2. `app.luvira.co.jp` の用途設計
3. カスタムドメイン対応の要否検討

## 絶対に守ること
### 1. 本番を雑に壊さない
次に触れる変更は、必ず依存関係を確認してから進めてください。

- FastAPI
- Streamlit
- Nginx
- systemd
- DNS
- firewall
- TLS / certbot
- env / secret 読み込み

これらに関わる場合は、
- どこに影響するか
- どの順で確認するか
を先に整理してから変更してください。

### 2. 大規模 rename を勝手に始めない
`ad-insight-*` から `campaignpilot-*` への全面 rename は、明示的な依頼がない限り行わないでください。

命名の不整合は既知ですが、現時点では「広範囲の rename による事故」の方が危険です。
必要性と影響範囲が整理されるまでは、既存名を尊重してください。

### 3. secrets を露出しない
- secrets をコミットしない
- secrets をログやレポートに出さない
- tracked file に移さない
- 既存の `.env` / secret load 方式を壊さない
- 弱い運用を見つけたら、その場で雑に直すより先に、現状・リスク・改善案を整理する

**ローカル `.env` の配置ルール（Windows開発環境）**
- 標準パスは `C:\Users\nario\.(プロジェクト名)\.env`（例: このプロジェクトなら `C:\Users\nario\.ad-insight-spec\.env`）
- リポジトリ直下（プロジェクトルート）に `.env` を作らない

### 4. docs を置き去りにしない
運用や挙動が変わる変更をしたときは、可能な限り同じ作業の中で docs も更新してください。
最低限確認すべき docs:
- `README.md`
- `docs/OPERATIONS.md`
- `docs/DEPLOYMENT.md`

### 5. 変更後は必ず検証する
変更が完了したら、最低でも次を意識して確認してください。
- 何を変えたか
- 何を実行したか
- 何が確認できたか
- 何が未確認か
- 必要ならロールバック観点

## 作業ポリシー
### 基本的に進めてよいこと
- code / docs の広い読解
- 依存関係の整理
- 小さな docs 不整合の修正
- テスト追加 / テスト改善
- エラーメッセージ改善
- 外部挙動を変えない保守改善
- PR にまとめやすい差分の準備

### 特に慎重に扱うこと
- systemd unit 変更
- nginx 設定変更
- TLS / certbot 関連変更
- firewall 変更
- 公開ルーティング変更
- env 読み込み変更
- 認証追加
- 直アクセス経路の停止 / 閉鎖

### 原則、明示依頼または必要性整理なしにやらないこと
- ad-insight 系から campaignpilot 系への全面 rename
- fallback 経路の破壊的削除
- DNS方針の変更
- wildcard 運用の変更
- プロジェクト管理外の sudo ポリシー変更
- `google_sudoers` の統治範囲に踏み込む変更

## 推奨する進め方
タスクを受けたら、次の順で考えてください。

1. 現状の挙動を理解する
2. 影響レイヤーを特定する
3. 最小で安全な変更セットを決める
4. まとまりのある単位で実装する
5. 具体的に検証する
6. 結果・未確認事項・残リスクを報告する

大きめの作業では、毎回細切れで止まるよりも、論理的にまとまった単位で実行し、最後に整理して報告する方針を優先してください。

## 検証チェックリスト
必要に応じて使ってください。

### アプリ / runtime
- service status 確認
- health endpoint 確認
- Streamlit UI 到達確認
- WebSocket 動作確認（関連変更時）
- smoke test 実行（存在する場合）

### Infra
- nginx config test
- TLS 証明書状態 / 自動更新経路の確認
- systemd daemon reload 要否確認
- networking 変更時の port / firewall 到達性確認

### Repo品質
- テスト成功、または未実施理由の明示
- 挙動変更時の docs 更新
- 関係ない差分を混ぜない

### Streamlit一覧UIのテスト観点（ClaudeCode向け）

Streamlitで一覧UI（Detail / Deleteタブなど）を変更する場合は、コード修正だけでなく、次のテスト観点を必ず満たすこと。

1. widget key の一意性
   - 同じ画面内で、widgetの `key` が重複しないことを確認する。
   - タブ違いでも同じキーを使わないこと。（例: `detail_select_*` と `delete_select_*` を分ける）
   - 一覧の各行で `key` を「タブ名 + 操作種別 + 業務ID/asset_id + index」などから構成し、行ごとに一意になるようにする。

2. データパターン別の描画確認
   - 通常ケースだけでなく、次のパターンで一覧を表示させる。
     - asset_id が `unknown_*` の行を複数含むケース
     - IDが重複する可能性がある行（仮ID・欠損補完など）
   - これらのケースでも画面がクラッシュせずに描画できることを確認する。

3. 全行ボタン押下テスト
   - 一覧の全行を表示した状態で、画面内のボタン（Detail / Deleteなど）を一度ずつ押してもエラーにならないことを確認する。
   - 特に、`StreamlitDuplicateElementKey` や `DuplicateWidgetID` がログに出ていないことを確認する。

4. タブ切り替えと状態の確認
   - Detail / Deleteなど、タブを切り替えながら操作してもエラーにならないことを確認する。
   - タブを行き来しても、不要なwidget再生成や状態の取りこぼしが起きていないことを確認する。

5. 例外・ログの確認
   - Streamlitアプリのログを確認し、以下のエラーが出ていないことを確認する。
     - `StreamlitDuplicateElementKey`
     - `DuplicateWidgetID`
     - その他、UIの基本的な例外（ValueError, KeyErrorなど）
   - 問題が出た場合は、その場しのぎで `key` を変えるのではなく、一覧UI全体の `key` 命名規約を見直すこと。

ClaudeCodeは「動いたかどうか」だけでなく、上記観点を満たしているかまでテストしてから修正完了とすること。

## この repo での報告スタイル
作業完了時は、できるだけ次の形で報告してください。

- 結果の要約
- 変更ファイル
- 実施した確認
- 未確認事項
- 次にやるとよいこと

## 新しく入った担当者やAIが最初に読む順番
1. `README.md`
2. `docs/OPERATIONS.md`
3. `docs/DEPLOYMENT.md`
4. `infra/` 配下の template 群
5. その後に code / infra を編集する

## デフォルトで次に勧めるべきこと
ユーザーから別指定がなければ、次はこの順で提案してください。

1. HTTPS 本番運用の安定監視
2. 直アクセス経路を残すか閉じるかの判断
3. firewall 引き締め
4. certbot 更新確認手順の明文化
5. その後に naming / branding / SaaS展開設計
