"""Score and rank content candidates using LLM."""

from __future__ import annotations

import json
import logging
import os
import re
from typing import TYPE_CHECKING

from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter

from pipepost.core.registry import register_step
from pipepost.core.step import Step


if TYPE_CHECKING:
    from pipepost.core.context import Candidate, FlowContext

logger = logging.getLogger(__name__)


class ScoringStep(Step):
    """Use LLM to score and rank content candidates by relevance and quality."""

    name = "score"

    def __init__(
        self,
        model: str | None = None,
        max_score_candidates: int = 5,
        niche: str = "general",
    ) -> None:
        self.model = model or os.getenv("PIPEPOST_MODEL", "deepseek/deepseek-chat")
        self.max_score_candidates = max_score_candidates
        self.niche = niche

    def should_skip(self, ctx: FlowContext) -> bool:
        """Skip if no candidates or only one candidate (nothing to rank)."""
        return len(ctx.candidates) <= 1

    async def execute(self, ctx: FlowContext) -> FlowContext:
        """Score candidates via LLM and reorder by score descending."""
        candidates = ctx.candidates[: self.max_score_candidates]
        prompt = self._build_scoring_prompt(candidates)

        try:
            raw = await self._call_llm(prompt)
            scores = self._parse_scores(raw, len(candidates))
        except Exception as exc:
            logger.warning("LLM scoring failed, keeping original order: %s", exc)
            return ctx

        if not scores:
            logger.warning("Could not parse scores, keeping original order")
            return ctx

        # Build a mapping of index -> score
        score_map: dict[int, float] = {}
        for idx, score_val in scores:
            if 0 <= idx < len(candidates):
                score_map[idx] = score_val

        # Update candidate scores
        for idx, score_val in score_map.items():
            candidates[idx].score = score_val

        # Sort scored candidates by score descending
        scored_indices = sorted(score_map, key=lambda i: score_map[i], reverse=True)
        scored_candidates = [candidates[i] for i in scored_indices]

        # Add any candidates that weren't scored (keep original order)
        scored_set = set(scored_indices)
        unscored_from_batch = [candidates[i] for i in range(len(candidates)) if i not in scored_set]
        remaining = ctx.candidates[self.max_score_candidates :]

        ctx.candidates = scored_candidates + unscored_from_batch + remaining

        logger.info(
            "Scored %d candidates. Top: %s (score=%.0f)",
            len(scored_candidates),
            ctx.candidates[0].title if ctx.candidates else "N/A",
            ctx.candidates[0].score if ctx.candidates else 0,
        )

        return ctx

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=1, max=10),
        retry=retry_if_exception_type(Exception),
        reraise=True,
        before_sleep=lambda rs: logger.warning(
            "LLM scoring attempt %d failed: %s — retrying",
            rs.attempt_number,
            rs.outcome.exception(),
        ),
    )
    async def _call_llm(self, prompt: str) -> str:
        """Call LLM for scoring with tenacity retry and exponential backoff."""
        import litellm

        response = await litellm.acompletion(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2048,
            temperature=0.2,
        )
        return str(response.choices[0].message.content or "")

    def _build_scoring_prompt(self, candidates: list[Candidate]) -> str:
        """Build a prompt asking the LLM to score candidates."""
        lines = []
        for i, c in enumerate(candidates, start=1):
            lines.append(f'{i}. "{c.title}" \u2014 {c.url}')
        candidate_list = "\n".join(lines)

        return (
            f"You are a content curator for a {self.niche} publication.\n"
            "Score these article candidates from 0-100 based on:\n"
            f"- Relevance to {self.niche} audience\n"
            "- Originality and freshness\n"
            "- Engagement potential\n"
            "- Quality of source\n\n"
            "Candidates:\n"
            f"{candidate_list}\n\n"
            "Respond with ONLY a JSON array:\n"
            '[{"index": 1, "score": 85, "reason": "Highly relevant..."}, ...]'
        )

    def _parse_scores(self, raw: str, count: int) -> list[tuple[int, float]]:
        """Parse JSON scores from LLM response.

        Returns list of (zero-based index, score) tuples.
        Returns empty list on parse failure.
        """
        # Strip markdown code blocks
        cleaned = re.sub(r"```(?:json)?\s*", "", raw)
        cleaned = re.sub(r"```", "", cleaned)
        cleaned = cleaned.strip()

        try:
            data = json.loads(cleaned)
        except (json.JSONDecodeError, ValueError):
            return []

        if not isinstance(data, list):
            return []

        results: list[tuple[int, float]] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            idx = item.get("index")
            score = item.get("score")
            if idx is None or score is None:
                continue
            try:
                # Convert 1-based index from prompt to 0-based
                zero_idx = int(idx) - 1
                score_val = float(score)
            except (TypeError, ValueError):
                continue
            if 0 <= zero_idx < count:
                results.append((zero_idx, score_val))

        return results


register_step("score", ScoringStep)
