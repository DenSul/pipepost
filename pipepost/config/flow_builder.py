"""Build a Flow from PipePostConfig — config-driven pipeline assembly."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from pipepost.exceptions import ConfigError


if TYPE_CHECKING:
    from pipepost.config.loader import PipePostConfig
    from pipepost.core.flow import Flow
    from pipepost.core.step import Step
    from pipepost.storage.sqlite import SQLiteStorage

logger = logging.getLogger(__name__)

_KNOWN_STEPS = frozenset(
    {
        "dedup",
        "scout",
        "score",
        "fetch",
        "translate",
        "adapt",
        "validate",
        "publish",
        "fanout_publish",
        "post_publish",
    }
)


def build_flow_from_config(config: PipePostConfig) -> Flow:
    """Construct a Flow instance from the validated PipePostConfig.

    Raises:
        ConfigError: If an unknown step name is encountered.
    """
    from pipepost.core.flow import Flow
    from pipepost.storage.sqlite import SQLiteStorage

    storage = SQLiteStorage(db_path=config.flow.storage.db_path)

    unknown = set(config.flow.steps) - _KNOWN_STEPS
    if unknown:
        raise ConfigError(f"Unknown step(s) in flow config: {', '.join(sorted(unknown))}")

    steps: list[Step] = []
    for step_name in config.flow.steps:
        steps.append(_build_step(step_name, config, storage))

    flow = Flow(
        name="config",
        steps=steps,
        on_error=config.flow.on_error,
    )
    logger.info("Built flow from config: %s", flow)
    return flow


def _build_step(
    step_name: str,
    config: PipePostConfig,
    storage: SQLiteStorage,
) -> Step:
    """Instantiate a single step by name using config values."""
    from pipepost.steps.adapt import AdaptStep
    from pipepost.steps.dedup import DeduplicationStep, PostPublishStep
    from pipepost.steps.fanout import FanoutPublishStep
    from pipepost.steps.fetch import FetchStep
    from pipepost.steps.publish import PublishStep
    from pipepost.steps.score import ScoringStep
    from pipepost.steps.scout import ScoutStep
    from pipepost.steps.translate import TranslateStep
    from pipepost.steps.validate import ValidateStep

    builders: dict[str, Step] = {
        "dedup": DeduplicationStep(storage=storage),
        "scout": ScoutStep(),
        "score": ScoringStep(
            niche=config.flow.score.niche,
            max_score_candidates=config.flow.score.max_score_candidates,
        ),
        "fetch": FetchStep(max_chars=config.fetch.max_chars),
        "translate": TranslateStep(
            model=config.translate.model,
            target_lang=config.translate.target_lang,
        ),
        "adapt": AdaptStep(
            style=config.flow.adapt.style,
            target_lang=config.translate.target_lang,
        ),
        "validate": ValidateStep(
            min_content_len=config.validate_.min_content_len,
            min_ratio=config.validate_.min_ratio,
        ),
        "publish": PublishStep(
            destination_name=config.flow.publish.destination_name,
        ),
        "fanout_publish": FanoutPublishStep(
            destination_names=config.flow.publish.destination_names,
        ),
        "post_publish": PostPublishStep(storage=storage),
    }

    return builders[step_name]
