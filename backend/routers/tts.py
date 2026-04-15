"""TTS Router"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from services import tts_service

router = APIRouter()

class TTSRequest(BaseModel):
    job_id: int
    text: str
    language: str = "Arabic"

@router.post("/generate")
async def generate_tts(req: TTSRequest):
    try:
        path = await tts_service.generate_voice(req.text, req.job_id, req.language)
        duration = tts_service.get_audio_duration(path)
        return {"tts_path": path, "duration_seconds": duration}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
