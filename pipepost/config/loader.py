"""YAML config loading with Pydantic validation and multi-layer merge."""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from pipepost.exceptions import ConfigError


logger = logging.getLogger(__name__)

_DEFAULT_CONFIG_PATHS = [
    Path("pipepost.yaml"),
    Path("pipepost.yml"),
    Path.home() / ".config" / "pipepost" / "pipepost.yaml",
]


class SourceConfig(BaseModel):
    """Configuration for a single content source."""

    name: str
    type: str = "rss"
    url: str = ""
    queries: list[str] = Field(default_factory=list)
    subreddits: list[str] = Field(default_factory=list)
    min_score: int = 50
    max_items: int = 20


class DestinationConfig(BaseModel):
    """Configuration for the publish destination."""

    type: str = "markdown"
    url: str = ""
    output_dir: str = "./output"
    headers: dict[str, str] = Field(default_factory=dict)


class TranslateConfig(BaseModel):
    """Configuration for the translation step."""

    model: str = "deepseek/deepseek-chat"
    target_lang: str = "ru"
    max_tokens: int = 16384
    min_ratio: float = 0.5


class FetchConfig(BaseModel):
    """Configuration for the fetch step."""

    max_chars: int = 20000
    timeout: float = 30.0


class ValidateConfig(BaseModel):
    """Configuration for the validation step."""

    min_content_len: int = 300
    min_ratio: float = 0.3


class ScoreConfig(BaseModel):
    """Configuration for the scoring step."""

    niche: str = "general"
    max_score_candidates: int = 5


class AdaptConfig(BaseModel):
    """Configuration for the adapt step."""

    style: str = "blog"


class PublishFlowConfig(BaseModel):
    """Configuration for publish/fanout steps within a flow."""

    destination_name: str = "default"
    destination_names: list[str] = Field(default_factory=list)


class StorageConfig(BaseModel):
    """Configuration for pipeline storage."""

    db_path: str = "pipepost.db"


class FlowConfig(BaseModel):
    """Configuration for a pipeline flow — step ordering and step-specific settings."""

    steps: list[str] = Field(
        default_factory=lambda: [
            "dedup",
            "scout",
            "fetch",
            "translate",
            "validate",
            "publish",
            "post_publish",
        ]
    )
    on_error: str = "stop"
    score: ScoreConfig = Field(default_factory=ScoreConfig)
    adapt: AdaptConfig = Field(default_factory=AdaptConfig)
    publish: PublishFlowConfig = Field(default_factory=PublishFlowConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)


class PipePostConfig(BaseModel):
    """Root configuration schema for PipePost."""

    sources: list[SourceConfig] = Field(default_factory=list)
    destination: DestinationConfig = Field(default_factory=DestinationConfig)
    translate: TranslateConfig = Field(default_factory=TranslateConfig)
    fetch: FetchConfig = Field(default_factory=FetchConfig)
    validate_: ValidateConfig = Field(default_factory=ValidateConfig, alias="validate")
    flow: FlowConfig = Field(default_factory=FlowConfig)
    verbose: bool = False

    model_config = {"populate_by_name": True}


def resolve_env_vars(data: object) -> object:
    """Recursively resolve ``${VAR_NAME}`` references in config values.

    Any string containing ``${VAR_NAME}`` will have that token replaced with the
    value of the corresponding environment variable (or an empty string if unset).
    """
    if isinstance(data, str):
        return re.sub(
            r"\$\{([^}]+)\}", lambda m: os.environ.get(m.group(1), ""), data
        )
    if isinstance(data, dict):
        return {k: resolve_env_vars(v) for k, v in data.items()}
    if isinstance(data, list):
        return [resolve_env_vars(item) for item in data]
    return data


def _find_config_file(explicit_path: str | None = None) -> Path | None:
    """Find the config file — explicit path, env var, or default locations."""
    if explicit_path:
        path = Path(explicit_path)
        if path.is_file():
            return path
        raise ConfigError(f"Config file not found: {explicit_path}")

    env_path = os.getenv("PIPEPOST_CONFIG")
    if env_path:
        path = Path(env_path)
        if path.is_file():
            return path
        raise ConfigError(f"Config file from PIPEPOST_CONFIG not found: {env_path}")

    for candidate in _DEFAULT_CONFIG_PATHS:
        if candidate.is_file():
            return candidate

    return None


def _load_yaml(path: Path) -> dict[str, Any]:
    """Load and parse a YAML file."""
    try:
        with path.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
            if data is None:
                return {}
            if not isinstance(data, dict):
                raise ConfigError(f"Config file must be a YAML mapping: {path}")
            return data
    except yaml.YAMLError as exc:
        raise ConfigError(f"Invalid YAML in {path}: {exc}") from exc


def _apply_env_overrides(data: dict[str, Any]) -> dict[str, Any]:
    """Apply environment variable overrides (highest priority after CLI)."""
    env_model = os.getenv("PIPEPOST_MODEL")
    if env_model:
        data.setdefault("translate", {})
        data["translate"]["model"] = env_model

    env_lang = os.getenv("PIPEPOST_LANG")
    if env_lang:
        data.setdefault("translate", {})
        data["translate"]["target_lang"] = env_lang

    env_dest_url = os.getenv("PIPEPOST_DEST_URL")
    if env_dest_url:
        data.setdefault("destination", {})
        data["destination"]["url"] = env_dest_url
        if "type" not in data.get("destination", {}):
            data["destination"]["type"] = "webhook"

    return data


def load_config(
    config_path: str | None = None,
    cli_overrides: dict[str, Any] | None = None,
) -> PipePostConfig:
    """Load config with merge priority: CLI args > env vars > YAML > defaults.

    Args:
        config_path: Explicit path to config file. None = auto-detect.
        cli_overrides: Dict of CLI argument overrides.

    Returns:
        Validated PipePostConfig.

    Raises:
        ConfigError: If config file is invalid or not found when explicitly specified.
    """
    # 1. Load YAML (or empty dict)
    yaml_path = _find_config_file(config_path)
    data: dict[str, Any] = {}
    if yaml_path:
        data = _load_yaml(yaml_path)
        logger.info("Loaded config from %s", yaml_path)

    # 1b. Resolve ${ENV_VAR} references in values
    data = resolve_env_vars(data)  # type: ignore[assignment]

    # 2. Apply env var overrides
    data = _apply_env_overrides(data)

    # 3. Apply CLI overrides (highest priority)
    if cli_overrides:
        for key, value in cli_overrides.items():
            if value is not None:
                _deep_set(data, key, value)

    # 4. Validate via Pydantic
    try:
        return PipePostConfig.model_validate(data)
    except Exception as exc:
        raise ConfigError(f"Config validation failed: {exc}") from exc


def _deep_set(data: dict[str, Any], key: str, value: Any) -> None:
    """Set a potentially nested key (e.g. 'translate.model')."""
    parts = key.split(".")
    target = data
    for part in parts[:-1]:
        target = target.setdefault(part, {})
    target[parts[-1]] = value
