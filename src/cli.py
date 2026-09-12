"""CLI entrypoint for modometa-scraper."""

import argparse
import logging
import sys
from datetime import datetime
from typing import Optional

from dateutil import parser as date_parser

from .config import DEFAULT_CACHE_DIR
from .config import DEFAULT_LOOKBACK_DAYS
from .scraper import MTGOSyncEngine


def setup_logging(verbose: bool = False, log_file: Optional[str] = None):
    if not log_file:
        log_file = datetime.now().strftime("scraper_%Y%m%d-%H%M%S.log")

    level = logging.DEBUG if verbose else logging.INFO
    log_format = "[%(asctime)s] [%(levelname)s] %(name)s: %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    handlers = [
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_file, encoding="utf-8"),
    ]

    logging.basicConfig(
        level=level, format=log_format, datefmt=date_format, handlers=handlers
    )


def parse_args():
    parser = argparse.ArgumentParser(
        description="MTGO Decklist and Tournament Cache Scraper",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--cache-dir",
        type=str,
        default=DEFAULT_CACHE_DIR,
        help="Path to the MTGO tournament cache directory",
    )
    parser.add_argument(
        "--auto-resume",
        action="store_true",
        help="Automatically detect the latest cached date and sync from (latest - lookback_days) through today",
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=DEFAULT_LOOKBACK_DAYS,
        help="Number of days to look back when auto-resuming or checking partial days/leagues",
    )
    parser.add_argument(
        "--start-date",
        type=str,
        default=None,
        help="Start date in YYYY-MM-DD format (overrides auto-resume)",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        default=None,
        help="End date in YYYY-MM-DD format (defaults to today)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-fetching and rewriting of existing tournament files",
    )
    parser.add_argument(
        "--skip-leagues",
        action="store_true",
        help="Exclude league tournaments from synchronization",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    parser.add_argument(
        "--log-file",
        type=str,
        default=None,
        help="Path to log file (defaults to scraper_YYYYMMDD-HHMMSS.log in local time)",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    setup_logging(args.verbose, args.log_file)

    start_date = date_parser.parse(args.start_date).date() if args.start_date else None
    end_date = date_parser.parse(args.end_date).date() if args.end_date else None

    engine = MTGOSyncEngine(cache_root=args.cache_dir)
    stats = engine.sync(
        start_date=start_date,
        end_date=end_date,
        auto_resume=args.auto_resume,
        lookback_days=args.lookback_days,
        force=args.force,
        skip_leagues=args.skip_leagues,
    )

    print("\n--- Sync Summary ---")
    print(f"Total Found: {stats['total_found']}")
    print(f"Created:     {stats['created']}")
    print(f"Updated:     {stats['updated']}")
    print(f"Skipped:     {stats['skipped']}")
    print(f"Failed:      {stats['failed']}")

    if stats.get("failed_events"):
        print("\n--- Failed Events ---")
        for t in stats["failed_events"]:
            date_str = f"[{t.date}] " if t.date else ""
            print(f"- {date_str}{t.name}: {t.uri}")


if __name__ == "__main__":
    main()
