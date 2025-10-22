# Sleepless Agent

A 24/7 AI assistant daemon that continuously works on tasks via Slack. Uses Claude Code CLI to process both random thoughts and serious jobs automatically with isolated workspaces.

## About
- Maintained by Context Machine Lab
- Ships as `sleepless-agent` on PyPI (`pip install sleepless-agent`)
- Automates task intake, execution, and reporting via Slack + Claude integration
- Designed for continuous operation with isolated workspaces and automated git hygiene

## Features

- 🤖 **Continuous Operation**: Runs 24/7 daemon, always ready for new tasks
- 💬 **Slack Integration**: Submit tasks via Slack commands
- 🎯 **Hybrid Autonomy**: Auto-applies random thoughts, requires review for serious jobs
- ⚡ **Smart Scheduling**: Optimizes task execution based on priorities
- 📊 **Task Queue**: SQLite-backed persistent task management
- 🔌 **Claude Code CLI**: Uses Claude Code for code generation, research, documentation, etc.
- 🏗️ **Isolated Workspaces**: Each task gets its own workspace for true parallelism
- 📝 **Result Storage**: All outputs saved with metadata for future reference

## Quick Start

### 1. Install

```bash
pip install sleepless-agent
```

### 2. Setup Slack App

1. Go to [api.slack.com/apps](https://api.slack.com/apps)
2. Create a new app or use existing workspace
3. Enable Socket Mode
4. Add these scopes to your bot:
   - `chat:write`
   - `slash_commands`
   - `app_mentions:read`
5. Create slash commands:
   - `/task` - Add new task
   - `/status` - Check queue status
   - `/results` - Get task results
   - `/priority` - Change task priority
   - `/cancel` - Cancel pending task
6. Get your tokens:
   - `SLACK_BOT_TOKEN`: Slack bot token (starts with `xoxb-`)
   - `SLACK_APP_TOKEN`: Slack app token (starts with `xapp-`)

### 3. Configure Environment

Set your Slack tokens as environment variables:

```bash
export SLACK_BOT_TOKEN="xoxb-..."
export SLACK_APP_TOKEN="xapp-..."
```

Or create a `.env` file in your working directory with the above variables.

### 4. Run

```bash
# Terminal 1: Start the daemon
python -m sleepless_agent.daemon

# Terminal 2 (optional): Monitor logs
tail -f logs/agent.log
```

## Releases
- Latest stable: **0.1.0** – published on [PyPI](https://pypi.org/project/sleepless-agent/0.1.0/)
- Install or upgrade with `pip install -U sleepless-agent`
- Release notes and changelog are tracked via GitHub Releases (tag `v0.1.0` onward)

## Slack Commands

### Task Management

**Add Task**
```
/task Analyze this Python code for performance issues
/task Add OAuth2 support to user service --serious
```
- Default: random priority
- Add `--serious` flag for high-priority tasks requiring review

**Check Status**
```
/status
```
Shows: pending, in-progress, completed, failed counts

**Get Results**
```
/results 42
```
Shows output and metadata from task #42

**Change Priority**
```
/priority 15 serious
/priority 20 random
```
Move tasks between queues

**Cancel Task**
```
/cancel 5
```
Cancel pending tasks only

### Monitoring

**Credit Status** (5-hour windows)
```
/credits
```
Shows: tasks executed, time remaining, queue capacity

**System Health**
```
/health
```
Shows: status, uptime, CPU, memory, database, storage

**Performance Metrics**
```
/metrics
```
Shows: success rate, avg duration, total processing time

## Architecture

```
Slack Bot
    ↓
Slack Commands → Task Queue (SQLite)
    ↓
Agent Daemon (Event Loop)
    ↓
Claude Executor (API)
    ↓
Result Manager (Storage + Git)
```

### Components

- **daemon.py**: Main event loop, task orchestration
- **bot.py**: Slack interface, command parsing
- **task_queue.py**: Task CRUD, priority scheduling
- **claude_code_executor.py**: Claude Code CLI wrapper with isolated workspace management
- **results.py**: Result storage, file management
- **models.py**: SQLAlchemy models for Task, Result
- **config.py**: Configuration management

## Task Types

The agent intelligently processes different task types:

1. **Code** - Code generation, refactoring, bug fixes
2. **Research** - Investigating libraries, documentation
3. **Brainstorm** - Creative ideation, design discussions
4. **Documentation** - Writing docs, tutorials, guides
5. **General** - Anything else

## Configuration

Edit `config.yaml` to customize:

```yaml
agent:
  max_parallel_tasks: 3        # Concurrent tasks
  task_timeout_seconds: 3600   # 1 hour per task

claude:
  model: claude-opus-4-1-20250805
  max_tokens: 4096

scheduler:
  serious_job_priority: 100
  random_thought_priority: 10
  max_retries: 3
```

## Development

### Add New Task Type

Edit `src/claude_executor.py` TASK_PROMPTS dict:

```python
TASK_PROMPTS = {
    "custom_type": """Your custom prompt template with {description}""",
}
```

### Database Schema

Tasks are stored with:
- `id`: Auto-incremented task ID
- `description`: Task text
- `priority`: "random" or "serious"
- `status`: "pending", "in_progress", "completed", "failed"
- `created_at`, `started_at`, `completed_at`: Timestamps
- `result_id`: Link to Result record

### Monitoring

Check logs:
```bash
tail -f logs/agent.log
```

Check database:
```bash
sqlite3 data/tasks.db "SELECT * FROM tasks;"
```

## Implementation Phases

✅ **Phase 1** - Foundation
- Task queue with SQLite
- Slack bot with basic commands
- Claude Code CLI integration
- Result storage with workspace tracking

✅ **Phase 2** - Isolated Workspaces
- Per-task workspace creation
- File modification tracking
- Claude Code subprocess management
- Timeout and error handling

✅ **Phase 3** - Smart Scheduling
- Credit tracking per 5-hour window
- Priority-based task queue (serious vs random)
- Parallel task execution (configurable)
- Queue capacity management

✅ **Phase 4** - Git Integration
- Auto-commits for random thoughts to `random-ideas` branch
- Feature branch creation for serious tasks
- PR creation with `gh` CLI
- Safety validation (secrets, syntax checking)

✅ **Phase 5** - Monitoring & Polish
- Health checks (CPU, memory, disk)
- Performance metrics logging (JSONL format)
- Slack commands: `/health`, `/metrics`, `/credits`
- Auto-recovery and graceful shutdown

## Troubleshooting

**Bot not responding to commands?**
- Check Slack app tokens in .env
- Verify Socket Mode is enabled
- Check logs: `tail -f logs/agent.log`

**Tasks not executing?**
- Verify Claude Code CLI is installed: `claude --version`
- Check Claude Code is in PATH or set CLAUDE_CODE_BINARY_PATH
- Review error messages in logs
- Check workspace permissions

**Database locked?**
- Close all other connections to tasks.db
- Try: `rm data/tasks.db && python -m sleepless_agent.daemon`

## License
- Released under the [MIT License](LICENSE)
