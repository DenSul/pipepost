"""AI Craft TILs source — fetches existing TIL titles to avoid duplicates."""

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

_DEFAULT_API_BASE = "http://localhost:8000/api"


class AICraftTILsSource(Source):
    """Fetch existing TIL titles from AI Craft backend to prevent duplicates."""

    name = "aicraft_tils"
    source_type = "api"

    def __init__(
        self,
        api_base: str = _DEFAULT_API_BASE,
        *,
        max_concurrency: int = 3,
    ) -> None:
        super().__init__(max_concurrency=max_concurrency)
        self.api_base = api_base.rstrip("/")

    async def fetch_candidates(self, limit: int = 20) -> list[Candidate]:
        """Fetch existing TILs as candidates (used for dedup, not for publishing)."""
        from pipepost.core.context import Candidate

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                async with self.rate_limit():
                    resp = await client.get(
                        f"{self.api_base}/tils",
                        params={"limit": limit},
                    )
                    resp.raise_for_status()

                raw = resp.json()
                data = raw.get("data", raw) if isinstance(raw, dict) else raw
                if not isinstance(data, list):
                    return []

                candidates: list[Candidate] = []
                for item in data:
                    title = item.get("title", "")
                    if not title:
                        continue
                    candidates.append(
                        Candidate(
                            url=item.get("sourceUrl", ""),
                            title=title,
                            snippet=item.get("titleRu", ""),
                            score=0.0,
                            source_name=self.name,
                            metadata={
                                "id": item.get("id", ""),
                                "tags": item.get("tags", []),
                                "difficulty": item.get("difficulty", ""),
                            },
                        ),
                    )
                return candidates

        except httpx.HTTPError as exc:
            raise SourceError(f"AI Craft TILs API request failed: {exc}") from exc

    @classmethod
    def from_config(cls, config: dict[str, object]) -> AICraftTILsSource:
        """Create from YAML config."""
        api_base = str(config.get("api_base", _DEFAULT_API_BASE))
        return cls(api_base=api_base)


register_source("aicraft_tils", AICraftTILsSource())
