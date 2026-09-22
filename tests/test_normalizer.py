from datetime import datetime
from datetime import timezone

from src.models import Deck
from src.models import DeckItem
from src.models import Round
from src.models import RoundItem
from src.models import Standing
from src.normalizer import DeckNormalizer
from src.normalizer import OrderNormalizer


def test_deck_normalizer_combines_and_sorts():
    deck = Deck(
        date=datetime.now(timezone.utc),
        player="Tester",
        result="",
        anchor_uri="",
        mainboard=[
            DeckItem(count=2, card_name="Lightning Bolt"),
            DeckItem(count=1, card_name="Brainstorm"),
            DeckItem(count=2, card_name="Lightning Bolt"),
        ],
        sideboard=[
            DeckItem(count=1, card_name="Pyroblast"),
            DeckItem(count=1, card_name="Hydroblast"),
        ],
    )
    normalized = DeckNormalizer.normalize(deck)

    # Mainboard should be sorted alphabetically and combined
    assert len(normalized.mainboard) == 2
    assert normalized.mainboard[0].card_name == "Brainstorm"
    assert normalized.mainboard[0].count == 1
    assert normalized.mainboard[1].card_name == "Lightning Bolt"
    assert normalized.mainboard[1].count == 4

    # Sideboard should be sorted alphabetically
    assert normalized.sideboard[0].card_name == "Hydroblast"
    assert normalized.sideboard[1].card_name == "Pyroblast"


def test_order_normalizer_playoff_bracket():
    decks = [
        Deck(datetime.now(timezone.utc), "Alice", "", "", [], []),
        Deck(datetime.now(timezone.utc), "Bob", "", "", [], []),
        Deck(datetime.now(timezone.utc), "Charlie", "", "", [], []),
        Deck(datetime.now(timezone.utc), "David", "", "", [], []),
    ]
    standings = [
        Standing(rank=1, player="Charlie", points=12, wins=4, losses=0),
        Standing(rank=2, player="Alice", points=9, wins=3, losses=1),
        Standing(rank=3, player="Bob", points=9, wins=3, losses=1),
        Standing(rank=4, player="David", points=9, wins=3, losses=1),
    ]
    # Playoff rounds: Semifinals and Finals
    # In Swiss, Charlie was #1. But Alice beats Charlie in Semis, Bob beats David.
    # In Finals, Alice beats Bob.
    rounds = [
        Round(
            round_name="Semifinals",
            matches=[
                RoundItem(player1="Alice", player2="Charlie", result="2-1-0"),
                RoundItem(player1="Bob", player2="David", result="2-0-0"),
            ],
        ),
        Round(
            round_name="Finals",
            matches=[
                RoundItem(player1="Alice", player2="Bob", result="2-1-0"),
            ],
        ),
    ]

    reordered = OrderNormalizer.reorder_decks(
        decks, standings, rounds, update_result=True
    )
    assert reordered[0].player == "Alice"
    assert reordered[0].result == "1st Place"

    assert reordered[1].player == "Bob"
    assert reordered[1].result == "2nd Place"


def test_order_normalizer_format_place():
    test_cases = {
        1: "1st Place",
        2: "2nd Place",
        3: "3rd Place",
        4: "4th Place",
        11: "11th Place",
        12: "12th Place",
        13: "13th Place",
        14: "14th Place",
        21: "21st Place",
        22: "22nd Place",
        23: "23rd Place",
        31: "31st Place",
        32: "32nd Place",
        33: "33rd Place",
        40: "40th Place",
        101: "101st Place",
        111: "111th Place",
        112: "112th Place",
        113: "113th Place",
        122: "122nd Place",
        133: "133rd Place",
    }
    for rank, expected in test_cases.items():
        assert OrderNormalizer.format_place(rank) == expected
