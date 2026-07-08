# JSON Schema - 動画カット別分析（video_cuts）v1.0

**Version**: 1.0
**Date**: 2026-07-08
**Status**: APPROVED
**Milestone**: 段階1（構成・テンポ俯瞰UI）表示を再現するための保存・再表示用最小スキーマ

---

## 📋 変更概要：旧形式 → v1.0

### 主な変更点

| 項目 | 旧形式 | v1.0 | 理由 |
|------|------|------|------|
| **格納場所** | `diagnostics.video_cuts`（`{"cuts": [...]}`）と `diagnostics.video_cuts_error` の2フィールド並存 | `diagnostics.video_cuts` の1フィールドに統合 | 生成成功/失敗/未実施の3状態を1箇所で表現する |
| **生成状況** | 「`video_cuts` が存在する」か「`video_cuts_error` が存在する」かで暗黙に判定（両方 null＝未実施、を明示できない） | `generation_status.status`（`success` / `failed` / `not_attempted`）で明示 | UI側の分岐ロジックを単純化し、「そもそも未実施」を「失敗」と区別できるようにする |
| **バージョン管理** | 無し | `schema_version`（`"1.0"`から開始） | 将来の構造変更をフロント側で分岐できるようにする |
| **動画全体の要約** | フロント側で毎回 `cuts[]` から `total_duration_seconds`/`cut_count` を再計算 | `video_summary` としてバックエンドで確定・保存 | カットが未整列・非連続でも表示側の再計算に依存しない |
| **role_tag** | LLMの自由記述（例:「Hook」「ベネフィット提示」「証拠・信頼形成」） | 内部語彙 `hook`/`benefit`/`proof`/`trust`/`cta`/`other` に正規化して保存 | 表示側の役割分類・配色を安定させ、自由記述の揺れを吸収する |
| **strength_or_issue / evidence** | 必須（strength_or_issueのみ）/ optional | 両方 optional | 段階1UIの確定表示項目には含まれないが、詳細表示・将来拡張のため保存は継続 |

---

## 🎯 最小スキーマ化の背景

1. **段階1UIの表示項目を先に固定し、それを支える最小構造だけを定義する**
   - 動画全体尺・カット数・各カットの開始/終了時刻・カット長（導出）・役割タグ・一言要約・改善提案
   - Hook位置・カット長は保存せず、`role_tag`+`start_seconds`、`end_seconds`-`start_seconds` から表示側で導出する（冗長データの二重管理を避ける）

2. **再生UIはまだ対象外**
   - `frame_path` / サムネイル参照など、再生・プレビュー機能に必要な項目は今回のスキーマに含めない
   - ただし将来の再生UI連携に備え、`start_seconds`/`end_seconds` は必須フィールドとする

3. **既存データとの互換性**
   - `GET /specs/{asset_id}` は保存済みレコードを Pydantic モデルへ再検証せず、DBに保存された生JSON（`record.spec_data`）をそのまま返す実装になっている。そのため旧形式で保存済みのレコードは移行不要でそのまま読み出せる。
   - フロントエンドは新形式（`generation_status` キーを持つ）と旧形式（`cuts` キーを直接持つ、エラーは別フィールド）の両方を判定して描画する。

---

## 📐 トップレベル構造

`diagnostics.video_cuts` の実体（動画フォーマット以外では `null`）:

```json
{
  "schema_version": "1.0",
  "generation_status": {
    "status": "success",
    "error_code": null
  },
  "video_summary": {
    "total_duration_seconds": 15.9,
    "cut_count": 6
  },
  "video_cuts": [
    {
      "cut_id": "cut_1",
      "start_seconds": 0.0,
      "end_seconds": 8.1,
      "role_tag": "hook",
      "summary": "2人の人物が並んで立っている画像が表示されている。",
      "improvement_suggestion": "画像にキャッチコピーやメッセージを追加して興味を引く要素を強化する。",
      "strength_or_issue": "冒頭としては視線を集めやすいが、広告の内容が瞬時に伝わりにくい。",
      "evidence": "人物は目立つ一方で、商品名やベネフィットを示す視覚要素がない。"
    }
  ]
}
```

## 🔧 フィールド定義

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| `schema_version` | string | ✅ | `"1.0"`から開始。将来の構造変更をフロント側で分岐できるようにする |
| `generation_status.status` | string | ✅ | `success` / `failed` / `not_attempted` のいずれか |
| `generation_status.error_code` | string \| null | ✅（値は`failed`時のみ非null） | 生成失敗時のエラーコード（`CUT_COVERAGE_INVALID` 等、既存のエラーコード体系を再利用） |
| `video_summary` | object \| null | `status=success`以外は`null` | |
| `video_summary.total_duration_seconds` | number | ✅（`video_summary`内） | 検出済み全カットの `end_seconds` の最大値 |
| `video_summary.cut_count` | number | ✅（`video_summary`内） | |
| `video_cuts` | array | ✅（空配列可） | |
| `video_cuts[].cut_id` | string | ✅ | バックエンドで採番済みのカットID（例: `cut_1`） |
| `video_cuts[].start_seconds` | number | ✅ | カット開始秒。バックエンド（`VideoService.detect_cuts`）で確定 |
| `video_cuts[].end_seconds` | number | ✅ | カット終了秒。同上 |
| `video_cuts[].role_tag` | string | ✅ | 内部語彙のいずれか: `hook` / `benefit` / `proof` / `trust` / `cta` / `other` |
| `video_cuts[].summary` | string | ✅ | 画面内容の短い要約 |
| `video_cuts[].improvement_suggestion` | string | ✅ | 具体的な改善提案 |
| `video_cuts[].strength_or_issue` | string \| null | optional | このカットの強みまたは問題点。段階1UIの確定表示項目には含まれない |
| `video_cuts[].evidence` | string \| null | optional | 判断の簡単な根拠。同上 |

### 意図的に含めないもの（段階1時点）

- カット長の保存フィールド: `end_seconds - start_seconds` から表示側で導出
- Hook位置の専用フィールド: `role_tag`（`hook`）+ `start_seconds` から表示側で導出
- `frame_path` / `thumbnail_path` / `thumbnail_url`: 再生・プレビューUIは次段階の対象

## 🏷 role_tag の内部語彙・正規化

LLM生成結果は自由記述で揺れる可能性があるため、`VideoCutContent.role_tag` は Pydantic の `validator` で以下のマッピングを通し、必ず内部語彙へ正規化してから保存する（`backend/app/schemas/llm_response.py::normalize_role_tag`）。

| 内部値 | 表示ラベル（日本語） | 正規化対象の入力例 |
|---|---|---|
| `hook` | Hook | `hook`, `Hook` |
| `benefit` | ベネフィット提示 | `benefit`, `ベネフィット`, `ベネフィット提示` |
| `proof` | 証拠提示 | `proof`, `証拠`, `証拠提示`, `証拠・信頼形成`（旧: 証拠と信頼を1カテゴリにまとめていた値） |
| `trust` | 信頼形成 | `trust`, `信頼`, `信頼形成` |
| `cta` | CTA | `cta`, `CTA` |
| `other` | その他 | 上記いずれにも一致しない値 |

旧データ（マッピング適用前に保存された `role_tag`）はDB上の値をそのまま保持しており、遡って書き換えることはしない。フロントエンドの表示側マッピング（`_role_tag_style_key`）は内部語彙の完全一致を優先し、一致しない場合のみ部分一致でのフォールバック判定を行う。

## 📄 例: status = success

```json
{
  "schema_version": "1.0",
  "generation_status": { "status": "success", "error_code": null },
  "video_summary": { "total_duration_seconds": 15.9, "cut_count": 3 },
  "video_cuts": [
    {
      "cut_id": "cut_1",
      "start_seconds": 0.0,
      "end_seconds": 3.2,
      "role_tag": "hook",
      "summary": "商品を手に取った人物のアップから始まる。",
      "improvement_suggestion": "最初の1秒に価格や割引率など具体的な数字を重ねると離脱を抑えられる。",
      "strength_or_issue": "人物の表情が明るく好印象だが、何の広告か即座には伝わらない。",
      "evidence": "テキストオーバーレイが無く、OCRテキストも検出されなかった。"
    },
    {
      "cut_id": "cut_2",
      "start_seconds": 3.2,
      "end_seconds": 10.5,
      "role_tag": "benefit",
      "summary": "商品の使用シーンとベネフィットを示すテキストが表示される。",
      "improvement_suggestion": "テキストの表示時間を長くし、読み切れるようにする。",
      "strength_or_issue": null,
      "evidence": null
    },
    {
      "cut_id": "cut_3",
      "start_seconds": 10.5,
      "end_seconds": 15.9,
      "role_tag": "cta",
      "summary": "CTAボタンとキャンペーン情報が表示される。",
      "improvement_suggestion": "ボタンの色をより高コントラストにし、視認性を上げる。",
      "strength_or_issue": "CTAの文言は明確だが、ボタンが背景と同化し目立ちにくい。",
      "evidence": "ボタン色 #4a3aa7 に対し背景色が近似の #3f3399 であることをOCR画像から確認。"
    }
  ]
}
```

## 📄 例: status = failed

```json
{
  "schema_version": "1.0",
  "generation_status": { "status": "failed", "error_code": "TIME_BUDGET_EXCEEDED" },
  "video_summary": null,
  "video_cuts": []
}
```

## 📄 例: status = not_attempted

```json
{
  "schema_version": "1.0",
  "generation_status": { "status": "not_attempted", "error_code": null },
  "video_summary": null,
  "video_cuts": []
}
```

`not_attempted` は、動画のカット検出自体が失敗した場合（`VideoService.detect_cuts` が例外・空リストを返した場合等）に用いる。画像フォーマットの場合はこの概念自体が該当しないため、`diagnostics.video_cuts` は `null`（このオブジェクト自体が存在しない）のままとする。

---

## 🔄 後方互換性の方針

- `schema_version` は `"1.0"` から開始する。
- Breaking changeを伴わない項目追加は、既存クライアントが壊れないよう optional フィールドとして追加する。
- 既存の required フィールドの削除・改名・型変更は行わない。
- `GET /specs/{asset_id}` は保存済みレコードを新スキーマへ再検証しないため、旧形式（`{"cuts": [...]}` 単体 + 別フィールドの `video_cuts_error`）のレコードは移行不要でそのまま読み出せる。フロントエンドは新旧両方の形状を判定して描画する（`frontend/streamlit_app.py::render_asset_detail`）。
- 新規に生成される分析結果は、動画フォーマットである限り常に `diagnostics.video_cuts` に本スキーマのオブジェクトを格納する（`generation_status.status` がいずれの値であっても、フィールド自体は必ず存在する）。
- `schema_version` は v1.0時点では1バージョンしか存在せず、現状のコードは「新形式（`generation_status`キーを持つ）か旧形式（`cuts`キーを直接持つ）か」で分岐しており、`schema_version` の値そのものを見て分岐する処理はまだ無い。将来 `schema_version` を上げる変更を行う際は、読み出し側（フロントエンド・バックエンドどちらも）で `schema_version` の値によって処理を分岐させること（`generation_status`キーの有無だけに頼った判定は、旧形式・新形式が今後3種類以上に増えた場合に破綻する）。

### role_tag の語彙追加ルール

- `VIDEO_CUT_ROLE_TAGS`（`hook`/`benefit`/`proof`/`trust`/`cta`/`other`）に新しい値を**追加**するのは non-breaking change として扱ってよい（`schema_version` の更新は不要）。既存の値の意味・呼び出し側の分岐ロジックに影響しないため。
  - ただし追加した場合は、フロントエンドの `ROLE_TAG_STYLES`（`frontend/streamlit_app.py`）に対応する色・アイコン・日本語ラベルを同時に追加すること。追加を怠ると `_role_tag_style_key` のフォールバックにより `other`（その他）として表示され、情報が欠落する。
- 既存の値（`hook`/`benefit`/`proof`/`trust`/`cta`/`other`）を**削除・改名**するのは breaking change。`schema_version` を上げ、旧値を読める後方互換のマッピングを残すこと（`_ROLE_TAG_NORMALIZATION_MAP` に旧値→新値のエントリを追加する形が望ましい。実例: 旧`証拠・信頼形成`→新`proof`）。

## 🔗 関連ドキュメント

- 全体スキーマ: [docs/specs/ad_insight_json_schema_v0_2.md](./ad_insight_json_schema_v0_2.md)
- モデル定義: `backend/app/schemas/llm_response.py`（`VideoCutsBlock` / `VideoCutGenerationStatus` / `VideoSummary` / `VideoCutContent`）
- 組み立てロジック: `backend/app/services/analysis_orchestrator.py::_step_llm`
- フロント描画: `frontend/streamlit_app.py`（`render_video_cuts` / `render_video_composition_header` / `render_video_cut_card`）

最終更新: 2026-07-08
ステータス: APPROVED
