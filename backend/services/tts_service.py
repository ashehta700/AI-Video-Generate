"""
TTS Service v2
────────────────────────────────────────────────────────────────────────────────
Text-to-Speech for any language.
Providers (in order of preference):
  1. ElevenLabs   — best quality, multilingual, requires API key
  2. Edge TTS     — FREE, Microsoft Azure voices, 100+ languages, no API key
  3. gTTS         — FREE, Google voices, basic quality, no API key
  4. PlayHT       — alternative premium, requires API key

Edge TTS supports: Arabic, English, French, Spanish, German, Urdu, Hindi, etc.
"""

import asyncio
import logging
from pathlib import Path
import httpx

from utils.storage import get_path
from utils.env import get_env_token, get_env_value

logger = logging.getLogger(__name__)

TTS_PROVIDER = get_env_token("TTS_PROVIDER", "edge")  # edge | elevenlabs | playht | gtts

# ElevenLabs
ELEVENLABS_API_KEY = get_env_token("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = get_env_value("ELEVENLABS_VOICE_ID", "pNInz6obpgDQGcFmaJgB")
ELEVENLABS_MODEL = get_env_value("ELEVENLABS_MODEL", "eleven_multilingual_v2")

# PlayHT
PLAYHT_API_KEY = get_env_token("PLAYHT_API_KEY", "")
PLAYHT_USER_ID = get_env_token("PLAYHT_USER_ID", "")
PLAYHT_VOICE = get_env_value("PLAYHT_VOICE", "ar-XA-Standard-A")

# Edge TTS (FREE) — configure voice per language
EDGE_TTS_VOICE = get_env_value("EDGE_TTS_VOICE", "ar-SA-HamedNeural")  # Default: Arabic

# Voice map for auto-selection by language
EDGE_VOICE_MAP = {
    "arabic":     "ar-SA-HamedNeural",      # Arabic Male (news anchor style)
    "arabic_f":   "ar-SA-ZariyahNeural",    # Arabic Female
    "english":    "en-US-GuyNeural",        # English Male
    "english_f":  "en-US-JennyNeural",      # English Female (news)
    "french":     "fr-FR-HenriNeural",      # French Male
    "spanish":    "es-ES-AlvaroNeural",     # Spanish Male
    "german":     "de-DE-ConradNeural",     # German Male
    "urdu":       "ur-PK-AsadNeural",       # Urdu Male
    "hindi":      "hi-IN-MadhurNeural",     # Hindi Male
    "turkish":    "tr-TR-AhmetNeural",      # Turkish Male
    "persian":    "fa-IR-FaridNeural",      # Persian/Farsi Male
    "hebrew":     "he-IL-AvriNeural",       # Hebrew Male
    "russian":    "ru-RU-DmitryNeural",     # Russian Male
    "chinese":    "zh-CN-YunxiNeural",      # Chinese Male
    "japanese":   "ja-JP-KeitaNeural",      # Japanese Male
    "korean":     "ko-KR-InJoonNeural",     # Korean Male
    "portuguese": "pt-BR-AntonioNeural",    # Portuguese Male
    "italian":    "it-IT-DiegoNeural",      # Italian Male
}

# Voice style map for kids/engaging content
VOICE_STYLE_MAP = {
    "friendly": {
        "arabic": "ar-SA-HamedNeural",
        "english": "en-US-SaraNeural",
        "french": "fr-FR-DeniseNeural",
        "spanish": "es-ES-ElviraNeural",
    },
    "energetic": {
        "arabic": "ar-SA-SharkurNeural",
        "english": "en-US-AriaNeural",
        "french": "fr-FR-HenriNeural",
        "spanish": "es-MX-DaliaNeural",
    },
    "calm": {
        "arabic": "ar-SA-ZariyahNeural",
        "english": "en-US-EmmaNeural",
        "french": "fr-FR-BelleNeural",
        "spanish": "es-ES-LiaNeural",
    },
    "kids": {
        "arabic": "ar-SA-LayanNeural",
        "english": "en-US-GuyNeural",
        "french": "fr-FR-EloiseNeural",
        "spanish": "es-MX-LibertoNeural",
    },
}


def get_edge_voice(language: str, voice_style: str = "default") -> str:
    """Get best Edge TTS voice for a language and style"""
    lang_lower = language.lower() if language else "arabic"
    
    # Extract base language (e.g., "arabic" from "arabic")
    base_lang = lang_lower.split()[0] if lang_lower else "arabic"
    
    # Check if voice style is specified and available
    if voice_style and voice_style != "default" and voice_style in VOICE_STYLE_MAP:
        style_map = VOICE_STYLE_MAP[voice_style]
        for key, voice in style_map.items():
            if key in base_lang:
                return voice
    
    # Fallback to default voice map
    for key, voice in EDGE_VOICE_MAP.items():
        if key in base_lang or base_lang in key:
            return voice
    return EDGE_TTS_VOICE  # fallback to configured default


async def generate_tts_edge(text: str, job_id: int, language: str = "", voice_style: str = "default") -> str:
    """
    Generate TTS using Microsoft Edge TTS — FREE, no API key needed.
    High quality neural voices for 100+ languages.
    """
    try:
        import edge_tts
    except ImportError:
        raise ImportError("edge-tts not installed. Run: pip install edge-tts")

    output_path = get_path("tts", f"tts_job{job_id}.mp3")
    voice = get_edge_voice(language, voice_style) if language else EDGE_TTS_VOICE

    logger.info(f"Edge TTS: voice={voice}, style={voice_style}, chars={len(text)}")
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_path)

    size_mb = Path(output_path).stat().st_size / (1024 * 1024)
    logger.info(f"Edge TTS done: {output_path} ({size_mb:.1f} MB)")
    return output_path


async def generate_tts_elevenlabs(text: str, job_id: int, language: str = "") -> str:
    """Generate TTS using ElevenLabs (premium, multilingual)"""
    if not ELEVENLABS_API_KEY:
        raise ValueError("ELEVENLABS_API_KEY not configured")

    output_path = get_path("tts", f"tts_job{job_id}.mp3")

    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}",
            headers={"xi-api-key": ELEVENLABS_API_KEY, "Content-Type": "application/json"},
            json={
                "text": text,
                "model_id": ELEVENLABS_MODEL,
                "voice_settings": {
                    "stability": 0.5,
                    "similarity_boost": 0.8,
                    "style": 0.3,
                    "use_speaker_boost": True,
                },
            },
        )
        r.raise_for_status()
        with open(output_path, "wb") as f:
            f.write(r.content)

    size_mb = Path(output_path).stat().st_size / (1024 * 1024)
    logger.info(f"ElevenLabs TTS: {output_path} ({size_mb:.1f} MB)")
    return output_path


async def generate_tts_gtts(text: str, job_id: int, language: str = "") -> str:
    """Generate TTS using gTTS (Google) — FREE, basic quality"""
    try:
        from gtts import gTTS
        import asyncio
    except ImportError:
        raise ImportError("gtts not installed. Run: pip install gtts")

    output_path = get_path("tts", f"tts_job{job_id}.mp3")

    # Map language names to gTTS codes
    lang_map = {
        "arabic": "ar", "english": "en", "french": "fr",
        "spanish": "es", "german": "de", "urdu": "ur",
        "hindi": "hi", "turkish": "tr", "russian": "ru",
        "chinese": "zh", "japanese": "ja", "korean": "ko",
        "portuguese": "pt", "italian": "it",
    }
    lang_code = "ar"  # default Arabic
    if language:
        lang_lower = language.lower()
        for key, code in lang_map.items():
            if key in lang_lower:
                lang_code = code
                break

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, lambda: gTTS(text=text, lang=lang_code, slow=False).save(output_path))

    logger.info(f"gTTS: {output_path}")
    return output_path


async def generate_tts_playht(text: str, job_id: int, language: str = "") -> str:
    """Generate TTS using PlayHT"""
    if not PLAYHT_API_KEY or not PLAYHT_USER_ID:
        raise ValueError("PLAYHT credentials not configured")

    output_path = get_path("tts", f"tts_job{job_id}.mp3")

    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(
            "https://api.play.ht/api/v2/tts/stream",
            headers={
                "Authorization": f"Bearer {PLAYHT_API_KEY}",
                "X-User-Id": PLAYHT_USER_ID,
                "Content-Type": "application/json",
                "Accept": "audio/mpeg",
            },
            json={"text": text, "voice": PLAYHT_VOICE, "quality": "premium", "output_format": "mp3"},
        )
        r.raise_for_status()
        with open(output_path, "wb") as f:
            f.write(r.content)

    logger.info(f"PlayHT TTS: {output_path}")
    return output_path


async def generate_stub_tts(text: str, job_id: int) -> str:
    """Silent stub audio for testing"""
    import subprocess
    output_path = get_path("tts", f"tts_job{job_id}.mp3")
    duration = max(10, len(text) // 15)
    cmd = [
        "ffmpeg", "-y", "-f", "lavfi",
        "-i", f"anullsrc=r=44100:cl=stereo",
        "-t", str(duration), "-q:a", "9",
        "-acodec", "libmp3lame", output_path,
    ]
    proc = await asyncio.create_subprocess_exec(*cmd,
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
    await proc.wait()
    logger.warning(f"[STUB] Silent TTS: {output_path}")
    return output_path


async def generate_voice(text: str, job_id: int, language: str = "", voice_style: str = "default") -> str:
    """
    Main TTS entry point.
    Auto-selects provider based on TTS_PROVIDER env or availability.
    Edge TTS is free and works without any API key.
    """
    if not text or len(text.strip()) < 5:
        raise ValueError("Text too short for TTS")

    logger.info(f"TTS job {job_id}: {len(text)} chars, provider={TTS_PROVIDER}, lang={language or 'default'}, style={voice_style}")

    providers = []

    # Build provider priority list - pass voice_style to edge TTS
    if TTS_PROVIDER == "elevenlabs" and ELEVENLABS_API_KEY:
        providers = [
            ("elevenlabs", lambda t, j, l: generate_tts_elevenlabs(t, j, l)),
            ("edge", lambda t, j, l: generate_tts_edge(t, j, l, voice_style)),
            ("gtts", lambda t, j, l: generate_tts_gtts(t, j, l)),
        ]
    elif TTS_PROVIDER == "playht" and PLAYHT_API_KEY:
        providers = [
            ("playht", lambda t, j, l: generate_tts_playht(t, j, l)),
            ("edge", lambda t, j, l: generate_tts_edge(t, j, l, voice_style)),
        ]
    elif TTS_PROVIDER == "gtts":
        providers = [
            ("gtts", lambda t, j, l: generate_tts_gtts(t, j, l)),
            ("edge", lambda t, j, l: generate_tts_edge(t, j, l, voice_style)),
        ]
    else:
        # Default: Edge TTS (free) first
        providers = [
            ("edge", lambda t, j, l: generate_tts_edge(t, j, l, voice_style)),
            ("elevenlabs", lambda t, j, l: generate_tts_elevenlabs(t, j, l)) if ELEVENLABS_API_KEY else None,
            ("gtts", lambda t, j, l: generate_tts_gtts(t, j, l)),
        ]
        providers = [p for p in providers if p]

    for name, fn in providers:
        try:
            path = await fn(text, job_id, language)
            logger.info(f"TTS success via {name}")
            return path
        except Exception as e:
            logger.warning(f"TTS provider {name} failed: {e}")
            continue

    # Final fallback: silent stub
    logger.error("All TTS providers failed — using silent stub")
    return await generate_stub_tts(text, job_id)


def get_audio_duration(audio_path: str) -> float:
    """Get audio duration in seconds"""
    import subprocess, json
    cmd = ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", audio_path]
    result = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return float(json.loads(result.stdout)["format"]["duration"])
    except Exception:
        return 0.0
