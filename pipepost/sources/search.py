"""DuckDuckGo search source — find articles by keyword queries."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from pipepost.sources.base import Source


if TYPE_CHECKING:
    from pipepost.core.context import Candidate

logger = logging.getLogger(__name__)

_DEFAULT_QUERIES = [
    "latest news",
    "trending articles",
]


class SearchSource(Source):
    """Find articles using DuckDuckGo search queries."""

    source_type = "search"

    def __init__(
        self,
        name: str = "search",
        queries: list[str] | None = None,
    ) -> None:
        self.name = name
        self.queries = queries or list(_DEFAULT_QUERIES)

    async def fetch_candidates(self, limit: int = 10) -> list[Candidate]:
        """Search DuckDuckGo for articles matching configured queries."""
        from duckduckgo_search import DDGS

        from pipepost.core.context import Candidate

        candidates: list[Candidate] = []
        per_query = max(1, limit // len(self.queries)) if self.queries else limit

        with DDGS() as ddgs:
            for query in self.queries:
                try:
                    results = list(ddgs.text(query, max_results=per_query))
                    for result in results:
                        href = result.get("href", "")
                        if href:
                            candidates.append(
                                Candidate(
                                    url=href,
                                    title=result.get("title", ""),
                                    snippet=result.get("body", "")[:200],
                                    source_name=self.name,
                                    metadata={"query": query},
                                ),
                            )
                except Exception as exc:
                    logger.warning("Search failed for '%s': %s", query, exc)
                    self._try_news_fallback(ddgs, query, per_query, candidates)

        return candidates[:limit]

    @staticmethod
    def _try_news_fallback(
        ddgs: object,
        query: str,
        limit: int,
        candidates: list[Candidate],
    ) -> None:
        """Fallback to news search when text search fails."""
        from pipepost.core.context import Candidate

        try:
            results = list(ddgs.news(query, max_results=limit))  # type: ignore[attr-defined]
            for result in results:
                url = result.get("url", "")
                if url:
                    candidates.append(
                        Candidate(
                            url=url,
                            title=result.get("title", ""),
                            snippet=result.get("body", "")[:200],
                            source_name="search",
                            metadata={"query": query, "type": "news"},
                        ),
                    )
        except Exception as exc:
            logger.warning("News fallback failed for '%s': %s", query, exc)

    @classmethod
    def from_config(cls, config: dict[str, object]) -> SearchSource:
        """Create SearchSource from YAML config dict."""
        return cls(
            name=str(config.get("name", "search")),
            queries=config.get("queries") or [],  # type: ignore[arg-type]
        )
