"""
YouTube Uploader Service
Uploads videos to YouTube with metadata, thumbnail, and schedule.
Uses Google YouTube Data API v3.
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
import httpx

from utils.env import get_env_token

logger = logging.getLogger(__name__)

YOUTUBE_CLIENT_ID = get_env_token("YOUTUBE_CLIENT_ID", "")
YOUTUBE_CLIENT_SECRET = get_env_token("YOUTUBE_CLIENT_SECRET", "")
YOUTUBE_REFRESH_TOKEN = get_env_token("YOUTUBE_REFRESH_TOKEN", "")
YOUTUBE_CHANNEL_ID = get_env_token("YOUTUBE_CHANNEL_ID", "")

YOUTUBE_CATEGORY_NEWS = "25"  # News & Politics
YOUTUBE_DEFAULT_LANGUAGE = "ar"


async def get_access_token() -> str:
    """Get fresh OAuth2 access token using refresh token"""
    if not all([YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, YOUTUBE_REFRESH_TOKEN]):
        raise ValueError("YouTube OAuth credentials not configured")

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": YOUTUBE_CLIENT_ID,
                "client_secret": YOUTUBE_CLIENT_SECRET,
                "refresh_token": YOUTUBE_REFRESH_TOKEN,
                "grant_type": "refresh_token",
            },
        )
        r.raise_for_status()
        return r.json()["access_token"]


async def upload_video(
    video_path: str,
    title: str,
    description: str,
    tags: list[str],
    thumbnail_path: Optional[str],
    schedule_time: Optional[datetime],
    is_shorts: bool = False,
    job_id: int = 0,
) -> dict:
    """
    Upload video to YouTube.
    Returns {video_id, url, status}
    """
    if not Path(video_path).exists():
        raise FileNotFoundError(f"Video not found: {video_path}")

    if not YOUTUBE_REFRESH_TOKEN:
        logger.warning("YouTube credentials not configured — returning stub")
        return _stub_upload_result(title, job_id)

    try:
        access_token = await get_access_token()
    except Exception as e:
        logger.error(f"Failed to get YouTube token: {e}")
        return _stub_upload_result(title, job_id)

    # Privacy: scheduled or private
    if schedule_time:
        privacy_status = "private"
        publish_at = schedule_time.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    else:
        privacy_status = "public"
        publish_at = None

    snippet = {
        "title": title[:100],
        "description": description[:5000],
        "tags": tags[:50],
        "categoryId": YOUTUBE_CATEGORY_NEWS,
        "defaultLanguage": YOUTUBE_DEFAULT_LANGUAGE,
        "defaultAudioLanguage": YOUTUBE_DEFAULT_LANGUAGE,
    }

    status_body = {"privacyStatus": privacy_status}
    if publish_at:
        status_body["publishAt"] = publish_at

    metadata = {"snippet": snippet, "status": status_body}

    file_size = Path(video_path).stat().st_size
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "X-Upload-Content-Length": str(file_size),
        "X-Upload-Content-Type": "video/mp4",
    }

    # Step 1: Initiate resumable upload
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            "https://www.googleapis.com/upload/youtube/v3/videos"
            "?uploadType=resumable&part=snippet,status",
            headers=headers,
            json=metadata,
        )
        r.raise_for_status()
        upload_url = r.headers.get("Location")

    if not upload_url:
        raise RuntimeError("No upload URL from YouTube")

    # Step 2: Upload video bytes
    logger.info(f"Uploading video to YouTube ({file_size / 1024 / 1024:.1f} MB)...")
    async with httpx.AsyncClient(timeout=600) as client:
        with open(video_path, "rb") as f:
            upload_r = await client.put(
                upload_url,
                content=f.read(),
                headers={"Content-Type": "video/mp4"},
            )
        upload_r.raise_for_status()
        video_data = upload_r.json()

    video_id = video_data["id"]
    logger.info(f"Video uploaded: https://youtu.be/{video_id}")

    # Step 3: Upload thumbnail
    if thumbnail_path and Path(thumbnail_path).exists():
        try:
            await upload_thumbnail(access_token, video_id, thumbnail_path)
        except Exception as e:
            logger.warning(f"Thumbnail upload failed: {e}")

    return {
        "video_id": video_id,
        "url": f"https://youtu.be/{video_id}",
        "status": "scheduled" if publish_at else "public",
        "publish_at": publish_at,
    }


async def upload_thumbnail(access_token: str, video_id: str, thumbnail_path: str):
    """Upload thumbnail for uploaded video"""
    with open(thumbnail_path, "rb") as f:
        thumb_bytes = f.read()

    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            f"https://www.googleapis.com/upload/youtube/v3/thumbnails/set?videoId={video_id}",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "image/jpeg",
            },
            content=thumb_bytes,
        )
        r.raise_for_status()
    logger.info(f"Thumbnail uploaded for video {video_id}")


def _stub_upload_result(title: str, job_id: int) -> dict:
    """Stub result for dev without YouTube credentials"""
    return {
        "video_id": f"STUB_{job_id:06d}",
        "url": f"https://youtube.com/watch?v=STUB_{job_id:06d}",
        "status": "stub",
        "publish_at": None,
        "note": "YouTube credentials not configured. Video saved locally.",
    }


def calculate_schedule_time(
    target_hour: int = 18,
    target_minute: int = 0,
    days_ahead: int = 0,
) -> datetime:
    """Calculate UTC publish time for scheduled upload"""
    now = datetime.now(timezone.utc)
    target = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
    target += timedelta(days=days_ahead)
    if target <= now:
        target += timedelta(days=1)
    return target
