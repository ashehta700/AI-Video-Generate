"""Audio Router"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from utils.database import get_db
from models.models import Job
from services import audio_service
from sqlalchemy import select

router = APIRouter()

class AudioRequest(BaseModel):
    job_id: int
    video_path: str

@router.post("/extract")
async def extract_audio(req: AudioRequest, db: AsyncSession = Depends(get_db)):
    try:
        path = await audio_service.extract_audio(req.video_path, req.job_id)
        return {"audio_path": path}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/info")
async def video_info(video_path: str):
    info = await audio_service.get_video_info(video_path)
    return info
