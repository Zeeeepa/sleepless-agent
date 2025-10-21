# Sleepless Agent - Quick Reference

## Commands

### 📋 Task Management
| Command | Purpose | Example |
|---------|---------|---------|
| `/task` | Add task | `/task Add OAuth2 support --serious` |
| `/status` | Queue status | `/status` |
| `/results` | Get task output | `/results 42` |
| `/priority` | Change priority | `/priority 15 serious` |
| `/cancel` | Cancel task | `/cancel 5` |

### 💳 Credits & Scheduling
| Command | Purpose | Example |
|---------|---------|---------|
| `/credits` | Credit window status | `/credits` |
| `/health` | System health | `/health` |
| `/metrics` | Performance stats | `/metrics` |

## Setup (5 minutes)

```bash
# 1. Install
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# 2. Configure
cp .env.example .env
nano .env  # Add SLACK and ANTHROPIC tokens

# 3. Run
python -m src.daemon
```

## Slack App Setup

1. api.slack.com/apps → Create New App
2. Enable Socket Mode (Settings > Socket Mode)
3. Add OAuth scopes: `chat:write`, `commands`, `app_mentions:read`
4. Create slash commands: `/task`, `/status`, `/results`, `/priority`, `/cancel`, `/credits`, `/health`, `/metrics`
5. Install app to workspace
6. Copy tokens to .env

## Task Types

| Type | Command | Behavior |
|------|---------|----------|
| **Random Thought** | `/task idea` | Auto-commits to `random-ideas` branch |
| **Serious Job** | `/task work --serious` | Creates PR on feature branch, requires review |

## Architecture

```
Slack → SlackBot → TaskQueue (SQLite)
                ↓
         Daemon Event Loop
         ↓
    ClaudeExecutor + Tools
         ↓
    GitManager + ResultManager
         ↓
    HealthMonitor + Metrics
```

## Files Structure

```
src/
├── daemon.py          Main event loop
├── bot.py             Slack interface
├── task_queue.py      Task management
├── claude_executor.py Claude API + tools
├── tools.py           File/bash operations
├── scheduler.py       Smart scheduling
├── git_manager.py     Git automation
├── monitor.py         Health & metrics
├── models.py          Database models
├── config.py          Config management
├── results.py         Result storage
```

## Configuration

**Key settings in config.yaml:**
```yaml
agent:
  max_parallel_tasks: 3        # 1-10 concurrent
  task_timeout_seconds: 3600   # Per task

claude:
  model: claude-opus-4-1-20250805
  max_tokens: 4096

credits:
  window_size_hours: 5
  max_tasks_per_window: 10
```

## Monitoring

```bash
# Live logs
tail -f logs/agent.log

# Database query
sqlite3 data/tasks.db "SELECT * FROM tasks WHERE status='completed';"

# Performance
tail logs/metrics.jsonl | jq .

# Slack commands
/health          # System status
/metrics         # Performance stats
/credits         # Credit window
```

## Deployment

**Linux (systemd):**
```bash
make install-service
sudo systemctl start sleepless-agent
```

**macOS (launchd):**
```bash
make install-launchd
# Verify: launchctl list | grep sleepless
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Bot not responding | Check `.env`, verify Socket Mode enabled, check logs |
| Tasks fail | Verify Claude API key, check workspace permissions |
| Git commits fail | Install `gh` CLI and authenticate |
| Out of credits | Wait for 5-hour window refresh |

## Make Commands

```bash
make help              # Show all commands
make setup             # Install dependencies
make run               # Run daemon
make dev               # Run with debug
make logs              # Follow logs
make db                # Query database
make db-reset          # Clear database
make status            # Check agent status
make stats             # Show metrics
make backup            # Backup data
```

## Metrics

The agent tracks:
- Tasks completed/failed (success rate)
- Average processing time per task
- System resources (CPU, memory, disk)
- Database health
- Uptime and operational statistics

View with: `/metrics` or `tail logs/metrics.jsonl`

## Tools Available to Claude

When processing tasks, Claude can:
- **read_file** - Read code/documents
- **write_file** - Create new files
- **edit_file** - Modify existing files
- **bash** - Execute shell commands
- **list_files** - Browse directories
- **search_files** - Find files
- **get_file_info** - File metadata

## Example Workflows

### Daily Brainstorm
```
/task Research new Rust async libraries
/task Compare Python web frameworks
/task Ideas for improving API performance
/status
```

### Production Fix
```
/task Fix authentication bug in login endpoint --serious
/results <id>    # Get the PR link
# Review and merge PR
```

### Code Audit
```
/task Security audit of user service --serious
/task Performance analysis of payment module --serious
/credits         # Monitor window usage
```

## Environment Variables

```bash
# Required
ANTHROPIC_API_KEY=sk-ant-...
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

## Performance Tips

1. **Use random thoughts to fill idle time** - Maximizes API usage
2. **Batch serious jobs** - Reduces context switching
3. **Monitor credits** - Use `/credits` frequently
4. **Review git history** - Check `random-ideas` branch regularly
5. **Check metrics** - Use `/metrics` to track performance

## Security Notes

- Secrets are validated before git commits
- Python syntax checked before commits
- Directory traversal prevented in file operations
- .env file never committed to git
- Workspace changes validated before applying

## Next Steps

1. Read GETTING_STARTED.md for detailed setup
2. Configure .env with your tokens
3. Run: `python -m src.daemon`
4. Test commands in Slack
5. Deploy as service using Makefile
6. Monitor with `/health` and `/metrics`

---

For questions, check README.md or GETTING_STARTED.md
