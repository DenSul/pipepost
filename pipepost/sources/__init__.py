"""PipePost sources — content discovery from various platforms."""

# Auto-discovered via registry.discover_modules("pipepost.sources")

from pipepost.sources.aicraft_tils import AICraftTILsSource
from pipepost.sources.base import Source
from pipepost.sources.hackernews import HackerNewsSource
from pipepost.sources.reddit import RedditSource
from pipepost.sources.rss import RSSSource
from pipepost.sources.search import SearchSource


__all__ = [
    "AICraftTILsSource",
    "HackerNewsSource",
    "RSSSource",
    "RedditSource",
    "SearchSource",
    "Source",
]
