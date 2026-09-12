"""Scryfall bulk data manager and card name normalizer."""

import gzip
import json
import logging
import os
import time
from typing import Dict
from typing import Optional

import requests

from .config import SCRYFALL_BULK_URL
from .config import SCRYFALL_CACHE_TTL_HOURS
from .config import get_user_agent


logger = logging.getLogger(__name__)

# Known MTGO naming discrepancies / typos
# https://github.com/fbettega/mtg_decklist_scrapper/blob/8f2ecae0efdd01b214de86bc2bc5e0243ffef981/comon_tools/tools.py#L30
STATIC_CORRECTIONS = {
    "Full Art Plains": "Plains",
    "Full Art Island": "Island",
    "Full Art Swamp": "Swamp",
    "Full Art Mountain": "Mountain",
    "Full Art Forest": "Forest",
    "Altar Of Dementia": "Altar of Dementia",
    "Rain Of Tears": "Rain of Tears",
    '"Name Sticker" Goblin': "_____ Goblin",
    "Jotun Grunt": "Jötun Grunt",
    "Sol'kanar the Tainted": "Sol'Kanar the Tainted",
    "Furnace Of Rath": "Furnace of Rath",
    "Lim-Dûl's Vault": "Lim-Dûl's Vault",
}

ALCHEMY_PREFIX = "A-"


class ScryfallNormalizer:
    _instance: Optional["ScryfallNormalizer"] = None
    _mappings: Dict[str, str] = {}
    _canonical_names: set[str] = set()
    _warned_cards: set[str] = set()

    def __init__(self, cache_dir: str = ".cache"):
        self.cache_dir = cache_dir
        self.cache_file = os.path.join(cache_dir, "scryfall_names.json")
        self._mappings = {}
        self._canonical_names = set()
        self._warned_cards = set()
        self.load_or_update()

    @classmethod
    def get_instance(cls, cache_dir: str = ".cache") -> "ScryfallNormalizer":
        if cls._instance is None:
            cls._instance = cls(cache_dir)
        return cls._instance

    def is_cache_valid(self) -> bool:
        if not os.path.exists(self.cache_file):
            return False
        mtime = os.path.getmtime(self.cache_file)
        age_seconds = time.time() - mtime
        return age_seconds < (SCRYFALL_CACHE_TTL_HOURS * 3600)

    def load_cache(self) -> bool:
        try:
            with open(self.cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and "mappings" in data:
                self._mappings = data.get("mappings", {})
                self._canonical_names = set(data.get("canonical", []))
            else:
                self._mappings = data
                self._canonical_names = set()
            logger.info(
                "Loaded %d card mappings and %d canonical names from cache (%s)",
                len(self._mappings),
                len(self._canonical_names),
                self.cache_file,
            )
            return True
        except Exception as e:
            logger.warning(
                "Failed to load Scryfall cache from %s: %s", self.cache_file, e
            )
            return False

    def load_or_update(self):
        if self.is_cache_valid():
            if self.load_cache():
                return

        logger.info("Fetching fresh Scryfall bulk data (oracle_cards)...")
        try:
            self._update_from_scryfall()
        except Exception as e:
            logger.error("Error updating Scryfall bulk data: %s", e)
            # Fall back to existing stale cache if available
            if os.path.exists(self.cache_file):
                self.load_cache()
            else:
                self._mappings = dict(STATIC_CORRECTIONS)

    def _update_from_scryfall(self):
        headers = {"User-Agent": get_user_agent()}
        resp = requests.get(SCRYFALL_BULK_URL, headers=headers, timeout=30)
        resp.raise_for_status()

        bulk_data = resp.json().get("data", [])
        oracle_item = next(
            (item for item in bulk_data if item.get("type") == "oracle_cards"), None
        )

        if not oracle_item:
            raise ValueError("No oracle_cards entry found in Scryfall bulk data")

        # Try jsonl_download_uri or download_uri
        download_url = oracle_item.get("jsonl_download_uri") or oracle_item.get(
            "download_uri"
        )
        if not download_url:
            raise ValueError("No download URI found for oracle_cards")

        is_gzipped = download_url.endswith(".gz")
        logger.info("Streaming bulk data from %s...", download_url)

        req = requests.get(download_url, stream=True, headers=headers, timeout=60)
        req.raise_for_status()

        mappings: Dict[str, str] = dict(STATIC_CORRECTIONS)
        canonical_names: set[str] = set(STATIC_CORRECTIONS.values())

        stream = gzip.GzipFile(fileobj=req.raw) if is_gzipped else req.raw
        count = 0

        for line in stream:
            if not line.strip():
                continue
            card = json.loads(line.decode("utf-8"))
            card_name = card.get("name", "")
            layout = card.get("layout", "")
            faces = card.get("card_faces", [])

            if card_name:
                canonical_names.add(card_name)

            # Split cards
            if layout == "split" and len(faces) == 2:
                front = faces[0].get("name", "")
                back = faces[1].get("name", "")
                target = f"{front} // {back}"
                mappings[front] = target
                mappings[f"{front}/{back}"] = target
                mappings[f"{front} / {back}"] = target
                mappings[f"{front}//{back}"] = target
                mappings[f"{front} /// {back}"] = target
                canonical_names.add(target)
                if front:
                    canonical_names.add(front)

            # Transform / DFC / Adventure / Flip cards:
            # On MTGO, these are almost universally cataloged by front face name only
            elif (
                layout in ("transform", "modal_dfc", "adventure", "flip")
                and len(faces) >= 2
            ):
                front = faces[0].get("name", "")
                if front:
                    canonical_names.add(front)
                # If someone has the full "Front // Back", map it down to Front face if that's what MTGO uses
                # or ensure variations map to canonical name
                mappings[card_name] = front
                mappings[f"{faces[0].get('name')}/{faces[1].get('name')}"] = front
                mappings[f"{faces[0].get('name')} // {faces[1].get('name')}"] = front

            # Flavor names (e.g. Universes Beyond / Godzilla promos)
            flavor_name = card.get("flavor_name")
            if flavor_name:
                mappings[flavor_name] = card_name

            count += 1

        self._mappings = mappings
        self._canonical_names = canonical_names
        os.makedirs(self.cache_dir, exist_ok=True)
        payload = {
            "mappings": mappings,
            "canonical": sorted(canonical_names),
        }
        with open(self.cache_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)

        logger.info(
            "Processed %d Scryfall cards, saved %d mappings and %d canonical names to %s",
            count,
            len(mappings),
            len(canonical_names),
            self.cache_file,
        )

    def normalize(self, card_name: str) -> str:
        name = card_name.strip()
        if name.startswith(ALCHEMY_PREFIX):
            name = name[len(ALCHEMY_PREFIX) :]

        if name in self._mappings:
            return self._mappings[name]

        if (
            self._canonical_names
            and name not in self._canonical_names
            and name not in self._warned_cards
        ):
            self._warned_cards.add(name)
            logger.warning(
                "Card name '%s' not recognized in Scryfall Oracle database", name
            )

        return name
