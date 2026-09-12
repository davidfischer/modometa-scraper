import json
from datetime import date
from unittest.mock import MagicMock

from src.models import Tournament
from src.scraper import MTGOSyncEngine
from src.scraper import atomic_write_json
from src.scraper import find_latest_cached_date
from src.scraper import load_failed_events
from src.scraper import save_failed_events


def test_find_latest_cached_date(tmp_path):
    # Setup dummy directory structure
    d1 = tmp_path / "2026" / "08" / "30"
    d2 = tmp_path / "2026" / "09" / "05"
    d1.mkdir(parents=True)
    d2.mkdir(parents=True)

    latest = find_latest_cached_date(str(tmp_path))
    assert latest == date(2026, 9, 5)


def test_resolve_date_range_auto_resume(tmp_path):
    d = tmp_path / "2026" / "09" / "08"
    d.mkdir(parents=True)

    engine = MTGOSyncEngine(
        cache_root=str(tmp_path), scryfall_cache_dir=str(tmp_path / ".cache")
    )
    start, end = engine.resolve_date_range(auto_resume=True, lookback_days=2)

    assert start == date(2026, 9, 6)  # 09-08 minus 2 days
    assert end >= date(2026, 9, 8)


def test_atomic_write_json(tmp_path):
    file_path = tmp_path / "test.json"
    data = {"hello": "world"}
    atomic_write_json(str(file_path), data)

    assert file_path.exists()
    with open(file_path, "r", encoding="utf-8") as f:
        loaded = json.load(f)
    assert loaded == data


def test_deferred_retry_succeeds(tmp_path):
    mock_client = MagicMock()
    mock_tournament = Tournament(
        date=date(2026, 9, 1),
        name="Legacy League",
        uri="https://www.mtgo.com/test",
        formats="Legacy",
        json_file="legacy-league.json",
    )
    mock_client.fetch_calendar.return_value = [mock_tournament]

    # Fail on first call, succeed on deferred retry
    mock_client.fetch_event_data.side_effect = [
        None,
        {"decklists": [{"player": "P1"}]},
    ]
    mock_item = MagicMock()
    mock_item.to_dict.return_value = {
        "Tournament": {"Name": "Legacy League"},
        "Decks": [],
    }
    mock_client.parse_event.return_value = mock_item

    mock_normalizer = MagicMock()
    engine = MTGOSyncEngine(
        cache_root=str(tmp_path),
        client=mock_client,
        normalizer=mock_normalizer,
    )

    stats = engine.sync(
        start_date=date(2026, 9, 1), end_date=date(2026, 9, 1), retry_delay=0
    )

    assert stats["created"] == 1
    assert stats["failed"] == 0
    assert mock_client.fetch_event_data.call_count == 2
    assert (tmp_path / "2026" / "09" / "01" / "legacy-league.json").exists()


def test_deferred_retry_fails_both(tmp_path):
    mock_client = MagicMock()
    mock_tournament = Tournament(
        date=date(2026, 9, 1),
        name="Legacy League",
        uri="https://www.mtgo.com/test",
        formats="Legacy",
        json_file="legacy-league.json",
    )
    mock_client.fetch_calendar.return_value = [mock_tournament]
    mock_client.fetch_event_data.return_value = None

    mock_normalizer = MagicMock()
    engine = MTGOSyncEngine(
        cache_root=str(tmp_path),
        client=mock_client,
        normalizer=mock_normalizer,
    )

    stats = engine.sync(
        start_date=date(2026, 9, 1), end_date=date(2026, 9, 1), retry_delay=0
    )

    assert stats["created"] == 0
    assert stats["failed"] == 1
    assert len(stats["failed_events"]) == 1
    assert stats["failed_events"][0] == mock_tournament
    assert mock_client.fetch_event_data.call_count == 2


def test_save_and_load_failed_events(tmp_path):
    t1 = Tournament(
        date=date(2026, 9, 1),
        name="Modern Challenge",
        uri="https://www.mtgo.com/decklist/modern-challenge-2026-09-01123",
        formats="Modern",
        json_file="modern-challenge-2026-09-01123.json",
        failure_reason="HTTP 404",
    )
    json_file = tmp_path / "failed.json"
    save_failed_events([t1], str(json_file))

    loaded = load_failed_events(str(json_file))
    assert len(loaded) == 1
    assert loaded[0].name == "Modern Challenge"
    assert loaded[0].failure_reason == "HTTP 404"

    # Test loading text file of URLs
    txt_file = tmp_path / "failed.txt"
    txt_file.write_text(
        "# Comment\nhttps://www.mtgo.com/decklist/legacy-challenge-2026-09-02456\n"
    )
    loaded_txt = load_failed_events(str(txt_file))
    assert len(loaded_txt) == 1
    assert loaded_txt[0].date == date(2026, 9, 2)
    assert loaded_txt[0].name == "Legacy Challenge"


def test_sync_specified_tournaments(tmp_path):
    mock_client = MagicMock()
    mock_tournament = Tournament(
        date=date(2026, 9, 1),
        name="Targeted Challenge",
        uri="https://www.mtgo.com/decklist/targeted-challenge-2026-09-01123",
        formats="Modern",
        json_file="targeted-challenge-2026-09-01123.json",
    )
    mock_client.fetch_event_data.return_value = {"decklists": [{"player": "P1"}]}
    mock_item = MagicMock()
    mock_item.to_dict.return_value = {"Tournament": {"Name": "Targeted Challenge"}}
    mock_client.parse_event.return_value = mock_item

    mock_normalizer = MagicMock()
    engine = MTGOSyncEngine(
        cache_root=str(tmp_path),
        client=mock_client,
        normalizer=mock_normalizer,
    )

    stats = engine.sync(tournaments=[mock_tournament], retry_delay=0)

    assert stats["total_found"] == 1
    assert stats["created"] == 1
    assert stats["failed"] == 0
    # fetch_calendar should NOT have been called
    assert mock_client.fetch_calendar.call_count == 0


def test_sync_skips_limited_event(tmp_path):
    mock_client = MagicMock()
    limited_tournament = Tournament(
        date=date(2026, 9, 10),
        name="Limited Super Qualifier",
        uri="https://www.mtgo.com/decklist/limited-super-qualifier-2024-06-0912645816",
        formats=None,
        json_file="limited-super-qualifier-2024-06-0912645816.json",
    )
    engine = MTGOSyncEngine(cache_root=str(tmp_path), client=mock_client)
    stats = engine.sync(tournaments=[limited_tournament])

    assert stats["skipped"] == 1
    assert stats["created"] == 0
    assert stats["failed"] == 0
    assert mock_client.fetch_event_data.call_count == 0


def test_cli_parse_retry_args(monkeypatch):
    from src.cli import parse_args

    monkeypatch.setattr("sys.argv", ["main.py", "--retry-failed"])
    args = parse_args()
    assert args.retry_failed == "failed_events.json"

    monkeypatch.setattr("sys.argv", ["main.py", "--retry-failed", "my_failed.json"])
    args = parse_args()
    assert args.retry_failed == "my_failed.json"

    monkeypatch.setattr(
        "sys.argv",
        [
            "main.py",
            "--url",
            "https://www.mtgo.com/decklist/event-1",
            "--url",
            "https://www.mtgo.com/decklist/event-2",
            "--delay",
            "0.25",
        ],
    )
    args = parse_args()
    assert args.url == [
        "https://www.mtgo.com/decklist/event-1",
        "https://www.mtgo.com/decklist/event-2",
    ]
    assert args.delay == 0.25

    monkeypatch.setattr("sys.argv", ["main.py"])
    args_default = parse_args()
    assert args_default.delay == 0.1
