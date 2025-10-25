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
    default_timeout: int = 1800  # 30 minute default timeout
    cleanup_random_workspaces: bool = True  # Clean up after random tasks complete
    preserve_serious_workspaces: bool = True  # Keep serious task workspaces for debugging


class MultiAgentPhaseConfig(BaseSettings):
    """Configuration for a single execution phase"""
    enabled: bool = True
    max_turns: int = 10
    timeout_seconds: int = 300


class MultiAgentReadmeConfig(BaseSettings):
    """Configuration for README management"""
    auto_create: bool = True
    auto_update: bool = True
    preserve_history: bool = True


class MultiAgentPlanConfig(BaseSettings):
    """Configuration for PLAN.md management"""
    auto_create: bool = True
    preserve_plan: bool = True
    include_context: bool = True


class ProPlanMonitoringConfig(BaseSettings):
    """Pro plan usage monitoring configuration

    Controls Claude Code Pro plan usage tracking and task scheduling decisions.
    Automatically pauses new task generation when usage exceeds the pause_threshold.
    """
    enabled: bool = True
    pause_threshold: float = 85.0  # Stop generating new tasks when usage >= 85% of limit
    usage_command: str = "claude /usage"  # CLI command to check usage
    check_frequency: str = "after_task"  # When to check: after_task | before_task | both

    # Auto-generation settings
    auto_generate_refinements: bool = True  # Generate tasks for incomplete work
    low_usage_threshold: float = 60.0  # Generate when usage < 60%
    max_auto_tasks_per_session: int = 3  # Limit auto-generated tasks


class MultiAgentWorkflowConfig(BaseSettings):
    """Multi-agent workflow configuration"""
    enabled: bool = True
    planner: MultiAgentPhaseConfig = Field(default_factory=lambda: MultiAgentPhaseConfig(max_turns=3, timeout_seconds=300))
    worker: MultiAgentPhaseConfig = Field(default_factory=lambda: MultiAgentPhaseConfig(max_turns=3, timeout_seconds=1800))
    evaluator: MultiAgentPhaseConfig = Field(default_factory=lambda: MultiAgentPhaseConfig(max_turns=3, timeout_seconds=300))
    readme: MultiAgentReadmeConfig = Field(default_factory=MultiAgentReadmeConfig)
    plan: MultiAgentPlanConfig = Field(default_factory=MultiAgentPlanConfig)
    pro_plan_monitoring: ProPlanMonitoringConfig = Field(default_factory=ProPlanMonitoringConfig)


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
    random_ratio: float = 0.6  # Fraction of auto-generated tasks kept low priority vs escalated to SERIOUS
    ai_model: str = "claude-sonnet-4-5-20250929"


class AgentConfig(BaseSettings):
    """Agent configuration"""
    workspace_root: Path = Path("./workspace")  # Root for isolated task workspaces
    shared_workspace: Path = Path("./workspace/shared")  # Optional shared resources
    db_path: Path = Path("./workspace/data/tasks.db")
    results_path: Path = Path("./workspace/data/results")
    max_parallel_tasks: int = 1
    task_timeout_seconds: int = 1800  # 30 minutes


class Config(BaseSettings):
    """Main configuration"""
    slack: SlackConfig
    claude_code: ClaudeCodeConfig
    agent: AgentConfig
    auto_generation: AutoGenerationConfig
    multi_agent_workflow: MultiAgentWorkflowConfig = Field(default_factory=MultiAgentWorkflowConfig)

    class Config:
        env_nested_delimiter = "__"

    def __init__(self, **data):
        slack_config = SlackConfig()
        claude_code_config = ClaudeCodeConfig()
        agent_config = AgentConfig()
        auto_generation_config = AutoGenerationConfig()
        multi_agent_workflow_config = MultiAgentWorkflowConfig()

        super().__init__(
            slack=slack_config,
            claude_code=claude_code_config,
            agent=agent_config,
            auto_generation=auto_generation_config,
            multi_agent_workflow=multi_agent_workflow_config,
            **data
        )


def get_config() -> Config:
    """Get configuration instance"""
    return Config()
