<div align="center">

# Sleepless Agent

**A 24/7 AgentOS that works while you sleep**

[![Documentation](https://img.shields.io/badge/Documentation-007ACC?style=for-the-badge&logo=markdown&logoColor=white)](https://context-machine-lab.github.io/sleepless-agent/)
[![DeepWiki](https://img.shields.io/badge/DeepWiki-582C83?style=for-the-badge&logo=wikipedia&logoColor=white)](https://deepwiki.com/context-machine-lab/sleepless-agent)
[![WeChat](https://img.shields.io/badge/WeChat-07C160?style=for-the-badge&logo=wechat&logoColor=white)](./assets/wechat.jpg)
[![Discord](https://img.shields.io/badge/Discord-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://discord.gg/74my3Wkn)

</div>

Have Claude Code Pro but not using it at night? Transform it into an AgentOS that handles your ideas and tasks while you sleep. This is a 24/7 AI assistant daemon powered by Claude Code CLI and Python Agent SDK that processes both random thoughts and serious tasks via Slack with isolated workspaces.


## ✨ Features

- 🤖 **Continuous Operation**: Runs 24/7 daemon, always ready for new tasks
- 💬 **Slack Integration**: Submit tasks via Slack commands
- 🎯 **Hybrid Autonomy**: Auto-applies random thoughts, requires review for serious tasks
- ⚡ **Smart Scheduling**: Optimizes task execution based on priorities
- 📊 **Task Queue**: SQLite-backed persistent task management
- 🔌 **Claude Code SDK**: Uses Python Agent SDK to interface with Claude Code CLI
- 🏗️ **Isolated Workspaces**: Each task gets its own workspace for true parallelism
- 📝 **Result Storage**: All outputs saved with metadata for future reference

## ⚙️ Prerequisites

- Python 3.11+
- Slack workspace admin access
- Claude Code CLI installed (`npm install -g @anthropic-ai/claude-code`)
- Git (for auto-commits)
- gh CLI (optional, for PR automation)

## 🚀 Quick Start

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
- `/think` - Capture thought or task (use `-p project-name` for serious tasks)
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
sle daemon
```

You should see startup logs similar to:
```
2025-10-24 23:30:12 | INFO     | sleepless_agent.interfaces.bot.start:50 Slack bot started and listening for events
2025-10-24 23:30:12 | INFO     | sleepless_agent.runtime.daemon.run:178 Sleepless Agent starting...
```
Logs are rendered with Rich for readability; set `SLEEPLESS_LOG_LEVEL=DEBUG` to increase verbosity.


## 💬 Slack Commands

All Slack commands align with the CLI commands for consistency:

### 📋 Task Management

| Command | Purpose | Example |
|---------|---------|---------|
| `/think` | Capture random thought | `/think Explore async ideas` |
| `/think -p <project>` | Add serious task to project | `/think Add OAuth2 support -p backend` |
| `/check` | Show system status | `/check` |
| `/cancel` | Cancel task or project | `/cancel 5` or `/cancel my-app` |

### 📊 Reporting & Trash

| Command | Purpose | Example |
|---------|---------|---------|
| `/report` | Today's report, task details, date/project report, or list all | `/report`, `/report 42`, `/report 2025-10-22`, `/report my-app`, `/report --list` |
| `/trash` | List, restore, or empty trash | `/trash list`, `/trash restore my-app`, `/trash empty` |

## ⌨️ Command Line Interface

Install the project (or run within the repo) and use the bundled CLI:

```bash
python -m sleepless_agent.interfaces.cli think "Ship release checklist" -p my-app
# or, after installing the package:
sle check
```

The CLI mirrors the Slack slash commands:

| Command | Purpose | Example |
|---------|---------|---------|
| `think <description>` | Capture a random thought | `think "Explore async patterns"` |
| `think <description> -p <project>` | Queue a serious task to project | `think "Build onboarding flow" -p backend` |
| `check` | Show system health, queue, and performance metrics | `check` |
| `report [identifier]` | Show task details, daily reports, or project summaries (`--list` for all reports) | `report 7` |
| `cancel <identifier>` | Move a task or project to trash | `cancel 9` or `cancel my-app` |
| `trash [subcommand] [identifier]` | Manage trash (list, restore, empty) | `trash restore my-app` |

Override storage locations when needed:

```bash
sle --db-path ./tmp/tasks.db --results-path ./tmp/results check
```

## 🏗️ Architecture

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

## 📁 File Structure

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

## ⚙️ Configuration

Runtime settings come from environment variables loaded via `.env` (see `.env.example`). Update those values or export them in your shell to tune agent behavior.

### Usage Management

The agent automatically monitors Claude Code usage and intelligently manages task execution based on configurable thresholds.

**How it works:**

1. **Usage Monitoring** - Every task checks usage via `claude /usage` command
2. **Time-based Thresholds** - Different thresholds for day and night operations
3. **Smart Scheduling** - Automatically pauses task generation when threshold is reached
4. **Automatic Resume** - Tasks resume when usage resets

**Time-Based Configuration (configurable in `config.yaml`):**
- **Nighttime (1 AM - 9 AM by default):** 96% threshold - agent works aggressively while you sleep
- **Daytime (9 AM - 1 AM by default):** 95% threshold - preserves capacity for your manual usage
- Configure via: `claude_code.threshold_day`, `claude_code.threshold_night`
- Time ranges via: `claude_code.night_start_hour`, `claude_code.night_end_hour`

**Visibility:**
- Dashboard: Shows usage percentage in `sle check`
- Logs: Each usage check logs current usage with applicable threshold
- Config: All thresholds and time ranges adjustable in `config.yaml`

**Behavior at threshold:**
- ⏸️ New task generation pauses at threshold
- ✅ Running tasks complete normally
- 📋 Pending tasks wait in queue
- ⏱️ Automatic resume when usage resets

## 🔧 Environment Variables

```bash
# Required
SLACK_BOT_TOKEN=xoxb-...
SLACK_APP_TOKEN=xapp-...
```

## 📝 Task Types

The agent intelligently processes different task types:

1. **Random Thoughts** - Auto-commits to `thought-ideas` branch
   ```
   /think Research async patterns in Rust
   /think What's the best way to implement caching?
   ```

2. **Serious Tasks** - Creates feature branch and PR, requires review (use `-p` flag)
   ```
   /think Add authentication to user service -p backend
   /think Refactor payment processing module -p payments
   ```

## 🛠️ Development

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

## 📊 Monitoring

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

## 🚢 Deployment

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

## 💡 Example Workflows

### Daily Brainstorm
```
/think Research new Rust async libraries
/think Compare Python web frameworks
/think Ideas for improving API performance
/check
```

### Production Fix
```
/think Fix authentication bug in login endpoint -p backend
/report <id>     # Get the PR link
# Review and merge PR
```

### Code Audit
```
/think Security audit of user service -p backend
/think Performance analysis of payment module -p payments
```

## 🔍 Troubleshooting

| Issue | Solution |
|-------|----------|
| Bot not responding | Check `.env` tokens, verify Socket Mode enabled, check logs: `tail -f workspace/data/agent.log` |
| Tasks not executing | Verify Claude Code CLI installed: `npm list -g @anthropic-ai/claude-code`, check workspace permissions |
| Tasks paused (threshold reached) | Usage has reached time-based threshold (20% daytime / 80% nighttime). Wait for window reset (check logs for reset time), or adjust thresholds in `config.yaml` (`claude_code.threshold_day` / `claude_code.threshold_night`). Run `sle check` to see current usage. |
| Git commits fail | Install `gh` CLI and authenticate: `gh auth login` |
| Out of credits | Wait for 5-hour window refresh. Review scheduler logs: `tail -f workspace/data/agent.log | grep credit` |
| Database locked | Close other connections, try: `rm workspace/data/tasks.db && python -m sleepless_agent.daemon` |

## ⚡ Performance Tips

1. **Use thoughts to fill idle time** - Maximizes usage
2. **Batch serious tasks** - Reduces context switching
3. **Monitor credits** - Watch scheduler logs for window resets
4. **Review git history** - Check `thought-ideas` branch regularly
5. **Check metrics** - Run `sle check` to track performance

## 🔒 Security Notes

- Secrets are validated before git commits
- Python syntax checked before commits
- Directory traversal prevented in file operations
- .env file never committed to git
- Workspace changes validated before applying

## 📦 Releases

- Latest stable: **0.1.0** – published on [PyPI](https://pypi.org/project/sleepless-agent/0.1.0/)
- Install or upgrade with `pip install -U sleepless-agent`
- Release notes tracked via GitHub Releases (tag `v0.1.0` onward)

## 📄 License

Released under the [MIT License](LICENSE)
