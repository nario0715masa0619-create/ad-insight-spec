"""
5軸診断（decision_support）のテキスト入力モード判定。

現状の5軸診断は画面上テキスト（テロップ）への依存が強く、テロップ無し動画
では実質何も出せない。一方で「テロップ無し・音声ナレーションあり」という
実運用上よくあるパターンでは、ASR（音声文字起こし）を使えば5軸診断は
本来可能である。この判定ロジックは、動画を以下の3モードに分類する:

- TEXT_MODE_RICH:        画面上テキスト（テロップ）が動画尺の一定割合以上を占める
- TEXT_MODE_ASR_ONLY:    テロップはほぼ無いが、ASRの発話量が十分にある
- TEXT_MODE_INSUFFICIENT: テロップもASRもほぼ無い（BGMのみの動画等）

判定は外部依存を持たない純粋関数で行い、単体テストしやすくする。
呼び出し側（analysis_orchestrator）が video_cuts のOCR結果・ASR結果を渡す。
"""
from typing import Optional, Dict, Any, List

TEXT_MODE_RICH = "TEXT_MODE_RICH"
TEXT_MODE_ASR_ONLY = "TEXT_MODE_ASR_ONLY"
TEXT_MODE_INSUFFICIENT = "TEXT_MODE_INSUFFICIENT"

# 動画尺のうちこの割合以上に画面上テキストがあれば TEXT_MODE_RICH とみなす。
# ラフな閾値（ユーザー合意の上での目安値）。
OCR_COVERAGE_THRESHOLD = 0.3

# この文字数未満のOCR結果は、ロゴ・商品パッケージの小さな文字等の誤検知と
# みなし、「明示テキストがあるカット」としてカウントしない。
OCR_MIN_CHARS_PER_CUT = 6

# ASRテキストの最低文字数（これ未満は発話量不足の判断材料の一つ）
ASR_MIN_CHARS = 20

# ASRの発話区間合計の最低秒数（これ未満は発話量不足の判断材料の一つ）
ASR_MIN_SPEECH_SECONDS = 3.0

# Whisperが無音・BGMのみの音声に対してよく生成する定型句（品質ガード）。
# 全文がこれらのいずれかと一致する場合は「発話が無いのに生成された
# ハルシネーション」とみなし、ASRテキストを信頼しない。
ASR_HALLUCINATION_PHRASES = [
    "ご視聴ありがとうございました",
    "ご視聴ありがとうございます",
    "字幕視聴ありがとうございました",
    "ご視聴ありがとうございました。",
    "thanks for watching",
    "thank you for watching",
]


def compute_ocr_coverage_ratio(video_cuts: Optional[List[Dict[str, Any]]], total_duration: float) -> float:
    """
    video_cuts（cut_id/start_seconds/end_seconds/ocr_text を持つdictのリスト、
    analysis_orchestrator.self.video_cuts と同じ形式）から、
    OCR_MIN_CHARS_PER_CUT 以上の文字が検出されたカットの合計時間 /
    動画全体の尺 を返す。

    video_cuts が空、または total_duration が0以下の場合は 0.0（=RICHとは
    判定されない）を返す。
    """
    if not video_cuts or total_duration <= 0:
        return 0.0

    covered_seconds = 0.0
    for cut in video_cuts:
        ocr_text = (cut.get("ocr_text") or "").strip()
        if len(ocr_text) < OCR_MIN_CHARS_PER_CUT:
            continue
        start = cut.get("start_seconds") or 0.0
        end = cut.get("end_seconds") or start
        covered_seconds += max(end - start, 0.0)

    return min(covered_seconds / total_duration, 1.0)


def is_asr_reliable(asr_result: Optional[Dict[str, Any]]) -> bool:
    """
    asr_result（ASRService.transcribe の戻り値）が、5軸診断の主要な
    テキストソースとして使える程度に信頼できる発話量を含むかを判定する。
    """
    if not asr_result or not asr_result.get("success"):
        return False

    text = (asr_result.get("asr_text") or "").strip()
    if not text:
        return False

    # Whisperの無音/BGM時ハルシネーション定型句と完全一致する場合は信頼しない
    if text.rstrip("。.") in [p.rstrip("。.") for p in ASR_HALLUCINATION_PHRASES]:
        return False

    speech_duration = asr_result.get("speech_duration_seconds") or 0.0
    return len(text) >= ASR_MIN_CHARS or speech_duration >= ASR_MIN_SPEECH_SECONDS


def classify_text_mode(ocr_coverage_ratio: float, asr_result: Optional[Dict[str, Any]]) -> str:
    """
    OCRカバレッジとASR結果から、5軸診断のテキスト入力モードを1つ返す。
    """
    if ocr_coverage_ratio >= OCR_COVERAGE_THRESHOLD:
        return TEXT_MODE_RICH

    if is_asr_reliable(asr_result):
        return TEXT_MODE_ASR_ONLY

    return TEXT_MODE_INSUFFICIENT
