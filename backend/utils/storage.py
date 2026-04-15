"""
Storage utility - local file system (S3-ready interface)
"""

import shutil
import logging
from pathlib import Path
from datetime import datetime

from utils.env import get_env_value

logger = logging.getLogger(__name__)

STORAGE_ROOT = get_env_value("STORAGE_ROOT", "./storage")

DIRS = {
    "clips": "clips",
    "audio": "audio",
    "transcripts": "transcripts",
    "tts": "tts",
    "composed": "composed",
    "thumbnails": "thumbnails",
    "chill": "chill",
    "temp": "temp",
}


def init_storage():
    for name, sub in DIRS.items():
        path = Path(STORAGE_ROOT) / sub
        path.mkdir(parents=True, exist_ok=True)
    logger.info(f"Storage initialized at {STORAGE_ROOT}")


def get_path(category: str, filename: str) -> str:
    base = Path(STORAGE_ROOT) / DIRS.get(category, "temp")
    base.mkdir(parents=True, exist_ok=True)
    return str(base / filename)


def timestamped_filename(prefix: str, ext: str) -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{prefix}_{ts}.{ext}"


def copy_to_storage(src: str, category: str, filename: str) -> str:
    dest = get_path(category, filename)
    shutil.copy2(src, dest)
    return dest


def file_exists(path: str) -> bool:
    return Path(path).exists()


def get_file_size_mb(path: str) -> float:
    return Path(path).stat().st_size / (1024 * 1024)


init_storage()
