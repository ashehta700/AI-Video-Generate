"""Chill Mode Router — vertical 9:16 short clips"""
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from utils.database import get_db
from models.models import Clip, ClipSource
from services import pipeline_service
from utils.env import get_env_bool

router = APIRouter()

class ChillRequest(BaseModel):
    clip_url: str
    source: str = "manual"
    title: str = ""
    keywords: list[str] = []
    background_music: bool = False

@router.post("/run")
async def run_chill(
    req: ChillRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Run pipeline in chill/shorts mode (vertical 9:16)"""
    try:
        src = ClipSource(req.source)
    except ValueError:
        src = ClipSource.MANUAL

    clip = Clip(url=req.clip_url, source=src, title=req.title, keywords=req.keywords)
    db.add(clip)
    await db.commit()
    await db.refresh(clip)

    job_id = await pipeline_service.create_job_for_clip(clip.id, db, is_shorts=True)
    background_tasks.add_task(pipeline_service.run_pipeline, job_id, db, is_shorts=True)

    return {"job_id": job_id, "mode": "chill_shorts", "status": "started"}

@router.get("/status")
async def chill_status():
    enabled = get_env_bool("CHILL_MODE_ENABLED", True)
    return {"chill_mode_enabled": enabled}
