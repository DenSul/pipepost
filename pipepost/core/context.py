"""Shared state passed between pipeline steps."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Candidate:
    """A content candidate found by a source."""

    url: str
    title: str
    snippet: str = ""
    score: float = 0.0
    source_name: str = ""
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass
class Article:
    """A fetched article with full content."""

    url: str
    title: str
    content: str  # markdown
    cover_image: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass
class TranslatedArticle:
    """An article translated to target language."""

    title: str
    title_translated: str
    content: str
    content_translated: str
    source_url: str
    source_name: str = ""
    tags: list[str] = field(default_factory=list)
    cover_image: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass
class PublishResult:
    """Result of publishing an article."""

    success: bool
    slug: str = ""
    url: str = ""
    error: str = ""


@dataclass
class FlowContext:
    """Shared state between pipeline steps."""

    candidates: list[Candidate] = field(default_factory=list)
    articles: list[Article] = field(default_factory=list)
    selected: Article | None = None
    translated: TranslatedArticle | None = None
    published: PublishResult | None = None
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, object] = field(default_factory=dict)

    # Configuration injected at flow start
    source_name: str = ""
    target_lang: str = "ru"
    existing_urls: set[str] = field(default_factory=set)

    @property
    def has_errors(self) -> bool:
        """Return True if any errors have been recorded."""
        return bool(self.errors)

    def add_error(self, msg: str) -> None:
        """Record an error message."""
        self.errors.append(msg)
