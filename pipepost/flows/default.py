"""Default flow — fetch, translate, validate, publish."""

from __future__ import annotations

from pipepost.core.flow import Flow
from pipepost.core.registry import register_flow
from pipepost.steps.fetch import FetchStep
from pipepost.steps.publish import PublishStep
from pipepost.steps.translate import TranslateStep
from pipepost.steps.validate import ValidateStep


_default_flow = Flow(
    name="default",
    steps=[
        FetchStep(),
        TranslateStep(),
        ValidateStep(),
        PublishStep(),
    ],
)

register_flow("default", _default_flow)
