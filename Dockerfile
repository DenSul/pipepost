# syntax=docker/dockerfile:1
# PipePost — multi-stage build

# ── Build stage ──────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

COPY pyproject.toml README.md ./
COPY pipepost/ pipepost/

RUN pip install --no-cache-dir --prefix=/install .

# ── Runtime stage ────────────────────────────────────────────
FROM python:3.12-slim

LABEL maintainer="Denis Sultanov <denis@denishub.dev>"
LABEL org.opencontainers.image.source="https://github.com/DenSul/pipepost"
LABEL org.opencontainers.image.licenses="AGPL-3.0"

# Non-root user
RUN groupadd --gid 1000 pipepost \
    && useradd --uid 1000 --gid 1000 --create-home pipepost

COPY --from=builder /install /usr/local

WORKDIR /app
# Default config mount point
VOLUME ["/app/config"]

USER pipepost

ENTRYPOINT ["pipepost"]
CMD ["health"]
