"""
Scraper Service v2 - FULLY RECOUPLED
"""

import asyncio
import logging
import os
import re
from datetime import datetime
from typing import Optional
from urllib.parse import quote_plus

import httpx
import yt_dlp
from bs4 import BeautifulSoup

from utils.env import get_env_token, get_env_value

logger = logging.getLogger(__name__)

STORAGE_ROOT = get_env_value("STORAGE_ROOT", "./storage")
YOUTUBE_API_KEY = get_env_token("YOUTUBE_API_KEY", "")

NITTER_INSTANCES = [
    "https://nitter.net",
    "https://nitter.poast.org",
    "https://nitter.cz",
    "https://nitter.privacydev.net",
]

CUSTOM_RSS_FEEDS = [
    f.strip()
    for f in get_env_value("CUSTOM_RSS_FEEDS", "").split(",")
    if f.strip() and not f.startswith("#")
]

# ─── YouTube Logic ─────────────────────────────────────────────────────────────

async def search_youtube(
    keywords: list[str],
    max_results: int = 20,
    language: str = "",
    published_after: str = "",
    video_type: str = "video",
) -> list[dict]:
    """Unified YouTube search: API first, then yt-dlp fallback"""
    query = " ".join(keywords)
    results = []

    if YOUTUBE_API_KEY:
        results = await _search_youtube_api(query, max_results, language, published_after, video_type)
    
    # If API fails or key is missing, use yt-dlp
    if not results:
        results = await _search_youtube_ytdlp(query, max_results)

    logger.info(f"YouTube total found: {len(results)}")
    return results

async def _search_youtube_api(query, max_results, language, published_after, video_type):
    """Search via YouTube Data API v3 - FIXED safeSearch"""
    lang_str = str(language) if language and not str(language).isdigit() else ""
    params = {
        "part": "snippet",
        "q": query,
        "type": "video",
        "maxResults": min(max_results, 50),
        "order": "relevance",
        "key": YOUTUBE_API_KEY,
        "safeSearch": "moderate",
    }
    if lang_str: params["relevanceLanguage"] = lang_str
    if published_after: params["publishedAfter"] = published_after

    results = []
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get("https://www.googleapis.com/youtube/v3/search", params=params)
            if r.status_code != 200: return []
            data = r.json()
            for item in data.get("items", []):
                vid_id = item.get("id", {}).get("videoId")
                if not vid_id: continue
                snippet = item.get("snippet", {})
                results.append({
                    "url": f"https://www.youtube.com/watch?v={vid_id}",
                    "video_id": vid_id,
                    "title": snippet.get("title", "No Title"),
                    "source": "youtube_api",
                    "thumbnail_url": snippet.get("thumbnails", {}).get("high", {}).get("url", ""),
                })
    except Exception as e:
        logger.error(f"YouTube API crash: {e}")
    return results

async def _search_youtube_ytdlp(query: str, max_results: int) -> list[dict]:
    """Fallback search using yt-dlp"""
    results = []
    ydl_opts = {"quiet": True, "extract_flat": True, "skip_download": True}
    try:
        loop = asyncio.get_event_loop()
        def _search():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                return ydl.extract_info(f"ytsearch{max_results}:{query}", download=False).get("entries", [])
        
        entries = await loop.run_in_executor(None, _search)
        for entry in entries:
            if not entry: continue
            results.append({
                "url": entry.get("url") or f"https://www.youtube.com/watch?v={entry.get('id')}",
                "title": entry.get("title"),
                "source": "youtube_ytdlp"
            })
    except Exception as e:
        logger.error(f"yt-dlp search failed: {e}")
    return results

# ─── Twitter Logic ─────────────────────────────────────────────────────────────

async def scrape_twitter_nitter(keywords: list[str], accounts: list[str] = None, max_posts: int = 20) -> list[dict]:
    """Scrape Twitter via Nitter instances"""
    results = []
    query = " ".join(keywords)
    for instance in NITTER_INSTANCES:
        try:
            encoded = quote_plus(query)
            url = f"{instance}/search?q={encoded}&f=videos"
            async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
                r = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
                if r.status_code != 200: continue
                soup = BeautifulSoup(r.text, "html.parser")
                items = soup.select(".timeline-item")[:max_posts]
                for item in items:
                    content = item.select_one(".tweet-content")
                    if content:
                        results.append({
                            "url": f"https://twitter.com{item.select_one('.tweet-link')['href']}" if item.select_one('.tweet-link') else "",
                            "title": content.get_text(strip=True)[:200],
                            "source": "twitter_nitter"
                        })
            if results: break
        except Exception: continue
    return results

# ─── RSS & Entry Points ────────────────────────────────────────────────────────

async def fetch_rss_feeds(feeds: list[str], keywords: list[str]) -> list[dict]:
    """Fetch and filter RSS feeds"""
    results = []
    valid_feeds = [f.strip() for f in feeds if f.strip().startswith("http")]
    if not valid_feeds: return []

    async with httpx.AsyncClient(timeout=30) as client:
        for feed_url in valid_feeds:
            try:
                r = await client.get(feed_url)
                soup = BeautifulSoup(r.text, "xml")
                for item in soup.find_all("item")[:15]:
                    title = item.find("title").get_text()
                    if not keywords or any(kw.lower() in title.lower() for kw in keywords):
                        results.append({
                            "url": item.find("link").get_text(),
                            "title": title,
                            "source": "rss"
                        })
            except Exception: continue
    return results

async def download_video(url: str, output_path: str, max_duration: int = 1800) -> Optional[tuple]:
    """Download using yt-dlp with better error handling"""
    
    # Normalize YouTube URLs
    if "youtube.com/shorts/" in url:
        url = url.replace("/shorts/", "/watch?v=")
    
    # Ensure directory exists
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    ydl_opts = {
        "outtmpl": output_path,
        "format": "bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best",
        "quiet": True,
        "no_warnings": False,
        "extract_flat": False,
        "nocheckcertificate": True,
        "ignoreerrors": False,
        "no_color": True,
        "geo_bypass": True,
        "extractor_retries": 3,
        "fragment_retries": 3,
        "socket_timeout": 60,
        "retries": 3,
    }
    
    try:
        loop = asyncio.get_event_loop()
        def _dl():
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    logger.info(f"Downloading: {url} -> {output_path}")
                    
                    # Extract info and download
                    info = ydl.extract_info(url, download=True)
                    
                    if info:
                        duration = info.get("duration", 0)
                        title = info.get("title", "Unknown")
                        
                        # Check duration limit
                        if max_duration and duration > max_duration:
                            logger.warning(f"Video too long: {duration}s > {max_duration}s limit")
                            # Still return, let caller decide
                        
                        logger.info(f"Downloaded: {title[:50]}, Duration: {duration}s")
                        return duration, output_path
                    return None
                    
            except Exception as e:
                logger.error(f"Download failed: {e}")
                raise
        
        return await loop.run_in_executor(None, _dl)
    except Exception as e:
        logger.error(f"download_video failed: {e}")
        return None
        return None


async def check_video_availability(url: str, max_duration: int = None) -> dict:
    """Check if a video is available without downloading"""
    # Normalize URL
    if "youtube.com/shorts/" in url:
        url = url.replace("/shorts/", "/watch?v=")
    
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,
        "skip_download": True,
        "geo_bypass": True,
        "nocheckcertificate": True,
    }
    
    try:
        loop = asyncio.get_event_loop()
        def _check():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if not info:
                    return {"available": False, "error": "No info returned"}
                
                duration = info.get("duration", 0)
                title = info.get("title", "Unknown")
                is_live = info.get("is_live", False)
                was_live = info.get("was_live", False)
                
                # Skip live streams or streams with no/live duration
                if is_live or was_live or duration == 0:
                    return {
                        "available": False,
                        "error": "Live stream or no duration (not suitable)",
                        "title": title,
                        "duration": duration,
                    }
                
                # Check duration
                if max_duration and duration > max_duration:
                    return {
                        "available": False,
                        "error": f"Video too long ({duration}s > {max_duration}s)",
                        "title": title,
                        "duration": duration,
                    }
                
                # Prefer videos with reasonable duration
                if duration < 30:
                    return {
                        "available": False,
                        "error": f"Video too short ({duration}s < 30s)",
                        "title": title,
                        "duration": duration,
                    }
                
                return {
                    "available": True,
                    "title": title,
                    "duration": duration,
                    "uploader": info.get("uploader"),
                    "thumbnail": info.get("thumbnail"),
                    "view_count": info.get("view_count"),
                }
        return await loop.run_in_executor(None, _check)
    except yt_dlp.utils.DownloadError as e:
        error_str = str(e)
        if "unavailable" in error_str.lower():
            return {"available": False, "error": "Video is unavailable"}
        if "private" in error_str.lower():
            return {"available": False, "error": "Video is private"}
        if "region" in error_str.lower() or "geo" in error_str.lower():
            return {"available": False, "error": "Video is region-restricted"}
        logger.warning(f"Video check failed: {url} - {e}")
        return {"available": False, "error": error_str[:100]}
    except Exception as e:
        logger.warning(f"Video unavailable: {url} - {e}")
        return {"available": False, "error": str(e)[:100]}

async def scrape_all(keywords, twitter_accounts=None, rss_feeds=None, max_youtube=20, max_twitter=15, language="") -> list[dict]:
    all_clips = []
    seen = set()
    
    yt = await search_youtube(keywords, max_results=max_youtube, language=language)
    tw = await scrape_twitter_nitter(keywords, accounts=twitter_accounts, max_posts=max_twitter)
    rss = await fetch_rss_feeds(rss_feeds or CUSTOM_RSS_FEEDS, keywords)

    for c in yt + tw + rss:
        if c.get("url") and c["url"] not in seen:
            seen.add(c["url"])
            
            raw_source = c.get("source", "").lower()
            if "twitter" in raw_source:
                c["source"] = "twitter"
            elif "youtube" in raw_source:
                c["source"] = "youtube"
            elif "rss" in raw_source:
                c["source"] = "rss"
            else:
                c["source"] = "manual"

            all_clips.append(c)
    
    return all_clips
