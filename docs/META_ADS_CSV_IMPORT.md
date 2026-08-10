# Meta Ads CSV インポートガイド

CampaignPilot の主入力は **Meta Ads CSV（数値の根拠）+ 広告クリエイティブ（訴求・表現の根拠）+
LP（遷移先体験の根拠）** の3点です（設計の詳細: [主入力の再定義メモ](plans/primary_input_redesign.md)）。
本ドキュメントは、そのうち数値（KPI）を取り込むための主要な手段である **Meta Ads CSV** の
使い方を説明します。

CampaignPilot は、Meta Ads Manager からエクスポートした CSV を **列の並べ替えや削除、値の整形をせずにそのまま** アップロードして、KPI（インプレッション・クリック・消化金額・結果など）を取り込めます。

CSVは `file_plus_lp_plus_manual_kpi`（標準・推奨: クリエイティブ+LP+CSV）と
`file_plus_kpi`（LPなし・広告面分析: クリエイティブ+CSV）の2モードで利用できます。
KPIファイル（JSON）を手入力するフローも引き続き利用できますが、これは **CSVが手元にない
場合の補助的な入力手段** という位置づけです（数値入力の主手段はCSV）。

## 何をアップロードすればよいか

Meta Ads Manager の「エクスポート」機能で書き出した CSV ファイルをそのままアップロードしてください。

- 列の順番を変える必要はありません
- 不要な列を削除する必要はありません（対応外の列は自動的に無視されます）
- 値を整形（カンマや%記号の除去など）する必要はありません

Streamlit UI の「新規分析」タブで、分析パターンを「🌟 標準（推奨）: CSV + クリエイティブ + LP」
（`file_plus_lp_plus_manual_kpi`）または「CSV + クリエイティブ（LPなし・広告面分析）」
（`file_plus_kpi`）に設定すると、①のセクションでKPI入力方法として
「Meta Ads CSV（そのままアップロード・推奨）」を選択できます。

## 対応している列（Phase 1）

日本語・英語どちらのエクスポートにも対応しています（代表的な表記ゆれのみ。完全な互換性は今後の課題）。

| 内部フィールド | 必須/任意 | 代表的な列名（日本語） | 代表的な列名（英語） |
|---|---|---|---|
| インプレッション (`impressions`) | **必須** | インプレッション | Impressions |
| クリック (`clicks`) | **必須** | クリック（すべて） / リンクのクリック数 | Clicks (all) / Link clicks |
| 消化金額 (`spend`) | 任意 | 消化金額 (JPY) | Amount spent (JPY) |
| 結果/コンバージョン (`conversions`) | 任意 | 結果 / コンバージョン | Results / Conversions |
| キャンペーン名 (`campaign_name`) | 任意（粒度判定に使用） | キャンペーン名 | Campaign name |
| 広告セット名 (`adset_name`) | 任意（粒度判定に使用） | 広告セット名 | Ad set name |
| 広告名 (`ad_name`) | 任意（粒度判定に使用） | 広告名 | Ad name |
| 分析期間 (`analysis_period`) | 任意 | レポート開始日 / レポート終了日 / 日付 | Reporting starts / Reporting ends / Day |

**必須なのは「インプレッション」「クリック」の2つのみです。** それ以外（消化金額・結果・名称・日付列）が無くても分析は継続できますが、算出できる指標が減ります（例: 結果が無いとCPAは算出されません）。

CTR / CPA / CVR は、CSVの値をそのまま使うのではなく、取り込んだインプレッション・クリック・消化金額・結果の合算値から自動計算されます（手入力(JSON)フローと同じ計算ロジック。複数行を合算した際にCSV上のレシオ値と不整合が起きるのを避けるため）。

## 対応している粒度

CSVに含まれる列から、以下の優先順で自動判定します。

1. 「広告名」列がある → **広告単位** (`ad`)
2. 「広告セット名」列がある（広告名列は無い） → **広告セット単位** (`adset`)
3. 「キャンペーン名」列がある（上記いずれも無い） → **キャンペーン単位** (`campaign`)
4. いずれも無い → `unknown`（KPIの取り込み自体は継続します）

判定結果は分析結果の `asset_meta.kpi_granularity` に記録されます。また、CSVから取り込み元であることは `asset_meta.kpi_source = "meta_ads_csv"` として記録されます（手入力(JSON)の場合は `null` のまま）。

## 複数行（日別内訳など）の扱い

Meta Ads Manager のCSVは、日別内訳など複数行にわたってエクスポートされることがあります。CampaignPilot は以下のように扱います。

- インプレッション・クリック・消化金額・結果は **全行を合算** します
- キャンペーン名/広告セット名/広告名は、複数の異なる値が含まれていた場合は **先頭の値を採用** し、その旨を警告として記録します
- 分析期間は、複数行の開始日の最小値〜終了日の最大値を採用します

複数の広告・キャンペーンのデータが1つのCSVに混在している場合、KPIは合算されてしまいます。1つの分析対象（1つの広告/広告セット/キャンペーン）につき1つのCSVをエクスポートしてアップロードすることを推奨します。

## 対応外・エラーになる場合

以下の場合は分析を開始できず、エラーメッセージで次に何をすればよいかを案内します。

| ケース | エラーコード | 対処 |
|---|---|---|
| CSVが空 | `META_ADS_CSV_EMPTY` | 正しくエクスポートされているか確認してください |
| ヘッダー行のみでデータ行が無い | `META_ADS_CSV_NO_DATA` | 集計期間や絞り込み条件を確認し、データ行を含む状態で再エクスポートしてください |
| 「インプレッション」「クリック」列が見つからない | `META_ADS_CSV_MISSING_REQUIRED_COLUMNS` | Meta Ads Manager のエクスポート設定でこれらの指標を含めて再エクスポートしてください |
| 列は見つかったが値が数値として読み取れない | `META_ADS_CSV_UNREADABLE_VALUES` | セルが空欄になっていないか確認してください |
| 文字コードを判定できない | `META_ADS_CSV_ENCODING_ERROR` | UTF-8 または Shift_JIS(CP932) で保存し直してください |

いずれの場合も、KPI入力方法を「JSONで手入力（補助的な方法）」に切り替えることで分析を継続できます。

## 手入力(JSON)との違い

CSVはCampaignPilotの主入力（数値の根拠）としての推奨手段、JSON手入力はCSVが手元にない
場合の補助的な入力手段という位置づけです。

| | Meta Ads CSV（推奨・主入力） | JSON手入力（補助） |
|---|---|---|
| 入力形式 | Meta Ads Managerエクスポートそのまま | `{"impressions": ..., "clicks": ...}` 形式のJSON |
| 列名の変換 | 自動（日本語/英語の主要パターン） | 不要（すでに内部フィールド名で記述） |
| 粒度判定 | 自動（campaign/adset/ad） | なし |
| 複数行の扱い | 自動合算 | 非対応（単一のKPIセットのみ） |
| 向いているケース | Meta Ads Managerから直接エクスポートできる場合（基本はこちら） | CSVが手元になく、KPIを他システムから個別に転記する場合 |

## 非対応（今回のスコープ外）

- Meta Marketing API との直接連携（OAuth/トークン認証を含む）
- Google Ads / TikTok Ads 等、他媒体のCSV
- インプレッション・クリック以外を起点にした欠損値の推定（例: CTRからのインプレッション逆算）
- 1つのCSVに複数の広告/キャンペーンが混在する場合の、行ごとの個別集計

## 実装の場所

- CSV解析ロジック: [`backend/app/services/meta_ads_csv_service.py`](../backend/app/services/meta_ads_csv_service.py)（`MetaAdsCsvService` / `MetaAdsCsvError`）
- パイプライン組み込み: [`backend/app/services/analysis_orchestrator.py`](../backend/app/services/analysis_orchestrator.py)（`_step_load_kpi` が `kpi_file` の拡張子で `.csv`/`.json` を振り分け）
- スキーマ拡張: [`backend/app/schemas/ad_insight.py`](../backend/app/schemas/ad_insight.py)（`AssetMeta.kpi_source` / `AssetMeta.kpi_granularity`）
- テスト: [`backend/tests/test_meta_ads_csv_service.py`](../backend/tests/test_meta_ads_csv_service.py)、[`backend/tests/test_orchestrator_meta_ads_csv_wiring.py`](../backend/tests/test_orchestrator_meta_ads_csv_wiring.py)
- サンプルCSV（ダミーデータ）: [`sample_data/meta_ads_csv/`](../sample_data/meta_ads_csv/)

`POST /api/v1/specs/analyze` エンドポイントの `kpi_file` パラメータはそのままで、ファイル拡張子（`.csv` / `.json`）で自動的に処理方式が切り替わります。

主入力の再定義（[主入力の再定義メモ](plans/primary_input_redesign.md)）にあわせて、`mode`パラメータに
`file_plus_kpi`（クリエイティブ + CSV/KPI、LPなし）を追加し、LPを直接URL文字列で渡せる
`lp_url`パラメータ（`lp_file`より優先）を追加しました。`kpi_file`自体の挙動（CSV/JSON振り分け）は変更していません。
