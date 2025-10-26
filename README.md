# Sleepless Agent

A 24/7 AI assistant daemon that continuously works on tasks via Slack. Uses Claude Code CLI via Python Agent SDK to process both random thoughts and serious jobs automatically with isolated workspaces.

## About

- Maintained by Context Machine Lab
- Ships as `sleepless-agent` on PyPI (`pip install sleepless-agent`)
- Automates task intake, execution, and reporting via Slack + Claude integration
- Designed for continuous operation with isolated workspaces and automated git hygiene

## Full Precedure

  1. Command arrives via CLI (sle think -p project "..." or sle think "...") or Slack (/think --project=project ... or /think ...)
  2. TaskQueue stores it in SQLite database with status PENDING
  3. Daemon polls every 5 seconds, calling _process_tasks()
  4. SmartScheduler decides if task can execute:
    - Checks budget (time-based quotas: 90% night, 10% day)
    - Checks available parallel slots
    - Prioritizes SERIOUS tasks (with -p/--project) over THOUGHT tasks (without -p)
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
pip install -e .
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
- `/check` - Check queue status
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
sle daemon

# Terminal 2 (optional): Monitor logs
tail -f workspace/data/agent.log
```

You should see startup logs similar to:
```
2025-10-24 23:30:12 | INFO     | sleepless_agent.interfaces.bot.start:50 Slack bot started and listening for events
2025-10-24 23:30:12 | INFO     | sleepless_agent.runtime.daemon.run:178 Sleepless Agent starting...
```
Logs are rendered with Rich for readability; set `SLEEPLESS_LOG_LEVEL=DEBUG` to increase verbosity.

### Logging

Rich console output is powered by [Rich](https://rich.readthedocs.io/) and now mirrors the structured events that feed our JSON logs. Every console line maps to a canonical `event` (for example `task.phase.done`, `scheduler.dispatch`, `usage.snapshot`) so you can skim the terminal or process the data programmatically.

Structured copies of each log line are written to JSONL files under `workspace/.logs` by default (override with `SLEEPLESS_LOG_DIR`). These files preserve context such as `task_id`, `phase`, `usage_percent`, and timing deltas, making it easy to build dashboards or run ad-hoc analysis later.

Set `SLEEPLESS_LOG_LEVEL` to tune verbosity; `DEBUG` includes low-level worker/evaluator metrics while `INFO` keeps to lifecycle milestones.


## Slack Commands

All Slack commands align with the CLI commands for consistency:

### 📋 Task Management

| Command | Purpose | Example |
|---------|---------|---------|
| `/task` | Add serious task | `/task Add OAuth2 support` |
| `/task` | With project | `/task Add OAuth2 support --project=backend` |
| `/think` | Capture random thought | `/think Explore async ideas` |
| `/check` | Show system status | `/check` |
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
sle check
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
sle --db-path ./tmp/tasks.db --results-path ./tmp/results status
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
- **config.yaml**: Configuration defaults
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
│   └── config.yaml         # Config defaults
├── workspace/              # All persistent data and task workspaces
│   ├── data/               # Persistent storage
│   │   ├── tasks.db        # SQLite database
│   │   ├── results/        # Task output files
│   │   ├── reports/        # Daily markdown reports
│   │   ├── agent.log       # Application logs
│   │   └── metrics.jsonl   # Performance metrics
│   ├── tasks/              # Task workspaces (task_1/, task_2/, etc.)
│   ├── projects/           # Project workspaces
│   └── trash/              # Soft-deleted projects
├── .env                    # Secrets (not tracked)
├── pyproject.toml          # Python package metadata & dependencies
├── README.md              # This file
└── docs/                  # Additional documentation
```

## Configuration

Runtime settings come from environment variables loaded via `.env` (see `.env.example`). Update those values or export them in your shell to tune agent behavior.

### Pro Plan Usage Management

The agent automatically monitors your Claude Code Pro plan usage and prevents task overruns with an **85% usage pause threshold**. This ensures you never accidentally exhaust your message limit.

**How it works:**

1. **Usage Monitoring** - Every task checks your Pro plan usage via `claude /usage` command
2. **Pause Threshold (85%)** - When usage reaches 85%, task generation automatically stops
3. **Resume on Reset** - Tasks resume after your 5-hour window resets
4. **Time-based Quotas** - Budget is split: 90% for night (8 PM - 8 AM), 10% for day (8 AM - 8 PM)

**Example flow:**
```
- Start of window: 0/40 messages (0% - all green)
- Mid-window: 28/40 messages (70% - status OK, tasks continue)
- Threshold reached: 34/40 messages (85% - tasks pause, logs warning)
- Window resets: 0/40 messages (resets at 18:59:00, tasks resume)
```

**Visibility:**
- Dashboard: Shows `Pro Usage: X% / Y% limit` in `sle check` (Y = 20% daytime, 80% nighttime)
- Logs: Each usage check logs Pro plan usage with time-based threshold
- Config: Adjustable via `claude_code.threshold_day` and `claude_code.threshold_night` in `config.yaml`

**Time-Based Thresholds:**
- **Daytime (8 AM - 8 PM):** Pause at 20% (saves quota for your manual usage)
- **Nighttime (8 PM - 8 AM):** Pause at 80% (agent works aggressively while you sleep)
- Time ranges are configurable via `claude_code.night_start_hour` and `claude_code.night_end_hour` in `config.yaml`
- ⏸️ New task generation pauses at threshold
- ✅ Running tasks complete normally
- 📋 Pending tasks wait in queue
- ⏱️ Grace period: +1 minute after reset to avoid edge cases

**Note:** Pro plan usage monitoring is mandatory and always enabled.

## Environment Variables

```bash
# Required
SLACK_BOT_TOKEN=xoxb-...
SLACK_APP_TOKEN=xapp-...

# Optional
AGENT_WORKSPACE=./workspace
AGENT_DB_PATH=./workspace/data/tasks.db
AGENT_RESULTS_PATH=./workspace/data/results
GIT_USER_NAME=Sleepless Agent
GIT_USER_EMAIL=agent@sleepless.local
SLEEPLESS_LOG_LEVEL=INFO
SLEEPLESS_LOG_DIR=workspace/.logs
```

## Task Types

The agent intelligently processes different task types:

1. **Thoughts** - Auto-commits to `thought-ideas` branch
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
SLEEPLESS_LOG_LEVEL=DEBUG python -m sleepless_agent.daemon
```

## Monitoring

### Real-time Logs
```bash
tail -f workspace/data/agent.log
```

### Database Queries
```bash
sqlite3 workspace/data/tasks.db "SELECT * FROM tasks WHERE status='completed' LIMIT 5;"
```

### Performance History
```bash
tail -100 workspace/data/metrics.jsonl | jq .
```

### Slack Commands
```
/check    # System status and performance stats
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
/check
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
| Bot not responding | Check `.env` tokens, verify Socket Mode enabled, check logs: `tail -f workspace/data/agent.log` |
| Tasks not executing | Verify Claude Code CLI installed: `npm list -g @anthropic-ai/claude-code`, check workspace permissions |
| Tasks paused (threshold reached) | Usage has reached time-based threshold (20% daytime / 80% nighttime). Wait for window reset (check logs for reset time), or adjust thresholds in `config.yaml` (`claude_code.threshold_day` / `claude_code.threshold_night`). Run `sle check` to see current usage. |
| Git commits fail | Install `gh` CLI and authenticate: `gh auth login` |
| Out of credits | Wait for 5-hour window refresh. Review scheduler logs: `tail -f workspace/data/agent.log | grep credit` |
| Database locked | Close other connections, try: `rm workspace/data/tasks.db && python -m sleepless_agent.daemon` |

## Performance Tips

1. **Use thoughts to fill idle time** - Maximizes usage
2. **Batch serious jobs** - Reduces context switching
3. **Monitor credits** - Watch scheduler logs for window resets
4. **Review git history** - Check `thought-ideas` branch regularly
5. **Check metrics** - Run `sle check` to track performance

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
