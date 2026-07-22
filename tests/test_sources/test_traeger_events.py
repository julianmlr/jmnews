"""Relevance-filter tests for the Träger business-event sources.

`insolvenz` and `nexxt_change` gate name-based portal hits through a stem
filter. These tests pin the widened Kinderheim-Branche recall (German
compounds / plurals now match) without re-opening the false-positive door.
"""

from __future__ import annotations

import pytest

from jmnews.sources.insolvenz import (
    _EXCLUDE_TOKENS,
    _RELEVANT_SHORT,
    _RELEVANT_TOKENS,
    WILDCARDS,
)
from jmnews.sources.nexxt_change import _is_relevant


def _insolvenz_relevant(name: str) -> bool:
    if not (_RELEVANT_TOKENS.search(name) or _RELEVANT_SHORT.search(name)):
        return False
    return not _EXCLUDE_TOKENS.search(name)


# --- insolvenz --------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        # Compounds / plurals that failed under the old trailing-\b regex.
        "Kindertagesstätte Regenbogen e.V.",
        "Wohngruppen Spandau gGmbH",
        "Sozialpädagogisches Zentrum Nord gGmbH",
        "Kinderkrippe Sonnenblume GmbH",
        "Albert-Schweitzer-Kinderdorf Berlin",
        "Heilpädagogische Einrichtung Süd gGmbH",
        # Already-covered stems still match.
        "Kinderheim Waldblick gGmbH",
        "Jugendhilfe Verbund Berlin e.V.",
        "Sophienhof gGmbH",
        "Hort an der Grundschule e.V.",
    ],
)
def test_insolvenz_keeps_sector_operators(name: str) -> None:
    assert _insolvenz_relevant(name)


@pytest.mark.parametrize(
    "name",
    [
        "Kindermann Metallbau GmbH",  # surname, no sector stem
        "Kindermöbel Handel GmbH",  # excluded branch
        "Hortensienweg Immobilien GmbH",  # short token needs boundary
        "Seniorenresidenz Sonnengarten GmbH",  # pflege, no youth stem
        "Zahnmedizinisches Versorgungszentrum",  # excluded
    ],
)
def test_insolvenz_drops_false_positives(name: str) -> None:
    assert not _insolvenz_relevant(name)


def test_insolvenz_wildcards_widened() -> None:
    # The neutrally-named-operator wildcards are present.
    assert "*Wohngrupp*" in WILDCARDS
    assert "*Pädagog*" in WILDCARDS


# --- nexxt_change -----------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "Verkauf Wohngruppen der stationären Jugendhilfe",
        "Kindertagesstätte mit 60 Plätzen abzugeben",
        "Sozialpädagogische Einrichtung sucht Nachfolger",
        "Kinderheim in Brandenburg zu verkaufen",
    ],
)
def test_nexxt_change_keeps_sector_offers(text: str) -> None:
    assert _is_relevant(text)


@pytest.mark.parametrize(
    "text",
    [
        "Seniorenheim mit Pflegeeinrichtung",
        "Betreutes Wohnen für Senioren",
        "Restaurant in bester Lage abzugeben",
    ],
)
def test_nexxt_change_drops_pflege_and_noise(text: str) -> None:
    assert not _is_relevant(text)
