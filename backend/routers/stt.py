"""STT Router"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from services import stt_service

router = APIRouter()

class STTRequest(BaseModel):
    job_id: int
    audio_path: str

@router.post("/transcribe")
async def transcribe(req: STTRequest):
    try:
        result = await stt_service.transcribe_audio(req.audio_path, req.job_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/srt")
async def build_srt(segments: list[dict]):
    srt = await stt_service.build_srt(segments)
    return {"srt": srt}
