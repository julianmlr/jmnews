"""Berlin Vergabeplattform — public tender announcements, social-sector filtered.

berlin.de/vergabeplattform publishes its Bekanntmachungen as an RSS feed, so we
use that instead of scraping the paginated HTML listing: one request instead of
six. That matters — berlin.de rate-limits us ("429 Calm down"), and a 429 in
the middle of the pagination silently cost us every remaining page.

The feed carries the same substance: the RIB detail link as the item URL and
"Verfahrensart / Ausführungsort" in the summary, across the same procedure mix
— including the below-EU-threshold ones (UVgO, VOB/A national) that never
reach TED.

It is the state's complete tender feed, so most entries are construction. We
keep only what matches JM's social sector, mirroring how vergabe_brandenburg
scopes itself by CPV; the Claude filter scores the survivors.
"""

from __future__ import annotations

import re
from datetime import datetime

from jmnews.models import NewsItem
from jmnews.sources.base import RSSSource

FEED_URL = (
    "https://www.berlin.de/vergabeplattform/veroeffentlichungen/"
    "bekanntmachungen/feed.rss"
)

# JM-relevant social-sector stems. Recall-oriented; the Claude filter does the
# final scoring.
_RELEVANCE_RE = re.compile(
    r"jugend|kita|kinder|erzieh|hort|sch(?:ü|ue)ler|wohngrupp|kinderheim"
    r"|betreu|pflege|sozial|migration|integration|fl(?:ü|ue)cht|asyl"
    r"|frauenhaus|gewaltschutz|frauen-?\s*und\s*kinderschutz|zuflucht"
    r"|beratung|eingliederung|teilhabe|behinder|obdach|wohnungslos"
    r"|unterbring|tr(?:ä|ae)ger|familie|senior|hilfe zur erziehung"
    r"|jugendhilfe|sgb\s*viii|heimerziehung|frühe hilfen|fruehe hilfen",
    re.IGNORECASE,
)


def is_relevant(text: str) -> bool:
    return _RELEVANCE_RE.search(text) is not None


class VergabeBerlin(RSSSource):
    name = "vergabe_berlin"

    def feed_urls(self) -> list[str]:
        return [FEED_URL]

    def fetch(self, since: datetime) -> list[NewsItem]:
        return [
            item
            for item in super().fetch(since)
            if is_relevant(f"{item.title} {item.snippet}")
        ]
