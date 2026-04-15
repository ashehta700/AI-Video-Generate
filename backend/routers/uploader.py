"""Uploader Router"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from services import uploader_service
from utils.env import get_env_token

router = APIRouter()

class UploadRequest(BaseModel):
    job_id: int
    video_path: str
    title: str
    description: str
    tags: list[str] = []
    thumbnail_path: Optional[str] = None
    schedule_hour_utc: Optional[int] = 15
    is_shorts: bool = False

@router.post("/upload")
async def upload(req: UploadRequest):
    try:
        schedule = uploader_service.calculate_schedule_time(req.schedule_hour_utc or 15)
        result = await uploader_service.upload_video(
            video_path=req.video_path,
            title=req.title,
            description=req.description,
            tags=req.tags,
            thumbnail_path=req.thumbnail_path,
            schedule_time=schedule,
            is_shorts=req.is_shorts,
            job_id=req.job_id,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/auth-url")
async def get_auth_url():
    """Return YouTube OAuth URL for first-time setup"""
    client_id = get_env_token("YOUTUBE_CLIENT_ID", "")
    if not client_id:
        return {"error": "YOUTUBE_CLIENT_ID not set"}
    auth_url = (
        "https://accounts.google.com/o/oauth2/auth"
        f"?client_id={client_id}"
        "&redirect_uri=urn:ietf:wg:oauth:2.0:oob"
        "&scope=https://www.googleapis.com/auth/youtube.upload"
        "&response_type=code"
        "&access_type=offline"
    )
    return {"auth_url": auth_url}
