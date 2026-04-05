"""HackerNews source — fetches top stories via Firebase API."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import httpx

from pipepost.core.registry import register_source
from pipepost.exceptions import SourceError
from pipepost.sources.base import Source


if TYPE_CHECKING:
    from pipepost.core.context import Candidate

logger = logging.getLogger(__name__)

_HN_API_BASE = "https://hacker-news.firebaseio.com/v0"


class HackerNewsSource(Source):
    """Fetch top stories from Hacker News."""

    name = "hackernews"
    source_type = "api"

    def __init__(self, min_score: int = 50, *, max_concurrency: int = 5) -> None:
        super().__init__(max_concurrency=max_concurrency)
        self.min_score = min_score

    async def fetch_candidates(self, limit: int = 10) -> list[Candidate]:
        """Fetch top HN stories above min_score."""
        from pipepost.core.context import Candidate

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                async with self.rate_limit():
                    resp = await client.get(f"{_HN_API_BASE}/topstories.json")
                    resp.raise_for_status()
                story_ids: list[int] = resp.json()[: limit * 2]

                candidates: list[Candidate] = []
                for sid in story_ids:
                    if len(candidates) >= limit:
                        break
                    try:
                        async with self.rate_limit():
                            item_resp = await client.get(f"{_HN_API_BASE}/item/{sid}.json")
                            item_resp.raise_for_status()
                        item = item_resp.json()
                        if not item or item.get("type") != "story" or not item.get("url"):
                            continue
                        score = item.get("score", 0)
                        if score < self.min_score:
                            continue
                        candidates.append(
                            Candidate(
                                url=item["url"],
                                title=item.get("title", ""),
                                snippet=f"Score: {score}, Comments: {item.get('descendants', 0)}",
                                score=float(score),
                                source_name=self.name,
                                metadata={
                                    "hn_id": sid,
                                    "comments": item.get("descendants", 0),
                                },
                            ),
                        )
                    except httpx.HTTPError as exc:
                        logger.warning("Failed to fetch HN item %s: %s", sid, exc)

                candidates.sort(key=lambda c: c.score, reverse=True)
                return candidates[:limit]
        except httpx.HTTPError as exc:
            raise SourceError(f"HackerNews API request failed: {exc}") from exc

    @classmethod
    def from_config(cls, config: dict[str, object]) -> HackerNewsSource:
        """Create from YAML config."""
        raw_score = config.get("min_score", 50)
        return cls(min_score=int(raw_score) if isinstance(raw_score, (int, str)) else 50)


register_source("hackernews", HackerNewsSource())
