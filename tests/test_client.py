import importlib
from datetime import date

import src.config
from src.client import MTGOClient
from src.models import Tournament


def test_parse_challenge_with_player_count():
    client = MTGOClient()
    tournament = Tournament(
        date=date(2026, 9, 10),
        name="Modern Challenge 64",
        uri="https://www.mtgo.com/decklist/modern-challenge-64-2026-09-1012854060",
        formats="Modern",
        json_file="modern-challenge-64-2026-09-1012854060.json",
    )
    raw_data = {
        "event_id": 12854060,
        "description": "Modern Challenge 64",
        "starttime": "2026-09-10 13:00:00.0",
        "format": "CMODERN",
        "type": "TOURNAMENT",
        "player_count": {
            "tournamentid": "12854060",
            "players": "93",
            "queued_players": "93",
        },
        "decklists": [
            {
                "player": "PlayerA",
                "loginid": "111",
                "main_deck": [
                    {"card_attributes": {"card_name": "Lightning Bolt"}, "qty": 4}
                ],
                "sideboard_deck": [
                    {"card_attributes": {"card_name": "Pyroblast"}, "qty": 2}
                ],
            }
        ],
        "standings": [
            {
                "login_name": "PlayerA",
                "loginid": "111",
                "score": "18",
                "rank": "1",
                "gamewinpercentage": "0.75",
                "opponentgamewinpercentage": "0.60",
                "opponentmatchwinpercentage": "0.65",
            }
        ],
        "brackets": [],
    }

    cache_item = client.parse_event(tournament, raw_data)
    assert cache_item is not None
    assert cache_item.tournament.player_count == 93

    data_dict = cache_item.to_dict()
    assert data_dict["Tournament"]["PlayerCount"] == 93
    assert data_dict["Tournament"]["Name"] == "Modern Challenge 64"
    assert len(data_dict["Decks"]) == 1
    assert data_dict["Decks"][0]["Player"] == "PlayerA"
    assert data_dict["Decks"][0]["Result"] == "1st Place"


def test_parse_league_without_player_count():
    client = MTGOClient()
    tournament = Tournament(
        date=date(2026, 9, 11),
        name="Legacy League",
        uri="https://www.mtgo.com/decklist/legacy-league-2026-09-1110967",
        formats="Legacy",
        json_file="legacy-league-2026-09-1110967.json",
    )
    raw_data = {
        "playeventid": 10967,
        "name": "Legacy League",
        "publish_date": "2026-09-11",
        "player_count": None,
        "decklists": [
            {
                "player": "PlayerB",
                "loginid": "222",
                "wins": {"wins": "5"},
                "main_deck": [
                    {"card_attributes": {"card_name": "Brainstorm"}, "qty": 4}
                ],
                "sideboard_deck": [],
            }
        ],
    }

    cache_item = client.parse_event(tournament, raw_data)
    assert cache_item is not None
    assert cache_item.tournament.player_count is None

    data_dict = cache_item.to_dict()
    assert "PlayerCount" not in data_dict["Tournament"]
    assert len(data_dict["Decks"]) == 1
    assert data_dict["Decks"][0]["Result"] == "5-0"
    assert data_dict["Rounds"] == []
    assert data_dict["Standings"] == []


def test_user_agent_from_environ(monkeypatch):
    monkeypatch.setenv("USER_AGENT", "CustomBot/2.0")
    importlib.reload(src.config)

    c = MTGOClient()
    assert c.session.headers["User-Agent"] == "CustomBot/2.0"

    # Reset
    monkeypatch.delenv("USER_AGENT", raising=False)
    importlib.reload(src.config)
