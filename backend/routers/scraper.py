"""Scraper Router"""
import os
from fastapi import APIRouter, Depends, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from utils.database import get_db
from models.models import Clip, ClipSource
from services import scraper_service
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


class ScrapeRequest(BaseModel):
    keywords: list[str] = []
    sources: list[str] = ["youtube", "twitter", "rss"]


class TestDownloadRequest(BaseModel):
    url: str
    output_path: str = "/app/storage/clips/test_download.mp4"


@router.post("/run")
async def run_scraper(request: ScrapeRequest, db: AsyncSession = Depends(get_db)):
    clips_data = await scraper_service.scrape_all(request.keywords)
    saved = []
    for c in clips_data:
        try:
            src = ClipSource(c.get("source", "manual"))
            src_value = src.value
        except ValueError:
            src_value = "manual"
        clip = Clip(
            url=c["url"], 
            source=src_value, 
            title=c.get("title"), 
            keywords=c.get("keywords", []),
            thumbnail_url=c.get("thumbnail_url")
        )
        db.add(clip)
        saved.append({
            "url": c["url"], 
            "source": src_value, 
            "title": c.get("title"),
            "thumbnail_url": c.get("thumbnail_url")
        })
    await db.commit()
    return {"scraped": len(saved), "clips": saved}


@router.get("/clips")
async def list_clips(limit: int = 20, db: AsyncSession = Depends(get_db)):
    from sqlalchemy import select, desc
    result = await db.execute(select(Clip).order_by(desc(Clip.created_at)).limit(limit))
    clips = result.scalars().all()
    return [{"id": c.id, "url": c.url, "source": c.source, 
             "title": c.title, "thumbnail_url": c.thumbnail_url,
             "duration": c.duration, "keywords": c.keywords, "created_at": c.created_at} for c in clips]


@router.post("/test-download")
async def test_download(request: TestDownloadRequest):
    """Test video download directly - useful for debugging"""
    logger.info(f"Test download request: {request.url}")
    logger.info(f"Output path: {request.output_path}")
    
    # Ensure directory exists
    os.makedirs(os.path.dirname(request.output_path), exist_ok=True)
    
    # First check video availability
    availability = await scraper_service.check_video_availability(request.url)
    logger.info(f"Availability check: {availability}")
    
    # Then try download
    result = await scraper_service.download_video(request.url, request.output_path)
    
    if result:
        duration, path = result
        return {
            "success": True,
            "duration": duration,
            "path": path,
            "availability": availability
        }
    else:
        return {
            "success": False,
            "error": "Download failed - check server logs for details",
            "availability": availability
        }
