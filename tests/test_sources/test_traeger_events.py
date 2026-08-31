"""Relevance-filter tests for the Träger business-event sources.

`insolvenz` and `nexxt_change` gate name-based portal hits through a stem
filter. These tests pin the widened Kinderheim-Branche recall (German
compounds / plurals now match) without re-opening the false-positive door.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from bs4 import BeautifulSoup

from jmnews.sources.insolvenz import (
    _EXCLUDE_TOKENS,
    _RELEVANT_SHORT,
    _RELEVANT_TOKENS,
    WILDCARDS,
    _field_name,
    _form_defaults,
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


# --- insolvenz: JSF-Formularfelder ------------------------------------------
#
# Das Portal hat seine Feld-Ids schon einmal umbenannt (`lsom_bundesland:lsom`
# -> `lsom_bundesland:codelist:scl_bundesland:mysom`). Ein veralteter Name
# quittiert Mojarra mit einem nackten 500 ohne Meldung, weshalb die Quelle das
# Payload aus dem tatsaechlich gelieferten Formular aufbaut. Diese Tests halten
# genau das fest.


def _form(fixtures_dir: Path) -> Any:
    html = (fixtures_dir / "insolvenz_suchformular.html").read_text(encoding="utf-8")
    return BeautifulSoup(html, "html.parser").find("form", id="frm_suche")


def test_form_defaults_cover_every_named_field(fixtures_dir: Path) -> None:
    form = _form(fixtures_dir)
    payload = _form_defaults(form)

    named = {el["name"] for el in form.find_all(["input", "select", "textarea"]) if el.get("name")}
    assert payload.keys() == named
    # JSF needs the form marker and the view token to accept the POST.
    assert payload["frm_suche"] == "frm_suche"
    assert payload["jakarta.faces.ViewState"]
    assert payload["frm_suche:cbt_suchen"] == "Suchen"


def test_form_defaults_use_the_no_selection_option(fixtures_dir: Path) -> None:
    payload = _form_defaults(_form(fixtures_dir))
    selects = [name for name in payload if name.endswith(":mysom") or name.endswith(":lsom")]
    assert selects
    # Every dropdown submits the portal's "no selection" entry untouched.
    assert {payload[name] for name in selects} <= {"NO_CODE", "0"}


def test_field_names_resolve_against_the_served_form(fixtures_dir: Path) -> None:
    payload = _form_defaults(_form(fixtures_dir))

    assert _field_name(payload, "ldi_datumVon:datumHtml5") == "frm_suche:ldi_datumVon:datumHtml5"
    assert _field_name(payload, "lsom_wildcard:lsom") == "frm_suche:lsom_wildcard:lsom"
    assert (
        _field_name(payload, "litx_firmaNachName:text")
        == "frm_suche:litx_firmaNachName:text"
    )


def test_field_name_raises_when_the_portal_renames_a_field() -> None:
    # A rename must surface as one named warning, not as a silent 500.
    with pytest.raises(ValueError, match="lsom_bundesland:lsom"):
        _field_name({"frm_suche:lsom_bundesland:codelist:x": ""}, "lsom_bundesland:lsom")
