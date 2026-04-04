"""HackerNews source — fetches top stories via Firebase API."""
from __future__ import annotations

import logging

import httpx

from pipepost.core.context import Candidate
from pipepost.core.registry import register_source
from pipepost.sources.base import Source

logger = logging.getLogger(__name__)


class HackerNewsSource(Source):
    name = "hackernews"
    source_type = "api"

    def __init__(self, min_score: int = 50):
        self.min_score = min_score

    async def fetch_candidates(self, limit: int = 10) -> list[Candidate]:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                "https://hacker-news.firebaseio.com/v0/topstories.json",
            )
            resp.raise_for_status()
            story_ids = resp.json()[: limit * 2]  # fetch more, filter later

            candidates: list[Candidate] = []
            for sid in story_ids:
                if len(candidates) >= limit:
                    break
                try:
                    r = await client.get(
                        f"https://hacker-news.firebaseio.com/v0/item/{sid}.json",
                    )
                    r.raise_for_status()
                    item = r.json()
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
                except Exception as e:
                    logger.warning("Failed to fetch HN item %s: %s", sid, e)

            candidates.sort(key=lambda c: c.score, reverse=True)
            return candidates[:limit]

    @classmethod
    def from_config(cls, config: dict) -> "HackerNewsSource":
        return cls(min_score=config.get("min_score", 50))


register_source("hackernews", HackerNewsSource())
