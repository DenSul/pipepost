"""Universal RSS/Atom source."""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from typing import TYPE_CHECKING

import httpx

from pipepost.sources.base import Source


if TYPE_CHECKING:
    from pipepost.core.context import Candidate

logger = logging.getLogger(__name__)

_USER_AGENT = "PipePost/1.0 (+https://github.com/DenSul/pipepost)"


class RSSSource(Source):
    """Fetch candidates from any RSS/Atom feed."""

    source_type = "rss"

    def __init__(self, name: str, feed_url: str, max_items: int = 20) -> None:
        self.name = name
        self.feed_url = feed_url
        self.max_items = max_items

    async def fetch_candidates(self, limit: int = 10) -> list[Candidate]:
        """Fetch and parse the RSS/Atom feed."""
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(
                self.feed_url,
                headers={"User-Agent": _USER_AGENT},
            )
            resp.raise_for_status()

        return self._parse_feed(resp.text, limit)

    def _parse_feed(self, xml_text: str, limit: int) -> list[Candidate]:
        """Parse RSS or Atom feed XML."""
        from pipepost.core.context import Candidate

        candidates: list[Candidate] = []
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as exc:
            logger.error("Failed to parse feed %s: %s", self.feed_url, exc)
            return []

        # RSS 2.0
        items = root.findall(".//item")
        if items:
            for item in items[: min(limit, self.max_items)]:
                title = (item.findtext("title") or "").strip()
                link = (item.findtext("link") or "").strip()
                desc = (item.findtext("description") or "").strip()
                if link:
                    candidates.append(
                        Candidate(
                            url=link,
                            title=title,
                            snippet=desc[:200],
                            source_name=self.name,
                        ),
                    )
            return candidates

        # Atom
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        entries = root.findall(".//atom:entry", ns)
        for entry in entries[: min(limit, self.max_items)]:
            title = (entry.findtext("atom:title", namespaces=ns) or "").strip()
            link_el = entry.find(
                "atom:link[@rel='alternate']",
                ns,
            ) or entry.find("atom:link", ns)
            link = link_el.get("href", "") if link_el is not None else ""
            summary = (entry.findtext("atom:summary", namespaces=ns) or "").strip()
            if link:
                candidates.append(
                    Candidate(
                        url=link,
                        title=title,
                        snippet=summary[:200],
                        source_name=self.name,
                    ),
                )

        return candidates

    @classmethod
    def from_config(cls, config: dict[str, object]) -> RSSSource:
        """Create from YAML config."""
        return cls(
            name=str(config.get("name", "rss")),
            feed_url=str(config["url"]),
            max_items=int(raw)
            if isinstance(raw := config.get("max_items", 20), (int, str))
            else 20,
        )

    def get_config_schema(self) -> dict[str, object]:
        """JSON schema for RSS source config."""
        return {
            "type": "object",
            "required": ["url"],
            "properties": {
                "name": {"type": "string"},
                "url": {"type": "string", "format": "uri"},
                "max_items": {"type": "integer", "default": 20},
            },
        }


# Don't register globally — RSS sources are created from config
