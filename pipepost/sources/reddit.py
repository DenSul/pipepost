"""Reddit source — fetches top posts from subreddits."""
from __future__ import annotations

import logging

import httpx

from pipepost.core.context import Candidate
from pipepost.core.registry import register_source
from pipepost.sources.base import Source

logger = logging.getLogger(__name__)


class RedditSource(Source):
    name = "reddit"
    source_type = "api"

    def __init__(
        self,
        subreddits: list[str] | None = None,
        min_score: int = 100,
    ):
        self.subreddits = subreddits or [
            "programming",
            "golang",
            "python",
            "devops",
        ]
        self.min_score = min_score

    async def fetch_candidates(self, limit: int = 10) -> list[Candidate]:
        candidates: list[Candidate] = []
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            for sub in self.subreddits:
                try:
                    resp = await client.get(
                        f"https://www.reddit.com/r/{sub}/top.json?t=day&limit=10",
                        headers={"User-Agent": "PipePost/1.0"},
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    for post in data.get("data", {}).get("children", []):
                        pd = post.get("data", {})
                        url = pd.get("url", "")
                        score = pd.get("score", 0)
                        if (
                            not url
                            or url.startswith("https://www.reddit.com")
                            or score < self.min_score
                        ):
                            continue
                        candidates.append(
                            Candidate(
                                url=url,
                                title=pd.get("title", ""),
                                snippet=pd.get("selftext", "")[:200],
                                score=float(score),
                                source_name=self.name,
                                metadata={
                                    "subreddit": sub,
                                    "reddit_id": pd.get("id"),
                                },
                            ),
                        )
                except Exception as e:
                    logger.warning("Failed to fetch r/%s: %s", sub, e)

        candidates.sort(key=lambda c: c.score, reverse=True)
        return candidates[:limit]

    @classmethod
    def from_config(cls, config: dict) -> "RedditSource":
        return cls(
            subreddits=config.get("subreddits"),
            min_score=config.get("min_score", 100),
        )


register_source("reddit", RedditSource())
