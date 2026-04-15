"""Thumbnail Router"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from services import thumbnail_service

router = APIRouter()

class ThumbnailRequest(BaseModel):
    job_id: int
    title: str
    source_label: str = "إسرائيل"
    ai_background: bool = True

@router.post("/generate")
async def generate_thumbnail(req: ThumbnailRequest):
    try:
        path = await thumbnail_service.generate_thumbnail(
            title=req.title,
            source_label=req.source_label,
            job_id=req.job_id,
            ai_background=req.ai_background,
        )
        return {"thumbnail_path": path}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
