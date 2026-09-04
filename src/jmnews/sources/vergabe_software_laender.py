"""Länder portals — software/IT tenders BELOW the EU thresholds.

TED only carries awards above the EU thresholds. The smaller contracts — and
with them most of the ones a small vendor can realistically win — are procured
below those thresholds and are published solely on the state platforms.

No state portal except Berlin offers an RSS feed (checked: NRW, Bayern,
Niedersachsen, Hessen, Sachsen, RLP, Bremen, Saarland — none). What they do
share is their software: Brandenburg, NRW and Rheinland-Pfalz all run the
Administration-Intelligence VMPCenter, whose CPV-filtered overview we already
scrape for Brandenburg. So this source reuses that parser across hosts instead
of needing one bespoke scraper per Land.

Reference hurdle: the portals name the procedure in the table, and a
Teilnahmewettbewerb ("TNW") is the two-stage variant that gates bidders behind
reference requirements — the same distinction TED expresses as
``neg-w-call`` vs ``open``. Those rows are dropped here, matching
vergabe_software_ted. As there, this removes the *pre-qualification round*; an
open procedure can still ask for references in its Eignungskriterien.
"""

from __future__ import annotations

import re

from jmnews.sources.vergabe_vmp import VMPCenterSource, build_overview_url

# Verified live: the VMPCenter overview responds on all three hosts.
PORTALS: tuple[tuple[str, str], ...] = (
    ("Brandenburg", "vergabemarktplatz.brandenburg.de"),
    ("NRW", "www.evergabe.nrw.de"),
    ("Rheinland-Pfalz", "www.vergabe.rlp.de"),
)

# 72 = IT services, 48 = software packages.
CPV_CODES: tuple[str, ...] = ("72000000-5", "48000000-8")

# Two-stage procedures gate bidders behind a reference check — drop them.
_REFERENCE_GATED_RE = re.compile(
    r"\bTNW\b|teilnahmewettbewerb|nicht ?offenes verfahren", re.IGNORECASE
)


class VergabeSoftwareLaender(VMPCenterSource):
    name = "vergabe_software_laender"

    def __init__(
        self,
        portals: tuple[tuple[str, str], ...] = PORTALS,
        cpv_codes: tuple[str, ...] = CPV_CODES,
    ) -> None:
        self._portals = portals
        self._cpv_codes = cpv_codes

    def targets(self) -> list[tuple[str, str]]:
        return [
            (build_overview_url(host, cpv), land)
            for land, host in self._portals
            for cpv in self._cpv_codes
        ]

    def keep(self, title: str, snippet: str) -> bool:
        return _REFERENCE_GATED_RE.search(f"{title} {snippet}") is None
