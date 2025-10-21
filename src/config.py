"""Configuration management"""

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings

# Load .env file
load_dotenv()


class SlackConfig(BaseSettings):
    """Slack bot configuration"""
    bot_token: str = Field(..., alias="SLACK_BOT_TOKEN")
    app_token: str = Field(..., alias="SLACK_APP_TOKEN")
    auto_thread_replies: bool = True
    notification_enabled: bool = True


class ClaudeConfig(BaseSettings):
    """Claude API configuration"""
    api_key: str = Field(..., alias="ANTHROPIC_API_KEY")
    model: str = "claude-opus-4-1-20250805"
    max_tokens: int = 4096
    temperature: float = 0.7


class AgentConfig(BaseSettings):
    """Agent configuration"""
    workspace: Path = Path("./workspace")
    db_path: Path = Path("./data/tasks.db")
    results_path: Path = Path("./data/results")
    max_parallel_tasks: int = 3
    task_timeout_seconds: int = 3600


class Config(BaseSettings):
    """Main configuration"""
    slack: SlackConfig
    claude: ClaudeConfig
    agent: AgentConfig

    class Config:
        env_nested_delimiter = "__"

    def __init__(self, **data):
        slack_config = SlackConfig()
        claude_config = ClaudeConfig()
        agent_config = AgentConfig()

        super().__init__(
            slack=slack_config,
            claude=claude_config,
            agent=agent_config,
            **data
        )


def get_config() -> Config:
    """Get configuration instance"""
    return Config()
