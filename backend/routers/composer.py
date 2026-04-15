"""Composer Router"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from services import composer_service

router = APIRouter()

class ComposeRequest(BaseModel):
    job_id: int
    video_path: str
    tts_path: str
    arabic_segments: list[dict]
    source_label: str = "إسرائيل"
    is_chill: bool = False

@router.post("/compose")
async def compose(req: ComposeRequest):
    try:
        path = await composer_service.compose_video(
            video_path=req.video_path,
            tts_path=req.tts_path,
            arabic_segments=req.arabic_segments,
            source_label=req.source_label,
            job_id=req.job_id,
            is_chill=req.is_chill,
        )
        return {"composed_path": path}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
