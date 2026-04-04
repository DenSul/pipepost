"""DuckDuckGo search source — find articles by keyword queries."""
from __future__ import annotations

import logging

from pipepost.core.context import Candidate
from pipepost.sources.base import Source

logger = logging.getLogger(__name__)


class SearchSource(Source):
    """Find articles using DuckDuckGo search queries."""

    source_type = "search"

    def __init__(
        self,
        name: str = "search",
        queries: list[str] | None = None,
    ):
        self.name = name
        self.queries = queries or [
            "latest programming tutorials",
            "tech news today",
        ]

    async def fetch_candidates(self, limit: int = 10) -> list[Candidate]:
        from duckduckgo_search import DDGS

        candidates: list[Candidate] = []
        per_query = max(1, limit // len(self.queries)) if self.queries else limit

        with DDGS() as ddgs:
            for q in self.queries:
                try:
                    results = list(ddgs.text(q, max_results=per_query))
                    for r in results:
                        if r.get("href"):
                            candidates.append(
                                Candidate(
                                    url=r["href"],
                                    title=r.get("title", ""),
                                    snippet=r.get("body", "")[:200],
                                    source_name=self.name,
                                    metadata={"query": q},
                                ),
                            )
                except Exception as e:
                    logger.warning("Search failed for '%s': %s", q, e)
                    # Fallback to news search
                    try:
                        results = list(ddgs.news(q, max_results=per_query))
                        for r in results:
                            if r.get("url"):
                                candidates.append(
                                    Candidate(
                                        url=r["url"],
                                        title=r.get("title", ""),
                                        snippet=r.get("body", "")[:200],
                                        source_name=self.name,
                                        metadata={"query": q, "type": "news"},
                                    ),
                                )
                    except Exception as e2:
                        logger.warning(
                            "News fallback failed for '%s': %s", q, e2,
                        )

        return candidates[:limit]

    @classmethod
    def from_config(cls, config: dict) -> "SearchSource":
        return cls(
            name=config.get("name", "search"),
            queries=config.get("queries", []),
        )
