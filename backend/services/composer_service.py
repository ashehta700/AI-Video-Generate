"""
Video Composer Service v2
Merges: source video + AI voice + subtitles + watermark
Supports landscape (16:9) and shorts (9:16) formats.
"""

import asyncio
import logging
import os
import tempfile
from pathlib import Path
from typing import Optional

from utils.storage import get_path
from utils.env import get_env_value

logger = logging.getLogger(__name__)

FFMPEG_BIN = get_env_value("FFMPEG_BIN", "ffmpeg")
FONT_PATH = get_env_value("FONT_PATH", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")


def _build_srt(segments: list[dict]) -> str:
    def ts(s: float) -> str:
        h, m = int(s // 3600), int((s % 3600) // 60)
        sec, ms = int(s % 60), int((s % 1) * 1000)
        return f"{h:02d}:{m:02d}:{sec:02d},{ms:03d}"

    lines = []
    for i, seg in enumerate(segments, 1):
        lines += [str(i), f"{ts(seg['start'])} --> {ts(seg['end'])}", seg.get("text", ""), ""]
    return "\n".join(lines)


async def compose_video(
    video_path: str,
    tts_path: str,
    subtitle_segments: list[dict],
    source_label: str,
    watermark_text: str,
    job_id: int,
    is_shorts: bool = False,
) -> str:
    if not Path(video_path).exists():
        raise FileNotFoundError(f"Video not found: {video_path}")
    if not Path(tts_path).exists():
        raise FileNotFoundError(f"TTS not found: {tts_path}")

    suffix = "shorts" if is_shorts else "composed"
    output_path = get_path(suffix, f"{suffix}_job{job_id}.mp4")

    # Write SRT file
    srt_content = _build_srt(subtitle_segments)
    srt_file = os.path.join(tempfile.gettempdir(), f"subs_job{job_id}.srt")
    with open(srt_file, "w", encoding="utf-8") as f:
        f.write(srt_content)

    safe_srt = srt_file.replace("\\", "\\\\").replace(":", "\\:")
    wm = (watermark_text or source_label)[:50]
    safe_wm = wm.replace("'", "\\'").replace(":", "\\:")

    font_style = f"FontSize=24,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,Outline=2,Alignment=2"

    if is_shorts:
        vf = (
            f"crop=ih*9/16:ih,"
            f"scale=1080:1920,"
            f"subtitles='{safe_srt}':force_style='{font_style.replace('24', '20')}',"
            f"drawtext=text='{safe_wm}':fontsize=16:fontcolor=white@0.6:x=10:y=10"
        )
    else:
        vf = (
            f"scale=1920:1080:force_original_aspect_ratio=decrease,"
            f"pad=1920:1080:(ow-iw)/2:(oh-ih)/2,"
            f"subtitles='{safe_srt}':force_style='{font_style}',"
            f"drawtext=text='{safe_wm}':fontsize=20:fontcolor=white@0.7:x=20:y=20"
        )

    cmd = [
        FFMPEG_BIN, "-y",
        "-i", video_path,
        "-i", tts_path,
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-vf", vf,
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k",
        "-shortest",
        "-movflags", "+faststart",
        output_path,
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    _, stderr = await proc.communicate()

    if proc.returncode != 0:
        err = stderr.decode("utf-8", errors="replace")
        logger.error(f"FFmpeg failed: {err[-500:]}")
        raise RuntimeError(f"Compose failed: {err[-300:]}")

    size_mb = Path(output_path).stat().st_size / (1024 * 1024)
    logger.info(f"Composed: {output_path} ({size_mb:.1f} MB)")

    try:
        os.remove(srt_file)
    except Exception:
        pass

    return output_path
