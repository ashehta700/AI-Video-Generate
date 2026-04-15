"""
Thumbnail Generation Service
Creates Arabic-text overlaid thumbnails.
Uses Pillow for compositing + DALL-E 3 for AI background (optional).
"""

import asyncio
import logging
import textwrap
from pathlib import Path
from typing import Optional
import httpx

from utils.storage import get_path
from utils.env import get_env_int, get_env_token, get_env_value

logger = logging.getLogger(__name__)

OPENAI_API_KEY = get_env_token("OPENAI_API_KEY", "")
THUMBNAIL_WIDTH = get_env_int("THUMBNAIL_WIDTH", 1280)
THUMBNAIL_HEIGHT = get_env_int("THUMBNAIL_HEIGHT", 720)

# Color scheme for thumbnail
BG_GRADIENT_START = get_env_value("THUMB_COLOR_START", "#1a1a2e")
BG_GRADIENT_END = get_env_value("THUMB_COLOR_END", "#16213e")
ACCENT_COLOR = get_env_value("THUMB_ACCENT", "#e94560")
TEXT_COLOR = get_env_value("THUMB_TEXT_COLOR", "#ffffff")


async def generate_ai_background(prompt: str) -> Optional[bytes]:
    """Generate background image using DALL-E 3"""
    if not OPENAI_API_KEY:
        return None
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(
                "https://api.openai.com/v1/images/generations",
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                json={
                    "model": "dall-e-3",
                    "prompt": f"News thumbnail background, dramatic lighting, {prompt}, no text, professional broadcast quality",
                    "size": "1792x1024",
                    "quality": "standard",
                    "n": 1,
                },
            )
            r.raise_for_status()
            data = r.json()
            img_url = data["data"][0]["url"]
            img_r = await client.get(img_url)
            return img_r.content
    except Exception as e:
        logger.warning(f"DALL-E thumbnail background failed: {e}")
        return None


def create_thumbnail_pillow(
    title: str,
    source_label: str,
    job_id: int,
    bg_image_bytes: Optional[bytes] = None,
) -> str:
    """Create thumbnail using Pillow"""
    try:
        from PIL import Image, ImageDraw, ImageFont, ImageFilter
        import io
        import struct

        output_path = get_path("thumbnails", f"thumb_job{job_id}.jpg")
        W, H = THUMBNAIL_WIDTH, THUMBNAIL_HEIGHT

        # Background
        if bg_image_bytes:
            try:
                bg = Image.open(io.BytesIO(bg_image_bytes)).convert("RGB")
                bg = bg.resize((W, H), Image.LANCZOS)
                bg = bg.filter(ImageFilter.GaussianBlur(3))
            except Exception:
                bg = _create_gradient(W, H)
        else:
            bg = _create_gradient(W, H)

        draw = ImageDraw.Draw(bg)

        # Dark overlay for text readability
        overlay = Image.new("RGBA", (W, H), (0, 0, 0, 120))
        bg = bg.convert("RGBA")
        bg = Image.alpha_composite(bg, overlay)
        draw = ImageDraw.Draw(bg)

        # Accent bar
        accent = tuple(int(ACCENT_COLOR.lstrip("#")[i:i+2], 16) for i in (0, 2, 4)) + (255,)
        draw.rectangle([0, H - 80, W, H], fill=accent)

        # Load fonts (fallback to default)
        try:
            font_large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 72)
            font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 32)
        except Exception:
            font_large = ImageFont.load_default()
            font_small = font_large

        # Title text (wrapped)
        wrapped = textwrap.fill(title, width=25)
        text_color = (255, 255, 255, 255)
        shadow_color = (0, 0, 0, 200)

        # Shadow
        draw.text((42, 62), wrapped, font=font_large, fill=shadow_color)
        # Title
        draw.text((40, 60), wrapped, font=font_large, fill=text_color)

        # Source label
        source_text = f"المصدر: {source_label}"
        draw.text((30, H - 60), source_text, font=font_small, fill=(255, 255, 255, 255))

        # Breaking news badge
        badge_color = (220, 20, 60, 255)
        draw.rectangle([W - 280, 20, W - 20, 75], fill=badge_color)
        draw.text((W - 270, 28), "عاجل ⚡", font=font_small, fill=(255, 255, 255, 255))

        # Save
        final = bg.convert("RGB")
        final.save(output_path, "JPEG", quality=90)
        logger.info(f"Thumbnail created: {output_path}")
        return output_path

    except ImportError:
        logger.warning("Pillow not installed — creating stub thumbnail")
        return _create_stub_thumbnail(job_id)


def _create_gradient(w: int, h: int):
    """Create a simple dark gradient background"""
    from PIL import Image
    img = Image.new("RGB", (w, h))
    for y in range(h):
        r = int(26 + (22 - 26) * y / h)
        g = int(26 + (33 - 26) * y / h)
        b = int(46 + (62 - 46) * y / h)
        for x in range(w):
            img.putpixel((x, y), (r, g, b))
    return img


def _create_stub_thumbnail(job_id: int) -> str:
    """Minimal stub when Pillow unavailable"""
    output_path = get_path("thumbnails", f"thumb_job{job_id}.txt")
    with open(output_path, "w") as f:
        f.write(f"STUB THUMBNAIL for job {job_id}\n")
    return output_path


async def generate_thumbnail(
    title: str,
    source_label: str,
    job_id: int,
    ai_background: bool = True,
    ai_prompt: str = "",
) -> str:
    """
    Main thumbnail generation entry point.
    Returns path to thumbnail image.
    """
    logger.info(f"Generating thumbnail for job {job_id}: {title[:50]}")

    bg_bytes = None
    prompt = ai_prompt.strip() if ai_prompt else title
    if ai_background and OPENAI_API_KEY:
        bg_bytes = await generate_ai_background(prompt[:200])

    loop = asyncio.get_event_loop()
    path = await loop.run_in_executor(
        None,
        create_thumbnail_pillow,
        title, source_label, job_id, bg_bytes,
    )
    return path
