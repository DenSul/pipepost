"""Core context — Candidate dataclass for pipeline items."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Candidate:
    """A content candidate discovered by a source."""

    url: str
    title: str = ""
    snippet: str = ""
    score: float = 0.0
    source_name: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
