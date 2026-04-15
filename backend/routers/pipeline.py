"""
Pipeline Router - manage and trigger the full pipeline
"""

import logging
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from utils.database import get_db
from models.models import Job, Clip, JobStatus, ClipSource
from services import pipeline_service

logger = logging.getLogger(__name__)
router = APIRouter()


class RunPipelineRequest(BaseModel):
    clip_url: Optional[str] = None
    source: str = "manual"
    title: Optional[str] = None
    keywords: list[str] = []
    chill_mode: bool = False
    voice_style: Optional[str] = "default"
    content_style: Optional[str] = "default"
    add_music: bool = True
    add_emojis: bool = True
    is_kids: bool = False
    duration_seconds: Optional[int] = 60
    hook_style: Optional[str] = "question"
    language: Optional[str] = None


class DailyPipelineRequest(BaseModel):
    keywords: list[str] = []
    max_videos: int = 3
    language: Optional[str] = None
    is_shorts: bool = False
    is_kids: bool = False


@router.get("/jobs")
async def list_jobs(limit: int = 20, db: AsyncSession = Depends(get_db)):
    """List recent pipeline jobs"""
    result = await db.execute(
        select(Job).order_by(desc(Job.created_at)).limit(limit)
    )
    jobs = result.scalars().all()
    return [
        {
            "id": j.id,
            "clip_id": j.clip_id,
            "status": j.status.value if hasattr(j.status, 'value') else j.status,
            "stage": j.stage,
            "is_chill_mode": j.is_chill_mode,
            "youtube_video_id": j.youtube_video_id,
            "youtube_url": j.youtube_url,
            "thumbnail_approved": j.thumbnail_approved,
            "subtitle_approved": j.subtitle_approved,
            "error_message": j.error_message,
            "created_at": j.created_at.isoformat() if j.created_at else None,
            "completed_at": j.completed_at.isoformat() if j.completed_at else None,
        }
        for j in jobs
    ]


@router.get("/jobs/{job_id}")
async def get_job(job_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "id": job.id,
        "clip_id": job.clip_id,
        "status": job.status.value if hasattr(job.status, 'value') else job.status,
        "stage": job.stage,
        "is_chill_mode": job.is_chill_mode,
        "audio_path": job.audio_path,
        "transcript_json": job.transcript_json,
        "translation_json": job.translation_json,
        "tts_path": job.tts_path,
        "composed_video_path": job.composed_video_path,
        "thumbnail_path": job.thumbnail_path,
        "metadata_json": job.metadata_json,
        "youtube_video_id": job.youtube_video_id,
        "youtube_url": job.youtube_url,
        "subtitle_approved": job.subtitle_approved,
        "thumbnail_approved": job.thumbnail_approved,
        "error_message": job.error_message,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


@router.post("/run")
async def run_pipeline(
    request: RunPipelineRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Trigger pipeline - auto-searches if no URL provided"""
    
    # If no URL provided, trigger auto-search pipeline
    if not request.clip_url or not request.clip_url.strip():
        logger.info(f"Auto-search mode: keywords={request.keywords}")
        # Create a placeholder clip for tracking
        clip = Clip(
            url="auto-search",
            source="manual",  # Use valid enum value
            title=f"Auto: {', '.join(request.keywords[:3])}",
            keywords=request.keywords,
        )
        db.add(clip)
        await db.commit()
        await db.refresh(clip)
        
        job_id = await pipeline_service.create_job_for_clip(
            clip.id, db, is_shorts=request.chill_mode
        )
        
        # Trigger auto-search pipeline
        background_tasks.add_task(
            pipeline_service.run_auto_search_pipeline, job_id, db,
            keywords=request.keywords,
            is_shorts=request.chill_mode,
            voice_style=request.voice_style,
            is_kids=request.is_kids,
            output_language=request.language,
        )
        
        return {"job_id": job_id, "clip_id": clip.id, "status": "auto_search"}
    
    # URL provided - use existing logic
    try:
        source = ClipSource(request.source)
        source_value = source.value
    except ValueError:
        source_value = "manual"

    clip = Clip(
        url=request.clip_url,
        source=source_value,
        title=request.title,
        keywords=request.keywords,
    )
    db.add(clip)
    await db.commit()
    await db.refresh(clip)

    job_id = await pipeline_service.create_job_for_clip(
        clip.id, db, is_shorts=request.chill_mode
    )

    background_tasks.add_task(
        pipeline_service.run_pipeline, job_id, db, 
        is_shorts=request.chill_mode,
        voice_style=request.voice_style,
        content_style=request.content_style,
        add_music=request.add_music,
        add_emojis=request.add_emojis,
        is_kids=request.is_kids,
        duration_seconds=request.duration_seconds,
        hook_style=request.hook_style,
        output_language=request.language,
    )

    return {"job_id": job_id, "clip_id": clip.id, "status": "started"}


@router.post("/daily")
async def run_daily(
    request: DailyPipelineRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Trigger daily scrape + pipeline"""
    background_tasks.add_task(
        pipeline_service.run_daily_pipeline,
        db,
        request.keywords,
        request.language or "Arabic",
        request.max_videos,
        is_shorts=request.is_shorts,
    )
    return {"status": "daily pipeline started", "keywords": request.keywords, "type": "shorts" if request.is_shorts else "full"}


@router.post("/jobs/{job_id}/approve")
async def approve_job(
    job_id: int,
    subtitle: Optional[bool] = None,
    thumbnail: Optional[bool] = None,
    db: AsyncSession = Depends(get_db),
):
    """Approve or reject subtitle/thumbnail for a job"""
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if subtitle is not None:
        job.subtitle_approved = subtitle
    if thumbnail is not None:
        job.thumbnail_approved = thumbnail

    db.add(job)
    await db.commit()
    return {"job_id": job_id, "subtitle_approved": job.subtitle_approved, "thumbnail_approved": job.thumbnail_approved}


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(
    job_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Cancel/kill a running job"""
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    job.status = JobStatus.FAILED
    job.error_message = "Cancelled by user"
    job.completed_at = datetime.now(timezone.utc)
    db.add(job)
    await db.commit()
    return {"job_id": job_id, "status": "cancelled"}


@router.post("/jobs/{job_id}/retry")
async def retry_job(
    job_id: int,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Retry a failed job"""
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    job.status = JobStatus.PENDING
    job.error_message = None
    job.retry_count = (job.retry_count or 0) + 1
    await db.commit()
    
    # Trigger the job to run
    background_tasks.add_task(
        pipeline_service.run_pipeline, job_id, db, is_shorts=job.is_chill_mode
    )
    
    return {"job_id": job_id, "status": "running"}


@router.delete("/jobs/{job_id}")
async def delete_job(job_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    await db.delete(job)
    await db.commit()
    return {"deleted": job_id}
