"""Tests for FlowContext and data models."""

from __future__ import annotations

from pipepost.core.context import (
    Article,
    Candidate,
    FlowContext,
    PublishResult,
    TranslatedArticle,
)


class TestCandidate:
    def test_creation_defaults(self):
        c = Candidate(url="https://x.com", title="T")
        assert c.snippet == ""
        assert c.score == 0.0
        assert c.source_name == ""
        assert c.metadata == {}

    def test_creation_full(self):
        c = Candidate(
            url="https://x.com",
            title="Title",
            snippet="Snip",
            score=99.0,
            source_name="hn",
            metadata={"k": "v"},
        )
        assert c.url == "https://x.com"
        assert c.score == 99.0
        assert c.metadata == {"k": "v"}

    def test_metadata_isolation(self):
        """Each instance gets its own metadata dict."""
        a = Candidate(url="a", title="a")
        b = Candidate(url="b", title="b")
        a.metadata["x"] = 1
        assert "x" not in b.metadata


class TestArticle:
    def test_creation(self):
        a = Article(url="https://x.com", title="T", content="body")
        assert a.cover_image is None
        assert a.metadata == {}

    def test_cover_image(self):
        a = Article(url="u", title="t", content="c", cover_image="https://img.png")
        assert a.cover_image == "https://img.png"


class TestTranslatedArticle:
    def test_creation(self):
        t = TranslatedArticle(
            title="Orig",
            title_translated="Перевод",
            content="english",
            content_translated="русский",
            source_url="https://x.com",
        )
        assert t.source_name == ""
        assert t.tags == []
        assert t.cover_image is None

    def test_tags_default_factory(self):
        a = TranslatedArticle(
            title="a",
            title_translated="б",
            content="c",
            content_translated="д",
            source_url="u",
        )
        b = TranslatedArticle(
            title="x",
            title_translated="y",
            content="z",
            content_translated="w",
            source_url="u2",
        )
        a.tags.append("python")
        assert "python" not in b.tags


class TestPublishResult:
    def test_success(self):
        r = PublishResult(success=True, slug="my-post", url="/out/my-post.md")
        assert r.success is True
        assert r.error == ""

    def test_failure(self):
        r = PublishResult(success=False, error="timeout")
        assert r.success is False
        assert r.slug == ""


class TestFlowContext:
    def test_empty_context(self):
        ctx = FlowContext()
        assert ctx.candidates == []
        assert ctx.articles == []
        assert ctx.selected is None
        assert ctx.translated is None
        assert ctx.published is None
        assert ctx.errors == []
        assert ctx.target_lang == "ru"
        assert ctx.existing_urls == set()

    def test_add_error(self):
        ctx = FlowContext()
        assert not ctx.has_errors
        ctx.add_error("boom")
        assert ctx.has_errors
        assert ctx.errors == ["boom"]

    def test_multiple_errors(self):
        ctx = FlowContext()
        ctx.add_error("err1")
        ctx.add_error("err2")
        assert len(ctx.errors) == 2
        assert ctx.has_errors

    def test_has_errors_property(self):
        ctx = FlowContext()
        assert ctx.has_errors is False
        ctx.errors.append("direct")
        assert ctx.has_errors is True

    def test_existing_urls_set(self):
        ctx = FlowContext(existing_urls={"https://a.com", "https://b.com"})
        assert "https://a.com" in ctx.existing_urls
        assert "https://c.com" not in ctx.existing_urls

    def test_metadata_default_factory(self):
        ctx1 = FlowContext()
        ctx2 = FlowContext()
        ctx1.metadata["key"] = "val"
        assert "key" not in ctx2.metadata

    def test_source_name_default(self):
        ctx = FlowContext()
        assert ctx.source_name == ""

    def test_source_name_custom(self):
        ctx = FlowContext(source_name="reddit")
        assert ctx.source_name == "reddit"

    def test_target_lang_custom(self):
        ctx = FlowContext(target_lang="es")
        assert ctx.target_lang == "es"

    def test_candidates_isolation(self):
        ctx1 = FlowContext()
        ctx2 = FlowContext()
        ctx1.candidates.append(Candidate(url="u", title="t"))
        assert len(ctx2.candidates) == 0

    def test_errors_isolation(self):
        ctx1 = FlowContext()
        ctx2 = FlowContext()
        ctx1.add_error("oops")
        assert not ctx2.has_errors


class TestTranslatedArticleMetadata:
    def test_metadata_isolation(self):
        a = TranslatedArticle(
            title="a",
            title_translated="b",
            content="c",
            content_translated="d",
            source_url="u",
        )
        b = TranslatedArticle(
            title="x",
            title_translated="y",
            content="z",
            content_translated="w",
            source_url="u2",
        )
        a.metadata["key"] = "val"
        assert "key" not in b.metadata


class TestArticleMetadata:
    def test_metadata_isolation(self):
        a = Article(url="u1", title="t1", content="c1")
        b = Article(url="u2", title="t2", content="c2")
        a.metadata["key"] = "val"
        assert "key" not in b.metadata
