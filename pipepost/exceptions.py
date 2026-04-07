"""PipePost exception hierarchy."""

from __future__ import annotations


class PipePostError(Exception):
    """Base exception for all PipePost errors."""


class SourceError(PipePostError):
    """Error during content source operations (fetch candidates, parse feeds)."""


class FetchError(PipePostError):
    """Error during article fetching (HTTP errors, parsing failures)."""


class TranslateError(PipePostError):
    """Error during LLM translation (API failures, parse errors)."""


class RewriteError(PipePostError):
    """Error during LLM content rewriting (API failures, parse errors)."""


class PublishError(PipePostError):
    """Error during article publishing (destination failures)."""


class ConfigError(PipePostError):
    """Error in configuration loading or validation."""


class ValidationError(PipePostError):
    """Error during article quality validation."""
