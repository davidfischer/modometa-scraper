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
