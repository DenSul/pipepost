"""Build a Flow from PipePostConfig — config-driven pipeline assembly."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from pipepost.core.registry import get_step_class, register_destination
from pipepost.exceptions import ConfigError


if TYPE_CHECKING:
    from pipepost.config.loader import DestinationConfig, PipePostConfig
    from pipepost.core.flow import Flow
    from pipepost.core.step import Step
    from pipepost.storage.sqlite import SQLiteStorage

logger = logging.getLogger(__name__)


def build_destination_from_config(dest_config: DestinationConfig) -> None:
    """Create a Destination from config and register it under its type name + 'default'."""
    from pipepost.destinations.markdown import MarkdownDestination
    from pipepost.destinations.openclaw import OpenClawDestination
    from pipepost.destinations.telegram import TelegramDestination
    from pipepost.destinations.webhook import WebhookDestination

    dest_type = dest_config.type
    factories = {
        "markdown": lambda: MarkdownDestination(output_dir=dest_config.output_dir),
        "webhook": lambda: WebhookDestination(
            url=dest_config.url,
            headers=dest_config.headers or None,
        ),
        "telegram": lambda: TelegramDestination.from_config(
            {
                "bot_token": dest_config.headers.get("bot_token", ""),
                "chat_id": dest_config.headers.get("chat_id", ""),
            }
        ),
        "openclaw": lambda: OpenClawDestination.from_config(
            {
                "gateway_url": dest_config.url,
            }
        ),
    }

    factory = factories.get(dest_type)
    if not factory:
        raise ConfigError(f"Unknown destination type: {dest_type}")

    dest = factory()
    register_destination(dest_type, dest)
    register_destination("default", dest)
    logger.info("Registered destination '%s' (also as 'default')", dest_type)


def build_flow_from_config(config: PipePostConfig) -> Flow:
    """Construct a Flow instance from the validated PipePostConfig.

    Raises:
        ConfigError: If an unknown step name is encountered.
    """
    from pipepost.core.flow import Flow
    from pipepost.storage.sqlite import SQLiteStorage

    build_destination_from_config(config.destination)

    storage = SQLiteStorage(db_path=config.flow.storage.db_path)

    for step_name in config.flow.steps:
        try:
            get_step_class(step_name)
        except KeyError as exc:
            raise ConfigError(f"Unknown step(s) in flow config: {step_name}") from exc

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
