# Service Interface Design - Phase 1

**Version**: 1.0  
**Date**: 2026-06-23  
**Purpose**: Service 間の入出力契約を固定し、結合時の迷いを減らす

---

## 📋 Service インターフェース仕様

### 1. IngestionService

**責務**: ファイル入力の受理・検証・正規化

| 項目 | 詳細 |
|------|------|
| **入力** | `file_path: str` |
| **出力** | `IngestedAsset: dict` |
| **出力スキーマ** | `{"format": "video_static", "data": <bytes>, "metadata": {...}}` |
| **例外** | `FileNotFoundError`, `UnsupportedFormatError`, `CorruptedFileError` |
| **依存** | なし |
| **テスト** | MP4, PNG, TXT 各 3ケース + 異常系 3ケース |

**メソッド一覧**:
```python
def ingest(file_path: str) -> dict:
    """ファイルを読み込み、IngestedAsset を返す"""

def validate_format(file_path: str) -> bool:
    """ファイル形式が対応しているか"""

def is_video(file_path: str) -> bool:
def is_image(file_path: str) -> bool:
def is_text(file_path: str) -> bool:
```

### 2. MetadataService
**責務**: 素材メタデータ抽出（asset_id 生成・ファイル基本情報）

| 項目 | 詳細 |
|------|------|
| **入力** | `ingested_asset: dict` (IngestionService の出力) |
| **出力** | `metadata: dict` |
| **出力スキーマ** | `{"asset_id": "asset_...", "duration_seconds": 30, "resolution": "1920x1080", ...}` |
| **例外** | なし（Ingestion でバリデーション済み） |
| **依存** | IngestionService |
| **テスト** | 動画・画像・テキスト 各 2ケース |

**メソッド一覧**:
```python
def extract(ingested_asset: dict) -> dict:
    """メタデータ抽出"""

def generate_asset_id() -> str:
    """asset_YYYYMMDD_HHmmss_local_<uuid> フォーマット"""

def extract_video_metadata(data: bytes) -> dict:
    """duration, fps, resolution 等"""

def extract_image_metadata(data: bytes) -> dict:
    """width, height, color_space 等"""
```

### 3. OCRService
**責務**: 画像内テキスト認識（Tesseract）

| 項目 | 詳細 |
|------|------|
| **入力** | `image_path: str` または `image_data: bytes` |
| **出力** | `{"text": "...", "confidence": 0.92}` |
| **例外** | `OCRError` |
| **依存** | なし |
| **テスト** | 日本語テキスト 3ケース + 英語 2ケース |

**メソッド一覧**:
```python
def extract_text(image_path: str) -> str:
    """画像からテキスト抽出"""

def extract_text_with_confidence(image_path: str) -> dict:
    """テキスト + 信頼度"""
```

### 4. VideoService
**責務**: ビデオフレーム抽出（FFmpeg）

| 項目 | 詳細 |
|------|------|
| **入力** | `video_path: str` |
| **出力** | `{"frames": ["frame1.png", "frame2.png", ...], "duration_seconds": 30}` |
| **例外** | `VideoError` |
| **依存** | なし（FFmpeg は外部コマンド） |
| **テスト** | MP4 3ケース + 破損ファイル 1ケース |

**メソッド一覧**:
```python
def extract_key_frames(video_path: str, num_frames: int = 5) -> list[str]:
    """均等な N フレームを抽出"""

def get_duration(video_path: str) -> float:
    """動画の長さを秒単位で"""

def get_resolution(video_path: str) -> tuple[int, int]:
    """解像度を取得"""
```

### 5. LPService
**責務**: ランディングページ解析（BeautifulSoup）

| 項目 | 詳細 |
|------|------|
| **入力** | `lp_input: str` (URL または ローカルHTMLパス) |
| **出力** | `{"fv_copy": "...", "form_fields": [...], "cta_text": "..."}` |
| **例外** | `LPFetchError`, `LPParseError` |
| **依存** | なし |
| **テスト** | URL 2ケース + ローカルHTML 2ケース + 異常系 1ケース |

**メソッド一覧**:
```python
def fetch_and_parse(lp_input: str) -> dict:
    """URL/ローカルパスから LP 情報を抽出"""

def extract_fv_copy(html: str) -> str:
    """FV コピー（h1 → h2 → 最初の p）"""

def extract_form_fields(html: str) -> list[str]:
    """フォーム項目名リスト"""

def extract_cta_text(html: str) -> str:
    """CTA ボタンテキスト"""

def extract_offer(html: str) -> str:
    """オファー内容（30日無料 等）"""
```

### 6. LLMService
**責務**: LLM ラベリング（Gemini 2.0 Flash）

| 項目 | 詳細 |
|------|------|
| **入力** | `{"image_paths": [...], "primary_text": "...", "headline": "..."}` |
| **出力** | `{"hook_type": "benefit", "tone": "inspirational", "emotions": [...]}` |
| **例外** | `LLMError` |
| **依存** | Google Generative AI SDK |
| **テスト** | 画像あり 2ケース + テキストのみ 1ケース |

**メソッド一覧**:
```python
def analyze_creative(image_paths: list[str], primary_text: str, headline: str) -> dict:
    """クリエイティブ分析（Hook, Tone, Emotion）"""

def calculate_message_consistency(ad_text: str, lp_copy: str) -> tuple[float, str]:
    """Message Consistency スコア + 根拠"""

def generate_recommendations(diagnostics: dict) -> list[str]:
    """改善案を LLM に生成させる"""
```

### 7. ConverterService
**責務**: 分析結果を ad_insight_spec v0.2 JSON に変換

| 項目 | 詳細 |
|------|------|
| **入力** | `{"metadata": {...}, "creative_analysis": {...}, ...}` (全 Service の出力をマージ) |
| **出力** | `ad_insight_spec: dict` (Pydantic v0.2 準拠) |
| **例外** | `ValidationError` |
| **依存** | 全 Service |
| **テスト** | 3モード各 1ケース |

**メソッド一覧**:
```python
def convert_to_ad_insight_spec(analysis_result: dict, mode: str) -> dict:
    """分析結果を v0.2 スキーマに変換"""

def populate_input_metadata(mode: str, file_paths: dict) -> dict:
    """input_metadata セクション生成"""

def populate_asset_meta(metadata: dict) -> dict:
    """asset_meta セクション生成"""

def populate_creative_core(analysis: dict) -> dict:
    """creative_core セクション生成"""

def populate_landing_page(lp_analysis: dict) -> dict:
    """landing_page セクション生成（オプション）"""

def populate_performance(kpi: dict) -> dict:
    """performance セクション生成（オプション）"""
```

---

## 🔗 Service 依存関係図
```text
IngestionService
    ↓
MetadataService
    ↓
┌───────────────────────────────┐
│ 並行実行（依存関係なし）       │
├───────────────────────────────┤
│ - VideoService                │
│ - OCRService                  │
│ - LPService                   │
└───────────────────────────────┘
    ↓ 結果をマージ
LLMService
    ↓
ConverterService
```

## 🎬 AnalysisOrchestrator の呼び出し順
```python
# 1. Ingestion
ingested = IngestionService().ingest(input_path)

# 2. Metadata
metadata = MetadataService().extract(ingested)

# 3. 並行実行
video_frames = VideoService().extract_key_frames(...) if is_video else []
ocr_result = OCRService().extract_text(...) if is_image else {}
lp_data = LPService().fetch_and_parse(...) if lp_input else {}

# 4. LLM ラベリング
llm_result = LLMService().analyze_creative(
    image_paths=video_frames,
    primary_text=...,
    headline=...
)

# 5. Converter
spec = ConverterService().convert_to_ad_insight_spec({
    'metadata': metadata,
    'video_frames': video_frames,
    'ocr': ocr_result,
    'lp': lp_data,
    'llm': llm_result
}, mode)
```

## 🚨 エラーハンドリング戦略
| エラー | 対応 |
|--------|------|
| `FileNotFoundError` | CLI で表示：「ファイルが見つかりません」 |
| `UnsupportedFormatError` | CLI で表示：「形式が非対応です。MP4/PNG/TXT のみ」→ exit code 1 |
| `LPFetchError` | 警告を残しつつ続行（LP なしでも定性診断は可能） |
| `LLMError` | 自動リトライ 3 回、その後失敗 → exit code 1 |
| `ValidationError` | デバッグ用に詳細エラーを stderr に出力 → exit code 1 |

## ✅ テスト観点（最小一覧）

### Unit Test
| Service | テストケース |
|---------|--------------|
| **Ingestion** | MP4 読み込み、PNG 読み込み、TXT 読み込み、ファイル不在、形式不正 |
| **Metadata** | asset_id 生成、動画メタデータ抽出、画像メタデータ抽出 |
| **Video** | フレーム抽出 5 枚、duration 取得、破損ファイル |
| **OCR** | 日本語テキスト抽出、英語テキスト抽出、信頼度計算 |
| **LP** | URL fetch、ローカル HTML 読み込み、フォーム項目抽出 |
| **LLM** | Hook 分類、Message Consistency 計算（モック LLM 使用） |
| **Converter** | file_only → v0.2 検証、file_plus_lp → v0.2 検証、kpi 入力 → v0.2 検証 |

### Integration Test
| シナリオ | 対応 |
|----------|------|
| **file_only**: 動画のみ → JSON 出力 | 全パイプライン + Converter 検証 |
| **file_plus_lp**: 動画 + LP → JSON 出力 | Ingestion → LLM → Converter |
| **file_plus_lp_plus_manual_kpi**: 完全版 | 全 Service + quantitative diagnostics |

---

## 📝 次のステップ
- `base_service.py`: 抽象基底クラス定義
- `analysis_orchestrator.py`: 呼び出し順を実装
- `cli/main.py`: Click エントリーポイント
- **`IngestionService`**: 実装開始
