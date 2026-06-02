"""Eric Topol Ground Truths — methodologically critical biomed analysis.

Substack RSS, weekly long-form pieces. Topol provides the evidence-quality
counterweight to the Attia/Sinclair/Bryan-Johnson personality-driven side
of the longevity space: data-driven, methodologically rigorous, frequently
critical of overhyped findings.

Output classification: context only.
"""

from __future__ import annotations

from jmnews.sources.base import RSSSource


class EricTopol(RSSSource):
    name = "eric_topol"

    def feed_urls(self) -> list[str]:
        return ["https://erictopol.substack.com/feed"]
