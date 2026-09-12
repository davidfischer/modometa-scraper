import os


MTGO_ROOT_URL = "https://www.mtgo.com"
MTGO_LIST_URL = "https://www.mtgo.com/decklists/{year}/{month:02d}"

VALID_FORMATS = [
    "Standard",
    "Modern",
    "Pioneer",
    "Legacy",
    "Vintage",
    "Pauper",
    "Commander",
]

SCRYFALL_BULK_URL = "https://api.scryfall.com/bulk-data"
SCRYFALL_CACHE_TTL_HOURS = 24

DEFAULT_LOOKBACK_DAYS = 2
DEFAULT_CACHE_DIR = "Tournaments/MTGO"

DEFAULT_USER_AGENT = (
    "modometa-scraper/1.0 (+https://github.com/davidfischer/modometa-scraper)"
)


def get_user_agent() -> str:
    """Return USER_AGENT from environment or fallback to default."""
    return os.environ.get("USER_AGENT", DEFAULT_USER_AGENT)


USER_AGENT = get_user_agent()
