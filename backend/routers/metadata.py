"""Metadata Router"""
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

class MetadataRequest(BaseModel):
    title: str
    description: str
    tags: list[str]
    source: str = ""

@router.post("/generate")
async def generate_metadata(req: MetadataRequest):
    """Return SEO-optimized metadata (already produced by translate service)"""
    seo_tags = list(set(req.tags + ["أخبار_عربية", "أخبار_إسرائيل", "عاجل"]))
    return {
        "title": req.title,
        "description": req.description,
        "tags": seo_tags[:50],
        "source": req.source,
        "character_count": {
            "title": len(req.title),
            "description": len(req.description),
        },
    }
