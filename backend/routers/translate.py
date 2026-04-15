"""Translate Router"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from services import translate_service

router = APIRouter()

class TranslateRequest(BaseModel):
    job_id: int
    hebrew_text: str

@router.post("/translate")
async def translate(req: TranslateRequest):
    try:
        result = await translate_service.translate_hebrew_to_arabic(req.hebrew_text, req.job_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/script")
async def build_script(translation: dict):
    script = await translate_service.build_arabic_script(translation)
    return {"script": script}
