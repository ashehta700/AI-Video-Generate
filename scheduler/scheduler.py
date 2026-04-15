"""
APScheduler-based daily automation scheduler.
Run standalone: python scheduler/scheduler.py
"""

import asyncio
import json
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../backend"))

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from utils.database import AsyncSessionLocal, init_db
from utils.env import get_env_int, get_env_value
from utils.logger import setup_logging
from services import pipeline_service

setup_logging()
logger = logging.getLogger("scheduler")

SCHEDULE_HOUR = get_env_int("SCHEDULE_HOUR", 8)
SCHEDULE_MINUTE = get_env_int("SCHEDULE_MINUTE", 0)
MAX_VIDEOS = get_env_int("MAX_VIDEOS_PER_DAY", 3)
DEFAULT_KEYWORDS_JSON = get_env_value(
    "DEFAULT_KEYWORDS",
    '["מלחמה","עזה","הסכם","ביטחון","ממשלה","ירי","פיגוע"]',
)


async def run_daily_job():
    """Main scheduled task: scrape + pipeline"""
    logger.info("⏰ Scheduled daily pipeline triggered")
    keywords = json.loads(DEFAULT_KEYWORDS_JSON)

    async with AsyncSessionLocal() as db:
        try:
            job_ids = await pipeline_service.run_daily_pipeline(
                db=db,
                keywords=keywords,
                max_videos=MAX_VIDEOS,
            )
            logger.info(f"✅ Daily pipeline done. Jobs: {job_ids}")
        except Exception as e:
            logger.error(f"❌ Daily pipeline error: {e}", exc_info=True)


async def run_health_check():
    """Periodic health check — log alive status"""
    logger.info("💓 Scheduler heartbeat — system healthy")


async def main():
    await init_db()

    scheduler = AsyncIOScheduler()

    # Main daily pipeline
    scheduler.add_job(
        run_daily_job,
        CronTrigger(hour=SCHEDULE_HOUR, minute=SCHEDULE_MINUTE),
        id="daily_pipeline",
        name="Daily Arabic News Pipeline",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=3600,  # 1hr grace period
    )

    # Heartbeat every 30 min
    scheduler.add_job(
        run_health_check,
        "interval",
        minutes=30,
        id="heartbeat",
        name="Health Check",
    )

    scheduler.start()
    logger.info(
        f"🕐 Scheduler started. Daily pipeline at {SCHEDULE_HOUR:02d}:{SCHEDULE_MINUTE:02d} UTC"
    )

    try:
        while True:
            await asyncio.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
        logger.info("Scheduler stopped")


if __name__ == "__main__":
    asyncio.run(main())
