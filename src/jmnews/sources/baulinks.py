"""baulinks.de — German Bau-Branche news.

Two feeds combined into one source:

- /rssfeed/bauportale/architektursoftware.rss
  Bau-IT / Bausoftware — direct competitor coverage for JM's Liquiditäts-
  tool: Nevaris Finance, RIB iTWO, BRZ 365, Phase0 AVA-KI, Vectorworks,
  in-Software etc. Posts about new features, releases, pricing changes,
  partnerships — exactly the competitive-intelligence signal needed.

- /rssfeed/baubranche/baukonjunktur.rss
  Bau-Konjunktur — ifo-Bauklima index, Baugenehmigungen,
  Bauinsolvenz-Statistiken, Euroconstruct prognoses. The macroeconomic
  Bedarfs-Trigger for a Bau-Liquiditätstool (when payment delays grow,
  the product gets more relevant).
"""

from __future__ import annotations

from jmnews.sources.base import RSSSource


class Baulinks(RSSSource):
    name = "baulinks"

    def feed_urls(self) -> list[str]:
        return [
            "https://www.baulinks.de/rssfeed/bauportale/architektursoftware.rss",
            "https://www.baulinks.de/rssfeed/baubranche/baukonjunktur.rss",
        ]
