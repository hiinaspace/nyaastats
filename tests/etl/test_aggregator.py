"""Tests for torrent aggregation helpers."""

import json

from nyaastats.etl.aggregator import extract_guessit_title


def test_extract_guessit_title_accepts_list_valued_titles():
    guessit_data = json.dumps(
        {"title": ["Gecko Hetalia World Stars", "S"], "episode": [13, 14, 15]}
    )

    assert extract_guessit_title(guessit_data) == "Gecko Hetalia World Stars"


def test_extract_guessit_title_returns_scalar_title():
    assert extract_guessit_title(json.dumps({"title": "Frieren"})) == "Frieren"
