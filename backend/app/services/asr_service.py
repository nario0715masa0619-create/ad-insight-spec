"""
ASRService - 動画の音声トラックをOpenAI Whisper APIで文字起こしする

「テロップ無し・音声ナレーションあり」動画の5軸診断を有効化するための、
音声文字起こし専用サービス。VideoService/OCRServiceと同じ
fail-soft・subprocess+timeoutパターンに従う（例外を投げず、失敗時は
success=Falseの空結果を返す。呼び出し元の分析全体を巻き込まない）。

新規の外部依存は追加しない: 音声抽出は既存のffmpeg（VideoServiceで使用中）、
文字起こしは既存のOPENAI_API_KEYで使えるWhisper API（openaiパッケージは
既に依存関係に存在）を使う。
"""
import os
import subprocess
import tempfile
import shutil
from pathlib import Path
from typing import Dict, Any
import logging

import httpx
import openai

from app.services.base_service import ProcessingError

logger = logging.getLogger(__name__)


class ASRService:
    """音声抽出 + Whisper APIによる文字起こし"""

    WHISPER_MODEL = "whisper-1"
    AUDIO_EXTRACT_TIMEOUT_SECONDS = 30
    TRANSCRIBE_TIMEOUT_SECONDS = 60

    @staticmethod
    def _extract_audio(video_path: str, output_dir: str) -> str:
        """
        音声トラックのみをmp3として抽出する。

        Whisper APIのファイルサイズ上限（25MB）を確実に下回らせるため、
        動画ファイルをそのまま渡さず音声のみ抽出する（モノラル・16kHz、
        音声認識用途としては十分な品質でファイルサイズを抑える）。

        Returns:
            抽出した音声ファイルのパス。失敗時は None（fail-soft）。
        """
        output_path = str(Path(output_dir) / "audio.mp3")
        cmd = [
            "ffmpeg",
            "-i", video_path,
            "-vn",
            "-ac", "1",
            "-ar", "16000",
            "-y",
            output_path,
        ]
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=ASRService.AUDIO_EXTRACT_TIMEOUT_SECONDS
        )
        if result.returncode != 0 or not Path(output_path).exists():
            raise ProcessingError(f"Audio extraction failed: {result.stderr[-300:]}")
        return output_path

    @staticmethod
    def transcribe(video_path: str) -> Dict[str, Any]:
        """
        動画の音声トラックをWhisper APIで文字起こしする。

        Returns（成功時）:
            {"success": True, "asr_text": str, "speech_duration_seconds": float}
        Returns（失敗時・音声トラック無し・APIキー未設定等、常にfail-soft）:
            {"success": False, "asr_text": "", "speech_duration_seconds": 0.0}

        例外は投げない（動画分析全体を巻き込まないため、ここで必ず吸収する）。
        """
        empty_result = {"success": False, "asr_text": "", "speech_duration_seconds": 0.0}

        from app.config import get_settings
        settings = get_settings()
        openai_api_key = settings.OPENAI_API_KEY
        if not openai_api_key:
            logger.warning("ASR transcription skipped: OPENAI_API_KEY is not configured")
            return empty_result

        temp_dir = tempfile.mkdtemp(prefix="ad_insight_asr_")
        try:
            try:
                audio_path = ASRService._extract_audio(video_path, temp_dir)
            except Exception as e:
                logger.warning(f"ASR audio extraction failed (non-fatal): {str(e)}")
                return empty_result

            try:
                proxy_url = os.getenv("HTTP_PROXY") or os.getenv("HTTPS_PROXY")
                http_client = httpx.Client(
                    proxy=proxy_url, timeout=ASRService.TRANSCRIBE_TIMEOUT_SECONDS
                ) if proxy_url else httpx.Client(timeout=ASRService.TRANSCRIBE_TIMEOUT_SECONDS)
                client = openai.OpenAI(api_key=openai_api_key, http_client=http_client)

                with open(audio_path, "rb") as audio_file:
                    response = client.audio.transcriptions.create(
                        model=ASRService.WHISPER_MODEL,
                        file=audio_file,
                        response_format="verbose_json",
                    )

                asr_text = (getattr(response, "text", "") or "").strip()
                segments = getattr(response, "segments", None) or []
                speech_duration = 0.0
                for seg in segments:
                    seg_start = seg.get("start") if isinstance(seg, dict) else getattr(seg, "start", 0.0)
                    seg_end = seg.get("end") if isinstance(seg, dict) else getattr(seg, "end", 0.0)
                    speech_duration += max((seg_end or 0.0) - (seg_start or 0.0), 0.0)

                return {
                    "success": bool(asr_text),
                    "asr_text": asr_text,
                    "speech_duration_seconds": round(speech_duration, 2),
                }
            except Exception as e:
                logger.warning(f"ASR transcription failed (non-fatal): {str(e)}")
                return empty_result
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
