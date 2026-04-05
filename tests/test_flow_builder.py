"""Tests for config-driven flow builder."""

from __future__ import annotations

import pytest

from pipepost.config.flow_builder import build_flow_from_config
from pipepost.config.loader import (
    AdaptConfig,
    FlowConfig,
    PipePostConfig,
    PublishFlowConfig,
    ScoreConfig,
    StorageConfig,
)
from pipepost.exceptions import ConfigError
from pipepost.steps.adapt import AdaptStep
from pipepost.steps.dedup import DeduplicationStep, PostPublishStep
from pipepost.steps.fanout import FanoutPublishStep
from pipepost.steps.fetch import FetchStep
from pipepost.steps.publish import PublishStep
from pipepost.steps.score import ScoringStep
from pipepost.steps.scout import ScoutStep
from pipepost.steps.translate import TranslateStep
from pipepost.steps.validate import ValidateStep


class TestBuildFlowFromConfig:
    def test_build_default_steps(self, tmp_path):
        cfg = PipePostConfig(
            flow=FlowConfig(storage=StorageConfig(db_path=str(tmp_path / "test.db"))),
        )
        flow = build_flow_from_config(cfg)
        assert len(flow.steps) == 7
        expected_names = [
            "dedup",
            "scout",
            "fetch",
            "translate",
            "validate",
            "publish",
            "post_publish",
        ]
        assert [s.name for s in flow.steps] == expected_names

    def test_build_custom_steps(self, tmp_path):
        cfg = PipePostConfig(
            flow=FlowConfig(
                steps=["fetch", "translate", "publish"],
                storage=StorageConfig(db_path=str(tmp_path / "test.db")),
            ),
        )
        flow = build_flow_from_config(cfg)
        assert len(flow.steps) == 3
        assert [s.name for s in flow.steps] == ["fetch", "translate", "publish"]

    def test_score_config_applied(self, tmp_path):
        cfg = PipePostConfig(
            flow=FlowConfig(
                steps=["score"],
                score=ScoreConfig(niche="crypto", max_score_candidates=10),
                storage=StorageConfig(db_path=str(tmp_path / "test.db")),
            ),
        )
        flow = build_flow_from_config(cfg)
        step = flow.steps[0]
        assert isinstance(step, ScoringStep)
        assert step.niche == "crypto"
        assert step.max_score_candidates == 10

    def test_adapt_config_applied(self, tmp_path):
        cfg = PipePostConfig(
            flow=FlowConfig(
                steps=["adapt"],
                adapt=AdaptConfig(style="telegram"),
                storage=StorageConfig(db_path=str(tmp_path / "test.db")),
            ),
        )
        flow = build_flow_from_config(cfg)
        step = flow.steps[0]
        assert isinstance(step, AdaptStep)
        assert step.style == "telegram"

    def test_translate_config_applied(self, tmp_path):
        cfg = PipePostConfig(
            translate={"model": "gpt-4", "target_lang": "es"},
            flow=FlowConfig(
                steps=["translate"],
                storage=StorageConfig(db_path=str(tmp_path / "test.db")),
            ),
        )
        flow = build_flow_from_config(cfg)
        step = flow.steps[0]
        assert isinstance(step, TranslateStep)
        assert step.model == "gpt-4"
        assert step.target_lang == "es"

    def test_publish_config_applied(self, tmp_path):
        cfg = PipePostConfig(
            flow=FlowConfig(
                steps=["publish"],
                publish=PublishFlowConfig(destination_name="telegram"),
                storage=StorageConfig(db_path=str(tmp_path / "test.db")),
            ),
        )
        flow = build_flow_from_config(cfg)
        step = flow.steps[0]
        assert isinstance(step, PublishStep)
        assert step.destination_name == "telegram"

    def test_fanout_step_used(self, tmp_path):
        cfg = PipePostConfig(
            flow=FlowConfig(
                steps=["fanout_publish"],
                publish=PublishFlowConfig(destination_names=["webhook", "markdown"]),
                storage=StorageConfig(db_path=str(tmp_path / "test.db")),
            ),
        )
        flow = build_flow_from_config(cfg)
        step = flow.steps[0]
        assert isinstance(step, FanoutPublishStep)
        assert step.destination_names == ["webhook", "markdown"]

    def test_unknown_step_raises_config_error(self, tmp_path):
        cfg = PipePostConfig(
            flow=FlowConfig(
                steps=["fetch", "magic_step"],
                storage=StorageConfig(db_path=str(tmp_path / "test.db")),
            ),
        )
        with pytest.raises(ConfigError, match="magic_step"):
            build_flow_from_config(cfg)

    def test_storage_path_from_config(self, tmp_path):
        db_file = str(tmp_path / "custom.db")
        cfg = PipePostConfig(
            flow=FlowConfig(
                steps=["dedup", "post_publish"],
                storage=StorageConfig(db_path=db_file),
            ),
        )
        flow = build_flow_from_config(cfg)
        dedup_step = flow.steps[0]
        post_step = flow.steps[1]
        assert isinstance(dedup_step, DeduplicationStep)
        assert isinstance(post_step, PostPublishStep)
        assert dedup_step.storage.db_path == db_file
        assert post_step.storage.db_path == db_file

    def test_on_error_propagated(self, tmp_path):
        cfg = PipePostConfig(
            flow=FlowConfig(
                steps=["fetch"],
                on_error="skip",
                storage=StorageConfig(db_path=str(tmp_path / "test.db")),
            ),
        )
        flow = build_flow_from_config(cfg)
        assert flow.on_error == "skip"

    def test_step_types_correct(self, tmp_path):
        cfg = PipePostConfig(
            flow=FlowConfig(
                steps=[
                    "dedup",
                    "scout",
                    "score",
                    "fetch",
                    "translate",
                    "adapt",
                    "validate",
                    "publish",
                    "post_publish",
                ],
                storage=StorageConfig(db_path=str(tmp_path / "test.db")),
            ),
        )
        flow = build_flow_from_config(cfg)
        expected_types = [
            DeduplicationStep,
            ScoutStep,
            ScoringStep,
            FetchStep,
            TranslateStep,
            AdaptStep,
            ValidateStep,
            PublishStep,
            PostPublishStep,
        ]
        for step, expected_type in zip(flow.steps, expected_types, strict=True):
            assert isinstance(step, expected_type), f"{step.name} is not {expected_type.__name__}"
