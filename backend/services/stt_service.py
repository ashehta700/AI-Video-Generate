"""
Speech-to-Text Service
Transcribes Hebrew audio using faster-whisper (Whisper-compatible, faster).
Returns timestamped transcript in JSON format.
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Optional

from utils.env import get_env_value

logger = logging.getLogger(__name__)

WHISPER_MODEL = get_env_value("WHISPER_MODEL", "medium")  # tiny, base, small, medium, large-v3
WHISPER_DEVICE = get_env_value("WHISPER_DEVICE", "cpu")   # cpu or cuda
WHISPER_COMPUTE = get_env_value("WHISPER_COMPUTE_TYPE", "int8")

_model = None  # Lazy-loaded singleton


def _load_model():
    global _model
    if _model is None:
        try:
            from faster_whisper import WhisperModel
            logger.info(f"Loading Whisper model: {WHISPER_MODEL} on {WHISPER_DEVICE}")
            _model = WhisperModel(
                WHISPER_MODEL,
                device=WHISPER_DEVICE,
                compute_type=WHISPER_COMPUTE,
            )
            logger.info("Whisper model loaded ✓")
        except ImportError:
            logger.warning("faster-whisper not installed — using stub")
            _model = "stub"
    return _model


def _transcribe_sync(audio_path: str) -> dict:
    """Synchronous transcription (runs in executor)"""
    model = _load_model()

    if model == "stub":
        # Stub for dev without GPU/model
        return {
            "text": "[STUB] Hebrew transcription placeholder. Install faster-whisper.",
            "language": "he",
            "segments": [
                {"id": 0, "start": 0.0, "end": 5.0, "text": "[STUB] Hebrew text", "confidence": 0.9}
            ],
        }

    segments_raw, info = model.transcribe(
        audio_path,
        language="he",
        beam_size=5,
        word_timestamps=True,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 500},
    )

    segments = []
    full_text_parts = []

    for seg in segments_raw:
        segments.append({
            "id": seg.id,
            "start": round(seg.start, 2),
            "end": round(seg.end, 2),
            "text": seg.text.strip(),
            "confidence": round(seg.avg_logprob, 3) if hasattr(seg, "avg_logprob") else None,
        })
        full_text_parts.append(seg.text.strip())

    return {
        "text": " ".join(full_text_parts),
        "language": info.language,
        "language_probability": round(info.language_probability, 3),
        "duration": round(info.duration, 2),
        "segments": segments,
    }


async def transcribe_audio(audio_path: str, job_id: int) -> dict:
    """
    Transcribe audio file asynchronously.
    Returns dict: {text, language, segments: [{id, start, end, text}]}
    """
    if not Path(audio_path).exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    logger.info(f"Transcribing {audio_path} (job {job_id})...")

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, _transcribe_sync, audio_path)

    logger.info(
        f"Transcription complete: {len(result['segments'])} segments, "
        f"language={result['language']}"
    )

    # Save transcript JSON alongside audio
    transcript_path = str(audio_path).replace(".wav", "_transcript.json")
    with open(transcript_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    return result


async def get_transcript_text(transcript_json: dict) -> str:
    """Extract plain text from transcript JSON"""
    return transcript_json.get("text", "")


async def build_srt(segments: list[dict]) -> str:
    """Convert Whisper segments to SRT subtitle format"""

    def fmt_time(seconds: float) -> str:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        ms = int((seconds % 1) * 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    lines = []
    for i, seg in enumerate(segments, 1):
        lines.append(str(i))
        lines.append(f"{fmt_time(seg['start'])} --> {fmt_time(seg['end'])}")
        lines.append(seg["text"])
        lines.append("")

    return "\n".join(lines)
