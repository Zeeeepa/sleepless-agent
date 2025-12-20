# Slack Setup Guide

Complete step-by-step guide to set up Slack integration for Sleepless Agent.

## Prerequisites

Before starting:
- Admin access to your Slack workspace
- Sleepless Agent installed locally
- Understanding of [basic concepts](../concepts/architecture.md)

## Step 1: Create a New Slack App

### 1.1 Navigate to Slack API

1. Go to [https://api.slack.com/apps](https://api.slack.com/apps)
2. Click **"Create New App"**
3. Choose **"From scratch"**

### 1.2 Configure Basic Information

```
App Name: Sleepless Agent
Pick a workspace: [Your Workspace]
```

Click **"Create App"**

### 1.3 App Configuration

In the **Basic Information** page:

1. Add an app icon (optional but recommended)
2. Add a description:
   ```
   24/7 AI agent that processes tasks autonomously using Claude Code
   ```
3. Set the background color: `#7C3AED` (purple)

## Step 2: Enable Socket Mode

Socket Mode allows real-time communication without exposing a public endpoint.

### 2.1 Enable Socket Mode

1. Go to **Settings → Socket Mode**
2. Toggle **Enable Socket Mode** to ON
3. You'll be prompted to create an app-level token

### 2.2 Create App Token

```
Token Name: sleepless-token
Scope: connections:write
```

Click **Generate**

⚠️ **Save this token!** It starts with `xapp-` and you'll need it for your `.env` file.

## Step 3: Configure Slash Commands

### 3.1 Navigate to Slash Commands

Go to **Features → Slash Commands**

### 3.2 Create Commands

Create each command by clicking **"Create New Command"**:

#### /think Command
```
Command: /think
Request URL: [Leave empty - Socket Mode handles this]
Short Description: Submit a task or thought
Usage Hint: [description] [-p project_name]
```

#### /check Command
```
Command: /check
Request URL: [Leave empty]
Short Description: Check system status and queue
Usage Hint: [no arguments]
```

#### /report Command
```
Command: /report
Request URL: [Leave empty]
Short Description: View task reports
Usage Hint: [task_id | date | project_name | --list]
```

#### /cancel Command
```
Command: /cancel
Request URL: [Leave empty]
Short Description: Cancel a task or project
Usage Hint: <task_id | project_name>
```

#### /trash Command
```
Command: /trash
Request URL: [Leave empty]
Short Description: Manage cancelled tasks
Usage Hint: <list | restore <id> | empty>
```

#### /usage Command
```
Command: /usage
Request URL: [Leave empty]
Short Description: Show Claude Code Pro plan usage
Usage Hint: [Leave empty]
```

#### /chat Command
```
Command: /chat
Request URL: [Leave empty]
Short Description: Start interactive chat mode with Claude
Usage Hint: <project_name> | end | status | help
```

## Step 4: Set OAuth Scopes

### 4.1 Navigate to OAuth & Permissions

Go to **Features → OAuth & Permissions**

### 4.2 Bot Token Scopes

Add these scopes:

| Scope | Purpose |
|-------|---------|
| `chat:write` | Send messages to channels |
| `chat:write.public` | Send messages to public channels without joining |
| `commands` | Receive slash commands |
| `app_mentions:read` | Respond to @mentions |
| `channels:read` | List channels |
| `channels:history` | Read message history (required for chat mode) |
| `groups:read` | Access private channels |
| `groups:history` | Read private channel history (required for chat mode) |
| `im:read` | Read direct messages |
| `im:write` | Send direct messages |
| `im:history` | Read DM history (required for chat mode) |
| `users:read` | Get user information |
| `reactions:write` | Add emoji reactions (for chat mode indicators) |

### 4.3 User Token Scopes (Optional)

These are optional but useful:

| Scope | Purpose |
|-------|---------|
| `files:write` | Upload files (for reports) |
| `files:read` | Read uploaded files |

## Step 5: Event Subscriptions

### 5.1 Enable Events

Go to **Features → Event Subscriptions**

Toggle **Enable Events** to ON

### 5.2 Subscribe to Bot Events

Add these bot events:

| Event | Purpose |
|-------|---------|
| `app_mention` | Respond when bot is mentioned |
| `message.channels` | Monitor channel messages (**required for chat mode**) |
| `message.groups` | Monitor private channel messages (**required for chat mode**) |
| `message.im` | Respond to direct messages |

> ⚠️ **Important for Chat Mode**: The `message.channels` and `message.groups` events are required for chat mode to receive messages in threads. Without these, chat mode will not work.

### 5.3 Event URL

Since we're using Socket Mode, leave the Request URL empty.

## Step 6: Install to Workspace

### 6.1 Install App

1. Go to **Settings → Install App**
2. Click **"Install to Workspace"**
3. Review permissions
4. Click **"Allow"**

### 6.2 Save Bot Token

After installation, you'll see a **Bot User OAuth Token**.

⚠️ **Save this token!** It starts with `xoxb-` and you'll need it for your `.env` file.

## Step 7: Configure Sleepless Agent

### 7.1 Create Environment File

```bash
# Create .env file
cp .env.example .env
```

### 7.2 Add Slack Tokens

Edit `.env`:

```bash
# Slack Configuration (Required)
SLACK_BOT_TOKEN=xoxb-your-bot-token-here
SLACK_APP_TOKEN=xapp-your-app-token-here

# Optional: Default channel for notifications
SLACK_DEFAULT_CHANNEL=general
```

### 7.3 Verify Configuration

```bash
# Test Slack connection
sle test-slack

# Should output:
# ✓ Slack bot token valid
# ✓ Slack app token valid
# ✓ Socket Mode connected
# ✓ Bot user: @sleepless-agent
```

## Step 8: Channel Setup

### 8.1 Add Bot to Channels

For each channel where you want to use the bot:

1. Go to the channel in Slack
2. Type: `/invite @sleepless-agent`
3. The bot will join the channel

### 8.2 Set Channel Permissions

For private channels:
1. Channel Details → Integrations
2. Add App → Sleepless Agent
3. Click Add

### 8.3 Configure Default Channels

In `config.yaml`:

```yaml
slack:
  default_channel: general
  error_channel: sleepless-errors
  report_channel: sleepless-reports
  notification_channels:
    - general
    - dev-team
```

## Step 9: Test the Integration

### 9.1 Start the Agent

```bash
sle daemon
```

You should see:
```
INFO | Slack bot started and listening for events
INFO | Sleepless Agent starting...
```

### 9.2 Test Commands in Slack

Try these commands:

```
/check
# Should show system status

/think Test task from Slack
# Should acknowledge and queue task

/report --list
# Should list available reports
```

### 9.3 Test Chat Mode

Try the interactive chat mode:

```
/chat my-project
# Should create a thread with welcome message

# In the thread, send a message:
"What files are in this project?"
# Claude should respond in the thread

# End the session:
exit
# Or use /chat end
```

## Chat Mode Usage

### Starting a Chat Session

```
/chat <project-name>
```

This creates:
- A new Slack thread for the conversation
- A project folder at `workspace/projects/<project-name>/`
- A session that maintains conversation history

### Chat Mode Commands

| Command | Description |
|---------|-------------|
| `/chat <project>` | Start chat mode for a project |
| `/chat end` | End current chat session |
| `/chat status` | Show current session info |
| `/chat help` | Show help |

### In-Thread Commands

While in a chat thread, you can:
- Send any message to interact with Claude
- Type `exit`, `end`, or `quit` to end the session
- Claude can read, write, and edit files in the project workspace

### Visual Indicators

| Indicator | Meaning |
|-----------|---------|
| 💬 (reaction) | Chat session is active |
| 🔄 Processing... | Claude is working on your request |
| ✅ (reaction) | Chat session has ended |

### Session Timeout

Sessions automatically end after 30 minutes of inactivity.

## Advanced Configuration

### Custom Emoji Reactions

Add custom emoji for task status:

```yaml
slack:
  reactions:
    pending: hourglass
    in_progress: gear
    completed: white_check_mark
    failed: x
```

### Thread Management

Configure threading behavior:

```yaml
slack:
  threading:
    enabled: true
    reply_in_thread: true
    broadcast_important: true
```

### Rate Limiting

Prevent Slack rate limit issues:

```yaml
slack:
  rate_limiting:
    max_messages_per_minute: 20
    retry_after: 60
    backoff_multiplier: 2
```

## Troubleshooting

### Bot Not Responding

1. **Check Socket Mode is enabled**
   ```bash
   # In Slack App settings
   Settings → Socket Mode → Should be ON
   ```

2. **Verify tokens**
   ```bash
   # Check .env file
   cat .env | grep SLACK
   ```

3. **Check bot status**
   ```bash
   # In terminal running daemon
   # Should show "listening for events"
   ```

### Commands Not Working

1. **Reinstall slash commands**
   - Delete and recreate each command
   - Reinstall app to workspace

2. **Check permissions**
   - Ensure all required scopes are added
   - Reinstall if scopes were changed

3. **Verify Socket Mode connection**
   ```bash
   sle test-slack --verbose
   ```

### Permission Errors

1. **Bot not in channel**
   ```
   /invite @sleepless-agent
   ```

2. **Missing scopes**
   - Add required scopes in OAuth & Permissions
   - Reinstall app after scope changes

3. **Private channel access**
   - Manually add app in channel settings

## Security Best Practices

### 1. Token Management

- Never commit tokens to Git
- Use environment variables only
- Rotate tokens periodically
- Restrict token access

### 2. Channel Restrictions

```yaml
slack:
  allowed_channels:
    - general
    - dev-team
  blocked_channels:
    - sensitive-data
  require_mention: true  # Only respond to @mentions
```

### 3. User Permissions

```yaml
slack:
  authorized_users:
    - U0123456789  # User IDs
    - U9876543210
  admin_users:
    - U0123456789
```

### 4. Audit Logging

```yaml
slack:
  audit:
    log_commands: true
    log_users: true
    retention_days: 90
```

## Monitoring Integration

### 1. Slack Metrics

Track Slack-specific metrics:

```python
def collect_slack_metrics():
    return {
        'commands_received': count_commands(),
        'response_time': avg_response_time(),
        'active_channels': count_active_channels(),
        'error_rate': calculate_error_rate()
    }
```

### 2. Health Checks

```yaml
monitoring:
  slack_health:
    check_interval: 60  # seconds
    timeout: 10
    alert_on_failure: true
```

### 3. Error Notifications

Configure error handling:

```yaml
slack:
  errors:
    notify_channel: sleepless-errors
    include_stacktrace: false
    rate_limit: 5  # Max 5 error messages per hour
```

## Next Steps

Now that Slack is configured:

1. [Configure environment variables](environment-setup.md)
2. [Set up Git integration](git-integration.md)
3. [Try your first task](../tutorials/first-task.md)
4. [Learn Slack workflows](../tutorials/slack-workflows.md)

## Additional Resources

- [Slack API Documentation](https://api.slack.com)
- [Socket Mode Guide](https://api.slack.com/apis/connections/socket)
- [Slash Commands Reference](https://api.slack.com/interactivity/slash-commands)
- [Bot Permissions](https://api.slack.com/scopes)