# CSV-onlyモード（クリエイティブなし分析）follow-up整理

## 背景

[PR #93](https://github.com/nario0715masa0619-create/ad-insight-spec/pull/93)（主入力の再定義:
Meta Ads CSV + 広告クリエイティブ + LP）のタスク定義では、「CSVのみ」を最も軽量な
fallback分析パターンとして位置づけていました。しかし実際の実装調査の結果、
**PR #93では実装を見送り**、`file_plus_kpi`（クリエイティブ + CSV/KPI、LPなし）を
「LPなしの広告面分析」として代替提供するに留めました。

本ドキュメントは、この判断の技術的根拠と、将来CSV-onlyモードを実装する場合の
論点・リスク・推奨方針を、次の実装判断がしやすい形で整理したものです。

**関連Issue**: [#94 feat: CSV-only分析モード（クリエイティブなし）の実装可否検討](https://github.com/nario0715masa0619-create/ad-insight-spec/issues/94)

## 現状: なぜ分析パイプラインがクリエイティブ前提なのか

CampaignPilotの分析パイプライン（`AnalysisOrchestrator`）は、設計の出発点から
「クリエイティブ（画像/動画）を分析対象の中心に置き、LP・KPIはそれに付随する
文脈情報として乗せる」という構造になっています。具体的には、以下の複数レイヤーが
クリエイティブファイルの存在を前提としています。

| レイヤー | ファイル | クリエイティブへの依存 |
|---|---|---|
| スキーマ検証 | `backend/app/schemas/ad_insight.py` | `AdInsightSpec.creative_core: CreativeCore = Field(..., ...)` — **必須フィールド**（Optionalではない）。CSVのみの分析結果はこの時点でPydantic検証に失敗する |
| asset_id生成 | `backend/app/services/metadata_service.py::_generate_asset_id()` | クリエイティブファイルの内容バイト列のハッシュ（`content_hash`）から`asset_id`を生成している。クリエイティブが無いと、この生成戦略自体が成立しない（CSV内容やタイムスタンプ由来の別戦略が必要） |
| Ingestion | `AnalysisOrchestrator._step_ingest()` | `input_path`（クリエイティブファイルパス）を無条件に`IngestionService.execute()`へ渡す。ファイルが無いと最初のステップで失敗する |
| Content Analysis | `AnalysisOrchestrator._step_content_analysis()` | 動画フレーム抽出・OCR・カット分割など、すべてクリエイティブファイルの存在を前提に分岐している |
| LLM分析 | `AnalysisOrchestrator._step_llm()` | `LLMService.analyze_creative()`にクリエイティブの説明文（OCR結果・動画メタデータ由来）を渡す設計。5軸診断（`decision_support`）もクリエイティブの分析結果（`creative_core`）を入力に使う |

**PR #93で新規追加した`file_plus_kpi`（クリエイティブ+CSV、LPなし）は、
上記のうちLPService呼び出しを省略するだけで済んだため、既存構造を壊さず
最小差分で実現できました。** 一方「CSVのみ」は、上記5レイヤーすべてに
クリエイティブ不在の分岐を追加する必要があり、性質が異なります。

## 追加実装時の論点

CSV-onlyモードを実装する場合、最低限以下の変更が必要になると見込まれます。

### 1. UI（Streamlit）
- 「分析パターン」に5つ目の選択肢を追加（例: `csv_only` / 「CSVのみ（数値傾向のみ・最小限）」）
- クリエイティブアップロードを必須から任意に変更するUI分岐
- 「クリエイティブが無いため、原因分析（訴求・表現面）はできません」という明示的な
  期待値コントロール文言（後述「リスク」参照）

### 2. バックエンド: mode / input validation
- `InputModeEnum`に新モード追加
- `AdInsightSpec.creative_core`を`Optional[CreativeCore]`に変更する必要がある
  （**破壊的変更に近い**。既存の全レコード・全テストが`creative_core`必須を前提に
  書かれているため、影響範囲の洗い出しが必要）
- `validate_mode_requirements`に新しい分岐を追加
- `POST /api/v1/specs/analyze`の`input_file`を必須（`File(...)`）から任意
  （`Optional[UploadFile] = File(None)`）に変更する必要がある

### 3. Orchestrator分岐
- `_step_ingest`をクリエイティブ有無で分岐（無い場合はスキップ）
- `_step_metadata`: クリエイティブが無い場合の`asset_id`生成戦略を新設
  （CSV内容ハッシュ + タイムスタンプ等の代替案が必要）
- `_step_content_analysis`: 動画/OCR処理を丸ごとスキップする分岐
- `_step_llm`: クリエイティブ分析（`creative_core`生成）をスキップし、
  5軸診断（`decision_support`）をKPI数値のみから生成する新しいプロンプト設計が必要
  （現行の5軸診断はクリエイティブの定性評価を前提にした軸が多く、CSVの数値だけでは
  「訴求軸」「クリエイティブ」「CTA」等の評価が原理的にできない）

### 4. credit pricing / requirement判定
- `credit_pricing.py`の`_MODE_TO_TIER`に新エントリを追加（想定: light〜standard、
  提供価値の低さを反映してlightが妥当か要検討）
- `VALID_ANALYZE_MODES`は自動追従するため変更不要

### 5. docs / テスト範囲
- `docs/META_ADS_CSV_IMPORT.md`、`docs/plans/primary_input_redesign.md`の更新
- スキーマ検証テスト（`test_input_mode_schema.py`と同様のパターン）
- Orchestratorのクリエイティブ不在分岐のユニットテスト
- `creative_core`をOptional化したことによる既存テストへの影響確認（回帰テスト全体の
  見直しが必要になる可能性が高い）

## リスク

### 1. 「分析価値の低い結果」を返す危険
CampaignPilotの価値提案は「数値・広告表現・遷移先をつないで改善判断を支援すること」
（[主入力の再定義メモ](./primary_input_redesign.md)参照）です。CSVのみの入力では、
5軸診断のうち「訴求軸」「クリエイティブ」「CTA」の評価根拠が原理的に存在しません。
これらを無理に埋めようとすると、根拠の無い推測（捏造）になりかねず、
「詳細だが薄い分析結果」を返してしまい、かえってプロダクトの信頼性を損なうリスクが
あります。

### 2. 既存モードとの責務の曖昧化
現在の4モードは「クリエイティブは常に主役、LP/KPIは付随情報」という一貫した
メンタルモデルで設計されています。CSV-onlyを追加すると、「クリエイティブ抜きでも
分析ツールとして成立する」という別のメンタルモデルが混在することになり、
ユーザーが「どのモードを選べば良いか」を判断しにくくなる懸念があります。

### 3. 分析品質期待値のズレ
Meta Ads Managerの数値だけでも「CTRが低い」「CPAが高い」等の**傾向**は分かりますが、
CampaignPilotが提供している5軸診断・改善提案（What/Why/How形式）は、本質的に
クリエイティブの定性評価に強く依存した設計です。CSVのみでこれと同水準の
アウトプット形式を維持しようとすると、ユーザーが「今までと同じ深さの分析が
出てくる」と誤解し、実際には数値トレンドの要約程度しか出せない、という
期待値ギャップが生じる可能性があります。

## 推奨方針

**結論: 今すぐ実装すべきではなく、まず要件整理を先行すべきです。**

理由:
1. 技術的な変更コストが4レイヤー（スキーマ・API・Orchestrator・LLMプロンプト設計）
   にまたがり、「最小差分」では収まらない
2. 出力形式（5軸診断）をそのまま流用できない可能性が高く、**CSVのみの場合に
   何を返すべきか**（数値傾向のサマリのみに絞るのか、5軸のうち算出可能な軸だけ
   返すのか等）というプロダクト設計判断が先に必要
3. `creative_core`のOptional化は既存の全レコード・全テストに影響しうる変更であり、
   軽微な追加とは言えない

**着手する場合の最小単位（推奨）**:
1. まず「CSVのみの場合、どんな分析結果を返すべきか」のプロダクト要件を先に確定する
   （5軸診断のうち何軸を残すか、あるいは全く別の軽量な出力形式にするか）
2. 要件が固まった後、`creative_core`のOptional化とAdInsightSpecへの影響範囲を
   洗い出すスパイク（実装ではなく調査）を先行する
3. 上記が完了してから、実装Issueを個別のタスクに分解する

## 受け入れ条件（実装Issueを起票する場合の目安）

- [ ] CSVのみの場合に返す分析結果の形式（5軸診断のうちどれを残すか）がプロダクト側で確定している
- [ ] `AdInsightSpec.creative_core`のOptional化による既存機能への影響範囲が洗い出されている
- [ ] `asset_id`生成戦略（クリエイティブ不在時）が決定している
- [ ] 新モードのUI・バックエンド・Orchestrator・docs・テストが揃っている
- [ ] 既存4モードの挙動に回帰が無いことが確認されている

## 非対象（本follow-up整理のスコープ外）

- CSV-onlyモードの実際の実装（本ドキュメントは論点整理のみ）
- 5軸診断のプロンプト再設計そのもの
- `creative_core`のOptional化の実装
- Meta Marketing APIとの直接連携（別論点）
