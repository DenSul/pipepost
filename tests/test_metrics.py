"""Tests for the Prometheus metrics module."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from prometheus_client import CollectorRegistry

import pipepost.metrics as metrics_mod
from pipepost.metrics import PipelineMetrics


@pytest.fixture(autouse=True)
def _fresh_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace global metrics with fresh ones per test to avoid duplicates."""
    registry = CollectorRegistry()
    from prometheus_client import Counter, Histogram

    monkeypatch.setattr(
        metrics_mod,
        "PIPELINE_RUNS_TOTAL",
        Counter("pipepost_pipeline_runs_total", "runs", ["flow", "status"], registry=registry),
    )
    monkeypatch.setattr(
        metrics_mod,
        "STEP_DURATION_SECONDS",
        Histogram("pipepost_step_duration_seconds", "dur", ["step", "status"], registry=registry),
    )
    monkeypatch.setattr(
        metrics_mod,
        "STEP_ERRORS_TOTAL",
        Counter("pipepost_step_errors_total", "errs", ["step"], registry=registry),
    )
    monkeypatch.setattr(
        metrics_mod,
        "CANDIDATES_FETCHED_TOTAL",
        Counter("pipepost_candidates_fetched_total", "cands", ["source"], registry=registry),
    )
    monkeypatch.setattr(
        metrics_mod,
        "ARTICLES_PUBLISHED_TOTAL",
        Counter("pipepost_articles_published_total", "pubs", ["destination"], registry=registry),
    )


def test_metrics_no_op_without_prometheus(monkeypatch: pytest.MonkeyPatch) -> None:
    """When prometheus_client is unavailable, methods must not raise."""
    monkeypatch.setattr(metrics_mod, "_HAS_PROMETHEUS", False)
    m = PipelineMetrics()

    # None of these should raise
    m.record_step("fetch", 1.0, success=True)
    m.record_step("translate", 0.5, success=False)
    m.record_pipeline_run("default", success=True)
    m.record_candidates("rss", 5)
    m.record_published("webhook")
    m.start_http_server(9999)


def test_record_step_success() -> None:
    m = PipelineMetrics()
    m.record_step("fetch", 1.23, success=True)

    val = metrics_mod.STEP_DURATION_SECONDS.labels(step="fetch", status="success")._sum.get()
    assert val == pytest.approx(1.23)
    # errors counter should not be incremented
    assert metrics_mod.STEP_ERRORS_TOTAL.labels(step="fetch")._value.get() == 0


def test_record_step_error() -> None:
    m = PipelineMetrics()
    m.record_step("translate", 0.5, success=False)

    val = metrics_mod.STEP_DURATION_SECONDS.labels(step="translate", status="error")._sum.get()
    assert val == pytest.approx(0.5)
    assert metrics_mod.STEP_ERRORS_TOTAL.labels(step="translate")._value.get() == 1


def test_record_pipeline_run() -> None:
    m = PipelineMetrics()
    m.record_pipeline_run("default", success=True)
    m.record_pipeline_run("default", success=False)

    success_val = metrics_mod.PIPELINE_RUNS_TOTAL.labels(
        flow="default", status="success"
    )._value.get()
    error_val = metrics_mod.PIPELINE_RUNS_TOTAL.labels(flow="default", status="error")._value.get()
    assert success_val == 1
    assert error_val == 1


def test_record_candidates() -> None:
    m = PipelineMetrics()
    m.record_candidates("hackernews", 10)

    assert metrics_mod.CANDIDATES_FETCHED_TOTAL.labels(source="hackernews")._value.get() == 10


def test_record_published() -> None:
    m = PipelineMetrics()
    m.record_published("markdown")

    assert metrics_mod.ARTICLES_PUBLISHED_TOTAL.labels(destination="markdown")._value.get() == 1


def test_start_http_server() -> None:
    m = PipelineMetrics()
    with patch.object(metrics_mod, "_start_http_server") as mock_start:
        m.start_http_server(9191)
        mock_start.assert_called_once_with(9191)
