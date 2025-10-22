"""External interfaces - Slack bot, CLI, and other integrations"""

from .bot import SlackBot
from .cli import main as cli_main

__all__ = ["SlackBot", "cli_main"]
