"""
AI Script Generation Service v2
────────────────────────────────────────────────────────────────────────────────
Generates professional video scripts from source content.
- Works for ANY topic (news, sports, tech, lifestyle, gaming, finance, etc.)
- Output language configurable (Arabic, English, French, Spanish, etc.)
- Uses Claude (Anthropic) as primary, OpenAI GPT-4o as fallback
- Returns structured JSON: {hook, body, closing, title, description, tags, cta}
"""

import json
import logging
import re
import httpx

from utils.env import get_env_token, get_env_value

logger = logging.getLogger(__name__)

ANTHROPIC_API_KEY = get_env_token("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY = get_env_token("OPENAI_API_KEY", "")
AI_PROVIDER = get_env_token("AI_PROVIDER", "anthropic")  # anthropic | openai

# Output language for generated scripts
OUTPUT_LANGUAGE = get_env_value("OUTPUT_LANGUAGE", "Arabic")

SCRIPT_PROMPT_TEMPLATE = """You are a professional YouTube content creator and scriptwriter.

TASK: Transform the following source content into an engaging YouTube video script.

SOURCE TITLE: {title}
SOURCE CONTENT/TRANSCRIPT: {content}
TOPIC KEYWORDS: {keywords}
VIDEO DURATION TARGET: {duration_minutes} minutes

REQUIREMENTS:
- Output language: {output_language}
- Tone: Professional, engaging, authoritative
- Style: Suitable for YouTube audience
- Include proper attribution to original source

OUTPUT FORMAT (JSON only, no markdown):
{{
  "hook": "Attention-grabbing opening line (15-25 words)",
  "body": "Full video script with 3-5 paragraphs. Natural speech rhythm. Include key facts and analysis.",
  "closing": "Strong call-to-action ending (subscribe, comment, like)",
  "title": "Optimized YouTube title (max 70 chars) — include numbers/power words",
  "description": "SEO-optimized YouTube description (200-300 words). Include timestamps placeholder, links section, hashtags.",
  "tags": ["tag1", "tag2", "tag3", "tag4", "tag5", "tag6", "tag7", "tag8", "tag9", "tag10"],
  "cta": "Subscribe CTA text in {output_language}",
  "thumbnail_prompt": "DALL-E prompt for a dramatic eye-catching thumbnail background image (no text, no people, dramatic lighting)",
  "category": "YouTube category (e.g. News, Technology, Sports, Entertainment, Education)"
}}

Rules:
- Use {output_language} for hook, body, closing, cta
- Use {output_language} for title and description  
- Tags can be multilingual for better reach
- Be factual and cite sources
- Make it compelling and watch-worthy
- hook must be in {output_language}"""


async def generate_script_anthropic(
    title: str,
    content: str,
    keywords: list[str],
    output_language: str,
    duration_minutes: int = 3,
) -> dict:
    """Generate script using Anthropic Claude"""
    if not ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY not set")

    prompt = SCRIPT_PROMPT_TEMPLATE.format(
        title=title,
        content=content[:3000],
        keywords=", ".join(keywords),
        output_language=output_language,
        duration_minutes=duration_minutes,
    )

    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-5-20251022",
                "max_tokens": 3000,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        r.raise_for_status()
        data = r.json()
        text = data["content"][0]["text"]
        clean = re.sub(r"```json|```", "", text).strip()
        return json.loads(clean)


async def generate_script_openai(
    title: str,
    content: str,
    keywords: list[str],
    output_language: str,
    duration_minutes: int = 3,
) -> dict:
    """Generate script using OpenAI GPT-4o"""
    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY not set")

    prompt = SCRIPT_PROMPT_TEMPLATE.format(
        title=title,
        content=content[:3000],
        keywords=", ".join(keywords),
        output_language=output_language,
        duration_minutes=duration_minutes,
    )

    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "gpt-4o",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.4,
                "response_format": {"type": "json_object"},
            },
        )
        r.raise_for_status()
        data = r.json()
        return json.loads(data["choices"][0]["message"]["content"])


def _stub_script(title: str, keywords: list[str], language: str) -> dict:
    """Fallback stub when no AI API is configured"""
    return {
        "hook": f"Breaking content about {', '.join(keywords[:2])}",
        "body": f"[STUB] This is a generated script for: {title}. Configure AI_PROVIDER and API keys for real content generation.",
        "closing": "Subscribe for more content!",
        "title": title[:70],
        "description": f"Video about {', '.join(keywords)}. Configure API keys for full description generation.",
        "tags": keywords[:10],
        "cta": "Subscribe and like this video!",
        "thumbnail_prompt": f"dramatic cinematic background related to {keywords[0] if keywords else 'news'}",
        "category": "News & Politics",
    }


async def generate_video_script(
    title: str,
    content: str,
    keywords: list[str],
    output_language: str = None,
    duration_minutes: int = 3,
    job_id: int = 0,
) -> dict:
    """
    Main script generation entry point.
    Tries primary provider, falls back to secondary, then stub.
    """
    lang = output_language or OUTPUT_LANGUAGE
    logger.info(f"Generating script (job {job_id}): '{title[:60]}' → {lang}")

    try:
        if AI_PROVIDER == "anthropic" and ANTHROPIC_API_KEY:
            result = await generate_script_anthropic(title, content, keywords, lang, duration_minutes)
        elif OPENAI_API_KEY:
            result = await generate_script_openai(title, content, keywords, lang, duration_minutes)
        elif ANTHROPIC_API_KEY:
            result = await generate_script_anthropic(title, content, keywords, lang, duration_minutes)
        else:
            logger.warning("No AI API configured — using stub script")
            result = _stub_script(title, keywords, lang)
    except Exception as e:
        logger.error(f"Script generation failed: {e}")
        try:
            # Fallback to alternate provider
            if AI_PROVIDER == "anthropic" and OPENAI_API_KEY:
                result = await generate_script_openai(title, content, keywords, lang, duration_minutes)
            elif ANTHROPIC_API_KEY:
                result = await generate_script_anthropic(title, content, keywords, lang, duration_minutes)
            else:
                result = _stub_script(title, keywords, lang)
        except Exception as e2:
            logger.error(f"Fallback script generation also failed: {e2}")
            result = _stub_script(title, keywords, lang)

    # Ensure all required fields exist
    required = ["hook", "body", "closing", "title", "description", "tags", "cta", "thumbnail_prompt", "category"]
    for field in required:
        if field not in result:
            result[field] = [] if field == "tags" else ""

    logger.info(f"Script ready (job {job_id}): '{result.get('title', '')[:50]}'")
    return result


def build_tts_script(script: dict) -> str:
    """Combine hook + body + closing into full narration for TTS"""
    parts = [
        script.get("hook", ""),
        script.get("body", ""),
        script.get("closing", ""),
        script.get("cta", ""),
    ]
    return "\n\n".join(p for p in parts if p.strip())
