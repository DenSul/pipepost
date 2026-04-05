"""Pipeline metrics — Prometheus instrumentation (optional dependency)."""

from __future__ import annotations

import logging


logger = logging.getLogger(__name__)

_HAS_PROMETHEUS = True

try:
    from prometheus_client import Counter, Histogram
    from prometheus_client import start_http_server as _start_http_server
except ImportError:
    _HAS_PROMETHEUS = False

# ---------------------------------------------------------------------------
# Metric definitions (created only when prometheus_client is available)
# ---------------------------------------------------------------------------

if _HAS_PROMETHEUS:
    PIPELINE_RUNS_TOTAL = Counter(
        "pipepost_pipeline_runs_total",
        "Total pipeline runs",
        ["flow", "status"],
    )
    STEP_DURATION_SECONDS = Histogram(
        "pipepost_step_duration_seconds",
        "Step execution duration in seconds",
        ["step", "status"],
    )
    STEP_ERRORS_TOTAL = Counter(
        "pipepost_step_errors_total",
        "Total step errors",
        ["step"],
    )
    CANDIDATES_FETCHED_TOTAL = Counter(
        "pipepost_candidates_fetched_total",
        "Total candidates fetched",
        ["source"],
    )
    ARTICLES_PUBLISHED_TOTAL = Counter(
        "pipepost_articles_published_total",
        "Total articles published",
        ["destination"],
    )


class PipelineMetrics:
    """Facade for pipeline Prometheus metrics.

    All methods are safe to call even when ``prometheus_client`` is not
    installed — they degrade to no-ops with a single debug log on first use.
    """

    def __init__(self) -> None:
        self._warned = False

    # -- internal helpers ---------------------------------------------------

    def _noop_warn(self) -> None:
        if not self._warned:
            logger.debug("prometheus_client not installed — metrics disabled")
            self._warned = True

    # -- public API ---------------------------------------------------------

    def record_step(self, step_name: str, duration: float, *, success: bool) -> None:
        """Record step execution duration and optional error."""
        if not _HAS_PROMETHEUS:
            self._noop_warn()
            return
        status = "success" if success else "error"
        STEP_DURATION_SECONDS.labels(step=step_name, status=status).observe(duration)
        if not success:
            STEP_ERRORS_TOTAL.labels(step=step_name).inc()

    def record_pipeline_run(self, flow_name: str, *, success: bool) -> None:
        """Record a completed pipeline run."""
        if not _HAS_PROMETHEUS:
            self._noop_warn()
            return
        status = "success" if success else "error"
        PIPELINE_RUNS_TOTAL.labels(flow=flow_name, status=status).inc()

    def record_candidates(self, source: str, count: int) -> None:
        """Record the number of candidates fetched from a source."""
        if not _HAS_PROMETHEUS:
            self._noop_warn()
            return
        CANDIDATES_FETCHED_TOTAL.labels(source=source).inc(count)

    def record_published(self, destination: str) -> None:
        """Record a successfully published article."""
        if not _HAS_PROMETHEUS:
            self._noop_warn()
            return
        ARTICLES_PUBLISHED_TOTAL.labels(destination=destination).inc()

    def start_http_server(self, port: int = 9090) -> None:
        """Start the Prometheus HTTP exporter."""
        if not _HAS_PROMETHEUS:
            self._noop_warn()
            return
        logger.info("Starting Prometheus metrics server on port %d", port)
        _start_http_server(port)


metrics = PipelineMetrics()
