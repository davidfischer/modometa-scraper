from datetime import date
from datetime import datetime
from datetime import timezone

from src.models import Deck
from src.models import DeckItem
from src.models import Standing
from src.models import Tournament


def test_tournament_serialization_with_player_count():
    t = Tournament(
        date=date(2026, 9, 10),
        name="Modern Challenge 64",
        uri="https://www.mtgo.com/decklist/modern-challenge-64-2026-09-1012854060",
        formats="Modern",
        player_count=93,
    )
    d = t.to_dict()
    assert d["Date"] == "2026-09-10"
    assert d["Name"] == "Modern Challenge 64"
    assert d["Formats"] == "Modern"
    assert d["PlayerCount"] == 93


def test_tournament_serialization_without_player_count():
    t = Tournament(
        date=date(2026, 9, 11),
        name="Legacy League",
        uri="https://www.mtgo.com/decklist/legacy-league-2026-09-1110967",
        formats="Legacy",
        player_count=None,
    )
    d = t.to_dict()
    assert d["Date"] == "2026-09-11"
    assert "PlayerCount" not in d


def test_deck_serialization():
    dt = datetime(2026, 9, 10, 13, 0, 0, tzinfo=timezone.utc)
    deck = Deck(
        date=dt,
        player="Alice",
        result="1st Place",
        anchor_uri="https://www.mtgo.com/decklist/test#deck_Alice",
        mainboard=[DeckItem(count=4, card_name="Lightning Bolt")],
        sideboard=[DeckItem(count=2, card_name="Pyroblast")],
    )
    d = deck.to_dict()
    assert d["Date"] == "2026-09-10T13:00:00+00:00"
    assert d["Player"] == "Alice"
    assert d["Result"] == "1st Place"
    assert len(d["Mainboard"]) == 1
    assert d["Mainboard"][0] == {"Count": 4, "CardName": "Lightning Bolt"}


def test_standing_serialization():
    s = Standing(
        rank=1,
        player="Alice",
        points=18,
        wins=6,
        losses=0,
        omwp=0.6543,
        gwp=0.75,
        ogwp=0.60,
    )
    d = s.to_dict()
    assert d["Rank"] == 1
    assert d["Player"] == "Alice"
    assert d["OMWP"] == 0.6543


def test_tournament_failed_dict_roundtrip():
    t = Tournament(
        date=date(2026, 9, 10),
        name="Modern Challenge 64",
        uri="https://www.mtgo.com/decklist/modern-challenge-64-2026-09-1012854060",
        formats="Modern",
        json_file="modern-challenge-64-2026-09-1012854060.json",
        failure_reason="HTTP 404",
    )
    failed_dict = t.to_failed_dict()
    assert failed_dict == {
        "date": "2026-09-10",
        "name": "Modern Challenge 64",
        "uri": "https://www.mtgo.com/decklist/modern-challenge-64-2026-09-1012854060",
        "formats": "Modern",
        "json_file": "modern-challenge-64-2026-09-1012854060.json",
        "failure_reason": "HTTP 404",
    }
    reconstituted = Tournament.from_failed_dict(failed_dict)
    assert reconstituted.date == t.date
    assert reconstituted.name == t.name
    assert reconstituted.uri == t.uri
    assert reconstituted.formats == t.formats
    assert reconstituted.json_file == t.json_file
    assert reconstituted.failure_reason == "HTTP 404"
    assert repr(reconstituted) == "Tournament(Modern Challenge 64, 2026-09-10, players=None, reason='HTTP 404')"
