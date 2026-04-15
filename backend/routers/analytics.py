"""Analytics Router"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, case
from utils.database import get_db
from models.models import Analytics, Job, JobStatus
import httpx
import logging
from datetime import datetime, timezone, timedelta

from utils.env import get_env_token

logger = logging.getLogger(__name__)
router = APIRouter()

YOUTUBE_API_KEY = get_env_token("YOUTUBE_API_KEY", "")


async def fetch_youtube_stats(video_id: str) -> dict:
    if not YOUTUBE_API_KEY or video_id.startswith("STUB"):
        return {"views": 0, "likes": 0, "comments": 0}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                "https://www.googleapis.com/youtube/v3/videos",
                params={
                    "part": "statistics",
                    "id": video_id,
                    "key": YOUTUBE_API_KEY,
                },
            )
            r.raise_for_status()
            data = r.json()
            if data.get("items"):
                stats = data["items"][0]["statistics"]
                return {
                    "views": int(stats.get("viewCount", 0)),
                    "likes": int(stats.get("likeCount", 0)),
                    "comments": int(stats.get("commentCount", 0)),
                }
    except Exception as e:
        logger.warning(f"YouTube stats fetch failed: {e}")
    return {"views": 0, "likes": 0, "comments": 0}


@router.get("/summary")
async def get_summary(db: AsyncSession = Depends(get_db)):
    """Get overall pipeline analytics summary"""
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Get counts using single query with aggregates
    result = await db.execute(
        select(
            func.count(Job.id).label('total'),
            func.count(case((Job.status == JobStatus.COMPLETED, 1))).label('completed'),
            func.count(case((Job.status == JobStatus.FAILED, 1))).label('failed'),
            func.count(case((Job.status == JobStatus.RUNNING, 1))).label('running'),
            func.count(case((Job.status == JobStatus.PENDING, 1))).label('pending'),
        )
    )
    counts = result.first()
    
    # Get completed today
    today_result = await db.execute(
        select(func.count(Job.id)).where(
            Job.status == JobStatus.COMPLETED,
            Job.completed_at >= today_start
        )
    )
    completed_today = today_result.scalar() or 0
    
    # Get analytics data
    analytics_result = await db.execute(
        select(
            func.coalesce(func.sum(Analytics.views), 0).label('total_views'),
            func.coalesce(func.sum(Analytics.estimated_revenue_usd), 0).label('total_revenue')
        )
    )
    analytics_data = analytics_result.first()

    return {
        "total_jobs": counts.total if counts else 0,
        "completed": counts.completed if counts else 0,
        "failed": counts.failed if counts else 0,
        "running": counts.running if counts else 0,
        "pending": counts.pending if counts else 0,
        "total_views": analytics_data.total_views if analytics_data else 0,
        "estimated_revenue_usd": round(float(analytics_data.total_revenue or 0), 2) if analytics_data else 0.0,
        "completed_today": completed_today,
        "active_jobs": counts.running if counts else 0,
    }


@router.post("/refresh/{job_id}")
async def refresh_analytics(job_id: int, db: AsyncSession = Depends(get_db)):
    """Fetch latest YouTube stats for a job"""
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if not job or not job.youtube_video_id:
        raise HTTPException(status_code=404, detail="Job or YouTube video not found")

    stats = await fetch_youtube_stats(job.youtube_video_id)

    # RPM estimate: ~$1.5 per 1000 views (conservative Arabic news)
    estimated_revenue = (stats["views"] / 1000) * 1.5
    watch_time_hours = stats["views"] * 2.5 / 60  # Assume 2.5 min avg watch time

    # Upsert analytics record
    existing = await db.execute(select(Analytics).where(Analytics.job_id == job_id))
    rec = existing.scalar_one_or_none()
    if rec:
        rec.views = stats["views"]
        rec.likes = stats["likes"]
        rec.comments = stats["comments"]
        rec.watch_time_hours = round(watch_time_hours, 2)
        rec.estimated_revenue_usd = round(estimated_revenue, 2)
    else:
        rec = Analytics(
            job_id=job_id,
            youtube_video_id=job.youtube_video_id,
            views=stats["views"],
            likes=stats["likes"],
            comments=stats["comments"],
            watch_time_hours=round(watch_time_hours, 2),
            estimated_revenue_usd=round(estimated_revenue, 2),
        )
        db.add(rec)
    await db.commit()

    return {**stats, "estimated_revenue_usd": round(estimated_revenue, 2),
            "watch_time_hours": round(watch_time_hours, 2)}


@router.get("/videos")
async def list_video_stats(db: AsyncSession = Depends(get_db)):
    """List all video analytics"""
    result = await db.execute(select(Analytics))
    records = result.scalars().all()
    return [
        {
            "job_id": r.job_id,
            "video_id": r.youtube_video_id,
            "views": r.views,
            "likes": r.likes,
            "comments": r.comments,
            "watch_time_hours": r.watch_time_hours,
            "estimated_revenue_usd": r.estimated_revenue_usd,
            "fetched_at": r.fetched_at,
        }
        for r in records
    ]
