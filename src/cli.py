"""CLI entrypoint for modometa-scraper."""

import argparse
import logging
import sys
from collections import Counter
from datetime import datetime
from typing import Optional

from dateutil import parser as date_parser

from .client import tournament_from_url
from .config import DEFAULT_CACHE_DIR
from .config import DEFAULT_LOOKBACK_DAYS
from .config import DEFAULT_REQUEST_DELAY
from .scraper import MTGOSyncEngine
from .scraper import load_failed_events
from .scraper import save_failed_events


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
        "--url",
        type=str,
        action="append",
        help="Direct MTGO tournament URL to sync (can be specified multiple times)",
    )
    parser.add_argument(
        "--retry-failed",
        type=str,
        nargs="?",
        const="failed_events.json",
        default=None,
        help="Retry tournaments from a failed events JSON file (defaults to failed_events.json if no path provided)",
    )
    parser.add_argument(
        "--failed-file",
        type=str,
        default="failed_events.json",
        help="Path to save failed tournaments JSON if any events fail",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=DEFAULT_REQUEST_DELAY,
        help="Delay in seconds between HTTP requests",
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

    tournaments_to_sync = None
    if args.url:
        tournaments_to_sync = [tournament_from_url(u) for u in args.url]
    elif args.retry_failed:
        try:
            tournaments_to_sync = load_failed_events(args.retry_failed)
        except Exception as e:
            print(
                f"Error loading failed events file '{args.retry_failed}': {e}",
                file=sys.stderr,
            )
            sys.exit(1)
        if not tournaments_to_sync:
            print(f"No tournaments found to retry in '{args.retry_failed}'.")
            sys.exit(0)
        print(
            f"Loaded {len(tournaments_to_sync)} tournament(s) to retry from '{args.retry_failed}'."
        )

    engine = MTGOSyncEngine(cache_root=args.cache_dir, request_delay=args.delay)
    stats = engine.sync(
        start_date=start_date,
        end_date=end_date,
        auto_resume=args.auto_resume,
        lookback_days=args.lookback_days,
        force=args.force,
        skip_leagues=args.skip_leagues,
        tournaments=tournaments_to_sync,
    )

    print("\n--- Sync Summary ---")
    print(f"Total Found: {stats['total_found']}")
    print(f"Created:     {stats['created']}")
    print(f"Updated:     {stats['updated']}")
    print(f"Skipped:     {stats['skipped']}")
    print(f"Failed:      {stats['failed']}")

    failed_events = stats.get("failed_events", [])
    if failed_events:
        save_failed_events(failed_events, args.failed_file)
        print(f"\nSaved {len(failed_events)} failed event(s) to: {args.failed_file}")
        print(
            f"To retry these events, run: python main.py --retry-failed {args.failed_file}"
        )

        reasons = Counter(t.failure_reason or "Unknown reason" for t in failed_events)
        print("\nFailure breakdown by reason:")
        for reason, count in reasons.most_common():
            print(f"  - {reason}: {count}")

        print("\n--- Failed Events Preview ---")
        preview_limit = min(len(failed_events), 10)
        for t in failed_events[:preview_limit]:
            date_str = f"[{t.date}] " if t.date else ""
            reason_str = f" ({t.failure_reason})" if t.failure_reason else ""
            print(f"- {date_str}{t.name}: {t.uri}{reason_str}")
        if len(failed_events) > preview_limit:
            print(
                f"... and {len(failed_events) - preview_limit} more (see {args.failed_file})"
            )
    elif args.retry_failed:
        print("\nAll retried tournaments succeeded!")


if __name__ == "__main__":
    main()
