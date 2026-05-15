from __future__ import annotations

import logging

from app.worker.scheduler_config import build_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


def run_worker() -> None:
    scheduler = build_scheduler()
    logger.info("Starting Kalshi research worker")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Stopping Kalshi research worker")
        scheduler.shutdown(wait=False)
