"""Data models matching MTG_decklistcache format with PlayerCount extension."""

from datetime import date
from datetime import datetime
from typing import List
from typing import Optional


class Tournament:
    def __init__(
        self,
        date: Optional[date] = None,
        name: Optional[str] = None,
        uri: Optional[str] = None,
        formats: Optional[str] = None,
        json_file: Optional[str] = None,
        player_count: Optional[int] = None,
        failure_reason: Optional[str] = None,
    ):
        self.date = date
        self.name = name
        self.uri = uri
        self.formats = formats
        self.json_file = json_file
        self.player_count = player_count
        self.failure_reason = failure_reason

    def __repr__(self):
        reason = f", reason='{self.failure_reason}'" if self.failure_reason else ""
        return f"Tournament({self.name}, {self.date}, players={self.player_count}{reason})"

    def __eq__(self, other):
        if not isinstance(other, Tournament):
            return False
        return (
            self.date == other.date
            and self.name == other.name
            and self.uri == other.uri
            and self.formats == other.formats
            and self.player_count == other.player_count
        )

    def to_dict(self):
        data = {
            "Date": self.date.isoformat() if self.date else None,
            "Name": self.name,
            "Uri": self.uri,
            "Formats": self.formats,
        }
        if self.player_count is not None:
            data["PlayerCount"] = self.player_count
        return data

    def to_failed_dict(self):
        data = {
            "date": self.date.isoformat() if self.date else None,
            "name": self.name,
            "uri": self.uri,
            "formats": self.formats,
            "json_file": self.json_file,
        }
        if self.failure_reason:
            data["failure_reason"] = self.failure_reason
        return data

    @classmethod
    def from_failed_dict(cls, data: dict) -> "Tournament":
        parsed_date = None
        if data.get("date"):
            try:
                parsed_date = date.fromisoformat(data["date"])
            except ValueError:
                parsed_date = None
        return cls(
            date=parsed_date,
            name=data.get("name"),
            uri=data.get("uri"),
            formats=data.get("formats"),
            json_file=data.get("json_file"),
            failure_reason=data.get("failure_reason"),
        )


class DeckItem:
    def __init__(self, count: int, card_name: str):
        self.count = count
        self.card_name = card_name

    def __repr__(self):
        return f"DeckItem({self.count}x {self.card_name})"

    def __eq__(self, other):
        if isinstance(other, DeckItem):
            return self.count == other.count and self.card_name == other.card_name
        return False

    def to_dict(self):
        return {
            "Count": self.count,
            "CardName": self.card_name,
        }


class Deck:
    def __init__(
        self,
        date: Optional[datetime],
        player: str,
        result: str,
        anchor_uri: str,
        mainboard: List[DeckItem],
        sideboard: List[DeckItem],
    ):
        self.date = date
        self.player = player
        self.result = result
        self.anchor_uri = anchor_uri
        self.mainboard = mainboard
        self.sideboard = sideboard

    def __repr__(self):
        return f"Deck(player='{self.player}', result='{self.result}')"

    def __eq__(self, other):
        if not isinstance(other, Deck):
            return False
        return (
            self.date == other.date
            and self.player == other.player
            and self.result == other.result
            and self.anchor_uri == other.anchor_uri
            and self.mainboard == other.mainboard
            and self.sideboard == other.sideboard
        )

    def to_dict(self):
        return {
            "Date": self.date.isoformat() if self.date else None,
            "Player": self.player,
            "Result": self.result,
            "AnchorUri": self.anchor_uri,
            "Mainboard": [item.to_dict() for item in self.mainboard],
            "Sideboard": [item.to_dict() for item in self.sideboard],
        }


class RoundItem:
    def __init__(self, player1: str, player2: str, result: str):
        self.player1 = player1
        self.player2 = player2
        self.result = result

    def __repr__(self):
        return f"RoundItem({self.player1} vs {self.player2}: {self.result})"

    def __eq__(self, other):
        if not isinstance(other, RoundItem):
            return False
        return (
            self.player1 == other.player1
            and self.player2 == other.player2
            and self.result == other.result
        )

    def to_dict(self):
        return {
            "Player1": self.player1,
            "Player2": self.player2,
            "Result": self.result,
        }


class Round:
    def __init__(self, round_name: str, matches: List[RoundItem]):
        self.round_name = round_name
        self.matches = matches

    def __repr__(self):
        return f"Round({self.round_name}, {len(self.matches)} matches)"

    def __eq__(self, other):
        if not isinstance(other, Round):
            return False
        return self.round_name == other.round_name and self.matches == other.matches

    def to_dict(self):
        return {
            "RoundName": self.round_name,
            "Matches": [match.to_dict() for match in self.matches],
        }


class Standing:
    def __init__(
        self,
        rank: int,
        player: str,
        points: int,
        wins: int,
        losses: int,
        draws: int = 0,
        omwp: Optional[float] = None,
        gwp: Optional[float] = None,
        ogwp: Optional[float] = None,
    ):
        self.rank = rank
        self.player = player
        self.points = points
        self.wins = wins
        self.losses = losses
        self.draws = draws
        self.omwp = omwp
        self.gwp = gwp
        self.ogwp = ogwp

    def __repr__(self):
        return (
            f"Standing(rank={self.rank}, player='{self.player}', points={self.points})"
        )

    def __eq__(self, other):
        if not isinstance(other, Standing):
            return False
        return (
            self.rank == other.rank
            and self.player == other.player
            and self.points == other.points
            and self.wins == other.wins
            and self.losses == other.losses
            and self.draws == other.draws
            and (
                self.omwp == other.omwp
                or (
                    self.omwp is not None
                    and other.omwp is not None
                    and abs(self.omwp - other.omwp) < 1e-4
                )
            )
            and (
                self.gwp == other.gwp
                or (
                    self.gwp is not None
                    and other.gwp is not None
                    and abs(self.gwp - other.gwp) < 1e-4
                )
            )
            and (
                self.ogwp == other.ogwp
                or (
                    self.ogwp is not None
                    and other.ogwp is not None
                    and abs(self.ogwp - other.ogwp) < 1e-4
                )
            )
        )

    def to_dict(self):
        return {
            "Rank": self.rank,
            "Player": self.player,
            "Points": self.points,
            "Wins": self.wins,
            "Losses": self.losses,
            "Draws": self.draws,
            "OMWP": self.omwp,
            "GWP": self.gwp,
            "OGWP": self.ogwp,
        }


class CacheItem:
    def __init__(
        self,
        tournament: Tournament,
        decks: List[Deck],
        rounds: Optional[List[Round]] = None,
        standings: Optional[List[Standing]] = None,
    ):
        self.tournament = tournament
        self.decks = decks
        self.rounds = rounds or []
        self.standings = standings or []

    def __repr__(self):
        return f"CacheItem({self.tournament.name}: {len(self.decks)} decks)"

    def to_dict(self):
        return {
            "Tournament": self.tournament.to_dict(),
            "Decks": [deck.to_dict() for deck in self.decks],
            "Rounds": [round_.to_dict() for round_ in self.rounds],
            "Standings": [standing.to_dict() for standing in self.standings],
        }
