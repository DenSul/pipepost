"""PipePost destinations — publish targets for translated content."""

from pipepost.destinations.base import Destination
from pipepost.destinations.markdown import MarkdownDestination
from pipepost.destinations.telegram import TelegramDestination
from pipepost.destinations.webhook import WebhookDestination


__all__ = [
    "Destination",
    "MarkdownDestination",
    "TelegramDestination",
    "WebhookDestination",
]
