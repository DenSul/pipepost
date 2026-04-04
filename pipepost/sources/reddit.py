"""Reddit source — fetches top posts from subreddits."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import httpx

from pipepost.core.registry import register_source
from pipepost.sources.base import Source


if TYPE_CHECKING:
    from pipepost.core.context import Candidate

logger = logging.getLogger(__name__)

_DEFAULT_SUBREDDITS = [
    "programming",
    "golang",
    "python",
    "devops",
]


class RedditSource(Source):
    """Fetch top posts from configurable subreddits."""

    name = "reddit"
    source_type = "api"

    def __init__(
        self,
        subreddits: list[str] | None = None,
        min_score: int = 100,
    ) -> None:
        self.subreddits = subreddits or list(_DEFAULT_SUBREDDITS)
        self.min_score = min_score

    async def fetch_candidates(self, limit: int = 10) -> list[Candidate]:
        """Fetch top posts from configured subreddits."""
        from pipepost.core.context import Candidate

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
                        post_data = post.get("data", {})
                        url = post_data.get("url", "")
                        score = post_data.get("score", 0)
                        if (
                            not url
                            or url.startswith("https://www.reddit.com")
                            or score < self.min_score
                        ):
                            continue
                        candidates.append(
                            Candidate(
                                url=url,
                                title=post_data.get("title", ""),
                                snippet=post_data.get("selftext", "")[:200],
                                score=float(score),
                                source_name=self.name,
                                metadata={
                                    "subreddit": sub,
                                    "reddit_id": post_data.get("id"),
                                },
                            ),
                        )
                except Exception as exc:
                    logger.warning("Failed to fetch r/%s: %s", sub, exc)

        candidates.sort(key=lambda c: c.score, reverse=True)
        return candidates[:limit]

    @classmethod
    def from_config(cls, config: dict[str, object]) -> RedditSource:
        """Create from YAML config."""
        raw_subs = config.get("subreddits")
        subreddits: list[str] | None = None
        if isinstance(raw_subs, list):
            subreddits = [str(s) for s in raw_subs]
        raw_score = config.get("min_score", 100)
        min_score = int(raw_score) if isinstance(raw_score, (int, str)) else 100
        return cls(subreddits=subreddits, min_score=min_score)


register_source("reddit", RedditSource())
