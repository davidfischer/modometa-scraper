"""Core scraping and incremental update engine for MTGO tournaments."""

import glob
import json
import logging
import os
import re
import time
from datetime import date
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from typing import List
from typing import Optional
from typing import Tuple

from .client import MTGOClient
from .client import tournament_from_url
from .config import DEFAULT_LOOKBACK_DAYS
from .config import DEFAULT_REQUEST_DELAY
from .models import Tournament
from .scryfall import ScryfallNormalizer


logger = logging.getLogger(__name__)


def sanitize_filename(filename: str) -> str:
    """Remove unsafe characters from filename."""
    return re.sub(r'[<>:"/\\|?*]', "", filename)


def find_latest_cached_date(cache_root: str) -> Optional[date]:
    """Scan cache directory structure YYYY/MM/DD to find the most recent date."""
    if not os.path.exists(cache_root):
        return None

    dates = []
    # Match YYYY/MM/DD folders
    pattern = os.path.join(cache_root, "*", "*", "*")
    for path in glob.glob(pattern):
        parts = os.path.normpath(path).split(os.sep)
        if len(parts) >= 3:
            try:
                y, m, d = int(parts[-3]), int(parts[-2]), int(parts[-1])
                dates.append(date(y, m, d))
            except ValueError:
                continue

    return max(dates) if dates else None


def atomic_write_json(target_path: str, data: dict):
    """Write JSON to a temp file and atomically replace the target file."""
    dir_name = os.path.dirname(target_path)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)
    temp_path = os.path.join(dir_name, f".tmp_{os.path.basename(target_path)}")

    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    os.replace(temp_path, target_path)


class MTGOSyncEngine:
    def __init__(
        self,
        cache_root: str,
        scryfall_cache_dir: str = ".cache",
        normalizer: Optional[ScryfallNormalizer] = None,
        client: Optional[MTGOClient] = None,
        request_delay: float = DEFAULT_REQUEST_DELAY,
    ):
        self.cache_root = os.path.abspath(cache_root)
        self.scryfall_cache_dir = scryfall_cache_dir
        self.client = client or MTGOClient(request_delay=request_delay)
        if client and hasattr(self.client, "request_delay"):
            self.client.request_delay = request_delay

        # Lazily loaded
        # This checks and updates the Scryfall cache if necessary
        self._normalizer = normalizer

    @property
    def normalizer(self) -> ScryfallNormalizer:
        if self._normalizer is None:
            self._normalizer = ScryfallNormalizer.get_instance(self.scryfall_cache_dir)
        return self._normalizer

    def resolve_date_range(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        auto_resume: bool = False,
        lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    ) -> Tuple[date, date]:
        """Determine date range based on explicit arguments or auto-resume."""
        today = datetime.now(timezone.utc).date()
        effective_end = end_date or today

        if auto_resume:
            latest_cached = find_latest_cached_date(self.cache_root)
            if latest_cached:
                effective_start = latest_cached - timedelta(days=lookback_days)
                logger.info(
                    "Auto-resume: latest cached date is %s. Starting from %s (lookback=%d days)",
                    latest_cached,
                    effective_start,
                    lookback_days,
                )
            else:
                effective_start = effective_end - timedelta(days=7)
                logger.info(
                    "Auto-resume: cache is empty. Defaulting to 7 days ago: %s",
                    effective_start,
                )
        else:
            effective_start = start_date or (
                effective_end - timedelta(days=DEFAULT_LOOKBACK_DAYS)
            )

        return effective_start, effective_end

    def _sync_tournament(
        self,
        t: Tournament,
        force: bool,
        lookback_days: int,
        today: date,
        stats: dict,
    ) -> bool:
        # Fallback date if missing
        if not t.date:
            t.date = today

        safe_filename = sanitize_filename(t.json_file or "unknown.json")
        target_dir = os.path.join(
            self.cache_root,
            str(t.date.year),
            f"{t.date.month:02d}",
            f"{t.date.day:02d}",
        )
        target_path = os.path.join(target_dir, safe_filename)

        is_league = "league" in t.name.lower()
        # Active/recent events are those within lookback days or leagues from recently
        is_recent = (today - t.date).days <= lookback_days

        file_exists = os.path.exists(target_path)
        cached_data = None
        if file_exists:
            try:
                with open(target_path, "r", encoding="utf-8") as f:
                    cached_data = json.load(f)
            except Exception as e:
                logger.warning(
                    "Could not read existing cache file %s: %s", target_path, e
                )
                file_exists = False

        # If it's a closed tournament in the past, file exists, and already has player count, we can skip
        if file_exists and not force and not is_league and not is_recent:
            cached_pc = (
                cached_data.get("Tournament", {}).get("PlayerCount")
                if cached_data
                else None
            )
            if cached_pc is not None:
                stats["skipped"] += 1
                return True

        logger.info("Checking tournament: %s (%s)", t.name, t.uri)
        raw_event = self.client.fetch_event_data(t.uri)
        if not raw_event:
            reason = getattr(self.client, "last_error", None)
            if not isinstance(reason, str):
                reason = "Failed to fetch event data"
            t.failure_reason = reason
            logger.warning(
                "Failed to fetch event data for %s: %s", t.uri, t.failure_reason
            )
            return False

        # Compare with cache if file exists
        if file_exists and not force and cached_data:
            remote_decks = len(raw_event.get("decklists", []))
            cached_decks = len(cached_data.get("Decks", []))

            raw_pc = raw_event.get("player_count", {})
            remote_pc = (
                int(raw_pc["players"])
                if raw_pc and "players" in raw_pc and raw_pc["players"]
                else None
            )
            cached_pc = cached_data.get("Tournament", {}).get("PlayerCount")

            if remote_decks == cached_decks and remote_pc == cached_pc:
                logger.debug(
                    "No updates for %s (%d decks, player_count=%s). Skipping.",
                    safe_filename,
                    remote_decks,
                    remote_pc,
                )
                stats["skipped"] += 1
                return True
            else:
                logger.info(
                    "Update detected for %s: decks (%d -> %d), player_count (%s -> %s)",
                    safe_filename,
                    cached_decks,
                    remote_decks,
                    cached_pc,
                    remote_pc,
                )

        # Parse event
        item = self.client.parse_event(t, raw_event, self.normalizer)
        if not item:
            reason = getattr(self.client, "last_error", None)
            if not isinstance(reason, str):
                reason = "Event yielded no valid cache item"
            t.failure_reason = reason
            logger.warning(
                "Event %s yielded no valid cache item: %s",
                safe_filename,
                t.failure_reason,
            )
            return False

        atomic_write_json(target_path, item.to_dict())
        t.failure_reason = None
        if file_exists:
            stats["updated"] += 1
            logger.info("Updated: %s", target_path)
        else:
            stats["created"] += 1
            logger.info("Created: %s", target_path)

        return True

    def sync(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        auto_resume: bool = False,
        lookback_days: int = DEFAULT_LOOKBACK_DAYS,
        force: bool = False,
        skip_leagues: bool = False,
        retry_delay: int = 5,
        tournaments: Optional[List[Tournament]] = None,
    ) -> dict:
        """Run synchronization across the resolved date range (or given tournaments) with deferred retry."""
        if tournaments is None:
            start, end = self.resolve_date_range(
                start_date, end_date, auto_resume, lookback_days
            )
            logger.info("Beginning sync for MTGO events from %s to %s", start, end)

            tournaments = self.client.fetch_calendar(start, end)
            if skip_leagues:
                tournaments = [t for t in tournaments if "league" not in t.name.lower()]
        else:
            logger.info("Beginning sync for %d specified event(s)", len(tournaments))

        stats = {
            "total_found": len(tournaments),
            "created": 0,
            "updated": 0,
            "skipped": 0,
            "failed": 0,
            "failed_events": [],
        }
        today = datetime.now(timezone.utc).date()
        deferred_retries = []

        for t in tournaments:
            success = self._sync_tournament(t, force, lookback_days, today, stats)
            if not success:
                logger.warning(
                    "Queueing %s (%s) for deferred retry at end of run",
                    t.name,
                    t.json_file,
                )
                deferred_retries.append(t)

        if deferred_retries:
            logger.info(
                "Starting deferred retry pass for %d failed event(s)...",
                len(deferred_retries),
            )
            if retry_delay > 0:
                time.sleep(retry_delay)
            for t in deferred_retries:
                logger.info("Deferred retry: %s (%s)", t.name, t.json_file)
                success = self._sync_tournament(t, force, lookback_days, today, stats)
                if not success:
                    logger.error(
                        "Deferred retry also failed for %s (%s). Marking as failed.",
                        t.name,
                        t.json_file,
                    )
                    stats["failed"] += 1
                    stats["failed_events"].append(t)

        logger.info("Sync complete! Stats: %s", stats)
        return stats


def save_failed_events(failed_events: List[Tournament], file_path: str) -> None:
    """Save failed tournaments to a JSON file."""
    data = [t.to_failed_dict() for t in failed_events]
    atomic_write_json(file_path, data)
    logger.info("Saved %d failed event(s) to %s", len(failed_events), file_path)


def load_failed_events(file_path: str) -> List[Tournament]:
    """Load failed tournaments from a JSON file or newline-separated text file of URLs."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Failed events file not found: {file_path}")

    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read().strip()

    if not content:
        return []

    tournaments = []
    if content.startswith("[") or content.startswith("{"):
        data = json.loads(content)
        if isinstance(data, dict):
            data = data.get("failed_events", [data])
        for item in data:
            if isinstance(item, dict):
                tournaments.append(Tournament.from_failed_dict(item))
            elif isinstance(item, str):
                tournaments.append(tournament_from_url(item))
    else:
        for line in content.splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                tournaments.append(tournament_from_url(line))

    return tournaments
