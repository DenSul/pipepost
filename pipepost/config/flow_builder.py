"""Build a Flow from PipePostConfig — config-driven pipeline assembly."""

from __future__ import annotations

import contextlib
import logging
from typing import TYPE_CHECKING

from pipepost.core.registry import (
    get_destination,
    get_step_class,
    register_destination,
    register_source,
)
from pipepost.exceptions import ConfigError


if TYPE_CHECKING:
    from pipepost.config.loader import DestinationConfig, PipePostConfig, SourceConfig
    from pipepost.core.flow import Flow
    from pipepost.core.step import Step
    from pipepost.destinations.base import Destination
    from pipepost.sources.base import Source
    from pipepost.storage.sqlite import SQLiteStorage

logger = logging.getLogger(__name__)


def build_destination_from_config(dest_config: DestinationConfig) -> None:
    """Create a Destination from config and register it under its type name + 'default'."""
    from pipepost.config.loader import (
        MarkdownDestinationConfig,
        OpenClawDestinationConfig,
        TelegramDestinationConfig,
        WebhookDestinationConfig,
    )
    from pipepost.destinations.markdown import MarkdownDestination
    from pipepost.destinations.openclaw import OpenClawDestination
    from pipepost.destinations.telegram import TelegramDestination
    from pipepost.destinations.webhook import WebhookDestination

    dest: Destination
    if isinstance(dest_config, MarkdownDestinationConfig):
        dest = MarkdownDestination(output_dir=dest_config.output_dir)
    elif isinstance(dest_config, WebhookDestinationConfig):
        dest = WebhookDestination(
            url=dest_config.url,
            headers=dest_config.headers or None,
        )
    elif isinstance(dest_config, TelegramDestinationConfig):
        dest = TelegramDestination(
            bot_token=dest_config.bot_token,
            chat_id=dest_config.chat_id,
            parse_mode=dest_config.parse_mode,
        )
    elif isinstance(dest_config, OpenClawDestinationConfig):
        dest = OpenClawDestination(
            gateway_url=dest_config.gateway_url,
            session_id=dest_config.session_id,
            channels=dest_config.channels or None,
        )
    else:
        raise ConfigError(f"Unknown destination type: {dest_config.type}")

    register_destination(dest_config.type, dest)
    register_destination("default", dest)
    logger.info("Registered destination '%s' (also as 'default')", dest_config.type)


_SOURCE_TYPE_MAP: dict[str, str] = {
    "hackernews": "pipepost.sources.hackernews.HackerNewsSource",
    "api": "pipepost.sources.hackernews.HackerNewsSource",
    "rss": "pipepost.sources.rss.RSSSource",
    "reddit": "pipepost.sources.reddit.RedditSource",
    "search": "pipepost.sources.search.SearchSource",
}


def _build_source_from_config(src_config: SourceConfig) -> Source:
    """Instantiate a Source from a SourceConfig using its from_config() classmethod."""
    import importlib

    source_type = src_config.type
    class_path = _SOURCE_TYPE_MAP.get(source_type)
    if class_path is None:
        raise ConfigError(f"Unknown source type: {source_type!r}")

    module_path, class_name = class_path.rsplit(".", 1)
    module = importlib.import_module(module_path)
    source_cls = getattr(module, class_name)

    config_dict: dict[str, object] = src_config.model_dump()
    return source_cls.from_config(config_dict)  # type: ignore[no-any-return]


def register_sources_from_config(sources: list[SourceConfig]) -> None:
    """Create and register sources defined in YAML config.

    Config-defined sources override any auto-discovered defaults with the same
    name, so that user customisation (custom URLs, queries, subreddits, etc.)
    takes effect.
    """
    for src_config in sources:
        source = _build_source_from_config(src_config)
        register_source(src_config.name, source)
        logger.info("Registered config source '%s' (type=%s)", src_config.name, src_config.type)


def build_flow_from_config(config: PipePostConfig) -> Flow:
    """Construct a Flow instance from the validated PipePostConfig.

    Raises:
        ConfigError: If an unknown step name is encountered.
    """
    from pipepost.core.flow import Flow
    from pipepost.storage.sqlite import SQLiteStorage

    # Register sources from config before building steps (overrides defaults).
    if config.sources:
        register_sources_from_config(config.sources)

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
    """Instantiate a single step by name using config values.

    Resolves the step class from the registry, then delegates construction
    to ``StepClass.from_config(build_ctx)`` so each step picks only the
    config fields it needs.
    """
    from pipepost.core.step import StepBuildContext

    # Eagerly resolve destinations when possible; fall back to None for lazy lookup.
    try:
        resolved_dest: Destination | None = get_destination(
            config.flow.publish.destination_name,
        )
    except KeyError:
        resolved_dest = None

    resolved_fanout: dict[str, Destination] | None = None
    if config.flow.publish.destination_names:
        resolved_fanout = {}
        for _dn in config.flow.publish.destination_names:
            with contextlib.suppress(KeyError):
                resolved_fanout[_dn] = get_destination(_dn)
        if not resolved_fanout:
            resolved_fanout = None

    build_ctx = StepBuildContext(
        storage=storage,
        model=config.translate.model,
        target_lang=config.translate.target_lang,
        max_tokens=config.translate.max_tokens,
        max_chars=config.fetch.max_chars,
        fetch_timeout=config.fetch.timeout,
        score_model=config.flow.score.model,
        niche=config.flow.score.niche,
        max_score_candidates=config.flow.score.max_score_candidates,
        adapt_model=config.flow.adapt.model,
        style=config.flow.adapt.style,
        rewrite_model=config.rewrite.model,
        rewrite_creativity=config.rewrite.creativity,
        transform_model=config.transform.model,
        transform_translate=config.transform.translate,
        transform_rewrite=config.transform.rewrite,
        transform_adapt=config.transform.adapt,
        transform_style=config.transform.style,
        transform_creativity=config.transform.creativity,
        min_content_len=config.validate_.min_content_len,
        min_ratio=config.validate_.min_ratio,
        filter_keywords_include=config.flow.filter.keywords_include,
        filter_keywords_exclude=config.flow.filter.keywords_exclude,
        filter_domain_blacklist=config.flow.filter.domain_blacklist,
        filter_min_title_length=config.flow.filter.min_title_length,
        destination_name=config.flow.publish.destination_name,
        destination_names=config.flow.publish.destination_names,
        destination=resolved_dest,
        destinations=resolved_fanout,
    )

    step_cls = get_step_class(step_name)
    return step_cls.from_config(build_ctx)
