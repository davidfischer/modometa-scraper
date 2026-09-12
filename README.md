# modometa-scraper

A lightweight, dedicated [MTGO](https://www.mtgo.com) (Magic: The Gathering Online) tournament scraper for maintaining a cache of MTGO league and challenge event data and decklists.

This is the decklist cache used by [MODOMeta](https://modometa.com/), an MTGO metagame analyzer.

If you're looking to explore MTGO tournament data, an event metadata and decklist cache built using this scraper is maintained at [`modometa-mtgo-data`](https://github.com/davidfischer/modometa-mtgo-data). Also, the database for MODOMeta is public. If you know SQL, you can download and explore the database yourself at https://data.modometa.com/modometa.db

## Key Features

- **Intra-Day & Incremental Updates:** Cleanly detects new 5-0 decklists in ongoing MTGO leagues throughout the day. This is designed to run multiple times a day and update the day's events into the event/decklist cache.
- **Fast Scryfall Normalization:** Uses Scryfall's [bulk data](https://scryfall.com/docs/api/bulk-data) (`oracle_cards`) cached locally (24h TTL) to verify all cards are normalized. A warning is emitted on an unrecognized card.
- **Polite scraping:** Scrapes mtgo.com serially rather than blasting Daybreak's servers triggering rate limits and has a short 0.1s delay. The scraper recovers from short temporary network blips and will restart/resume automatically after waiting (30s+) for the network to recover. When running a longer sync, it will retry any failed events at the end as well and save any persisting failures to a JSON file for inspection or targeted retry.

## Installation

Requires Python 3.14+.

```bash
git clone https://github.com/davidfischer/modometa-scraper.git
cd modometa-scraper

# Using uv (recommended)
uv sync
```

## CLI Usage

```bash
# Auto-resume from latest cached date with a 2-day lookback window:
uv run modometa-scraper --cache-dir /path/to/cache/Tournaments/MTGO --auto-resume --lookback-days 2

# Sync a specific date range (~1hr / month of events):
uv run modometa-scraper --cache-dir ./.cache/MTGO --start-date 2026-09-01 --end-date 2026-09-11

# Force re-download of tournaments in the window:
uv run modometa-scraper --cache-dir ./.cache/MTGO --start-date 2026-09-10 --force

# Exclude league events:
uv run modometa-scraper --cache-dir ./.cache/MTGO --auto-resume --skip-leagues

# Retry failed tournaments from a previous run (defaults to failed_events.json):
uv run modometa-scraper --retry-failed

# Sync a specific tournament directly by URL:
uv run modometa-scraper --url https://www.mtgo.com/decklist/modern-challenge-64-2026-09-1012854060
```

See `uv run modometa-scraper --help` for full details.

## JSON Format

```json
{
  "Tournament": {
    "Date": "2026-09-10",
    "Name": "Modern Challenge 64",
    "Uri": "https://www.mtgo.com/decklist/modern-challenge-64-2026-09-1012854060",
    "Formats": "Modern",
    "PlayerCount": 93
  },
  "Decks": [
    {
      "Date": "2026-09-10T13:00:00+00:00",
      "Player": "Alice",
      "Result": "1st Place",
      "AnchorUri": "https://www.mtgo.com/decklist/modern-challenge-64-2026-09-1012854060#deck_Alice",
      "Mainboard": [
        { "Count": 4, "CardName": "Lightning Bolt" }
      ],
      "Sideboard": [
        { "Count": 2, "CardName": "Pyroblast" }
      ]
    }
  ],
  "Rounds": [
    {
      "RoundName": "Finals",
      "Matches": [
        { "Player1": "Alice", "Player2": "Bob", "Result": "2-1-0" }
      ]
    }
  ],
  "Standings": [
    {
      "Rank": 1,
      "Player": "Alice",
      "Points": 18,
      "Wins": 6,
      "Losses": 0,
      "Draws": 0,
      "OMWP": 0.67,
      "GWP": 0.75,
      "OGWP": 0.61
    }
  ]
}
```

## Tips

* Failures are very common pulling data from MTGO.com.
  Tournaments can also get canceled if not enough people signup and it's hard to differentiate a fail-to-fire from an error.
  Use `uv run modometa-scraper --retry-failed` to retry errors (again since it retries already).
* The scraper looks for JavaScript on the tournament page (`MTGO.decklists.data`).
  Sometimes the page responds but without this data due to an error.
  These need to be retried.
* The scraper takes ~1 hour per month of data.
  It is helpful to run in small increments of no more than a few months at a time.
* The short 0.1s delay between requests to MTGO.com is important.
  Setting it to 0 (`--delay=0`) is probably a mistake.
  Pulling a tournament from MTGO.com can take 3-10 seconds and a 0.1s delay is only 1-3% overhead.
  MTGO.com occasionally has errors for a few seconds where the decklist page redirects
  (which responds instantly from their CDN) and without the 0.1s delay the scraper will fail for tens of tournaments in just a few seconds.

## Running Tests & Linting

```bash
uv run pytest
uv run ruff check
```

## Prior art

This was heavily influenced by [`MTG_decklistcache`](https://github.com/fbettega/MTG_decklistcache) but only for MTGO and with a few optimizations and features. The JSON format from this scraper is compatible with a few additions.
