"""Brandenburg Vergabemarktplatz — public tenders by CPV category.

Two categories are polled, both named as indicators in the JM profile:

- CPV 85000000-9 "Health and social work services": the core feed
  (Jugendhilfe, Pflege, Migrationssozialarbeit, Unterbringung …).
- CPV 80000000-4 "Education and training services": adds tenders that never
  surface under CPV 85 — MBJS-Rahmenvereinbarungen, Grundbildung, schulische
  Präventions- und Jugendmaßnahmen der Landkreise, many of them published as
  "Beabsichtigte Ausschreibung", i.e. before the actual procurement starts.

The CPV label goes into the snippet so the downstream Claude filter can tell
a Bildungs- from a Sozialvergabe (see the profile rule for this source).

The portal is a Java/Struts app that returns ISO-8859-1 HTML; standard
ScrapingSource assumes UTF-8 so we handle the HTTP + decode ourselves.
"""

from __future__ import annotations

from jmnews.sources.vergabe_vmp import VMPCenterSource, build_overview_url

HOST = "vergabemarktplatz.brandenburg.de"

# (CPV code, short label for the snippet)
CPV_CATEGORIES: tuple[tuple[str, str], ...] = (
    ("85000000-9", "CPV 85 Sozialwesen"),
    ("80000000-4", "CPV 80 Bildung"),
)


def build_category_url(cpv: str) -> str:
    return build_overview_url(HOST, cpv)


class VergabeBrandenburg(VMPCenterSource):
    name = "vergabe_brandenburg"
    base_url = f"https://{HOST}"

    def __init__(
        self, categories: tuple[tuple[str, str], ...] = CPV_CATEGORIES
    ) -> None:
        self._categories = categories

    def targets(self) -> list[tuple[str, str]]:
        return [(build_category_url(cpv), label) for cpv, label in self._categories]
