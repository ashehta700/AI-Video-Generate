"""
Logging setup - structured, color-coded console output
"""

import logging
import sys

from utils.env import get_env_value


def setup_logging():
    log_level = get_env_value("LOG_LEVEL", "INFO").upper()
    
    fmt = "%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"

    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format=fmt,
        datefmt=datefmt,
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("logs/app.log", encoding="utf-8"),
        ],
    )

    # Quieten noisy libraries
    for noisy in ["httpx", "httpcore", "urllib3", "asyncio"]:
        logging.getLogger(noisy).setLevel(logging.WARNING)
