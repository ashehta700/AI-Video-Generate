"""Settings Router — manage app configuration"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from utils.database import get_db
from models.models import AppSettings
from typing import Optional
import json

router = APIRouter()

DEFAULTS = {
    "keywords": json.dumps(["מלחמה", "עזה", "הסכם", "ביטחון", "ממשלה", "ירי", "פיגוע"]),
    "max_videos_per_day": "3",
    "video_length_min": "2",
    "video_length_max": "5",
    "voice_style": "news",
    "upload_hour_utc": "15",
    "chill_mode_enabled": "true",
    "ai_thumbnail": "true",
    "translation_provider": "openai",
    "tts_provider": "elevenlabs",
    "watermark_text": "arabic-news-auto",
}


async def get_setting(db: AsyncSession, key: str) -> Optional[str]:
    result = await db.execute(select(AppSettings).where(AppSettings.key == key))
    rec = result.scalar_one_or_none()
    if rec:
        return rec.value
    return DEFAULTS.get(key)


async def set_setting(db: AsyncSession, key: str, value: str):
    result = await db.execute(select(AppSettings).where(AppSettings.key == key))
    rec = result.scalar_one_or_none()
    if rec:
        rec.value = value
    else:
        rec = AppSettings(key=key, value=value)
        db.add(rec)
    await db.commit()


class SettingsUpdate(BaseModel):
    keywords: Optional[list[str]] = None
    max_videos_per_day: Optional[int] = None
    video_length_min: Optional[int] = None
    video_length_max: Optional[int] = None
    voice_style: Optional[str] = None
    upload_hour_utc: Optional[int] = None
    chill_mode_enabled: Optional[bool] = None
    ai_thumbnail: Optional[bool] = None
    translation_provider: Optional[str] = None
    tts_provider: Optional[str] = None
    watermark_text: Optional[str] = None


@router.get("/")
async def get_all_settings(db: AsyncSession = Depends(get_db)):
    settings = {}
    for key, default in DEFAULTS.items():
        val = await get_setting(db, key)
        # Try to parse JSON
        try:
            settings[key] = json.loads(val)
        except (json.JSONDecodeError, TypeError):
            settings[key] = val
    return settings


@router.put("/")
async def update_settings(body: SettingsUpdate, db: AsyncSession = Depends(get_db)):
    updates = body.model_dump(exclude_none=True)
    for key, value in updates.items():
        if isinstance(value, (list, dict)):
            str_val = json.dumps(value, ensure_ascii=False)
        else:
            str_val = str(value).lower() if isinstance(value, bool) else str(value)
        await set_setting(db, key, str_val)
    return {"updated": list(updates.keys())}


@router.get("/{key}")
async def get_single_setting(key: str, db: AsyncSession = Depends(get_db)):
    val = await get_setting(db, key)
    if val is None:
        raise HTTPException(status_code=404, detail=f"Setting '{key}' not found")
    try:
        return {key: json.loads(val)}
    except Exception:
        return {key: val}
