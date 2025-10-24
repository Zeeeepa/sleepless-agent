# Sleepless Agent

A 24/7 AI assistant daemon that continuously works on tasks via Slack. Uses Claude Code CLI via Python Agent SDK to process both random thoughts and serious jobs automatically with isolated workspaces.

## About

- Maintained by Context Machine Lab
- Ships as `sleepless-agent` on PyPI (`pip install sleepless-agent`)
- Automates task intake, execution, and reporting via Slack + Claude integration
- Designed for continuous operation with isolated workspaces and automated git hygiene

## Full Precedure

  1. Command arrives via CLI (sleepless task "...") or Slack (/task ...)
  2. TaskQueue stores it in SQLite database with status PENDING
  3. Daemon polls every 5 seconds, calling _process_tasks()
  4. SmartScheduler decides if task can execute:
    - Checks budget (time-based quotas: 90% night, 10% day)
    - Checks available parallel slots
    - Prioritizes SERIOUS tasks over RANDOM thoughts
    - Returns list of tasks to execute
  5. Daemon executes via _execute_task():
    - Marks task as IN_PROGRESS
    - Creates isolated workspace
    - Calls ClaudeCodeExecutor
  6. ClaudeCodeExecutor runs the task:
    - Builds enhanced prompt based on task type/priority
    - Calls Claude SDK with streaming
    - Tracks file modifications and commands
    - Returns results with metrics
  7. Daemon completes the flow:
    - Commits to git (for SERIOUS tasks)
    - Stores results in database
    - Marks as COMPLETED or FAILED
    - Sends Slack notification


## Features

- 🤖 **Continuous Operation**: Runs 24/7 daemon, always ready for new tasks
- 💬 **Slack Integration**: Submit tasks via Slack commands
- 🎯 **Hybrid Autonomy**: Auto-applies random thoughts, requires review for serious jobs
- ⚡ **Smart Scheduling**: Optimizes task execution based on priorities
- 📊 **Task Queue**: SQLite-backed persistent task management
- 🔌 **Claude Code SDK**: Uses Python Agent SDK to interface with Claude Code CLI
- 🏗️ **Isolated Workspaces**: Each task gets its own workspace for true parallelism
- 📝 **Result Storage**: All outputs saved with metadata for future reference

## Prerequisites

- Python 3.11+
- Slack workspace admin access
- Claude Code CLI installed (`npm install -g @anthropic-ai/claude-code`)
- Git (for auto-commits)
- gh CLI (optional, for PR automation)

## Quick Start

### 1. Install

```bash
pip install sleepless-agent
```

Or for development:
```bash
git clone <repo>
cd sleepless-agent
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt
```

### 2. Setup Slack App

Visit https://api.slack.com/apps and create a new app:

**Basic Information**
- Choose "From scratch"
- Name: "Sleepless Agent"
- Pick your workspace

**Enable Socket Mode**
- Settings > Socket Mode > Toggle ON
- Generate app token (starts with `xapp-`)

**Create Slash Commands**
Settings > Slash Commands > Create New Command:
- `/task` - Add serious task
- `/think` - Capture random thought
- `/status` - Check queue status
- `/cancel` - Cancel task or project
- `/report` - Show reports or task details
- `/trash` - Manage trash (list, restore, empty)

**OAuth Scopes**
Features > OAuth & Permissions > Bot Token Scopes:
- `chat:write`
- `commands`
- `app_mentions:read`

**Install App**
- Install to workspace
- Get bot token (starts with `xoxb-`)

### 3. Configure Environment

```bash
cp .env.example .env
nano .env  # Edit with your tokens
```

Set:
- `SLACK_BOT_TOKEN` - xoxb-... token
- `SLACK_APP_TOKEN` - xapp-... token

(Claude API key no longer needed - uses Claude Code CLI)

### 4. Run

```bash
# Terminal 1: Start the daemon
sleepless daemon

# Terminal 2 (optional): Monitor logs
tail -f logs/agent.log
```

You should see:
```
INFO - Slack bot started and listening for events
INFO - Sleepless Agent starting...
```

## Slack Commands

All Slack commands align with the CLI commands for consistency:

### 📋 Task Management

| Command | Purpose | Example |
|---------|---------|---------|
| `/task` | Add serious task | `/task Add OAuth2 support` |
| `/task` | With project | `/task Add OAuth2 support --project=backend` |
| `/think` | Capture random thought | `/think Explore async ideas` |
| `/status` | Show system status | `/status` |
| `/cancel` | Cancel task or project | `/cancel 5` or `/cancel my-app` |

### 📊 Reporting & Trash

| Command | Purpose | Example |
|---------|---------|---------|
| `/report` | Today's report | `/report` |
| `/report` | Task details | `/report 42` |
| `/report` | Date report | `/report 2025-10-22` |
| `/report` | Project report | `/report my-app` |
| `/report` | List all reports | `/report --list` |
| `/trash` | List trash | `/trash list` |
| `/trash` | Restore project | `/trash restore my-app` |
| `/trash` | Empty trash | `/trash empty` |

## Command Line Interface

Install the project (or run within the repo) and use the bundled CLI:

```bash
python -m sleepless_agent.interfaces.cli task "Ship release checklist"
# or, after installing the package:
sleepless status
```

The CLI mirrors the Slack slash commands:

| Command | Purpose | Example |
|---------|---------|---------|
| `task <description>` | Queue a serious task | `task "Build onboarding flow"` |
| `think <description>` | Capture a random thought | `think "Explore async patterns"` |
| `status` | Show system health, queue, and performance metrics | `status` |
| `report [identifier]` | Show task details, daily reports, or project summaries (`--list` for all reports) | `report 7` |
| `cancel <identifier>` | Move a task or project to trash | `cancel 9` or `cancel my-app` |
| `trash [subcommand] [identifier]` | Manage trash (list, restore, empty) | `trash restore my-app` |

Override storage locations when needed:

```bash
sleepless --db-path ./tmp/tasks.db --results-path ./tmp/results status
```

## Architecture

```
Slack Bot
    ↓
Slack Commands → Task Queue (SQLite)
    ↓
Agent Daemon (Event Loop)
    ↓
Claude Executor (Claude Code CLI)
    ↓
Result Manager (Storage + Git)
```

### Components

- **daemon.py**: Main event loop, task orchestration
- **bot.py**: Slack interface, command parsing
- **task_queue.py**: Task CRUD, priority scheduling
- **claude_code_executor.py**: Python Agent SDK wrapper with isolated workspace management
- **results.py**: Result storage, file management
- **models.py**: SQLAlchemy models for Task, Result
- **config.py**: Configuration management
- **git_manager.py**: Git automation (commits, PRs)
- **monitor.py**: Health checks and metrics

## File Structure

```
sleepless-agent/
├── src/sleepless_agent/
│   ├── __init__.py
│   ├── daemon.py           # Main event loop
│   ├── bot.py              # Slack interface
│   ├── task_queue.py       # Task management
│   ├── claude_code_executor.py  # Claude CLI wrapper
│   ├── scheduler.py        # Smart scheduling
│   ├── git_manager.py      # Git automation
│   ├── monitor.py          # Health & metrics
│   ├── models.py           # Database models
│   ├── results.py          # Result storage
│   └── config.py           # Config management
├── data/
│   ├── tasks.db            # SQLite database
│   └── results/            # Task output files
├── workspace/              # Task workspaces (task_1/, task_2/, etc.)
├── logs/                   # Log files
├── config.yaml             # Configuration
├── .env                    # Secrets (not tracked)
├── requirements.txt        # Python dependencies
├── README.md              # This file
└── docs/                  # Additional documentation
```

## Configuration

Edit `config.yaml` to customize:

```yaml
agent:
  max_parallel_tasks: 3        # 1-10 concurrent tasks
  task_timeout_seconds: 3600   # 1 hour per task

claude_code:
  binary_path: "claude"        # Path to claude binary
  default_timeout: 3600        # Timeout in seconds
  cleanup_random_workspaces: true

scheduler:
  serious_job_priority: 100
  random_thought_priority: 10
  max_retries: 3
```

## Environment Variables

```bash
# Required
SLACK_BOT_TOKEN=xoxb-...
SLACK_APP_TOKEN=xapp-...

# Optional
AGENT_WORKSPACE=./workspace
AGENT_DB_PATH=./data/tasks.db
AGENT_RESULTS_PATH=./data/results
GIT_USER_NAME=Sleepless Agent
GIT_USER_EMAIL=agent@sleepless.local
LOG_LEVEL=INFO
DEBUG=false
```

## Task Types

The agent intelligently processes different task types:

1. **Random Thoughts** - Auto-commits to `random-ideas` branch
   ```
   /think Research async patterns in Rust
   /think What's the best way to implement caching?
   ```

2. **Serious Jobs** - Creates feature branch and PR, requires review
   ```
   /task Add authentication to user service
   /task Refactor payment processing module
   ```

## Development

### Add New Task Type

Edit task prompt configuration as needed in `daemon.py` or implement custom executors.

### Database Schema

Tasks are stored with:
- `id`: Auto-incremented task ID
- `description`: Task text
- `priority`: "random" or "serious"
- `status`: "pending", "in_progress", "completed", "failed"
- `created_at`, `started_at`, `completed_at`: Timestamps
- `result_id`: Link to Result record

### Testing

```bash
# Run tests
pytest

# Run with debug logging
DEBUG=true python -m sleepless_agent.daemon
```

## Monitoring

### Real-time Logs
```bash
tail -f logs/agent.log
```

### Database Queries
```bash
sqlite3 data/tasks.db "SELECT * FROM tasks WHERE status='completed' LIMIT 5;"
```

### Performance History
```bash
tail -100 logs/metrics.jsonl | jq .
```

### Slack Commands
```
/status    # System status and performance stats
/report --list  # Available reports
```

## Deployment

### Linux (systemd)
```bash
make install-service
sudo systemctl start sleepless-agent
```

### macOS (launchd)
```bash
make install-launchd
launchctl list | grep sleepless
```

## Example Workflows

### Daily Brainstorm
```
/think Research new Rust async libraries
/think Compare Python web frameworks
/think Ideas for improving API performance
/status
```

### Production Fix
```
/task Fix authentication bug in login endpoint
/report <id>     # Get the PR link
# Review and merge PR
```

### Code Audit
```
/task Security audit of user service
/task Performance analysis of payment module
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Bot not responding | Check `.env` tokens, verify Socket Mode enabled, check logs: `tail -f logs/agent.log` |
| Tasks not executing | Verify Claude Code CLI installed: `npm list -g @anthropic-ai/claude-code`, check workspace permissions |
| Git commits fail | Install `gh` CLI and authenticate: `gh auth login` |
| Out of credits | Wait for 5-hour window refresh. Review scheduler logs: `tail -f logs/agent.log | grep credit` |
| Database locked | Close other connections, try: `rm data/tasks.db && python -m sleepless_agent.daemon` |

## Performance Tips

1. **Use random thoughts to fill idle time** - Maximizes usage
2. **Batch serious jobs** - Reduces context switching
3. **Monitor credits** - Watch scheduler logs for window resets
4. **Review git history** - Check `random-ideas` branch regularly
5. **Check metrics** - Run `sleepless status` to track performance

## Security Notes

- Secrets are validated before git commits
- Python syntax checked before commits
- Directory traversal prevented in file operations
- .env file never committed to git
- Workspace changes validated before applying

## Releases

- Latest stable: **0.1.0** – published on [PyPI](https://pypi.org/project/sleepless-agent/0.1.0/)
- Install or upgrade with `pip install -U sleepless-agent`
- Release notes tracked via GitHub Releases (tag `v0.1.0` onward)

## Additional Documentation

For more detailed information, see the docs/ folder:

- **[GETTING_STARTED.md](docs/GETTING_STARTED.md)** - Detailed setup guide and architecture overview
- **[QUICK_REFERENCE.md](docs/QUICK_REFERENCE.md)** - Command reference and quick tips
- **[CLAUDE_CODE_REDESIGN.md](docs/CLAUDE_CODE_REDESIGN.md)** - Technical design document for Claude Code migration

## License

Released under the [MIT License](LICENSE)
