# Security Inventory

## 1. 目的
この文書は、CampaignPilot（旧: Ad-Insight-Spec / AIS）の現行セキュリティ運用、Secrets管理、公開経路、およびFirewall設定の実態を棚卸しし、現時点の判断と次アクションを明確にするための運用メモです。

※ 対象は現在稼働中の本番サービスに限定し、退役済み・非稼働プロジェクトは除外します。

## 2. 対象システム
- **公開名**: CampaignPilot
- **内部名称**: Ad-Insight-Spec（AIS）
- **本番URL**: https://campaignpilot.luvira.co.jp
- **構成要素**: Nginx, FastAPI, Streamlit, systemd, GCP VM

## 3. 棚卸しの前提
- **確認日**: 2026-07-03
- **基本方針**:
  - まず実態確認を行う。
  - 脆弱な運用を見つけてもその場で不用意に修正せず、現状・リスク・改善案を整理する。
  - 必要な是正のみを段階的に実施する。

## 4. Secrets管理の現状

### ローカル開発環境
- **.env 標準パス**: `C:\Users\nario\.（プロジェクト名）\.env`
- **例**: `C:\Users\nario\.ad-insight-spec\.env`

### 本番環境
- **.env パス**: `/etc/ad-insight-spec/.env`

### GitHub管理方針
- `.env` 自体は `.gitignore` によりリポジトリ管理対象外とし、コミットしない。
- テンプレートとして `.env.example` のみ管理する。

### 確認済み事項
- `.env` 実体はリポジトリに含まれていない。
- 本番 `.env` およびTLS秘密鍵の実体権限は適切に制限されている。
- Secret Manager等の高度なSecrets管理の導入は未実施。

## 5. 公開経路とFirewallの現状

### 正式公開経路
- **プロトコル**: HTTP (80) / HTTPS (443)
- **リバースプロキシ**: Nginx経由
- **正式URL**: `https://campaignpilot.luvira.co.jp`

### 直アクセス経路
- **Streamlit**: `http://34.84.24.83:8501`
- **FastAPI**: `http://34.84.24.83:8000` （外部未開放の既知ギャップあり）

### 確認時点の主なFirewallルール
- HTTP (80) / HTTPS (443)
- Streamlit (8501)
- SSH (22)
- ICMP / internal

## 6. 棚卸し結果

### 高優先
- `default-allow-rdp (tcp:3389)` が未使用の公開穴として存在していた。

### 中優先
- `allow-streamlit-8501` により、平文・無TLSの直アクセス経路が依然として残っている。

### 低優先
- Secret Managerが未導入である。
- IAM権限の最小化が未着手である。

### 管理境界外
- `google_sudoers` による広範なsudo権限。
- GCP IAM全体の broader governance（広範なガバナンス）。

## 7. 実施済み対応

### RDPルール削除 (2026-07-03)
- `default-allow-rdp (tcp:3389)` を削除した。
- 削除前に 3389 ポートの待受プロセスが存在しないことを確認済み。
- 削除後の正常性確認:
  - `https://campaignpilot.luvira.co.jp/health` → 200 OK
  - `http://34.84.24.83:8501` → 200 OK
  - SSH疎通 → 正常
  - `ad-insight-fastapi`, `ad-insight-streamlit`, `nginx` サービス → active
  - FastAPI内部 `/health` → healthy
- **関連コミット**: `8f63abf` (ルールの削除および `docs/DEPLOYMENT.md` 追記)

## 8. 現時点の判断

### 維持するもの
- 正式なHTTPS公開経路
- SSH接続
- 現行の本番 `.env` 管理方式

### 継続判断としたもの
- Streamlit 8501 直アクセスの閉鎖可否
- Secrets管理の高度化
- IAM最小権限化

### 8501直アクセスの扱いについての運用メモ
現時点では 8501 の直アクセス経路を**維持**する。
ただしこれは恒久的な方針ではなく、HTTPS本番運用の安定性と監視運用が十分に確認できた後、別タスクとして閉鎖または制限を判断する。

#### 閉鎖条件
`allow-streamlit-8501` は、次の条件を満たした後に閉鎖または制限を検討する。

1. **HTTPS本番経路の安定運用**
   - `https://campaignpilot.luvira.co.jp` が連続30日以上、重大インシデントおよび想定外のダウンタイムなしを満たしていること。

2. **監視・ヘルスチェックの整備**
   - 本番用ヘルスチェックの監視が運用に組み込まれていること。
   - 障害検知後の一次対応フローが整理されていること。

3. **デバッグ用途の代替手段**
   - 8501直アクセスに依存しないトラブルシュート手段（例: ログ確認、SSH、ローカルフォワード等）が確保されていること。

4. **閉鎖前の最終確認**
   - 閉鎖前に、8501経由の実利用有無を確認すること。
   - 閉鎖後の状態確認項目を事前に整理すること。

上記を満たした時点で、ClaudeCodeに閉鎖またはアクセス制限の実施を依頼する。

## 9. 次アクション

### 短期
1. HTTPS本番運用の安定監視
2. 8501直アクセスを閉じる条件の定義
3. 必要に応じた運用 docs の追記

### 中期
1. Secrets管理の高度化検討
2. IAM最小権限化の検討
3. 認証機能 / SaaS運用設計との接続整理

## 更新履歴
- 2026-07-03: 初版作成、`default-allow-rdp (3389)` 削除結果を反映
