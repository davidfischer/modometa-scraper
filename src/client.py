"""MTGO client for scraping calendar listings and parsing tournament pages."""

import json
import logging
import os
import re
import time
from datetime import date
from datetime import datetime
from datetime import timezone
from typing import List
from typing import Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from dateutil.parser import isoparse
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .config import MTGO_LIST_URL
from .config import MTGO_ROOT_URL
from .config import SKIP_FORMATS
from .config import VALID_FORMATS
from .config import get_user_agent
from .models import CacheItem
from .models import Deck
from .models import DeckItem
from .models import Round
from .models import RoundItem
from .models import Standing
from .models import Tournament
from .normalizer import DeckNormalizer
from .normalizer import OrderNormalizer
from .scryfall import ScryfallNormalizer


logger = logging.getLogger(__name__)


def parse_event_date(date_str: str) -> datetime:
    """Parse MTGO date strings into UTC datetime."""
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_str, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    # Fallback to isoparse
    dt = isoparse(date_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def tournament_from_url(url: str) -> Tournament:
    """Construct a Tournament instance from an MTGO event URL."""
    clean_url = url.split("?")[0].rstrip("/")
    slug = os.path.splitext(os.path.basename(clean_url))[0]
    json_filename = f"{slug}.json"

    date_match = re.search(r"(\d{4})-(\d{2})-(\d{2})", slug)
    parsed_date = None
    if date_match:
        try:
            parsed_date = date(
                int(date_match.group(1)),
                int(date_match.group(2)),
                int(date_match.group(3)),
            )
        except ValueError:
            pass

    name_part = slug[: date_match.start()].rstrip("-_") if date_match else slug
    title = (
        " ".join(word.capitalize() for word in name_part.split("-"))
        if name_part
        else slug
    )

    base_fmt = title.split()[0] if title else ""
    if base_fmt == "Duel":
        fmt = "Commander"
    elif base_fmt in VALID_FORMATS:
        fmt = base_fmt
    else:
        fmt = None

    return Tournament(
        date=parsed_date,
        name=title,
        uri=url,
        formats=fmt,
        json_file=json_filename,
    )


class MTGOClient:
    def __init__(
        self,
        session: Optional[requests.Session] = None,
        max_retries: int = 2,
    ):
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": get_user_agent()})
        self.max_retries = max_retries
        self.last_error: Optional[str] = None

        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    @staticmethod
    def _increment_month(d: date) -> date:
        """Increment date by one month to the 1st of the next month."""
        if d.month == 12:
            return date(d.year + 1, 1, 1)
        return date(d.year, d.month + 1, 1)

    def fetch_calendar(self, start_date: date, end_date: date) -> List[Tournament]:
        """Fetch all tournaments listed in MTGO calendar between start_date and end_date."""
        tournaments = []
        current_month = date(start_date.year, start_date.month, 1)
        target_month = date(end_date.year, end_date.month, 1)

        while current_month <= target_month:
            url = MTGO_LIST_URL.format(
                year=current_month.year, month=current_month.month
            )
            logger.info("Fetching calendar: %s", url)

            try:
                resp = self.session.get(url, timeout=30)
                if resp.status_code != 200:
                    logger.warning(
                        "Calendar returned HTTP %d for %s", resp.status_code, url
                    )
                    current_month = self._increment_month(current_month)
                    continue

                soup = BeautifulSoup(resp.text, "html.parser")
                items = soup.select("li.decklists-item")

                for item in items:
                    a_tag = item.select_one("a")
                    h3_tag = item.select_one("a > div > h3")
                    time_tag = item.select_one("a > time")

                    if not a_tag or not h3_tag or not time_tag:
                        continue

                    title = h3_tag.text.strip()
                    if any(
                        title.lower().startswith(skip.lower()) for skip in SKIP_FORMATS
                    ):
                        continue
                    event_url = urljoin(MTGO_ROOT_URL, a_tag.get("href", ""))
                    date_str = time_tag.get("datetime", "")

                    try:
                        parsed_date = isoparse(date_str).date()
                    except Exception as e:
                        logger.warning("Failed to parse date '%s': %s", date_str, e)
                        continue

                    if not (start_date <= parsed_date <= end_date):
                        continue

                    # Determine format
                    base_fmt = title.split()[0] if title else ""
                    if base_fmt == "Duel":
                        fmt = "Commander"
                    elif base_fmt in VALID_FORMATS:
                        fmt = base_fmt
                    else:
                        fmt = None

                    slug = os.path.splitext(os.path.basename(event_url))[0]
                    json_filename = f"{slug}.json"

                    tournaments.append(
                        Tournament(
                            date=parsed_date,
                            name=title,
                            uri=event_url,
                            formats=fmt,
                            json_file=json_filename,
                        )
                    )

            except Exception as e:
                logger.error("Error fetching calendar for %s: %s", url, e)

            current_month = self._increment_month(current_month)

        tournaments.sort(key=lambda t: (t.date, t.name))
        return tournaments

    @staticmethod
    def tournament_from_url(url: str) -> Tournament:
        return tournament_from_url(url)

    def fetch_event_data(self, event_url: str) -> Optional[dict]:
        """Download MTGO event page and extract window.MTGO.decklists.data JSON."""
        self.last_error = None
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.get(event_url, timeout=30)
                if resp.status_code != 200:
                    self.last_error = f"HTTP {resp.status_code}"
                    logger.warning(
                        "Event page returned HTTP %d for %s (attempt %d/%d)",
                        resp.status_code,
                        event_url,
                        attempt,
                        self.max_retries,
                    )
                    if resp.status_code == 404:
                        return None
                    if attempt < self.max_retries:
                        time.sleep(2 * attempt)
                        continue
                    return None

                match = re.search(
                    r"window\.MTGO\.decklists\.data\s*=\s*(\{.*?\});\s*(?:window\.|\n|</script>)",
                    resp.text,
                    re.DOTALL,
                )
                if not match:
                    # Fallback to line scanning
                    for line in resp.text.splitlines():
                        stripped = line.strip()
                        if stripped.startswith("window.MTGO.decklists.data = "):
                            raw_json = stripped[
                                len("window.MTGO.decklists.data = ") : -1
                            ]
                            return json.loads(raw_json)
                    self.last_error = "No MTGO.decklists.data found on page"
                    logger.warning("No MTGO.decklists.data found on page %s", event_url)
                    return None

                data = json.loads(match.group(1))
                if data.get("errorCode") == "SERVER_ERROR":
                    self.last_error = "Server error in MTGO event data"
                    logger.warning("Server error in MTGO event data for %s", event_url)
                    return None

                return data
            except Exception as e:
                self.last_error = f"Network error: {e}"
                logger.warning(
                    "Error downloading event data for %s (attempt %d/%d): %s",
                    event_url,
                    attempt,
                    self.max_retries,
                    e,
                )
                if attempt < self.max_retries:
                    time.sleep(2 * attempt)
                else:
                    logger.error(
                        "Failed downloading event data after %d attempts for %s",
                        self.max_retries,
                        event_url,
                    )
                    return None
        return None

    def parse_event(
        self,
        tournament: Tournament,
        event_json: dict,
        normalizer: Optional[ScryfallNormalizer] = None,
    ) -> Optional[CacheItem]:
        """Parse raw event JSON into a CacheItem with player count and normalized decks."""
        if not event_json:
            self.last_error = "No event data"
            return None

        # Extract player count
        raw_player_count = event_json.get("player_count")
        if raw_player_count and isinstance(raw_player_count, dict):
            players_val = raw_player_count.get("players")
            if players_val is not None:
                try:
                    tournament.player_count = int(players_val)
                except ValueError, TypeError:
                    pass

        event_type = "tournament" if "starttime" in event_json else "league"

        winloss = (
            self._parse_winloss(event_json) if event_type == "tournament" else None
        )
        standings = (
            self._parse_standings(event_json, winloss)
            if event_type == "tournament"
            else []
        )
        brackets = (
            self._parse_brackets(event_json) if event_type == "tournament" else []
        )
        decks = self._parse_decks(
            tournament, event_type, winloss, event_json, normalizer
        )

        if not decks:
            self.last_error = "Tournament has no decks (event likely did not fire)"
            logger.info("Tournament %s has no decks, skipping", tournament.json_file)
            return None

        if all(len(d.mainboard) == 0 for d in decks):
            self.last_error = "Tournament has only empty decks"
            logger.info(
                "Tournament %s has only empty decks, skipping", tournament.json_file
            )
            return None

        # Reorder decks based on standings and playoff brackets
        if standings:
            decks = OrderNormalizer.reorder_decks(
                decks, standings, brackets, update_result=True
            )

        return CacheItem(
            tournament=tournament,
            decks=decks,
            rounds=brackets,
            standings=standings,
        )

    @staticmethod
    def _parse_winloss(event_json: dict) -> Optional[dict]:
        raw_winloss = event_json.get("winloss")
        if not raw_winloss or not isinstance(raw_winloss, list):
            return None

        result = {}
        for entry in raw_winloss:
            login_id = str(entry.get("loginid"))
            wins = entry.get("wins", 0)
            losses = entry.get("losses", 0)
            result[login_id] = f"{wins}-{losses}"
        return result

    @staticmethod
    def _parse_standings(event_json: dict, winloss: Optional[dict]) -> List[Standing]:
        raw_standings = event_json.get("standings")
        if not raw_standings or not isinstance(raw_standings, list):
            return []

        standings = []
        for s in raw_standings:
            player = s.get("login_name", "")
            player_id = str(s.get("loginid", ""))
            rank = int(s.get("rank", 0))
            points = int(s.get("score", 0))
            gwp = float(s.get("gamewinpercentage", 0.0))
            ogwp = float(s.get("opponentgamewinpercentage", 0.0))
            omwp = float(s.get("opponentmatchwinpercentage", 0.0))

            wins = 0
            losses = 0
            if winloss and player_id in winloss:
                parts = winloss[player_id].split("-")
                if len(parts) >= 2:
                    wins = int(parts[0])
                    losses = int(parts[1])

            standings.append(
                Standing(
                    rank=rank,
                    player=player,
                    points=points,
                    wins=wins,
                    losses=losses,
                    draws=0,
                    omwp=omwp,
                    gwp=gwp,
                    ogwp=ogwp,
                )
            )

        standings.sort(key=lambda s: s.rank)
        return standings

    @staticmethod
    def _parse_brackets(event_json: dict) -> List[Round]:
        raw_brackets = event_json.get("brackets")
        if not raw_brackets or not isinstance(raw_brackets, list):
            return []

        rounds = []
        for b in raw_brackets:
            matches = []
            for match in b.get("matches", []):
                players = match.get("players", [])
                if len(players) < 2:
                    continue
                p1_name = players[0].get("player", "")
                p2_name = players[1].get("player", "")
                p1_wins = players[0].get("wins", 0)
                p2_wins = players[1].get("wins", 0)
                p2_winner = players[1].get("winner", False)

                if p2_winner:
                    matches.append(
                        RoundItem(
                            player1=p2_name,
                            player2=p1_name,
                            result=f"{p2_wins}-{p1_wins}-0",
                        )
                    )
                else:
                    matches.append(
                        RoundItem(
                            player1=p1_name,
                            player2=p2_name,
                            result=f"{p1_wins}-{p2_wins}-0",
                        )
                    )

            round_name = "Quarterfinals"
            if len(matches) == 2:
                round_name = "Semifinals"
            elif len(matches) == 1:
                round_name = "Finals"
            elif len(matches) == 8:
                round_name = "Round of 16"

            rounds.append(Round(round_name=round_name, matches=matches))

        # Only retain standard bracket rounds matching MTG_decklistcache convention
        valid_rounds = [
            r
            for r in rounds
            if r.round_name in {"Quarterfinals", "Semifinals", "Finals"}
        ]
        return valid_rounds

    def _parse_decks(
        self,
        tournament: Tournament,
        event_type: str,
        winloss: Optional[dict],
        event_json: dict,
        normalizer: Optional[ScryfallNormalizer],
    ) -> List[Deck]:
        raw_decklists = event_json.get("decklists")
        if not raw_decklists or not isinstance(raw_decklists, list):
            return []

        date_str = (
            event_json.get("publish_date")
            if event_type == "league"
            else event_json.get("starttime")
        )
        event_datetime = (
            parse_event_date(date_str) if date_str else datetime.now(timezone.utc)
        )

        decks = []
        rank = 1

        for raw_deck in raw_decklists:
            player = raw_deck.get("player", "")
            player_id = str(raw_deck.get("loginid", ""))

            mainboard = []
            for item in raw_deck.get("main_deck", []):
                name = item.get("card_attributes", {}).get("card_name", "")
                count = int(item.get("qty", 1))
                norm_name = normalizer.normalize(name) if normalizer else name
                mainboard.append(DeckItem(count=count, card_name=norm_name))

            sideboard = []
            for item in raw_deck.get("sideboard_deck", []):
                name = item.get("card_attributes", {}).get("card_name", "")
                count = int(item.get("qty", 1))
                norm_name = normalizer.normalize(name) if normalizer else name
                sideboard.append(DeckItem(count=count, card_name=norm_name))

            # Determine result
            if event_type == "league":
                wins = (
                    raw_deck.get("wins", {}).get("wins", "0")
                    if isinstance(raw_deck.get("wins"), dict)
                    else str(raw_deck.get("wins", "0"))
                )
                result = {
                    "5": "5-0",
                    "4": "4-1",
                    "3": "3-2",
                    "2": "2-4",
                    "1": "1-4",
                    "0": "0-5",
                }.get(str(wins), "")
            else:
                if winloss and player_id in winloss:
                    result = winloss[player_id]
                else:
                    if rank == 1:
                        result = "1st Place"
                    elif rank == 2:
                        result = "2nd Place"
                    elif rank == 3:
                        result = "3rd Place"
                    else:
                        result = f"{rank}th Place"
                    rank += 1

            deck = Deck(
                date=event_datetime,
                player=player,
                result=result,
                anchor_uri=f"{tournament.uri}#deck_{player}",
                mainboard=mainboard,
                sideboard=sideboard,
            )

            # Deduplicate and sort cards alphabetically
            decks.append(DeckNormalizer.normalize(deck))

        return decks
