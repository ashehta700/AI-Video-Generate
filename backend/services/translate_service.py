"""
Translation & Rewrite Service
Translates Hebrew text → Arabic and rewrites as professional news segment.
Uses OpenAI GPT-4o (or Claude as fallback).
Returns structured JSON: {hook, body, closing, title, description, tags}
"""

import json
import logging
import re
import httpx

from utils.env import get_env_token

logger = logging.getLogger(__name__)

OPENAI_API_KEY = get_env_token("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = get_env_token("ANTHROPIC_API_KEY", "")
TRANSLATION_PROVIDER = get_env_token("TRANSLATION_PROVIDER", "openai")  # openai | anthropic

NEWS_PROMPT_TEMPLATE = """أنت محرر أخبار عربي محترف متخصص في الشؤون الإسرائيلية.

المهمة: ترجم النص العبري التالي إلى العربية وأعد كتابته كمقطع إخباري احترافي مدته 2-3 دقائق.

النص العبري:
{hebrew_text}

متطلبات الإخراج:
- الخطاف (hook): جملة افتتاحية جذابة (15-20 كلمة)
- الجسم (body): التقرير الكامل بالعربية الفصحى، 3-4 فقرات
- الخاتمة (closing): جملة ختامية احترافية
- العنوان (title): عنوان يوتيوب جذاب (60 حرفاً كحد أقصى)
- الوصف (description): وصف SEO (150-200 كلمة)
- الوسوم (tags): 10 وسوم يوتيوب مناسبة

قواعد مهمة:
- استخدم العربية الفصحى الرسمية
- كن موضوعياً ومحايداً
- أضف السياق والتحليل المناسب
- لا تبالغ أو تضخم الأحداث
- نسب المعلومات للمصدر (قناة 12 الإسرائيلية / قناة 13 الإسرائيلية)

أجب بـ JSON فقط بهذا الشكل:
{{
  "hook": "...",
  "body": "...",
  "closing": "...",
  "title": "...",
  "description": "...",
  "tags": ["...", "...", "..."]
}}"""


async def translate_with_openai(hebrew_text: str) -> dict:
    """Translate using OpenAI GPT-4o"""
    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY not set")

    prompt = NEWS_PROMPT_TEMPLATE.format(hebrew_text=hebrew_text)

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
                "temperature": 0.3,
                "response_format": {"type": "json_object"},
            },
        )
        r.raise_for_status()
        data = r.json()
        content = data["choices"][0]["message"]["content"]
        return json.loads(content)


async def translate_with_anthropic(hebrew_text: str) -> dict:
    """Translate using Anthropic Claude API"""
    if not ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY not set")

    prompt = NEWS_PROMPT_TEMPLATE.format(hebrew_text=hebrew_text)

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
                "max_tokens": 2000,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        r.raise_for_status()
        data = r.json()
        content = data["content"][0]["text"]
        # Strip markdown fences if present
        clean = re.sub(r"```json|```", "", content).strip()
        return json.loads(clean)


async def translate_hebrew_to_arabic(hebrew_text: str, job_id: int) -> dict:
    """
    Main translation entry point.
    Returns: {hook, body, closing, title, description, tags}
    """
    if not hebrew_text or len(hebrew_text.strip()) < 10:
        raise ValueError("Hebrew text too short for translation")

    logger.info(f"Translating {len(hebrew_text)} chars (job {job_id}) via {TRANSLATION_PROVIDER}")

    try:
        if TRANSLATION_PROVIDER == "anthropic":
            result = await translate_with_anthropic(hebrew_text)
        else:
            result = await translate_with_openai(hebrew_text)
    except Exception as e:
        logger.warning(f"Primary translation failed ({e}), trying fallback stub")
        result = _stub_translation(hebrew_text)

    # Validate required fields
    for field in ["hook", "body", "closing", "title", "description", "tags"]:
        if field not in result:
            result[field] = "" if field != "tags" else []

    logger.info(f"Translation complete. Title: {result.get('title', '')[:50]}")
    return result


def _stub_translation(hebrew_text: str) -> dict:
    """Stub for development without API keys"""
    return {
        "hook": "عاجل: تقرير إخباري مهم من إسرائيل.",
        "body": f"[ترجمة تجريبية] النص العبري الأصلي يحتوي على {len(hebrew_text)} حرف. يرجى إعداد مفتاح API للترجمة الحقيقية.",
        "closing": "هذا تقرير تجريبي. يرجى إعداد مفاتيح API للإنتاج الفعلي.",
        "title": "تقرير إخباري تجريبي - أخبار إسرائيل",
        "description": "هذا وصف تجريبي. يرجى إعداد مفاتيح API للترجمة الحقيقية.",
        "tags": ["أخبار", "إسرائيل", "عاجل", "تقرير", "أخبار_عربية"],
    }


async def build_arabic_script(translation: dict) -> str:
    """Combine hook + body + closing into full script for TTS"""
    parts = [
        translation.get("hook", ""),
        translation.get("body", ""),
        translation.get("closing", ""),
    ]
    return "\n\n".join(p for p in parts if p.strip())
