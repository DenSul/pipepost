"""Tests for PipePost exception hierarchy."""

from __future__ import annotations

import pytest

from pipepost.exceptions import (
    ConfigError,
    FetchError,
    PipePostError,
    PublishError,
    SourceError,
    TranslateError,
    ValidationError,
)


class TestExceptionHierarchy:
    """All custom exceptions should inherit from PipePostError."""

    @pytest.mark.parametrize(
        "exc_cls",
        [SourceError, FetchError, TranslateError, PublishError, ConfigError, ValidationError],
    )
    def test_inherits_from_pipepost_error(self, exc_cls: type[Exception]):
        assert issubclass(exc_cls, PipePostError)

    @pytest.mark.parametrize(
        "exc_cls",
        [SourceError, FetchError, TranslateError, PublishError, ConfigError, ValidationError],
    )
    def test_inherits_from_exception(self, exc_cls: type[Exception]):
        assert issubclass(exc_cls, Exception)

    def test_pipepost_error_is_base(self):
        assert issubclass(PipePostError, Exception)


class TestExceptionInstantiation:
    @pytest.mark.parametrize(
        "exc_cls",
        [
            PipePostError,
            SourceError,
            FetchError,
            TranslateError,
            PublishError,
            ConfigError,
            ValidationError,
        ],
    )
    def test_can_create_with_message(self, exc_cls: type[Exception]):
        exc = exc_cls("something went wrong")
        assert str(exc) == "something went wrong"

    @pytest.mark.parametrize(
        "exc_cls",
        [
            PipePostError,
            SourceError,
            FetchError,
            TranslateError,
            PublishError,
            ConfigError,
            ValidationError,
        ],
    )
    def test_can_create_without_message(self, exc_cls: type[Exception]):
        exc = exc_cls()
        assert str(exc) == ""

    @pytest.mark.parametrize(
        "exc_cls",
        [SourceError, FetchError, TranslateError, PublishError, ConfigError, ValidationError],
    )
    def test_catchable_as_pipepost_error(self, exc_cls: type[Exception]):
        with pytest.raises(PipePostError):
            raise exc_cls("test")

    @pytest.mark.parametrize(
        "exc_cls",
        [SourceError, FetchError, TranslateError, PublishError, ConfigError, ValidationError],
    )
    def test_catchable_as_exception(self, exc_cls: type[Exception]):
        with pytest.raises(Exception):
            raise exc_cls("test")


class TestExceptionChaining:
    def test_fetch_error_from_cause(self):
        cause = ConnectionError("network down")
        exc = FetchError("fetch failed")
        exc.__cause__ = cause
        assert exc.__cause__ is cause

    def test_raise_from_preserves_chain(self):
        with pytest.raises(TranslateError) as exc_info:
            try:
                raise RuntimeError("API timeout")
            except RuntimeError as e:
                raise TranslateError("LLM call failed") from e
        assert exc_info.value.__cause__ is not None
        assert isinstance(exc_info.value.__cause__, RuntimeError)
