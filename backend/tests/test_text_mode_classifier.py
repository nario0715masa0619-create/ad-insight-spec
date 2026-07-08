import pytest

from app.services.text_mode_classifier import (
    compute_ocr_coverage_ratio,
    is_asr_reliable,
    classify_text_mode,
    TEXT_MODE_RICH,
    TEXT_MODE_ASR_ONLY,
    TEXT_MODE_INSUFFICIENT,
    OCR_COVERAGE_THRESHOLD,
    OCR_MIN_CHARS_PER_CUT,
    ASR_MIN_CHARS,
    ASR_MIN_SPEECH_SECONDS,
)


class TestComputeOcrCoverageRatio:
    def test_empty_video_cuts_returns_zero(self):
        assert compute_ocr_coverage_ratio([], 10.0) == 0.0

    def test_zero_duration_returns_zero(self):
        cuts = [{"ocr_text": "十分なテロップテキスト", "start_seconds": 0.0, "end_seconds": 10.0}]
        assert compute_ocr_coverage_ratio(cuts, 0.0) == 0.0

    def test_full_coverage(self):
        cuts = [{"ocr_text": "十分なテロップテキスト", "start_seconds": 0.0, "end_seconds": 10.0}]
        assert compute_ocr_coverage_ratio(cuts, 10.0) == 1.0

    def test_partial_coverage(self):
        cuts = [
            {"ocr_text": "十分なテロップテキスト", "start_seconds": 0.0, "end_seconds": 3.0},
            {"ocr_text": "", "start_seconds": 3.0, "end_seconds": 10.0},
        ]
        assert compute_ocr_coverage_ratio(cuts, 10.0) == pytest.approx(0.3)

    def test_short_ocr_text_below_min_chars_is_ignored(self):
        """OCR_MIN_CHARS_PER_CUT未満のテキスト（ロゴ等の誤検知想定）はカバレッジに含めない"""
        short_text = "a" * (OCR_MIN_CHARS_PER_CUT - 1)
        cuts = [{"ocr_text": short_text, "start_seconds": 0.0, "end_seconds": 10.0}]
        assert compute_ocr_coverage_ratio(cuts, 10.0) == 0.0

    def test_ocr_text_at_min_chars_is_counted(self):
        text = "a" * OCR_MIN_CHARS_PER_CUT
        cuts = [{"ocr_text": text, "start_seconds": 0.0, "end_seconds": 10.0}]
        assert compute_ocr_coverage_ratio(cuts, 10.0) == 1.0


class TestIsAsrReliable:
    def test_none_result_is_unreliable(self):
        assert is_asr_reliable(None) is False

    def test_failed_result_is_unreliable(self):
        assert is_asr_reliable({"success": False, "asr_text": "", "speech_duration_seconds": 0.0}) is False

    def test_empty_text_is_unreliable(self):
        assert is_asr_reliable({"success": True, "asr_text": "   ", "speech_duration_seconds": 5.0}) is False

    @pytest.mark.parametrize(
        "phrase",
        ["ご視聴ありがとうございました", "ご視聴ありがとうございました。", "thank you for watching"],
    )
    def test_known_hallucination_phrase_is_unreliable(self, phrase):
        assert is_asr_reliable({"success": True, "asr_text": phrase, "speech_duration_seconds": 1.0}) is False

    def test_sufficient_char_count_is_reliable(self):
        text = "x" * ASR_MIN_CHARS
        assert is_asr_reliable({"success": True, "asr_text": text, "speech_duration_seconds": 0.0}) is True

    def test_sufficient_speech_duration_is_reliable(self):
        assert is_asr_reliable(
            {"success": True, "asr_text": "短い発話", "speech_duration_seconds": ASR_MIN_SPEECH_SECONDS}
        ) is True

    def test_below_both_thresholds_is_unreliable(self):
        assert is_asr_reliable(
            {"success": True, "asr_text": "短い", "speech_duration_seconds": 0.5}
        ) is False


class TestClassifyTextMode:
    def test_high_ocr_coverage_is_rich_regardless_of_asr(self):
        assert classify_text_mode(OCR_COVERAGE_THRESHOLD, None) == TEXT_MODE_RICH
        assert classify_text_mode(1.0, None) == TEXT_MODE_RICH

    def test_low_ocr_with_reliable_asr_is_asr_only(self):
        asr_result = {"success": True, "asr_text": "x" * ASR_MIN_CHARS, "speech_duration_seconds": 5.0}
        assert classify_text_mode(0.0, asr_result) == TEXT_MODE_ASR_ONLY

    def test_low_ocr_without_asr_is_insufficient(self):
        assert classify_text_mode(0.0, None) == TEXT_MODE_INSUFFICIENT

    def test_low_ocr_with_unreliable_asr_is_insufficient(self):
        asr_result = {"success": True, "asr_text": "ご視聴ありがとうございました", "speech_duration_seconds": 1.0}
        assert classify_text_mode(0.1, asr_result) == TEXT_MODE_INSUFFICIENT

    def test_boundary_just_below_threshold_needs_asr(self):
        asr_result = {"success": True, "asr_text": "x" * ASR_MIN_CHARS, "speech_duration_seconds": 5.0}
        assert classify_text_mode(OCR_COVERAGE_THRESHOLD - 0.01, asr_result) == TEXT_MODE_ASR_ONLY
        assert classify_text_mode(OCR_COVERAGE_THRESHOLD - 0.01, None) == TEXT_MODE_INSUFFICIENT
