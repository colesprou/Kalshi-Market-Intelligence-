from __future__ import annotations

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.config import settings
from app.worker.jobs.research_jobs import (
    calculate_derived_metrics_job,
    calculate_market_feature_buckets_job,
    calculate_opportunity_scores_job,
    cleanup_aggregation_job,
    detect_market_events_job,
    discover_markets_job,
    fast_poll_live_markets_job,
    pull_kalshi_orderbooks_job,
    pull_kalshi_private_fills_job,
    pull_kalshi_trades_job,
    pull_sharp_book_limits_job,
    pull_sharp_book_odds_job,
)


def build_scheduler() -> BlockingScheduler:
    scheduler = BlockingScheduler(timezone="UTC")
    defaults = {"max_instances": 1, "coalesce": True, "misfire_grace_time": 30}

    scheduler.add_job(
        discover_markets_job,
        IntervalTrigger(seconds=settings.discover_markets_interval_seconds),
        id="discover_markets",
        replace_existing=True,
        **defaults,
    )
    scheduler.add_job(
        pull_kalshi_orderbooks_job,
        IntervalTrigger(seconds=settings.kalshi_orderbook_interval_seconds),
        id="pull_kalshi_orderbooks",
        replace_existing=True,
        **defaults,
    )
    scheduler.add_job(
        fast_poll_live_markets_job,
        IntervalTrigger(seconds=settings.fast_poll_interval_seconds),
        id="fast_poll_live_markets",
        replace_existing=True,
        **defaults,
    )
    scheduler.add_job(
        pull_kalshi_trades_job,
        IntervalTrigger(seconds=settings.kalshi_trades_interval_seconds),
        id="pull_kalshi_trades",
        replace_existing=True,
        **defaults,
    )
    scheduler.add_job(
        pull_kalshi_private_fills_job,
        IntervalTrigger(seconds=settings.private_fills_interval_seconds),
        id="pull_kalshi_private_fills",
        replace_existing=True,
        **defaults,
    )
    scheduler.add_job(
        pull_sharp_book_odds_job,
        IntervalTrigger(seconds=settings.sharp_odds_interval_seconds),
        id="pull_sharp_book_odds",
        replace_existing=True,
        **defaults,
    )
    scheduler.add_job(
        pull_sharp_book_limits_job,
        IntervalTrigger(seconds=settings.sharp_limits_interval_seconds),
        id="pull_sharp_book_limits",
        replace_existing=True,
        **defaults,
    )
    scheduler.add_job(
        calculate_derived_metrics_job,
        IntervalTrigger(seconds=settings.derived_metrics_interval_seconds),
        id="calculate_derived_metrics",
        replace_existing=True,
        **defaults,
    )
    scheduler.add_job(
        calculate_opportunity_scores_job,
        IntervalTrigger(seconds=settings.opportunity_scores_interval_seconds),
        id="calculate_opportunity_scores",
        replace_existing=True,
        **defaults,
    )
    scheduler.add_job(
        calculate_market_feature_buckets_job,
        IntervalTrigger(seconds=settings.feature_bucket_interval_seconds),
        id="calculate_market_feature_buckets",
        replace_existing=True,
        **defaults,
    )
    scheduler.add_job(
        detect_market_events_job,
        IntervalTrigger(seconds=settings.event_detection_interval_seconds),
        id="detect_market_events",
        replace_existing=True,
        **defaults,
    )
    scheduler.add_job(
        cleanup_aggregation_job,
        IntervalTrigger(seconds=settings.cleanup_interval_seconds),
        id="cleanup_aggregation",
        replace_existing=True,
        **defaults,
    )
    return scheduler
