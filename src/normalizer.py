"""Deck and order normalizers matching MTG_decklistcache conventions."""

from typing import List

from .models import Deck
from .models import DeckItem
from .models import Round
from .models import Standing


class DeckNormalizer:
    @staticmethod
    def normalize(deck: Deck) -> Deck:
        deck.mainboard = sorted(
            DeckNormalizer.combine_duplicates(deck.mainboard),
            key=lambda item: item.card_name,
        )
        deck.sideboard = sorted(
            DeckNormalizer.combine_duplicates(deck.sideboard),
            key=lambda item: item.card_name,
        )
        return deck

    @staticmethod
    def combine_duplicates(input_items: List[DeckItem]) -> List[DeckItem]:
        combined = {}
        for item in input_items:
            if item.card_name not in combined:
                combined[item.card_name] = DeckItem(card_name=item.card_name, count=0)
            combined[item.card_name].count += item.count
        return list(combined.values())


class OrderNormalizer:
    @staticmethod
    def reorder_decks(
        decks: List[Deck],
        standings: List[Standing],
        bracket_rounds: List[Round],
        update_result: bool = True,
    ) -> List[Deck]:
        ordered_decks = []
        player_order = OrderNormalizer.get_player_order(
            decks, standings, bracket_rounds
        )

        position = 1
        for player in player_order:
            deck = next((d for d in decks if d.player == player), None)
            if deck is None:
                position += 1
                continue

            rank = f"{position}th Place"
            if position == 1:
                rank = "1st Place"
            elif position == 2:
                rank = "2nd Place"
            elif position == 3:
                rank = "3rd Place"

            position += 1

            if update_result:
                deck.result = rank

            ordered_decks.append(deck)

        return ordered_decks

    @staticmethod
    def get_player_order(
        decks: List[Deck],
        standings: List[Standing],
        bracket_rounds: List[Round],
    ) -> List[str]:
        result = []

        for standing in standings:
            if not hasattr(standing, "rank") or standing.rank is None:
                standing.rank = (
                    sum(1 for s in standings if s.points > standing.points) + 1
                )

        max_rank = max((s.rank for s in standings), default=0)
        for i in range(1, max_rank + 1):
            player_name = next((s.player for s in standings if s.rank == i), None)
            if player_name is None:
                result.append("-")
            else:
                result.append(player_name)

        # Adjust order using playoff bracket rounds (Finals pushed last so winners end on top)
        if bracket_rounds:
            for bracket_round in bracket_rounds:
                result = OrderNormalizer.push_to_top(
                    result,
                    [match.player2 for match in bracket_round.matches],
                    standings,
                )
                result = OrderNormalizer.push_to_top(
                    result,
                    [match.player1 for match in bracket_round.matches],
                    standings,
                )

        # Add any players with decks that weren't in standings
        for deck in decks:
            if deck.player not in result:
                result.append(deck.player)

        return list(dict.fromkeys(result))

    @staticmethod
    def push_to_top(
        players: List[str],
        pushed_players: List[str],
        standings: List[Standing],
    ) -> List[str]:
        player_ranks = {
            player: next(s.rank for s in standings if s.player == player)
            for player in pushed_players
            if any(s.player == player for s in standings)
        }

        remaining_players = [p for p in players if p not in pushed_players]

        # Pushed players sorted by rank, followed by remaining players
        result = [p for p, _ in sorted(player_ranks.items(), key=lambda x: x[1])]
        result.extend(remaining_players)
        return result
