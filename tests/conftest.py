"""Shared fixtures for PipePost tests."""

from __future__ import annotations

import sys
import types
from unittest.mock import AsyncMock


# Ensure litellm is importable even when the real package is broken
# (e.g., Windows long-path issue). Tests mock acompletion anyway.
if "litellm" not in sys.modules:
    _mock_litellm = types.ModuleType("litellm")
    _mock_litellm.acompletion = AsyncMock()  # type: ignore[attr-defined]
    sys.modules["litellm"] = _mock_litellm

import pytest

from pipepost.core.context import (
    Article,
    Candidate,
    FlowContext,
    PublishResult,
    TranslatedArticle,
)


@pytest.fixture
def sample_candidate() -> Candidate:
    return Candidate(
        url="https://example.com/article-1",
        title="Test Article",
        snippet="A short snippet about testing",
        score=150.0,
        source_name="hackernews",
        metadata={"hn_id": 12345},
    )


@pytest.fixture
def sample_article() -> Article:
    return Article(
        url="https://example.com/article-1",
        title="Test Article",
        content="# Test Article\n\nThis is a fairly long article content. " * 20,
        cover_image="https://example.com/cover.jpg",
        metadata={"hn_id": 12345},
    )


@pytest.fixture
def sample_translated() -> TranslatedArticle:
    return TranslatedArticle(
        title="Test Article",
        title_translated="Тестовая статья",
        content="# Test Article\n\nOriginal content here. " * 20,
        content_translated="# Тестовая статья\n\nПереведённый контент. " * 20,
        source_url="https://example.com/article-1",
        source_name="hackernews",
        tags=["python", "testing"],
        cover_image="https://example.com/cover.jpg",
    )


@pytest.fixture
def sample_context(sample_candidate: Candidate) -> FlowContext:
    return FlowContext(
        candidates=[sample_candidate],
        source_name="hackernews",
        target_lang="ru",
    )


@pytest.fixture
def context_with_article(sample_context: FlowContext, sample_article: Article) -> FlowContext:
    sample_context.selected = sample_article
    return sample_context


@pytest.fixture
def context_with_translated(
    context_with_article: FlowContext,
    sample_translated: TranslatedArticle,
) -> FlowContext:
    context_with_article.translated = sample_translated
    return context_with_article


@pytest.fixture
def sample_publish_result() -> PublishResult:
    return PublishResult(success=True, slug="test-article", url="/output/test-article.md")
