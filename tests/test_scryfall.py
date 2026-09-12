import json
import logging

from src.scryfall import ScryfallNormalizer


def test_scryfall_normalizer_static_and_prefix(tmp_path):
    cache_dir = tmp_path / ".cache"
    cache_file = cache_dir / "scryfall_names.json"
    cache_dir.mkdir(parents=True)

    # Pre-seed cache with sample mappings
    mappings = {
        "Wear/Tear": "Wear // Tear",
        "Wear": "Wear // Tear",
        '"Name Sticker" Goblin': "_____ Goblin",
    }
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(mappings, f)

    normalizer = ScryfallNormalizer(cache_dir=str(cache_dir))

    # Test exact mapping
    assert normalizer.normalize("Wear/Tear") == "Wear // Tear"

    # Test static mapping
    assert normalizer.normalize('"Name Sticker" Goblin') == "_____ Goblin"

    # Test Alchemy prefix stripping
    assert normalizer.normalize("A-Bowmasters") == "Bowmasters"

    # Test untransformed card
    assert normalizer.normalize("Lightning Bolt") == "Lightning Bolt"


def test_scryfall_normalizer_warning_on_unrecognized(tmp_path, caplog):

    cache_dir = tmp_path / ".cache"
    cache_file = cache_dir / "scryfall_names.json"
    cache_dir.mkdir(parents=True)

    payload = {
        "mappings": {"Wear/Tear": "Wear // Tear"},
        "canonical": ["Lightning Bolt", "Brainstorm", "Wear // Tear"],
    }
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(payload, f)

    normalizer = ScryfallNormalizer(cache_dir=str(cache_dir))

    with caplog.at_level(logging.WARNING):
        # Valid recognized card should not warn
        assert normalizer.normalize("Lightning Bolt") == "Lightning Bolt"
        assert "not recognized" not in caplog.text

        # Unrecognized card should warn once but still return the name safely
        result = normalizer.normalize("Fake Card Name 12345")
        assert result == "Fake Card Name 12345"
        assert "Fake Card Name 12345" in caplog.text
