# Environment Setup Guide

Comprehensive guide to configuring environment variables and settings for Sleepless Agent.

## Overview

Sleepless Agent uses environment variables for sensitive configuration and a YAML file for runtime settings.

```
Configuration Sources:
├── .env                 # Secrets and tokens
├── config.yaml          # Runtime configuration
└── Environment vars     # Override any setting
```

## Environment Variables (.env)

### 1. Create Environment File

```bash
# Copy template
cp .env.example .env

# Set restrictive permissions
chmod 600 .env
```

### 2. Required Variables

These variables **must** be set:

```bash
# Slack Integration (Required)
SLACK_BOT_TOKEN=xoxb-your-bot-token-here-replace-with-real-token
SLACK_APP_TOKEN=xapp-your-app-token-here-replace-with-real-token
```

### 3. Optional Variables

Customize behavior with these optional settings:

```bash
# Workspace Configuration
AGENT_WORKSPACE=./workspace              # Root workspace directory
AGENT_DB_PATH=./workspace/data/tasks.db  # Database location
AGENT_RESULTS_PATH=./workspace/data/results  # Results storage

# Git Configuration
GIT_USER_NAME=Sleepless Agent           # Git commit author name
GIT_USER_EMAIL=agent@sleepless.local    # Git commit author email
GIT_DEFAULT_BRANCH=main                 # Default branch name
GIT_REMOTE_URL=git@github.com:user/repo.git  # Remote repository

# Logging Configuration
SLEEPLESS_LOG_LEVEL=INFO               # DEBUG, INFO, WARNING, ERROR
SLEEPLESS_LOG_DIR=workspace/.logs      # Log file directory
SLEEPLESS_LOG_MAX_SIZE=10485760        # Max log size (10MB)
SLEEPLESS_LOG_BACKUP_COUNT=5           # Number of log backups

# Performance Settings
SLEEPLESS_MAX_WORKERS=5                # Max parallel tasks
SLEEPLESS_TASK_TIMEOUT=1800            # Task timeout (seconds)
SLEEPLESS_POLL_INTERVAL=250            # Queue poll interval (ms)

# Claude Configuration
CLAUDE_MODEL=claude-sonnet-4-5-20250929  # Model to use
CLAUDE_MAX_RETRIES=3                     # Retry attempts
CLAUDE_RETRY_DELAY=60                    # Retry delay (seconds)
```

### 4. Environment Variable Precedence

Variables are loaded in this order (later overrides earlier):

1. Default values in code
2. `config.yaml` file
3. `.env` file
4. System environment variables
5. Command-line arguments

Example:
```bash
# Override log level for single run
SLEEPLESS_LOG_LEVEL=DEBUG sle daemon
```

## Configuration File (config.yaml)

### 1. Location

The configuration file can be in:

```bash
# Priority order:
1. ./config.yaml          # Current directory
2. ~/.sleepless/config.yaml  # User home
3. /etc/sleepless/config.yaml  # System-wide
4. src/sleepless_agent/config.yaml  # Package default
```

### 2. Complete Configuration

```yaml
# Claude Code Configuration
claude_code:
  binary_path: claude           # Path to Claude CLI
  model: claude-sonnet-4-5-20250929
  night_start_hour: 20         # 8 PM
  night_end_hour: 8            # 8 AM
  threshold_day: 20.0          # Day usage limit (%)
  threshold_night: 80.0        # Night usage limit (%)
  usage_command: claude /usage  # Command to check usage
  max_retries: 3
  retry_delay: 60

# Git Integration
git:
  use_remote_repo: true
  remote_repo_url: git@github.com:username/repo.git
  auto_create_repo: true
  default_branch: main
  commit_message_format: "[Agent] {task_type}: {description}"
  auto_push: true
  create_pull_requests: true

# Agent Configuration
agent:
  workspace_root: ./workspace
  task_timeout_seconds: 1800   # 30 minutes
  max_concurrent_tasks: 5
  poll_interval_ms: 250
  cleanup_age_days: 7
  auto_cleanup: true

# Multi-Agent Workflow
multi_agent_workflow:
  planner:
    enabled: true
    max_turns: 3
    timeout: 300
  worker:
    enabled: true
    max_turns: 5
    timeout: 1200
  evaluator:
    enabled: true
    max_turns: 2
    timeout: 300

# Slack Configuration
slack:
  default_channel: general
  error_channel: sleepless-errors
  thread_replies: true
  rate_limit: 20  # messages per minute
  reactions:
    pending: hourglass
    in_progress: gear
    completed: white_check_mark
    failed: x

# Auto Task Generation
auto_generation:
  enabled: true
  min_queue_size: 3
  max_queue_size: 20
  generation_interval: 3600  # 1 hour
  types:
    - refine_code
    - write_tests
    - improve_docs
  prompts:
    - name: refine_focused
      weight: 0.4
      prompt: "Refine and improve existing code..."
    - name: test_generation
      weight: 0.3
      prompt: "Generate tests for untested code..."
    - name: documentation
      weight: 0.3
      prompt: "Improve documentation..."

# Monitoring
monitoring:
  metrics_enabled: true
  metrics_interval: 60  # seconds
  health_check_interval: 300
  alert_thresholds:
    queue_depth: 50
    error_rate: 0.1
    disk_usage_percent: 80
    memory_usage_percent: 85

# Logging
logging:
  level: INFO
  format: json  # json or text
  file_rotation: true
  max_size_mb: 10
  backup_count: 5
  include_timestamps: true
  include_context: true
```

## Environment-Specific Configurations

### 1. Development Environment

`.env.development`:
```bash
SLEEPLESS_LOG_LEVEL=DEBUG
SLEEPLESS_MAX_WORKERS=2
CLAUDE_MODEL=claude-sonnet-4-5-20250929
GIT_AUTO_PUSH=false
SLACK_DEFAULT_CHANNEL=dev-testing
```

`config.dev.yaml`:
```yaml
claude_code:
  threshold_day: 50.0    # More lenient for testing
  threshold_night: 90.0

agent:
  task_timeout_seconds: 600  # Shorter timeout
  cleanup_age_days: 1        # Aggressive cleanup

monitoring:
  metrics_interval: 10       # More frequent updates
```

### 2. Production Environment

`.env.production`:
```bash
SLEEPLESS_LOG_LEVEL=WARNING
SLEEPLESS_MAX_WORKERS=10
CLAUDE_MODEL=claude-sonnet-4-5-20250929
GIT_AUTO_PUSH=true
SLACK_DEFAULT_CHANNEL=production-alerts
```

`config.prod.yaml`:
```yaml
claude_code:
  threshold_day: 15.0    # Conservative
  threshold_night: 75.0

agent:
  task_timeout_seconds: 3600  # 1 hour
  max_concurrent_tasks: 8

monitoring:
  alert_thresholds:
    queue_depth: 20
    error_rate: 0.05
```

### 3. Testing Environment

`.env.test`:
```bash
SLEEPLESS_LOG_LEVEL=ERROR
SLEEPLESS_TEST_MODE=true
CLAUDE_MODEL=mock          # Use mock for testing
SLACK_BOT_TOKEN=xoxb-test
SLACK_APP_TOKEN=xapp-test
```

## Docker Configuration

### 1. Docker Environment

`docker-compose.yml`:
```yaml
version: '3.8'

services:
  sleepless-agent:
    image: sleepless-agent:latest
    env_file:
      - .env
    environment:
      - AGENT_WORKSPACE=/workspace
      - SLEEPLESS_LOG_DIR=/logs
    volumes:
      - ./workspace:/workspace
      - ./logs:/logs
      - ./config.yaml:/app/config.yaml:ro
    restart: unless-stopped
```

### 2. Docker Secrets

```yaml
version: '3.8'

secrets:
  slack_bot_token:
    external: true
  slack_app_token:
    external: true

services:
  sleepless-agent:
    image: sleepless-agent:latest
    secrets:
      - slack_bot_token
      - slack_app_token
    environment:
      - SLACK_BOT_TOKEN_FILE=/run/secrets/slack_bot_token
      - SLACK_APP_TOKEN_FILE=/run/secrets/slack_app_token
```

## Cloud Deployment

### 1. AWS Systems Manager

Store sensitive variables in Parameter Store:

```bash
# Store tokens
aws ssm put-parameter \
  --name /sleepless/slack_bot_token \
  --value "xoxb-..." \
  --type SecureString

# Retrieve in application
aws ssm get-parameter \
  --name /sleepless/slack_bot_token \
  --with-decryption
```

### 2. Kubernetes ConfigMaps & Secrets

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: sleepless-secrets
type: Opaque
data:
  slack-bot-token: <base64-encoded-token>
  slack-app-token: <base64-encoded-token>

---
apiVersion: v1
kind: ConfigMap
metadata:
  name: sleepless-config
data:
  config.yaml: |
    claude_code:
      threshold_day: 20.0
      threshold_night: 80.0
```

### 3. Environment Variable Injection

```yaml
apiVersion: apps/v1
kind: Deployment
spec:
  template:
    spec:
      containers:
      - name: sleepless-agent
        envFrom:
        - secretRef:
            name: sleepless-secrets
        - configMapRef:
            name: sleepless-config
```

## Validation & Testing

### 1. Configuration Validation

```bash
# Validate configuration
sle config validate

# Test specific settings
sle config test --component slack
sle config test --component git
sle config test --component claude
```

### 2. Environment Check Script

Create `check_env.sh`:

```bash
#!/bin/bash

echo "Checking Sleepless Agent Environment..."

# Check required variables
required_vars=("SLACK_BOT_TOKEN" "SLACK_APP_TOKEN")

for var in "${required_vars[@]}"; do
    if [ -z "${!var}" ]; then
        echo "❌ Missing required: $var"
        exit 1
    else
        echo "✅ Found: $var"
    fi
done

# Check optional variables
optional_vars=("GIT_USER_NAME" "GIT_USER_EMAIL" "SLEEPLESS_LOG_LEVEL")

for var in "${optional_vars[@]}"; do
    if [ -z "${!var}" ]; then
        echo "⚠️  Missing optional: $var (using default)"
    else
        echo "✅ Found: $var = ${!var}"
    fi
done

# Check file permissions
if [ -f ".env" ]; then
    perms=$(stat -c %a .env 2>/dev/null || stat -f %A .env)
    if [ "$perms" != "600" ]; then
        echo "⚠️  Warning: .env has permissions $perms (should be 600)"
    fi
fi

echo "Environment check complete!"
```

### 3. Configuration Dump

```bash
# Show effective configuration
sle config show

# Export configuration
sle config export > config_backup.yaml

# Show specific section
sle config show --section claude_code
```

## Security Best Practices

### 1. File Permissions

```bash
# Secure environment files
chmod 600 .env
chmod 644 config.yaml

# Secure workspace
chmod 755 workspace/
chmod 700 workspace/data/
```

### 2. Secret Management

Never store secrets in:
- Git repositories
- Configuration files
- Log files
- Error messages

Always use:
- Environment variables
- Secret management services
- Encrypted storage
- Secure file permissions

### 3. Token Rotation

```bash
# Rotate tokens periodically
sle tokens rotate --slack
sle tokens rotate --git

# Verify new tokens
sle tokens verify
```

## Troubleshooting

### Common Issues

1. **Environment variables not loading**
   ```bash
   # Check file exists and readable
   ls -la .env

   # Verify format (no spaces around =)
   grep -E "^[A-Z_]+=" .env
   ```

2. **Configuration conflicts**
   ```bash
   # Show configuration sources
   sle config sources

   # Show final merged config
   sle config show --merged
   ```

3. **Permission denied**
   ```bash
   # Fix permissions
   chmod 600 .env
   chown $USER:$USER .env
   ```

## Migration Guide

### From v0.x to v1.x

```bash
# Backup old configuration
cp .env .env.backup
cp config.yaml config.yaml.backup

# Migrate configuration
sle migrate config

# Verify migration
sle config validate
```

## Next Steps

- [Set up Git integration](git-integration.md)
- [Configure project management](project-management.md)
- [Deploy to production](deployment.md)
- [Monitor the system](../tutorials/monitoring-tasks.md)