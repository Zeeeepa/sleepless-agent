# Sleepless Agent - Getting Started Guide

Welcome! Here's how to get your 24/7 AI assistant up and running.

## 5-Minute Setup

### 1. Prerequisites
- Python 3.11+
- Slack workspace admin access
- Claude API key (from Anthropic)
- Git (for auto-commits)
- gh CLI (optional, for PR automation)

### 2. Install Dependencies
```bash
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt
```

### 3. Create Slack Bot

Visit https://api.slack.com/apps and create a new app:

**1. Basic Information**
- Choose "From scratch"
- Name: "Sleepless Agent"
- Pick your workspace

**2. Enable Socket Mode**
- Settings > Socket Mode > Toggle ON
- Generate app token (starts with `xapp-`)

**3. Create Slash Commands**
Settings > Slash Commands > Create New Command

Add these commands:
- `/task` → Request URL: (leave empty for Socket Mode)
- `/think`
- `/status`
- `/results`
- `/credits`
- `/health`
- `/metrics`
- `/priority`
- `/cancel`

**4. OAuth Scopes**
Features > OAuth & Permissions > Scopes > Bot Token Scopes

Add:
- `chat:write`
- `commands`
- `app_mentions:read`

**5. Install App**
Install to workspace, get bot token (starts with `xoxb-`)

### 4. Configure Agent

```bash
cp .env.example .env
nano .env  # Edit with your tokens
```

Fill in:
- `ANTHROPIC_API_KEY` - Your Claude API key
- `SLACK_BOT_TOKEN` - xoxb-... token
- `SLACK_APP_TOKEN` - xapp-... token

### 5. Run Agent

```bash
sleepless daemon
```

You should see:
```
INFO - Slack bot started and listening for events
INFO - Sleepless Agent starting...
```

## Using the Agent

### Task Priorities

**Random Thoughts** (default)
```
/think Research async patterns in Rust
/think What's the best way to implement caching?
```
- Auto-committed to `random-ideas` branch
- Fills idle time when no serious tasks pending

**Serious Jobs** (high priority)
```
/task Add authentication to user service
/task Refactor payment processing module
```
- Creates feature branch: `task/{id}-{description}`
- Creates pull request when complete
- Requires review before merge

### Example Workflow

**Morning Check:**
```
/status        # See overnight progress
/health        # Check system status
/metrics       # View performance
```

**Throughout Day:**
```
/task Fix bug in authentication flow
/think Analyze database query performance
/think Should we migrate to async/await?
```

**Check Results:**
```
/results 42    # Get task #42 output
/credits       # See credit usage
```

### Command Line Interface

The CLI offers the same capabilities without Slack:

```bash
python -m sleepless_agent.interfaces.cli status
# After installation:
sleepless task "Draft onboarding plan"
```

CLI commands mirror the slash commands:

| Command | Purpose |
|---------|---------|
| `task <description>` | Queue a serious task |
| `think <description>` | Log a random thought |
| `status` | Show queue snapshot |
| `results <id>` | Inspect task status and errors |
| `priority <id> random|serious` | Update priority |
| `cancel <id>` | Cancel a pending task |
| `credits [--hours N]` | Summarize recent executions |
| `health` | Run system health checks |
| `metrics` | View aggregated performance metrics |

Use flags to target alternate storage locations when scripting:

```bash
sleepless --db-path ./data/tasks.db --results-path ./data/results status
```

## Architecture Overview

```
┌─────────────────────────────────────────┐
│         Slack Interface                 │
│  /task /status /results /priority ...   │
└────────────────────┬────────────────────┘
                     │
        ┌────────────▼────────────┐
        │    SlackBot (Socket)    │
        └────────────┬────────────┘
                     │
        ┌────────────▼────────────┐
        │   Task Queue (SQLite)   │
        │  Pending → Running →    │
        │  Completed ← Failed     │
        └────────────┬────────────┘
                     │
        ┌────────────▼────────────┐
        │    Daemon Event Loop    │
        │   - Process Tasks       │
        │   - Monitor Health      │
        │   - Track Credits       │
        └────────────┬────────────┘
                     │
    ┌────────────────┼────────────────┐
    │                │                │
┌───▼──┐      ┌──────▼────┐     ┌────▼───┐
│Claude│      │Git Manager│     │Monitor │
│ API  │      │ - Commits │     │-Health │
│      │      │ - PRs     │     │-Metrics│
└───▼──┐      └──────▼────┘     └────▼───┘
    │                │                │
    └────────────────┼────────────────┘
                     │
            ┌────────▼────────┐
            │Results Storage  │
            │- Database       │
            │- Files          │
            │- Git history    │
            └─────────────────┘
```

## File Structure

```
sleepless-agent/
├── src/
│   ├── daemon.py           # Main event loop
│   ├── bot.py              # Slack interface
│   ├── task_queue.py       # Task management
│   ├── claude_executor.py  # Claude API wrapper
│   ├── tools.py            # File/bash operations
│   ├── scheduler.py        # Smart scheduling
│   ├── git_manager.py      # Git automation
│   ├── monitor.py          # Health & metrics
│   ├── models.py           # Database models
│   ├── config.py           # Config management
│   ├── results.py          # Result storage
│   └── __init__.py
├── data/
│   ├── tasks.db            # SQLite database
│   └── results/            # Task output files
├── workspace/              # Agent working dir
├── logs/                   # Log files
├── config.yaml             # Configuration
├── .env                    # Secrets
├── requirements.txt        # Python deps
└── README.md
```

## Configuration

Edit `config.yaml` to customize:

```yaml
agent:
  max_parallel_tasks: 3        # 1-10 concurrent tasks
  task_timeout_seconds: 3600   # How long per task

claude:
  model: claude-opus-4-1-20250805  # Model choice
  max_tokens: 4096             # Response length

credits:
  track_windows: true
  window_size_hours: 5         # Assumes 5h refresh
  max_tasks_per_window: 10

scheduler:
  serious_job_priority: 100
  random_thought_priority: 10
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

### Check Health
```bash
/health
```

## Common Tasks

### Process All Random Thoughts
```
/think Some interesting idea 1
/think Some interesting idea 2
/think Some interesting idea 3
/status              # Monitor progress
/credits             # Check credit usage
```

### Submit Serious Job with Context
```
/task Add comprehensive error handling to API service
# Agent reads codebase, understands context, writes implementation
/results 15          # Get task #15 output
# Review the PR that was created
```

### Change Task Priority
```
/status              # Find task ID
/priority 7 serious  # Promote to serious
/priority 8 random   # Demote to random
```

## Advanced Features

### Tool Use in Action

When Claude processes a task, it can:
1. **Read code** - Understand existing implementations
2. **Analyze files** - Search across codebase
3. **Write code** - Create new files or modify existing
4. **Run commands** - Execute tests, build, deploy
5. **Check results** - Validate changes before committing

### Smart Scheduling

The scheduler:
- Fills idle time with random thoughts
- Prioritizes serious jobs during peak hours
- Tracks credits per 5-hour window
- Manages parallel execution intelligently

### Git Integration

**For Random Thoughts:**
```
Auto-commit to random-ideas branch
Filename: idea_{task_id}_{timestamp}.md
```

**For Serious Jobs:**
```
1. Create branch: task/{id}-{description}
2. Apply changes
3. Validate (no secrets, no syntax errors)
4. Commit with task metadata
5. Create PR with description
6. Link in Slack notification
```

## Troubleshooting

### Bot doesn't respond

**Check:**
```bash
# 1. Tokens in .env
cat .env | grep -E "SLACK|ANTHROPIC"

# 2. Bot is running
pgrep -f "sleepless_agent.daemon"

# 3. Logs
tail -50 logs/agent.log | grep ERROR

# 4. Socket Mode enabled in Slack app
# Settings > Socket Mode > Check toggle
```

### Tasks fail with tool errors

**Check workspace permissions:**
```bash
ls -la ./workspace
# Should be readable/writable

# Try manual tool test:
python -c "from sleepless_agent.tools import ToolExecutor; t = ToolExecutor('./workspace'); print(t.list_files())"
```

### Git commits fail

**Install gh CLI:**
```bash
# macOS
brew install gh

# Linux
sudo apt install gh

# Then authenticate
gh auth login
```

### Out of credits

**Wait for window to refresh** (5 hours from first task)

Check current window:
```
/credits    # Shows time remaining
```

## Next Steps

1. **Deploy as Service**
   ```bash
   # macOS (launchd)
   cp deployment/com.sleepless-agent.plist ~/Library/LaunchAgents/
   launchctl load ~/Library/LaunchAgents/com.sleepless-agent.plist

   # Linux (systemd)
   sudo cp deployment/sleepless-agent.service /etc/systemd/system/
   sudo systemctl enable sleepless-agent
   sudo systemctl start sleepless-agent
   ```

2. **Monitor Production**
   ```bash
   # Set up alerts for failures
   sleepless health        # Daily check
   sleepless metrics       # Weekly review
   ```

3. **Customize Task Types**
   - Edit `TASK_PROMPTS` in `claude_executor.py`
   - Add domain-specific instructions
   - Fine-tune for your workflow

4. **Extend Functionality**
   - Add custom tools in `tools.py`
   - Create new slash commands in `bot.py`
   - Implement plugins system

## Support

**Issues?**
- Check logs: `tail -f logs/agent.log`
- Review config: `cat config.yaml`
- Test Claude API: `python -c "from anthropic import Anthropic; print('OK')"`
- Verify Slack: Manually post in workspace

**Want to contribute?**
- Report issues on GitHub
- Submit PRs for improvements
- Share your customizations

## Credits

Built with ❤️ for maximizing Claude API usage.

Powered by:
- Claude API (Anthropic)
- Slack SDK
- SQLAlchemy
- GitPython
