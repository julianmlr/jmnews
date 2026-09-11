"""End-to-end pipeline: collect → filter → briefing → deliver."""

from __future__ import annotations

import sys
import zoneinfo
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import NamedTuple

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger

from jmnews.briefing import BriefingGenerator
from jmnews.config import Settings
from jmnews.delivery.telegram import DeliveryStatus, TelegramDelivery
from jmnews.filter import Filter
from jmnews.sources import enabled_sources
from jmnews.storage import Storage


class RunSummary(NamedTuple):
    run_id: str
    new_items: int
    filtered: int
    briefing_items: int
    ignored_count: int
    delivery_status: DeliveryStatus
    briefing_id: str


def setup_logging(settings: Settings) -> None:
    """Configure loguru: stderr + rotating file in log_dir."""
    logger.remove()
    logger.add(
        sys.stderr,
        level=settings.log_level,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}",
    )
    log_dir = Path(settings.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    logger.add(
        log_dir / "jmnews.log",
        level=settings.log_level,
        rotation="10 MB",
        retention="7 days",
        encoding="utf-8",
        enqueue=True,
    )


def collection_window_start(
    lookback_hours: int, *, now: datetime | None = None
) -> datetime:
    """Start of the collection window, floored to midnight UTC.

    Many sources publish date-only timestamps (nexxt-change, Insolvenzportal,
    die Vergabeplattformen, Südkurier), which parse to 00:00 of that day. A
    plain rolling `now - lookback_hours` cut then silently drops a whole day
    of items: the 06:45 run compares them against *yesterday 06:45*, so an ad
    that went online yesterday at 10:00 carries published_at = yesterday 00:00
    and is already outside the window — it was not yet online during the
    previous run and can never be collected afterwards. With a 24h lookback and
    a 06:45 schedule that blind spot swallowed ~72% of each day's postings.

    Flooring to midnight makes the window cover whole calendar days, which is
    the granularity the data actually has. Re-collecting an item that is
    already known is harmless: storage dedups by id (INSERT OR IGNORE), only
    unclassified items are filtered, and delivered items are never re-sent.
    """
    now = now or datetime.now(UTC)
    return (now - timedelta(hours=lookback_hours)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )


def run_once(settings: Settings) -> RunSummary:
    """Run the full collect → filter → briefing → deliver pipeline once."""
    storage = Storage(settings.db_path)
    run_id = storage.start_run("full")
    logger.info("Pipeline run {} starting", run_id)

    try:
        storage.backup()
        since = collection_window_start(settings.lookback_hours)

        new_items = _collect(storage, since)
        filtered = _filter(storage, settings, since)
        briefing_id, briefing_count, ignored, delivery_status = _briefing_and_deliver(
            storage, settings, since
        )
        storage.purge_old(days=settings.purge_days)
        storage.finish_run(run_id, "success")
        logger.info(
            "Pipeline run {} done: new={} filtered={} briefing={} ignored={} delivery={}",
            run_id,
            new_items,
            filtered,
            briefing_count,
            ignored,
            delivery_status,
        )
        return RunSummary(
            run_id=run_id,
            new_items=new_items,
            filtered=filtered,
            briefing_items=briefing_count,
            ignored_count=ignored,
            delivery_status=delivery_status,
            briefing_id=briefing_id,
        )
    except Exception as exc:
        logger.exception("Pipeline run {} failed", run_id)
        storage.finish_run(run_id, "failed", str(exc))
        raise


def _collect(storage: Storage, since: datetime) -> int:
    total_new = 0
    for source in enabled_sources():
        try:
            items = source.fetch(since)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Source {} fetch failed: {}", source.name, exc)
            continue
        inserted = storage.upsert_items(items)
        total_new += inserted
        logger.info(
            "[{}] fetched={} inserted={}",
            source.name,
            len(items),
            inserted,
        )
    return total_new


def _filter(storage: Storage, settings: Settings, since: datetime) -> int:
    unfiltered = storage.get_unfiltered_items_since(since)
    if not unfiltered:
        logger.info("No unfiltered items in window")
        return 0
    flt = Filter(settings)
    results = flt.classify(unfiltered)
    for r in results:
        storage.apply_filter_result(r)
    return len(results)


def run_daemon(settings: Settings) -> None:
    """Block on a scheduler that fires run_once daily at the configured time.

    Per spec the collect job is scheduled at 06:45 Berlin time; the full
    pipeline (collect → filter → briefing → deliver) typically completes
    in well under 15 minutes, hitting the 07:00 delivery target.
    """
    tz = zoneinfo.ZoneInfo(settings.timezone)
    sched = BlockingScheduler(timezone=tz)
    trigger = CronTrigger(
        hour=settings.collect_hour,
        minute=settings.collect_minute,
        timezone=tz,
    )
    sched.add_job(
        _safe_run,
        trigger=trigger,
        args=[settings],
        id="daily_briefing",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=600,  # tolerate up to 10 minutes if the system was busy
    )
    logger.info(
        "Daemon started; daily briefing at {:02d}:{:02d} {}",
        settings.collect_hour,
        settings.collect_minute,
        settings.timezone,
    )

    # Start the Telegram chat bot in a worker thread (no-op if disabled
    # or if credentials are missing). The scheduler continues to block
    # the main thread; the chat thread is a daemon so it dies with us.
    from jmnews import api, chat
    from jmnews.storage import Storage

    storage = Storage(settings.db_path)
    chat.run_in_thread(settings, storage)
    # Read-only JSON API for external consumers (e.g. the daily Claude
    # cloud routine). Also a daemon thread; no-op without JMNEWS_API_TOKEN.
    api.run_in_thread(settings, storage)

    sched.start()


def _safe_run(settings: Settings) -> None:
    """Wrapper so a single failed run does not kill the daemon."""
    try:
        run_once(settings)
    except Exception:  # noqa: BLE001
        logger.exception("Scheduled run failed; daemon continues")


def _briefing_and_deliver(
    storage: Storage,
    settings: Settings,
    since: datetime,
) -> tuple[str, int, int, DeliveryStatus]:
    items = storage.get_items_for_briefing(since)
    counts = storage.count_items_by_category(since)
    ignored_count = counts.get("ignore", 0)
    briefing_date = date.today()

    gen = BriefingGenerator(settings)
    briefing = gen.generate(items, briefing_date, ignored_count=ignored_count)
    storage.save_briefing(briefing)

    delivery = TelegramDelivery(settings)
    status = delivery.deliver(briefing)
    briefing.delivery_status = status
    briefing.delivered_at = datetime.now(UTC)
    storage.save_briefing(briefing)

    if status in ("telegram", "file"):
        storage.mark_delivered([i.id for i in items], briefing.id)

    return briefing.id, len(items), ignored_count, status
