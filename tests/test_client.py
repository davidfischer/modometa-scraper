import importlib
from datetime import date
from unittest.mock import MagicMock

import src.config
from src.client import MTGOClient
from src.client import tournament_from_url
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


def test_tournament_from_url():
    url = (
        "https://www.mtgo.com/decklist/modern-challenge-64-2026-09-1012854060?query=1/"
    )
    t = tournament_from_url(url)
    assert t.name == "Modern Challenge 64"
    assert t.date == date(2026, 9, 10)
    assert t.formats == "Modern"
    assert t.json_file == "modern-challenge-64-2026-09-1012854060.json"
    assert t.uri == url

    duel_url = "https://www.mtgo.com/decklist/duel-commander-league-2026-09-0210931"
    t_duel = tournament_from_url(duel_url)
    assert t_duel.formats == "Commander"

    premodern_url = (
        "https://www.mtgo.com/decklist/premodern-challenge-32-2026-09-1012854063"
    )
    t_premodern = tournament_from_url(premodern_url)
    assert t_premodern.formats == "Premodern"

    contraption_url = "https://www.mtgo.com/decklist/contraption-league-2026-06-0810735"
    t_contraption = tournament_from_url(contraption_url)
    assert t_contraption.name == "Contraption League"
    assert t_contraption.formats is None

    premodern_contraption_url = "https://www.mtgo.com/decklist/premodern-challenge-32---contraption-2025-12-3012828126"
    t_premodern_contraption = tournament_from_url(premodern_contraption_url)
    assert t_premodern_contraption.name == "Premodern Challenge 32   Contraption"
    assert t_premodern_contraption.formats == "Premodern"


def test_fetch_event_data_404_no_retry():
    client = MTGOClient(max_retries=3)
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    client.session.get = MagicMock(return_value=mock_resp)

    res = client.fetch_event_data("https://www.mtgo.com/decklist/missing-event")
    assert res is None
    assert client.session.get.call_count == 1  # Did not retry on 404!
    assert client.last_error == "HTTP 404"


def test_parse_event_no_decks_sets_last_error():
    client = MTGOClient()
    t = Tournament(name="Test", json_file="test.json")
    res = client.parse_event(t, {"decklists": []})
    assert res is None
    assert client.last_error == "Tournament has no decks (event likely did not fire)"


def test_fetch_calendar_skips_configured_skip_formats():
    client = MTGOClient()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = """
    <html>
      <body>
        <li class="decklists-item">
          <a href="/decklist/modern-challenge-64-2026-09-1012854060">
            <div><h3>Modern Challenge 64</h3></div>
            <time datetime="2026-09-10T13:00:00.000Z"></time>
          </a>
        </li>
        <li class="decklists-item">
          <a href="/decklist/limited-super-qualifier-2026-09-1012645816">
            <div><h3>Limited Super Qualifier</h3></div>
            <time datetime="2026-09-10T14:05:00.000Z"></time>
          </a>
        </li>
        <li class="decklists-item">
          <a href="/decklist/contraption-league-2026-06-0810735">
            <div><h3>Contraption League</h3></div>
            <time datetime="2026-06-08T10:00:00.000Z"></time>
          </a>
        </li>
        <li class="decklists-item">
          <a href="/decklist/premodern-challenge-32-2026-09-1012854063">
            <div><h3>Premodern Challenge 32</h3></div>
            <time datetime="2026-09-10T17:00:00.000Z"></time>
          </a>
        </li>
      </body>
    </html>
    """
    client.session.get = MagicMock(return_value=mock_resp)

    tournaments = client.fetch_calendar(date(2026, 9, 1), date(2026, 9, 30))
    assert len(tournaments) == 2
    assert tournaments[0].name == "Modern Challenge 64"
    assert tournaments[0].formats == "Modern"
    assert tournaments[1].name == "Premodern Challenge 32"
    assert tournaments[1].formats == "Premodern"
