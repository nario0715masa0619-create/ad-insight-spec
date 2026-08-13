# CampaignPilot（旧: Ad-Insight-Spec）

CampaignPilot（旧: Ad-Insight-Spec）は、広告クリエイティブ（画像・動画）とランディングページ（LP）から抽出した情報を元に、LLM を用いて広告の定性・定量分析を行い、統合された JSON 仕様 (AdInsightSpec v0.2) に変換して管理するシステムです。

> 🧪 **現在、招待制のモニターベータとして提供しています。** 自由なアカウント登録はできません。
> 利用方法は [docs/MONITOR_BETA_OPERATION.md](docs/MONITOR_BETA_OPERATION.md)、
> モニター企業・ユーザーの管理方法は [docs/MONITOR_ACCOUNT_MANAGEMENT.md](docs/MONITOR_ACCOUNT_MANAGEMENT.md) を参照してください。

## 営業・提案関連資料

提案時の説明、初回商談、社内共有で使える営業関連資料を docs/ 配下に整理しています。
開発者向けのセットアップ情報を見る前に、まずプロダクトの価値や伝え方を確認したい場合は、以下の資料から参照するのが自然です。

- [CampaignPilot 説明資料](docs/campaignpilot_sales_doc.md)
  - 何を解決する仕組みなのか、導入価値と技術的な裏付けをまとめた資料
- [CampaignPilot トークスクリプト](docs/campaignpilot_talk_script.md)
  - 顧客に対して価値をどう伝えるかを整理した営業用の話し方集
- [CampaignPilot 営業トーク実戦版](docs/campaignpilot_sales_talk_advanced.md)
  - 初回商談用の5分台本、深掘りトーク、クロージング文句まで含めた実戦向け資料
## クイックスタート

### 1. インストール
`ash
git clone https://github.com/nario0715masa0619-create/ad-insight-spec.git
cd ad-insight-spec/backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
`

### 2. 環境変数設定
ackend/.env を作成し、以下を設定します。
`env
OPENAI_API_KEY=your_openai_api_key_here
GEMINI_API_KEY=your_gemini_api_key_here
LLM_MODEL=gpt  # または gemini
`

### 3. アプリケーション起動
**バックエンド (FastAPI)**
`ash
cd backend
uvicorn app.main:app --host 127.0.0.1 --port 8000
`

**フロントエンド (Streamlit UI)**
別のターミナルを開き、ルートディレクトリから実行します。
`ash
streamlit run frontend/streamlit_app.py
`

## 全体構成図
- **7つのコアサービス**: Ingestion, Metadata, Video, LP, OCR, LLM, Converter
- **DB (SQLite)**: 分析結果と履歴（バージョン）を管理
- **UI (Streamlit)**: 簡易的なユーザーインターフェースによる動作確認

## ✨ v1.0.0+P0 の改善点

### AIS改善文章品質向上（P0）
従来の分析結果の課題：
- 改善提案が抽象的（「訴求力に改善余地」など）
- ユーザーが「次に何をすべきか」判断しづらい

**v1.0.0+P0 での改善：**
1. **根拠付き改善コメント**
   - 単なる抽象的な指摘ではなく、「背景色とテキストのコントラスト比が3:1で WCAG 基準未達」など、数値・根拠を含める
2. **アクション明確化**
   - 「フォントカラーを白、ドロップシャドウを追加」など、実施手順までを記載
3. **優先度ラベル**
   - P0（必須）、P1（強く推奨）、P2（参考） で優先順位を明示
4. **fail-soft 対応**
   - LLM API エラー時も分析結果は破損せず表示。UI上で警告のみ表示
5. **UI での即座確認**
   - 分析完了と同時に改善提案（上位3件）を「✨ 改善提案」セクションで表示
   - 1行要約 + 詳細展開（根拠・アクション）で、3分以内に次アクションを判断可能

**技術的保証：**
- ユニットテスト 33/33 PASS（バリデーション5観点、スキーマ整合性）
- 統合E2E 8シナリオ全PASS（正常系、fail-soft、後方互換性）
- 既存API互換性 100%（P0導入前のデータも安全に取得可能）

### ✨ 最新のUI/UX改善
直近のアップデート (PR #21〜#27) にて、Streamlit UI の操作性と視認性が大幅に向上し、JSONを読み解くことなく、直感的に操作・確認できるようになりました（※既存API仕様や分析ロジック自体は変更していません）。

1. **Analyze タブ (分析の実行)**
   - **モードごとの要件明示**: `file_plus_lp` (画像+LP)、`file_plus_lp_plus_manual_kpi` (画像+LP+KPI) など、選択した分析モードに応じて必須入力項目がUI上で明確に案内されます。
   - **安全なバリデーション**: 必須入力が不足している場合は warning が表示され、分析実行ボタンが無効化されるため、無駄なエラーを未然に防ぎます。
   - **エラー表示の親切化**: 入力不足やAPI失敗時に生JSONやスタックトレースを出力せず、短い案内文と次のアクションを優先表示します。

2. **List タブ (一覧確認)**
   - **人間向けの一覧表示**: JSON主体の表示から、要約・優先度・次アクションを中心とした人間向けの一覧表示に変わり、状況を一目で把握できるようになりました。

3. **Detail タブ (詳細確認)**
   - **選択式の直感的なUI**: Asset ID を手入力する必要がなくなり、一覧から対象を選択して詳細を取得できます。
   - **CreativeCore の自然文表示**: 詳細データ内の「Visuals」「Tone」「AI Labels」などを分かりやすい自然文で表示します。生JSONは折りたたみの補助表示へ格下げされました。

4. **Delete タブ (削除)**
   - **選択式削除**: 削除対象の Asset ID も選択式となり、手入力によるミスを防ぎます（List情報が未取得の場合のみ手入力へフォールバック）。

5. **LLM 改善コメントの復旧**
   - UI上でLLMの改善提案コメント表示が復旧し、分析完了と同時に具体的な改善アクションを即座に確認できます。

## Phase 完了状態一覧

| Phase | タスク | ステータス |
|-------|--------|------------|
| Phase 1 | 基盤構築（FastAPI, SQLite, SQLiteRepository） | ✅ 完了 |
| Phase 2a | 統合スキーマ v0.2 と API 基本設計 (CRUD) | ✅ 完了 |
| Phase 2b | E2E 分析パイプラインと Streamlit UI | ✅ 完了 |
| Phase 2c-1 | LLMService 統合 (GPT/Gemini デュアル実装) | ✅ 完了 |
| Phase 2c-2 | OCRService 統合 (Tesseract, 画像/動画フレーム対応) | ✅ 完了 |
| Phase 2c-3 | AnalysisOrchestrator と ConverterService の完成 | ✅ 完了 |

> 上表がこのプロジェクトの現在地です。`docs/phase1_final_summary.md`・`docs/plans/phase2a_backlog.md`・
> `docs/plans/phase2a_design_decisions.md`は各Phase着手前の初期計画メモ（historical planning docs）であり、
> 実装状況を反映していません。現状確認は本ファイルと現行コードを参照してください。

## 主要機能

CampaignPilotの主入力は **Meta Ads CSV（数値の根拠）+ 広告クリエイティブ（訴求・表現の根拠）+ LP（遷移先体験の根拠）** の3点です。この3点をつなぐことで、CTR/CPA等の数値だけでは分からない「なぜ数値が悪化したか」（クリエイティブの訴求が弱いのか、LPとの接続が悪いのか）まで踏み込んだ改善判断を支援します（設計の詳細: [主入力の再定義メモ](docs/plans/primary_input_redesign.md)）。

- **4つの分析パターン**（`mode`パラメータ。詳細は [Meta Ads CSV インポートガイド](docs/META_ADS_CSV_IMPORT.md)）:
  1. `file_plus_lp_plus_manual_kpi`（標準・推奨）: クリエイティブ + LP + CSV/KPI
  2. `file_plus_kpi`: クリエイティブ + CSV/KPI（LPなし・広告面分析）
  3. `file_plus_lp`: クリエイティブ + LP（数値なし・簡易分析）
  4. `file_only`: クリエイティブのみ（最小・簡易分析）
- **4つのエンドポイント**: analyze, GET, GET by ID, DELETE
- **Streamlit UI**: CSVアップロード・クリエイティブアップロード（複数可）・LP URL入力から分析実行、結果の一覧表示、詳細確認までをブラウザ上で実行可能
- **Meta Ads CSV インポート**: Meta Ads Manager からエクスポートしたCSVを、列の整形なしでそのままアップロードしてKPIを取り込み可能（`file_plus_lp_plus_manual_kpi`/`file_plus_kpi` モードの推奨入力手段。手入力(JSON)はCSVが手元にない場合の補助的な方法。詳細は [Meta Ads CSV インポートガイド](docs/META_ADS_CSV_IMPORT.md)）

## API エンドポイント

- **POST /api/v1/specs/analyze**
  - ファイルの分析を実行し、結果を DB に保存後、JSON を返却
- **GET /api/v1/specs**
  - 分析結果の一覧を取得（ページング対応、論理削除済みは除外）
- **GET /api/v1/specs/{asset_id}**
  - 指定した sset_id の分析結果を取得（?version= で指定可能）
- **DELETE /api/v1/specs/{asset_id}**
  - 指定した sset_id の全バージョンを論理削除

## 現状の制約・既知の制限
- **非同期処理の未対応**: 長時間の LLM 処理や動画処理においてタイムアウトのリスクがあります（今後の拡張で Celery 等を導入予定）。
- **Tesseract OCR の依存**: OCR の利用にはホストマシンへの Tesseract-OCR 本体のインストールが必須です。
- **LP 解析の制限**: 簡易的なスクレイピングのみ実装されており、動的ページには完全対応していません。

## 参考・次ステップ
詳細なシステム構成や運用手順については、以下のドキュメントを参照してください。
- [ARCHITECTURE.md](docs/ARCHITECTURE.md): システム設計・データベース設計
- [OPERATIONS.md](docs/OPERATIONS.md): 開発・本番環境での運用ガイド
- [META_ADS_CSV_IMPORT.md](docs/META_ADS_CSV_IMPORT.md): Meta Ads CSV インポートガイド（対応列・粒度判定・エラー時の対処）
