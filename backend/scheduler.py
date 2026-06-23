"""Price-monitor scheduler.

Runs all configured Scrapy spiders for every distinct active Alert.search_query
on a fixed interval (default: every 12 hours) and once immediately on startup.

How to run
----------
From the ``backend/`` directory:

    uv run python scheduler.py

The script must be started from ``backend/`` so that:
  * ``models.*`` imports resolve (Python path rooted at ``backend/``).
  * ``SCRAPY_SETTINGS_MODULE`` resolves to ``price_scrapers.settings``, whose
    module lives at ``backend/scrapers/price_scrapers/settings.py``.  The
    ``scrapy.cfg`` file that Scrapy uses to locate that module is in
    ``backend/scrapers/``, so we ``os.chdir`` into that directory before
    calling ``get_project_settings()`` and restore the original cwd afterwards.

CrawlerProcess note
-------------------
A ``CrawlerProcess`` (or its underlying Twisted reactor) can only be started
**once** per Python interpreter process.  To handle multiple search queries and
multiple spiders per run we therefore:
  1. Queue *all* crawls with ``process.crawl(...)`` before calling
     ``process.start()``.
  2. Use a fresh ``CrawlerProcess`` every 12 hours by running each scheduled
     call inside a ``concurrent.futures.ProcessPoolExecutor`` worker so that
     each invocation gets its own interpreter (and thus its own reactor).
     This sidesteps the "reactor already started" limitation cleanly.
"""

from __future__ import annotations

import logging
import os
import sys
from concurrent.futures import ProcessPoolExecutor, wait
from pathlib import Path

from apscheduler.schedulers.blocking import BlockingScheduler

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

INTERVAL_HOURS: int = 12

# Spiders to run for every search_query.  Add new spider names here as more
# marketplaces are implemented.
SPIDER_NAMES: list[str] = ["mercadolibre"]

# Absolute paths so the worker subprocess can find them even if the OS cwd
# changes between scheduler ticks.
_BACKEND_DIR = Path(__file__).resolve().parent          # backend/
_SCRAPERS_DIR = _BACKEND_DIR / "scrapers"               # backend/scrapers/

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Worker function (runs in a subprocess)
# ---------------------------------------------------------------------------


def _crawl_worker(
    scrapers_dir: str,
    backend_dir: str,
    search_queries: list[str],
    spider_names: list[str],
) -> None:
    """Entry point executed inside a fresh subprocess.

    A subprocess gets its own Twisted reactor, so ``CrawlerProcess`` can be
    started without hitting the "reactor already running" error that occurs
    when re-using the same interpreter for multiple scheduler ticks.

    Parameters
    ----------
    scrapers_dir:
        Absolute path to ``backend/scrapers/``.  We ``chdir`` here so that
        Scrapy's ``get_project_settings()`` picks up ``scrapy.cfg`` and
        resolves ``price_scrapers.settings`` correctly.
    backend_dir:
        Absolute path to ``backend/``.  Added to ``sys.path`` so that
        ``models.*`` imports inside the Scrapy pipeline continue to work.
    search_queries:
        Distinct active search queries fetched from the DB.
    spider_names:
        Names of spiders to run for every query.
    """
    import os
    import sys

    # Make ``models.*`` importable inside the pipeline.
    if backend_dir not in sys.path:
        sys.path.insert(0, backend_dir)

    # Change into the scrapy project root so ``scrapy.cfg`` is found and
    # ``price_scrapers.settings`` resolves via the ``[settings]`` section.
    os.chdir(scrapers_dir)

    # Add the scrapers dir to sys.path so ``price_scrapers.*`` is importable.
    if scrapers_dir not in sys.path:
        sys.path.insert(0, scrapers_dir)

    from scrapy.crawler import CrawlerProcess
    from scrapy.utils.project import get_project_settings

    settings = get_project_settings()
    # Target marketplaces (e.g. Mercado Libre) forbid their listing pages in
    # robots.txt; for this personal-use tool we disable robots obedience here so
    # the scheduled runs behave like the manual `-s ROBOTSTXT_OBEY=False` runs.
    settings.set("ROBOTSTXT_OBEY", False)
    process = CrawlerProcess(settings)

    for query in search_queries:
        for spider_name in spider_names:
            process.crawl(spider_name, search_query=query)

    process.start()  # blocks until all crawls finish


# ---------------------------------------------------------------------------
# Main scheduled function
# ---------------------------------------------------------------------------


def run_spiders() -> None:
    """Query active alerts and launch Scrapy spiders for each search_query.

    Failures inside the subprocess are caught and logged so the scheduler
    loop is never interrupted.
    """
    # Import here (not at module top) so that the module can be imported
    # without needing a live database connection (e.g. during testing or when
    # the file is imported by tools/linters).
    from models.alert import Alert
    from models.base import SessionLocal

    db = SessionLocal()
    try:
        rows: list[str] = (
            db.query(Alert.search_query)
            .filter(Alert.is_active.is_(True))
            .distinct()
            .all()
        )
        search_queries = [row[0] for row in rows]
    finally:
        db.close()

    if not search_queries:
        logger.info("run_spiders: no active alerts found — nothing to scrape.")
        return

    total_crawls = len(search_queries) * len(SPIDER_NAMES)
    logger.info(
        "run_spiders: launching %d crawl(s) for %d query(ies) across spider(s): %s",
        total_crawls,
        len(search_queries),
        ", ".join(SPIDER_NAMES),
    )

    try:
        with ProcessPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                _crawl_worker,
                str(_SCRAPERS_DIR),
                str(_BACKEND_DIR),
                search_queries,
                SPIDER_NAMES,
            )
            # wait() surfaces exceptions without crashing the scheduler.
            done, _ = wait([future])
            future.result()  # re-raise any exception from the worker
        logger.info("run_spiders: all crawls completed successfully.")
    except Exception:
        logger.exception(
            "run_spiders: spider run failed — scheduler will retry at next interval."
        )


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    scheduler = BlockingScheduler()

    # Run immediately on startup, then every INTERVAL_HOURS hours.
    scheduler.add_job(run_spiders, "interval", hours=INTERVAL_HOURS, id="spider_job")

    logger.info(
        "Scheduler starting — running spiders now and then every %d hour(s).",
        INTERVAL_HOURS,
    )

    # Fire once right away before the first scheduled tick.
    try:
        run_spiders()
    except Exception:
        logger.exception("Initial spider run failed — continuing with scheduled runs.")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped.")
