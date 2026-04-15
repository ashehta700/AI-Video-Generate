"""
Universal Video Automation System - v2
FastAPI Backend — keyword-driven, any topic, any language
"""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
import os

from routers import scraper, pipeline, settings, analytics, tts, composer, thumbnail, uploader, chill
from utils.database import init_db
from utils.env import get_env_value
from utils.logger import setup_logging

setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Starting Universal Video Automation API v2...")
    await init_db()
    logger.info("✅ Database ready")
    yield
    logger.info("🛑 Shutdown complete")


app = FastAPI(
    title="Universal Video Automation API v2",
    description="Keyword-driven video creation from YouTube search & Twitter/X scraping",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static dashboard
_backend_dir = os.path.dirname(os.path.abspath(__file__))

_candidates = [
    get_env_value("DASHBOARD_DIR", ""),         # explicit env override
    "/app/dashboard",                           # Docker default mount
    "/app/dashobord",                            # Common misspelling
    os.path.join(_backend_dir, "dashboard"),    # backend/dashboard/
    os.path.join(_backend_dir, "dashobord"),     # backend/dashobord/
    os.path.join(_backend_dir, "../dashboard"), # project_root/dashboard/
    os.path.join(_backend_dir, "../dashobord"),  # project_root/dashobord/
]

DASHBOARD_DIR = next(
    (p for p in _candidates if p and os.path.isdir(p)),
    "/app/dashboard",  # last resort — created below
)
os.makedirs(DASHBOARD_DIR, exist_ok=True)

# Serve dashboard assets if present
app.mount("/dashboard", StaticFiles(directory=DASHBOARD_DIR, html=True), name="dashboard")

# Routers
app.include_router(scraper.router,   prefix="/api/scraper",   tags=["Scraper"])
app.include_router(pipeline.router,  prefix="/api/pipeline",  tags=["Pipeline"])
app.include_router(settings.router,  prefix="/api/settings",  tags=["Settings"])
app.include_router(analytics.router, prefix="/api/analytics", tags=["Analytics"])
app.include_router(tts.router,       prefix="/api/tts",       tags=["TTS"])
app.include_router(composer.router,  prefix="/api/composer",  tags=["Composer"])
app.include_router(thumbnail.router, prefix="/api/thumbnail", tags=["Thumbnail"])
app.include_router(uploader.router,  prefix="/api/uploader",  tags=["Uploader"])
app.include_router(chill.router,     prefix="/api/chill",     tags=["Chill"])


@app.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    """Serve the main dashboard HTML"""
    index_path = os.path.join(DASHBOARD_DIR, "index.html")
    if not os.path.exists(index_path):
        return HTMLResponse(
            content=(
                "<h2 style='font-family:sans-serif;padding:40px'>"
                f"Dashboard not found at: {index_path}<br><br>"
                "Make sure your docker-compose.yml has this volume:<br>"
                "<code>- ./dashboard:/app/dashboard</code>"
                "</h2>"
            ),
            status_code=404,
        )
    with open(index_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@app.get("/health")
async def health():
    return {"status": "healthy", "version": "2.0.0", "service": "Universal Video Automation"}
