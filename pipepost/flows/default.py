"""Default flow — scout, dedup, fetch, translate, validate, publish, persist."""

from __future__ import annotations

from pipepost.core.flow import Flow
from pipepost.core.registry import register_flow
from pipepost.steps.dedup import DeduplicationStep, PostPublishStep
from pipepost.steps.fetch import FetchStep
from pipepost.steps.publish import PublishStep
from pipepost.steps.scout import ScoutStep
from pipepost.steps.translate import TranslateStep
from pipepost.steps.validate import ValidateStep
from pipepost.storage.sqlite import SQLiteStorage


_storage = SQLiteStorage()

_default_flow = Flow(
    name="default",
    steps=[
        DeduplicationStep(storage=_storage),
        ScoutStep(),
        FetchStep(),
        TranslateStep(),
        ValidateStep(),
        PublishStep(),
        PostPublishStep(storage=_storage),
    ],
)

register_flow("default", _default_flow)
