"""Abstract base class for publish destinations."""
from __future__ import annotations

from abc import ABC, abstractmethod

from pipepost.core.context import PublishResult, TranslatedArticle


class Destination(ABC):
    """A target where translated articles are published."""

    name: str

    @abstractmethod
    async def publish(self, article: TranslatedArticle) -> PublishResult:
        """Publish an article. Return result."""

    async def check_duplicate(self, url: str) -> bool:
        """Check if article with this source URL already exists."""
        return False

    def __repr__(self) -> str:
        return f"<Destination:{self.name}>"
