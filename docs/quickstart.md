# Quickstart Guide

Get Sleepless Agent running in 5 minutes! This guide covers the minimal setup needed to start processing tasks.

## Prerequisites

Before starting, ensure you have:

- ✅ Python 3.11+ installed
- ✅ Node.js 16+ installed
- ✅ Slack workspace access
- ✅ Claude Code CLI installed

## Step 1: Install Claude Code CLI

```bash
npm install -g @anthropic-ai/claude-code
```

Verify installation:
```bash
claude --version
```

## Step 2: Install Sleepless Agent

```bash
pip install sleepless-agent
```

Or from source:
```bash
git clone https://github.com/context-machine-lab/sleepless-agent
cd sleepless-agent
pip install -e .
```

## Step 3: Quick Slack Setup

1. Visit [https://api.slack.com/apps](https://api.slack.com/apps)
2. Click "Create New App" → "From scratch"
3. Name it "Sleepless Agent" and select your workspace

### Enable Socket Mode
- Go to Settings → Socket Mode → Enable
- Create an app-level token (name: "sleepless-token")
- Save the `xapp-...` token

### Add Slash Commands
Go to Features → Slash Commands and create:
- `/think` - Submit tasks
- `/check` - Check status

### Set Bot Permissions
Features → OAuth & Permissions → Bot Token Scopes:
- `chat:write`
- `commands`

### Install to Workspace
- Click "Install to Workspace"
- Save the `xoxb-...` bot token

## Step 4: Configure Environment

Create a `.env` file:

```bash
# Required Slack tokens
SLACK_BOT_TOKEN=xoxb-your-bot-token-here
SLACK_APP_TOKEN=xapp-your-app-token-here

# Optional: Custom workspace location
AGENT_WORKSPACE=./workspace
```

## Step 5: Start the Agent

```bash
sle daemon
```

You should see:
```
2025-10-24 23:30:12 | INFO | Sleepless Agent starting...
2025-10-24 23:30:12 | INFO | Slack bot started and listening for events
```

## Step 6: Test Your Setup

In Slack, try these commands:

```
/think Research Python async patterns
/check
```

The agent should acknowledge your task and show the queue status.

## What's Next?

### Essential Configuration

1. **Set up Git integration** for automated commits:
   ```bash
   git config --global user.name "Sleepless Agent"
   git config --global user.email "agent@sleepless.local"
   ```

2. **Configure Pro plan thresholds** in `config.yaml`:
   ```yaml
   claude_code:
     threshold_day: 20.0    # Pause at 20% during day
     threshold_night: 80.0  # Pause at 80% at night
   ```

3. **Set working hours** for optimal usage:
   ```yaml
   claude_code:
     night_start_hour: 20  # 8 PM
     night_end_hour: 8     # 8 AM
   ```

### Recommended Next Steps

- 📖 Read the [Architecture Overview](concepts/architecture.md)
- 🔧 Complete [Slack Setup](guides/slack-setup.md) for all features
- 🎯 Try the [First Task Tutorial](tutorials/first-task.md)
- 📊 Learn about [Task Management](guides/project-management.md)

## Common Issues

### Agent not responding in Slack?
- Verify Socket Mode is enabled
- Check both tokens are correct in `.env`
- Ensure the bot is in your channel

### Tasks not executing?
- Run `claude --version` to verify CLI installation
- Check `sle check` for usage limits
- Review logs: `tail -f workspace/data/agent.log`

### Usage threshold reached?
- Agent pauses at configured thresholds
- Wait for 5-hour window reset
- Adjust thresholds in `config.yaml` if needed

## Getting Help

- 💬 [Discord Community](https://discord.gg/74my3Wkn)
- 📚 [Full Documentation](index.md)
- 🐛 [Report Issues](https://github.com/context-machine-lab/sleepless-agent/issues)

---

🎉 **Congratulations!** You now have a 24/7 AI agent working for you. Check out the [tutorials](tutorials/first-task.md) to learn more advanced features.