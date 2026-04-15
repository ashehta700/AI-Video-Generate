"""
Audio Extraction Service
Extracts audio from video files using FFmpeg.
Output: 16kHz mono WAV (optimal for Whisper)
"""

import asyncio
import logging
import subprocess
from pathlib import Path

from utils.storage import get_path, timestamped_filename
from utils.env import get_env_value

logger = logging.getLogger(__name__)

FFMPEG_BIN = get_env_value("FFMPEG_BIN", "ffmpeg")


async def extract_audio(video_path: str, job_id: int) -> str:
    """
    Extract audio from video file.
    Returns path to extracted WAV file.
    """
    if not Path(video_path).exists():
        raise FileNotFoundError(f"Video not found: {video_path}")

    output_filename = f"audio_job{job_id}.wav"
    output_path = get_path("audio", output_filename)

    cmd = [
        FFMPEG_BIN,
        "-y",                        # overwrite
        "-i", video_path,
        "-vn",                       # no video
        "-acodec", "pcm_s16le",      # PCM 16-bit
        "-ar", "16000",              # 16kHz sample rate (Whisper optimal)
        "-ac", "1",                  # mono
        "-af", "loudnorm",           # normalize loudness
        output_path,
    ]

    logger.info(f"Extracting audio from {video_path} → {output_path}")
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()

    if proc.returncode != 0:
        error = stderr.decode("utf-8", errors="replace")
        logger.error(f"FFmpeg audio extraction failed: {error}")
        raise RuntimeError(f"FFmpeg failed: {error[-300:]}")

    size_mb = Path(output_path).stat().st_size / (1024 * 1024)
    logger.info(f"Audio extracted: {output_path} ({size_mb:.1f} MB)")
    return output_path


async def get_video_info(video_path: str) -> dict:
    """Get video metadata using ffprobe"""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_format", "-show_streams",
        video_path,
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    if proc.returncode != 0:
        return {}
    import json
    try:
        return json.loads(stdout.decode())
    except Exception:
        return {}


async def trim_video(
    video_path: str,
    start: float,
    end: float,
    output_path: str,
) -> str:
    """Trim video segment from start to end seconds"""
    duration = end - start
    cmd = [
        FFMPEG_BIN, "-y",
        "-ss", str(start),
        "-i", video_path,
        "-t", str(duration),
        "-c:v", "libx264",
        "-c:a", "aac",
        "-preset", "fast",
        output_path,
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"Trim failed: {stderr.decode()[-200:]}")
    return output_path
