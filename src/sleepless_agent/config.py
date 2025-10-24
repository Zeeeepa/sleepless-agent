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


class ClaudeCodeConfig(BaseSettings):
    """Claude Code CLI configuration"""
    binary_path: str = "claude"  # Path to claude binary (default: from PATH)
    default_timeout: int = 3600  # 1 hour default timeout
    cleanup_random_workspaces: bool = True  # Clean up after random tasks complete
    preserve_serious_workspaces: bool = True  # Keep serious task workspaces for debugging


class AutoGenerationConfig(BaseSettings):
    """Auto-task generation configuration"""
    enabled: bool = True  # Enable automatic task generation
    usage_threshold_percent: int = 60  # Generate tasks when usage < X% of daily budget
    budget_ceiling_percent: int = 85  # Stop generation when usage >= X% of daily budget
    rate_limit_night: int = 2  # Tasks per hour (night: 8PM-8AM)
    rate_limit_day: int = 1  # Tasks per hour (day: 8AM-8PM)

    # Task source weights (percentages, should sum to 100)
    source_weights: dict = {
        "pool": 30,  # Predefined task pool
        "code": 25,  # Code analysis (TODOs, tech debt)
        "ai": 25,    # AI-generated ideas
        "backlog": 20  # Project backlog (GitHub issues, etc.)
    }

    # Task type distribution
    random_ratio: float = 0.6  # 60% RANDOM tasks, 40% SERIOUS


class AgentConfig(BaseSettings):
    """Agent configuration"""
    workspace_root: Path = Path("./workspace")  # Root for isolated task workspaces
    shared_workspace: Path = Path("./workspace/shared")  # Optional shared resources
    db_path: Path = Path("./data/tasks.db")
    results_path: Path = Path("./data/results")
    max_parallel_tasks: int = 3
    task_timeout_seconds: int = 3600


class Config(BaseSettings):
    """Main configuration"""
    slack: SlackConfig
    claude_code: ClaudeCodeConfig
    agent: AgentConfig
    auto_generation: AutoGenerationConfig

    class Config:
        env_nested_delimiter = "__"

    def __init__(self, **data):
        slack_config = SlackConfig()
        claude_code_config = ClaudeCodeConfig()
        agent_config = AgentConfig()
        auto_generation_config = AutoGenerationConfig()

        super().__init__(
            slack=slack_config,
            claude_code=claude_code_config,
            agent=agent_config,
            auto_generation=auto_generation_config,
            **data
        )


def get_config() -> Config:
    """Get configuration instance"""
    return Config()
