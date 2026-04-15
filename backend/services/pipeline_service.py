"""
Pipeline Orchestrator v2
────────────────────────────────────────────────────────────────────────────────
Stages:
  1. Scrape     — YouTube search + Twitter/Nitter + RSS
  2. Download   — yt-dlp (YouTube, Twitter, TikTok, etc.)
  3. Transcribe — Faster-Whisper STT (any language → text)
  4. Script     — AI generates script in output language
  5. TTS        — Edge TTS / ElevenLabs voice-over
  6. Compose    — FFmpeg: video + voice + subtitles + watermark
  7. Thumbnail  — Pillow + AI background
  8. Upload     — YouTube Data API with scheduled publishing

Fully keyword-driven. Works for any topic in any language.
"""

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from models.models import Job, Clip, JobStatus
from services import (
    scraper_service,
    script_service,
    tts_service,
    composer_service,
    thumbnail_service,
    uploader_service,
)
from services import stt_service, audio_service
from utils.storage import get_path, timestamped_filename
from utils.env import get_env_int, get_env_value
from pathlib import Path

logger = logging.getLogger(__name__)

MAX_RETRIES = get_env_int("PIPELINE_MAX_RETRIES", 2)
UPLOAD_HOUR = get_env_int("UPLOAD_HOUR_UTC", 15)
OUTPUT_LANGUAGE = get_env_value("OUTPUT_LANGUAGE", "Arabic")
VIDEO_DURATION_MINUTES = get_env_int("VIDEO_DURATION_MINUTES", 3)


async def _update_job(db: AsyncSession, job_id: int, **kwargs):
    await db.execute(update(Job).where(Job.id == job_id).values(**kwargs))
    await db.commit()


async def run_pipeline(
    job_id: int,
    db: AsyncSession,
    output_language: str = None,
    is_shorts: bool = False,
    voice_style: str = "default",
    content_style: str = "default",
    add_music: bool = True,
    add_emojis: bool = True,
    is_kids: bool = False,
    duration_seconds: int = 60,
    hook_style: str = "question",
):
    """
    Execute full video production pipeline for a single job.
    """
    lang = output_language or OUTPUT_LANGUAGE

    logger.info(f"{'='*60}")
    logger.info(f"Pipeline START — job {job_id} | lang={lang} | shorts={is_shorts} | kids={is_kids}")
    logger.info(f"Voice: {voice_style} | Content: {content_style} | Music: {add_music} | Emojis: {add_emojis}")

    # Load job + clip
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise ValueError(f"Job {job_id} not found")

    clip_result = await db.execute(select(Clip).where(Clip.id == job.clip_id))
    clip = clip_result.scalar_one_or_none()
    if not clip:
        raise ValueError(f"Clip {job.clip_id} not found")

    await _update_job(db, job_id,
        status=JobStatus.RUNNING,
        started_at=datetime.now(timezone.utc),
        stage="downloading",
    )

    try:
        # ── Stage 1: Download ──────────────────────────────────────────
        logger.info(f"[Job {job_id}] Stage 1: Downloading...")
        # Inside run_pipeline function
        if not clip.local_path:
            output_fn = timestamped_filename(f"clip_{job_id}", "mp4")
            # Force absolute path
            output_path = os.path.join(
                get_env_value("STORAGE_ROOT", "/app/storage"),
                "clips",
                output_fn,
            )
            
            # Ensure the directory exists before downloading
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            logger.info(f"[Job {job_id}] Calling download for: {clip.url}")
            result_dl = await scraper_service.download_video(clip.url, output_path)
            if result_dl:
                duration, local_path = result_dl
                # Handle webm downloads - find the actual downloaded file
                actual_path = local_path
                base_dir = os.path.dirname(local_path)
                base_name = os.path.splitext(local_path)[0]
                
                # Check for .webm files with same base name
                for ext in ['.webm', '.mkv', '.mp4', '.avi', '.mov']:
                    potential_path = f"{base_name}{ext}"
                    if os.path.exists(potential_path):
                        actual_path = potential_path
                        logger.info(f"[Job {job_id}] Found actual file: {actual_path}")
                        break
                
                # Save the ABSOLUTE path to the DB
                clip.local_path = actual_path 
                await db.commit()
                logger.info(f"[Job {job_id}] Download complete: {actual_path}")
            else:
                raise RuntimeError(f"Download failed for {clip.url} - check logs for details")
        
        # Handle webm/mkv downloads - find the actual file
        video_path = clip.local_path
        if video_path and not os.path.exists(video_path):
            base_name = os.path.splitext(video_path)[0]
            for ext in ['.webm', '.mkv', '.mp4', '.avi', '.mov']:
                potential_path = f"{base_name}{ext}"
                if os.path.exists(potential_path):
                    video_path = potential_path
                    clip.local_path = video_path
                    await db.commit()
                    logger.info(f"[Job {job_id}] Found actual file: {video_path}")
                    break
        
        logger.info(f"[Job {job_id}] Video: {video_path}")

        # ── Stage 2: Extract audio ─────────────────────────────────────
        await _update_job(db, job_id, stage="audio_extraction")
        logger.info(f"[Job {job_id}] Stage 2: Extracting audio...")
        audio_path = await audio_service.extract_audio(video_path, job_id)
        await _update_job(db, job_id, audio_path=audio_path)

        # ── Stage 3: Transcribe ────────────────────────────────────────
        await _update_job(db, job_id, stage="transcription")
        logger.info(f"[Job {job_id}] Stage 3: Transcribing audio...")
        transcript = await stt_service.transcribe_audio(audio_path, job_id)
        await _update_job(db, job_id, transcript_json=transcript)

        source_text = transcript.get("text", "") or clip.title or ""
        source_title = clip.title or "Untitled"
        keywords = clip.keywords or []

        # ── Stage 4: Generate AI script ────────────────────────────────
        await _update_job(db, job_id, stage="script_generation")
        logger.info(f"[Job {job_id}] Stage 4: Generating {lang} script...")
        script = await script_service.generate_video_script(
            title=source_title,
            content=source_text,
            keywords=keywords,
            output_language=lang,
            duration_minutes=VIDEO_DURATION_MINUTES,
            job_id=job_id,
        )
        await _update_job(db, job_id, translation_json=script)

        # ── Stage 5: TTS voice-over ────────────────────────────────────
        await _update_job(db, job_id, stage="tts")
        logger.info(f"[Job {job_id}] Stage 5: Generating voice-over...")
        full_script = script_service.build_tts_script(script)
        tts_path = await tts_service.generate_voice(full_script, job_id, language=lang)
        await _update_job(db, job_id, tts_path=tts_path)

        # ── Stage 6: Compose video ─────────────────────────────────────
        await _update_job(db, job_id, stage="composing")
        logger.info(f"[Job {job_id}] Stage 6: Composing final video...")

        # Build subtitle segments from transcript
        segments = _build_segments_from_transcript(transcript, script)
        source_label = clip.source or "Source"

        composed_path = await composer_service.compose_video(
            video_path=video_path,
            tts_path=tts_path,
            subtitle_segments=segments,
            source_label=source_label,
            watermark_text=get_env_value("WATERMARK_TEXT", ""),
            job_id=job_id,
            is_shorts=is_shorts,
        )
        await _update_job(db, job_id, composed_video_path=composed_path)

        # ── Stage 7: Thumbnail ─────────────────────────────────────────
        await _update_job(db, job_id, stage="thumbnail")
        logger.info(f"[Job {job_id}] Stage 7: Generating thumbnail...")
        thumb_path = await thumbnail_service.generate_thumbnail(
            title=script.get("title", source_title),
            source_label=source_label,
            ai_prompt=script.get("thumbnail_prompt", ""),
            job_id=job_id,
        )
        await _update_job(db, job_id, thumbnail_path=thumb_path)

        # ── Stage 8: Metadata ──────────────────────────────────────────
        await _update_job(db, job_id, stage="metadata")
        meta = {
            "title": script.get("title", ""),
            "description": script.get("description", ""),
            "tags": script.get("tags", []),
            "category": script.get("category", ""),
            "source": source_label,
            "language": lang,
            "is_shorts": is_shorts,
        }
        await _update_job(db, job_id, metadata_json=meta)

        # ── Stage 9: Upload ────────────────────────────────────────────
        await _update_job(db, job_id, stage="uploading")
        logger.info(f"[Job {job_id}] Stage 9: Uploading to YouTube...")
        schedule = uploader_service.calculate_schedule_time(UPLOAD_HOUR)
        upload_result = await uploader_service.upload_video(
            video_path=composed_path,
            title=meta["title"],
            description=meta["description"],
            tags=meta["tags"],
            thumbnail_path=thumb_path,
            schedule_time=schedule,
            is_shorts=is_shorts,
            job_id=job_id,
        )

        await _update_job(db, job_id,
            youtube_video_id=upload_result.get("video_id"),
            youtube_url=upload_result.get("url"),
            status=JobStatus.COMPLETED,
            stage="done",
            completed_at=datetime.now(timezone.utc),
        )

        logger.info(f"✅ Pipeline COMPLETE — job {job_id} → {upload_result.get('url')}")
        return upload_result

    except Exception as e:
        logger.error(f"❌ Pipeline FAILED — job {job_id}: {e}", exc_info=True)
        await _update_job(db, job_id,
            status=JobStatus.FAILED,
            error_message=str(e)[:1000],
            completed_at=datetime.now(timezone.utc),
        )
        raise


def _build_segments_from_transcript(transcript: dict, script: dict) -> list[dict]:
    """Map generated script text to original video time segments"""
    original_segments = transcript.get("segments", [])
    if not original_segments:
        return []

    # Combine the AI generated script parts
    full_text = f"{script.get('hook', '')} {script.get('body', '')} {script.get('closing', '')}".strip()
    words = full_text.split()
    if not words:
        return []

    mapped = []
    # Calculate roughly how many words per segment based on original timing
    words_per_seg = max(1, len(words) // max(1, len(original_segments)))

    for i, seg in enumerate(original_segments):
        start_idx = i * words_per_seg
        end_idx = min(start_idx + words_per_seg, len(words))
        chunk = " ".join(words[start_idx:end_idx])
        if chunk:
            mapped.append({
                "start": seg["start"],
                "end": seg["end"],
                "text": chunk,
            })
    return mapped


def _get_category_id(category_name: str) -> str:
    """Map category name to YouTube category ID"""
    category_map = {
        "news": "25",
        "technology": "28",
        "gaming": "20",
        "sports": "17",
        "entertainment": "24",
        "education": "27",
        "music": "10",
        "travel": "19",
        "science": "28",
        "howto": "26",
        "comedy": "23",
        "film": "1",
        "autos": "2",
        "pets": "15",
        "people": "22",
        "nonprofits": "29",
    }
    cat_lower = category_name.lower() if category_name else ""
    for key, cid in category_map.items():
        if key in cat_lower:
            return cid
    return "25"  # Default: News & Politics


async def create_job_for_clip(clip_id: int, db: AsyncSession, is_shorts: bool = False) -> int:
    """Create pipeline job record in DB"""
    job = Job(clip_id=clip_id, status=JobStatus.PENDING, is_chill_mode=is_shorts)
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return job.id


async def run_daily_pipeline(
    db: AsyncSession,
    keywords: list[str],
    output_language: str = None,
    max_videos: int = 3,
    twitter_accounts: list[str] = None,
    rss_feeds: list[str] = None,
    is_shorts: bool = False,
    youtube_language: str = "",
) -> list[int]:
    """
    Complete keyword-driven pipeline:
    1. Search YouTube + scrape Twitter/Nitter + fetch RSS
    2. Store clips in DB
    3. Run full video production for each (up to max_videos)
    """
    from utils.database import AsyncSessionLocal
    
    # Map numeric language values to names
    lang_map = {1: "English", 2: "Arabic", 3: "French", 4: "Spanish", 5: "Turkish", 6: "Urdu", 7: "Hindi"}
    
    # Use provided language or default to Arabic
    lang = str(output_language) if output_language else "Arabic"
    if lang.isdigit() and int(lang) in lang_map:
        lang = lang_map[int(lang)]
    
    logger.info(f"Keyword pipeline: {keywords} | lang={lang} | max={max_videos} | shorts={is_shorts}")

    # Scrape sources
    clips_data = await scraper_service.scrape_all(
        keywords=keywords,
        twitter_accounts=twitter_accounts,
        rss_feeds=rss_feeds,
        max_youtube=max_videos * 5,
        max_twitter=max_videos * 3,
        language=youtube_language,
    )
    clips_data = clips_data[:max_videos]

    if not clips_data:
        logger.warning("No clips found for the given keywords")
        return []

    # Store clips and create jobs
    job_ids = []
    for clip_data in clips_data:
        try:
            clip = Clip(
                url=clip_data["url"],
                source=clip_data.get("source", "manual"),
                title=clip_data.get("title", ""),
                keywords=clip_data.get("keywords", keywords),
                thumbnail_url=clip_data.get("thumbnail_url"),
            )
            db.add(clip)
            await db.commit()
            await db.refresh(clip)

            job_id = await create_job_for_clip(clip.id, db, is_shorts=is_shorts)
            job_ids.append(job_id)
            
            # Create a new db session for each background task
            asyncio.create_task(_run_pipeline_background(job_id, lang, is_shorts))
            logger.info(f"Successfully queued job {job_id} for {clip.url}")
            
        except Exception as e:
            logger.error(f"Failed to create job for {clip_data.get('url')}: {e}")

    logger.info(f"Keyword pipeline complete. Jobs queued: {job_ids}")
    return job_ids


async def _run_pipeline_background(job_id: int, lang: str, is_shorts: bool):
    """Run pipeline in a new database session (for background tasks)"""
    from utils.database import AsyncSessionLocal
    
    async with AsyncSessionLocal() as db:
        for attempt in range(MAX_RETRIES + 1):
            try:
                await run_pipeline(job_id, db, output_language=lang, is_shorts=is_shorts)
                break
            except Exception as e:
                if attempt < MAX_RETRIES:
                    wait = 30 * (attempt + 1)
                    logger.warning(f"Retry {attempt+1}/{MAX_RETRIES} for job {job_id} in {wait}s")
                    await asyncio.sleep(wait)
                else:
                    logger.error(f"Job {job_id} permanently failed")


async def run_auto_search_pipeline(
    job_id: int,
    db: AsyncSession,
    keywords: list[str],
    is_shorts: bool = False,
    voice_style: str = "default",
    is_kids: bool = False,
    output_language: str = None,
):
    """
    Auto-search pipeline: Search YouTube for videos, download, process, and publish.
    """
    from utils.database import AsyncSessionLocal
    
    lang = output_language or OUTPUT_LANGUAGE
    
    # Max duration: 10min for shorts/kids, 30min for full videos
    if is_shorts or is_kids:
        max_dur = 600  # 10 minutes - allows real content
    else:
        max_dur = 1800  # 30 minutes for full
    
    logger.info(f"🚀 Auto-search pipeline: job={job_id}, keywords={keywords}, shorts={is_shorts}")
    
    async with AsyncSessionLocal() as session:
        try:
            # Load job and clip
            result_job = await session.execute(select(Job).where(Job.id == job_id))
            job = result_job.scalar_one_or_none()
            if not job:
                logger.error(f"[Job {job_id}] Job not found")
                return
            
            # Update job status
            await _update_job(session, job_id, status=JobStatus.RUNNING, stage="searching")
            
            # Search YouTube for videos
            logger.info(f"[Job {job_id}] Searching YouTube for: {keywords}")
            # Get more results so we have options when some are unavailable
            max_search_results = 20 if is_shorts or is_kids else 15
            search_results = await scraper_service.search_youtube(
                keywords=keywords,
                max_results=max_search_results,
                language=lang,
            )
            
            if not search_results:
                logger.warning(f"[Job {job_id}] No videos found for: {keywords}")
                await _update_job(session, job_id,
                    status=JobStatus.FAILED,
                    error_message=f"No videos found for: {keywords}"
                )
                return
            
            # Try to find a suitable video - check availability first
            video = None
            video_url = None
            video_title = None
            
            logger.info(f"[Job {job_id}] Checking {len(search_results)} videos for availability...")
            
            for v in search_results:
                url = v.get("url", "")
                if not url or not url.startswith("http"):
                    continue
                
                # Check availability first
                logger.info(f"[Job {job_id}] Checking: {url}")
                availability = await scraper_service.check_video_availability(url, max_duration=max_dur)
                
                if availability.get("available"):
                    video = v
                    video_url = url
                    video_title = availability.get("title", v.get("title", "Unknown"))
                    duration = availability.get("duration", 0)
                    logger.info(f"[Job {job_id}] ✅ Video available: {video_title[:50]} ({duration}s)")
                    break
                else:
                    logger.warning(f"[Job {job_id}] ⏭ Skipping: {availability.get('error', 'unavailable')}")
            
            if not video:
                logger.error(f"[Job {job_id}] No available videos found")
                await _update_job(session, job_id,
                    status=JobStatus.FAILED,
                    error_message="No available videos found - all checked videos were unavailable, private, or region-restricted"
                )
                return
            
            logger.info(f"[Job {job_id}] Selected video: {video_title}")
            
            # Update job with video info
            await _update_job(session, job_id, stage="downloading")
            
            # Download the video
            output_fn = timestamped_filename(f"clip_{job_id}", "mp4")
            output_path = Path(get_env_value("STORAGE_ROOT", "/app/storage")) / "clips" / output_fn
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            result_dl = await scraper_service.download_video(video_url, str(output_path), max_duration=max_dur)
            
            if not result_dl:
                logger.error(f"[Job {job_id}] Download failed: {video_url}")
                await _update_job(session, job_id,
                    status=JobStatus.FAILED,
                    error_message=f"Download failed: {video_url}"
                )
                return
            
            duration, local_path = result_dl
            
            # Handle webm/mp4 extensions
            base_name = Path(local_path).stem
            for ext in ['.webm', '.mkv', '.mp4', '.avi', '.mov']:
                potential_path = Path(local_path).parent / f"{base_name}{ext}"
                if potential_path.exists():
                    local_path = str(potential_path)
                    break
            
            logger.info(f"[Job {job_id}] Downloaded: {local_path}")
            
            # Update clip with actual video URL and local path
            result_clip = await session.execute(select(Clip).where(Clip.id == job_id))
            clip = result_clip.scalar_one_or_none()
            if clip:
                clip.url = video_url
                clip.title = video_title
                clip.local_path = local_path
                await session.commit()
                logger.info(f"[Job {job_id}] Updated clip: {clip.id} -> {video_url}")
            
            # Continue to next stages (audio extraction, transcription, etc.)
            await _update_job(session, job_id, stage="audio_extraction")
            logger.info(f"[Job {job_id}] Stage 2: Extracting audio...")
            audio_path = await audio_service.extract_audio(local_path, job_id)
            await _update_job(session, job_id, audio_path=audio_path)
            
            await _update_job(session, job_id, stage="transcription")
            logger.info(f"[Job {job_id}] Stage 3: Transcribing audio...")
            transcript = await stt_service.transcribe_audio(audio_path, job_id)
            await _update_job(session, job_id, transcript_json=transcript)
            
            source_text = transcript.get("text", "") or video_title or ""
            keywords = keywords or []
            
            await _update_job(session, job_id, stage="script_generation")
            logger.info(f"[Job {job_id}] Stage 4: Generating {lang} script...")
            script = await script_service.generate_video_script(
                title=video_title,
                content=source_text,
                keywords=keywords,
                output_language=lang,
                duration_minutes=3,
                job_id=job_id,
            )
            await _update_job(session, job_id, translation_json=script)
            
            await _update_job(session, job_id, stage="tts")
            logger.info(f"[Job {job_id}] Stage 5: Generating voice-over...")
            full_script = script_service.build_tts_script(script)
            tts_path = await tts_service.generate_voice(full_script, job_id, language=lang)
            await _update_job(session, job_id, tts_path=tts_path)
            
            await _update_job(session, job_id, stage="composing")
            logger.info(f"[Job {job_id}] Stage 6: Composing final video...")
            segments = _build_segments_from_transcript(transcript, script)
            composed_path = await composer_service.compose_video(
                video_path=local_path,
                tts_path=tts_path,
                subtitle_segments=segments,
                source_label="YouTube",
                watermark_text=get_env_value("WATERMARK_TEXT", ""),
                job_id=job_id,
                is_shorts=is_shorts,
            )
            await _update_job(session, job_id, composed_video_path=composed_path)
            
            await _update_job(session, job_id, stage="thumbnail")
            logger.info(f"[Job {job_id}] Stage 7: Generating thumbnail...")
            thumb_path = await thumbnail_service.generate_thumbnail(
                title=script.get("title", video_title),
                source_label="YouTube",
                ai_prompt=script.get("thumbnail_prompt", ""),
                job_id=job_id,
            )
            await _update_job(session, job_id, thumbnail_path=thumb_path)
            
            meta = {
                "title": script.get("title", ""),
                "description": script.get("description", ""),
                "tags": script.get("tags", []),
                "category": script.get("category", ""),
                "source": "auto-search",
                "language": lang,
                "is_shorts": is_shorts,
            }
            await _update_job(session, job_id, metadata_json=meta)
            
            await _update_job(session, job_id, stage="uploading")
            logger.info(f"[Job {job_id}] Stage 8: Uploading to YouTube...")
            schedule = uploader_service.calculate_schedule_time(UPLOAD_HOUR)
            upload_result = await uploader_service.upload_video(
                video_path=composed_path,
                title=meta["title"],
                description=meta["description"],
                tags=meta["tags"],
                thumbnail_path=thumb_path,
                schedule_time=schedule,
                is_shorts=is_shorts,
                job_id=job_id,
            )
            
            await _update_job(session, job_id,
                youtube_video_id=upload_result.get("video_id"),
                youtube_url=upload_result.get("url"),
                status=JobStatus.COMPLETED,
                stage="done",
                completed_at=datetime.now(timezone.utc),
            )
            
            logger.info(f"✅ Auto-search pipeline COMPLETE — job {job_id} → {upload_result.get('url')}")
            
        except Exception as e:
            logger.error(f"[Job {job_id}] Auto-search pipeline failed: {e}", exc_info=True)
            await _update_job(session, job_id,
                status=JobStatus.FAILED,
                error_message=str(e)[:500]
            )
