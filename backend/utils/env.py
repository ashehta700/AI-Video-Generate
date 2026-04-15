"""
Environment helpers
Clean env values, strip inline comments, and parse common types.
"""

import logging
import os
import re

logger = logging.getLogger(__name__)

_INLINE_COMMENT_RE = re.compile(r"\s+#.*$")


def _strip_inline_comment(value: str) -> str:
    return _INLINE_COMMENT_RE.sub("", value).strip()


def clean_env_value(value: str) -> str:
    if value is None:
        return ""
    cleaned = value.strip()
    if not cleaned:
        return ""
    return _strip_inline_comment(cleaned)


def clean_env_token(value: str) -> str:
    cleaned = clean_env_value(value)
    if not cleaned:
        return ""
    if cleaned.lower().startswith("bearer "):
        cleaned = cleaned.split(None, 1)[1].strip()
    if any(ch.isspace() for ch in cleaned):
        cleaned = cleaned.split()[0]
    return cleaned


def get_env_value(name: str, default: str = "") -> str:
    return clean_env_value(os.getenv(name, default))


def get_env_token(name: str, default: str = "") -> str:
    return clean_env_token(os.getenv(name, default))


def get_env_int(name: str, default: int) -> int:
    raw = get_env_value(name, str(default))
    try:
        return int(raw)
    except (TypeError, ValueError):
        logger.warning(f"Invalid int for {name}, using default {default}")
        return default


def get_env_bool(name: str, default: bool = False) -> bool:
    raw = get_env_value(name, "")
    if not raw:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}
