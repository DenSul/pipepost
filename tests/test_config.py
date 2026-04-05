"""Tests for config loader — YAML parsing, env var merge, Pydantic validation."""

from __future__ import annotations

import pytest

from pipepost.config.loader import (
    AdaptConfig,
    DestinationConfig,
    FetchConfig,
    FlowConfig,
    PipePostConfig,
    PublishFlowConfig,
    ScoreConfig,
    SourceConfig,
    StorageConfig,
    TranslateConfig,
    ValidateConfig,
    _apply_env_overrides,
    _deep_set,
    _find_config_file,
    _load_yaml,
    load_config,
    resolve_env_vars,
)
from pipepost.exceptions import ConfigError


class TestPipePostConfigDefaults:
    def test_empty_config_has_defaults(self):
        cfg = PipePostConfig()
        assert cfg.sources == []
        assert cfg.destination.type == "markdown"
        assert cfg.translate.model == "deepseek/deepseek-chat"
        assert cfg.translate.target_lang == "ru"
        assert cfg.fetch.max_chars == 20000
        assert cfg.validate_.min_content_len == 300
        assert cfg.verbose is False

    def test_source_config_defaults(self):
        src = SourceConfig(name="test")
        assert src.type == "rss"
        assert src.url == ""
        assert src.queries == []
        assert src.subreddits == []
        assert src.min_score == 50
        assert src.max_items == 20

    def test_destination_config_defaults(self):
        dest = DestinationConfig()
        assert dest.type == "markdown"
        assert dest.output_dir == "./output"
        assert dest.headers == {}

    def test_translate_config_defaults(self):
        tr = TranslateConfig()
        assert tr.model == "deepseek/deepseek-chat"
        assert tr.target_lang == "ru"
        assert tr.max_tokens == 16384
        assert tr.min_ratio == 0.5

    def test_fetch_config_defaults(self):
        fc = FetchConfig()
        assert fc.max_chars == 20000
        assert fc.timeout == 30.0

    def test_validate_config_defaults(self):
        vc = ValidateConfig()
        assert vc.min_content_len == 300
        assert vc.min_ratio == 0.3


class TestPipePostConfigValidation:
    def test_valid_config_from_dict(self):
        data = {
            "sources": [{"name": "tech-rss", "type": "rss", "url": "https://feed.example.com"}],
            "destination": {"type": "webhook", "url": "https://api.example.com"},
            "translate": {"model": "gpt-4", "target_lang": "es"},
        }
        cfg = PipePostConfig.model_validate(data)
        assert len(cfg.sources) == 1
        assert cfg.sources[0].name == "tech-rss"
        assert cfg.destination.type == "webhook"
        assert cfg.translate.model == "gpt-4"

    def test_validate_alias_works(self):
        data = {"validate": {"min_content_len": 500, "min_ratio": 0.4}}
        cfg = PipePostConfig.model_validate(data)
        assert cfg.validate_.min_content_len == 500
        assert cfg.validate_.min_ratio == 0.4

    def test_multiple_sources(self):
        data = {
            "sources": [
                {"name": "hn", "type": "hackernews", "min_score": 100},
                {"name": "reddit", "type": "reddit", "subreddits": ["python", "rust"]},
            ],
        }
        cfg = PipePostConfig.model_validate(data)
        assert len(cfg.sources) == 2
        assert cfg.sources[1].subreddits == ["python", "rust"]


class TestLoadYaml:
    def test_loads_valid_yaml(self, tmp_path):
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text("translate:\n  model: gpt-4\n  target_lang: fr\n", encoding="utf-8")
        data = _load_yaml(yaml_file)
        assert data["translate"]["model"] == "gpt-4"
        assert data["translate"]["target_lang"] == "fr"

    def test_empty_yaml_returns_empty_dict(self, tmp_path):
        yaml_file = tmp_path / "empty.yaml"
        yaml_file.write_text("", encoding="utf-8")
        data = _load_yaml(yaml_file)
        assert data == {}

    def test_invalid_yaml_raises_config_error(self, tmp_path):
        yaml_file = tmp_path / "bad.yaml"
        yaml_file.write_text("{{invalid: yaml: [}", encoding="utf-8")
        with pytest.raises(ConfigError, match="Invalid YAML"):
            _load_yaml(yaml_file)

    def test_non_dict_yaml_raises_config_error(self, tmp_path):
        yaml_file = tmp_path / "list.yaml"
        yaml_file.write_text("- item1\n- item2\n", encoding="utf-8")
        with pytest.raises(ConfigError, match="YAML mapping"):
            _load_yaml(yaml_file)


class TestFindConfigFile:
    def test_explicit_path_found(self, tmp_path):
        cfg = tmp_path / "custom.yaml"
        cfg.write_text("verbose: true\n", encoding="utf-8")
        result = _find_config_file(str(cfg))
        assert result == cfg

    def test_explicit_path_missing_raises(self, tmp_path):
        with pytest.raises(ConfigError, match="not found"):
            _find_config_file(str(tmp_path / "nonexistent.yaml"))

    def test_env_var_path(self, tmp_path, monkeypatch):
        cfg = tmp_path / "env.yaml"
        cfg.write_text("verbose: true\n", encoding="utf-8")
        monkeypatch.setenv("PIPEPOST_CONFIG", str(cfg))
        result = _find_config_file()
        assert result == cfg

    def test_env_var_missing_file_raises(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PIPEPOST_CONFIG", str(tmp_path / "ghost.yaml"))
        with pytest.raises(ConfigError, match="PIPEPOST_CONFIG"):
            _find_config_file()

    def test_no_config_returns_none(self, monkeypatch, tmp_path):
        monkeypatch.delenv("PIPEPOST_CONFIG", raising=False)
        monkeypatch.chdir(tmp_path)
        result = _find_config_file()
        assert result is None


class TestApplyEnvOverrides:
    def test_model_override(self, monkeypatch):
        monkeypatch.setenv("PIPEPOST_MODEL", "claude-3-opus")
        data = _apply_env_overrides({})
        assert data["translate"]["model"] == "claude-3-opus"

    def test_lang_override(self, monkeypatch):
        monkeypatch.setenv("PIPEPOST_LANG", "de")
        data = _apply_env_overrides({})
        assert data["translate"]["target_lang"] == "de"

    def test_dest_url_override_sets_webhook_type(self, monkeypatch):
        monkeypatch.setenv("PIPEPOST_DEST_URL", "https://api.example.com")
        data = _apply_env_overrides({})
        assert data["destination"]["url"] == "https://api.example.com"
        assert data["destination"]["type"] == "webhook"

    def test_dest_url_preserves_existing_type(self, monkeypatch):
        monkeypatch.setenv("PIPEPOST_DEST_URL", "https://api.example.com")
        data = {"destination": {"type": "custom"}}
        data = _apply_env_overrides(data)
        assert data["destination"]["type"] == "custom"

    def test_no_env_vars_no_changes(self, monkeypatch):
        monkeypatch.delenv("PIPEPOST_MODEL", raising=False)
        monkeypatch.delenv("PIPEPOST_LANG", raising=False)
        monkeypatch.delenv("PIPEPOST_DEST_URL", raising=False)
        data = {"translate": {"model": "original"}}
        result = _apply_env_overrides(data)
        assert result["translate"]["model"] == "original"


class TestDeepSet:
    def test_simple_key(self):
        data: dict = {}
        _deep_set(data, "verbose", True)
        assert data["verbose"] is True

    def test_nested_key(self):
        data: dict = {}
        _deep_set(data, "translate.model", "gpt-4")
        assert data["translate"]["model"] == "gpt-4"

    def test_deeply_nested_key(self):
        data: dict = {}
        _deep_set(data, "a.b.c", "deep")
        assert data["a"]["b"]["c"] == "deep"

    def test_overwrite_existing(self):
        data = {"translate": {"model": "old"}}
        _deep_set(data, "translate.model", "new")
        assert data["translate"]["model"] == "new"


class TestLoadConfig:
    def test_load_from_yaml_file(self, tmp_path, monkeypatch):
        monkeypatch.delenv("PIPEPOST_CONFIG", raising=False)
        monkeypatch.delenv("PIPEPOST_MODEL", raising=False)
        monkeypatch.delenv("PIPEPOST_LANG", raising=False)
        monkeypatch.delenv("PIPEPOST_DEST_URL", raising=False)
        cfg_file = tmp_path / "pipepost.yaml"
        cfg_file.write_text(
            "translate:\n  model: gpt-4\n  target_lang: ja\nverbose: true\n",
            encoding="utf-8",
        )
        cfg = load_config(config_path=str(cfg_file))
        assert cfg.translate.model == "gpt-4"
        assert cfg.translate.target_lang == "ja"
        assert cfg.verbose is True

    def test_load_with_cli_overrides(self, tmp_path, monkeypatch):
        monkeypatch.delenv("PIPEPOST_MODEL", raising=False)
        monkeypatch.delenv("PIPEPOST_LANG", raising=False)
        monkeypatch.delenv("PIPEPOST_DEST_URL", raising=False)
        cfg_file = tmp_path / "pipepost.yaml"
        cfg_file.write_text("translate:\n  model: gpt-4\n", encoding="utf-8")
        cfg = load_config(
            config_path=str(cfg_file),
            cli_overrides={"translate.model": "claude-3"},
        )
        assert cfg.translate.model == "claude-3"

    def test_load_no_file_uses_defaults(self, tmp_path, monkeypatch):
        monkeypatch.delenv("PIPEPOST_CONFIG", raising=False)
        monkeypatch.delenv("PIPEPOST_MODEL", raising=False)
        monkeypatch.delenv("PIPEPOST_LANG", raising=False)
        monkeypatch.delenv("PIPEPOST_DEST_URL", raising=False)
        monkeypatch.chdir(tmp_path)
        cfg = load_config()
        assert cfg.translate.model == "deepseek/deepseek-chat"
        assert cfg.sources == []

    def test_env_overrides_yaml(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PIPEPOST_MODEL", "env-model")
        monkeypatch.delenv("PIPEPOST_LANG", raising=False)
        monkeypatch.delenv("PIPEPOST_DEST_URL", raising=False)
        cfg_file = tmp_path / "pipepost.yaml"
        cfg_file.write_text("translate:\n  model: yaml-model\n", encoding="utf-8")
        cfg = load_config(config_path=str(cfg_file))
        assert cfg.translate.model == "env-model"

    def test_cli_overrides_env(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PIPEPOST_MODEL", "env-model")
        monkeypatch.delenv("PIPEPOST_LANG", raising=False)
        monkeypatch.delenv("PIPEPOST_DEST_URL", raising=False)
        monkeypatch.chdir(tmp_path)
        cfg = load_config(cli_overrides={"translate.model": "cli-model"})
        assert cfg.translate.model == "cli-model"


class TestResolveEnvVars:
    def test_resolves_string_values(self, monkeypatch):
        monkeypatch.setenv("TEST_TOKEN", "secret123")
        data = {"token": "${TEST_TOKEN}", "nested": {"key": "${TEST_TOKEN}"}, "plain": "hello"}
        result = resolve_env_vars(data)
        assert result == {"token": "secret123", "nested": {"key": "secret123"}, "plain": "hello"}

    def test_resolves_in_lists(self, monkeypatch):
        monkeypatch.setenv("ITEM", "resolved")
        data = {"items": ["${ITEM}", "literal"]}
        result = resolve_env_vars(data)
        assert result == {"items": ["resolved", "literal"]}

    def test_missing_env_var_replaced_with_empty(self, monkeypatch):
        monkeypatch.delenv("NONEXISTENT_VAR_XYZ", raising=False)
        data = {"key": "${NONEXISTENT_VAR_XYZ}"}
        result = resolve_env_vars(data)
        assert result == {"key": ""}

    def test_partial_substitution(self, monkeypatch):
        monkeypatch.setenv("HOST", "localhost")
        data = {"url": "http://${HOST}:8080/path"}
        result = resolve_env_vars(data)
        assert result == {"url": "http://localhost:8080/path"}

    def test_non_string_values_unchanged(self):
        data = {"count": 42, "flag": True, "empty": None}
        result = resolve_env_vars(data)
        assert result == {"count": 42, "flag": True, "empty": None}

    def test_load_config_resolves_env_vars(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MY_MODEL", "gpt-4-turbo")
        monkeypatch.delenv("PIPEPOST_CONFIG", raising=False)
        monkeypatch.delenv("PIPEPOST_MODEL", raising=False)
        monkeypatch.delenv("PIPEPOST_LANG", raising=False)
        monkeypatch.delenv("PIPEPOST_DEST_URL", raising=False)
        cfg_file = tmp_path / "pipepost.yaml"
        cfg_file.write_text(
            "translate:\n  model: ${MY_MODEL}\n  target_lang: ja\n",
            encoding="utf-8",
        )
        cfg = load_config(config_path=str(cfg_file))
        assert cfg.translate.model == "gpt-4-turbo"


class TestFlowConfigDefaults:
    def test_flow_config_default_steps(self):
        fc = FlowConfig()
        assert fc.steps == [
            "dedup",
            "scout",
            "fetch",
            "translate",
            "validate",
            "publish",
            "post_publish",
        ]

    def test_flow_config_default_on_error(self):
        fc = FlowConfig()
        assert fc.on_error == "stop"

    def test_score_config_defaults(self):
        sc = ScoreConfig()
        assert sc.niche == "general"
        assert sc.max_score_candidates == 5

    def test_adapt_config_defaults(self):
        ac = AdaptConfig()
        assert ac.style == "blog"

    def test_publish_flow_config_defaults(self):
        pc = PublishFlowConfig()
        assert pc.destination_name == "default"
        assert pc.destination_names == []

    def test_storage_config_defaults(self):
        sc = StorageConfig()
        assert sc.db_path == "pipepost.db"

    def test_pipepost_config_has_flow(self):
        cfg = PipePostConfig()
        assert isinstance(cfg.flow, FlowConfig)
        assert cfg.flow.on_error == "stop"

    def test_full_config_with_flow_section(self):
        data = {
            "sources": [{"name": "hn", "type": "hackernews"}],
            "translate": {"model": "gpt-4", "target_lang": "es"},
            "flow": {
                "steps": ["dedup", "scout", "score", "fetch", "translate", "publish"],
                "on_error": "skip",
                "score": {"niche": "tech", "max_score_candidates": 3},
                "adapt": {"style": "telegram"},
                "publish": {"destination_name": "webhook"},
                "storage": {"db_path": "/tmp/custom.db"},
            },
        }
        cfg = PipePostConfig.model_validate(data)
        assert cfg.flow.steps == [
            "dedup",
            "scout",
            "score",
            "fetch",
            "translate",
            "publish",
        ]
        assert cfg.flow.on_error == "skip"
        assert cfg.flow.score.niche == "tech"
        assert cfg.flow.score.max_score_candidates == 3
        assert cfg.flow.adapt.style == "telegram"
        assert cfg.flow.publish.destination_name == "webhook"
        assert cfg.flow.storage.db_path == "/tmp/custom.db"
