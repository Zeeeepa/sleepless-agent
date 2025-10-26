# CLI Commands Reference

Complete reference for all Sleepless Agent command-line interface commands.

## Overview

The Sleepless Agent CLI is accessed through the `sle` command:

```bash
sle [OPTIONS] COMMAND [ARGS]
```

## Global Options

These options can be used with any command:

| Option | Description | Default |
|--------|-------------|---------|
| `--help` | Show help message | - |
| `--version` | Show version number | - |
| `--config FILE` | Path to config file | `./config.yaml` |
| `--db-path PATH` | Database file path | `./workspace/data/tasks.db` |
| `--results-path PATH` | Results directory | `./workspace/data/results` |
| `--log-level LEVEL` | Logging level | `INFO` |
| `--verbose` | Enable verbose output | `False` |
| `--quiet` | Suppress output | `False` |

## Core Commands

### daemon

Start the agent daemon for continuous operation.

```bash
sle daemon [OPTIONS]
```

**Options:**
- `--test` - Run in test mode (dry run)
- `--test-slack` - Test Slack connection only
- `--no-slack` - Run without Slack integration
- `--poll-interval MS` - Queue polling interval (default: 250ms)
- `--max-workers N` - Maximum parallel tasks (default: 5)

**Examples:**
```bash
# Start daemon normally
sle daemon

# Test mode without executing tasks
sle daemon --test

# Run without Slack
sle daemon --no-slack

# Custom polling interval
sle daemon --poll-interval 500
```

### think

Submit a new task or thought.

```bash
sle think DESCRIPTION [OPTIONS]
```

**Arguments:**
- `DESCRIPTION` - Task description (required)

**Options:**
- `-p, --project NAME` - Assign to project (makes it serious)
- `--priority LEVEL` - Set priority (low/normal/high)
- `--deadline DATETIME` - Set deadline
- `--depends-on ID` - Dependency on another task
- `--dry-run` - Preview without creating

**Examples:**
```bash
# Random thought
sle think "Research async patterns in Python"

# Serious project task
sle think "Implement caching layer" -p backend

# High priority with deadline
sle think "Fix critical bug" --priority high --deadline "2024-10-25 18:00"

# Task with dependency
sle think "Deploy to production" --depends-on 42
```

### check

Check system status and queue.

```bash
sle check [OPTIONS]
```

**Options:**
- `--detailed` - Show detailed information
- `--queue` - Show queue details only
- `--metrics` - Show performance metrics
- `--json` - Output as JSON

**Examples:**
```bash
# Basic status check
sle check

# Detailed status with metrics
sle check --detailed --metrics

# Queue status as JSON
sle check --queue --json
```

**Output includes:**
- System health status
- Claude usage (current/limit)
- Queue depth by priority
- Active tasks
- Recent completions
- Performance metrics

### report

View task reports and summaries.

```bash
sle report [IDENTIFIER] [OPTIONS]
```

**Arguments:**
- `IDENTIFIER` - Task ID, date (YYYY-MM-DD), or project name (optional)

**Options:**
- `--list` - List all available reports
- `--format FORMAT` - Output format (text/markdown/json)
- `--output FILE` - Save to file
- `--last N` - Show last N reports

**Examples:**
```bash
# Today's report
sle report

# Specific task report
sle report 42

# Date report
sle report 2024-10-24

# Project report
sle report backend

# List all reports
sle report --list

# Save report to file
sle report --output report.md
```

### cancel

Cancel a task or entire project.

```bash
sle cancel IDENTIFIER [OPTIONS]
```

**Arguments:**
- `IDENTIFIER` - Task ID or project name (required)

**Options:**
- `--force` - Skip confirmation
- `--cascade` - Cancel dependent tasks
- `--reason TEXT` - Cancellation reason

**Examples:**
```bash
# Cancel specific task
sle cancel 42

# Cancel entire project
sle cancel backend

# Force cancel with reason
sle cancel 42 --force --reason "No longer needed"

# Cancel with dependencies
sle cancel 42 --cascade
```

### trash

Manage cancelled/deleted tasks.

```bash
sle trash SUBCOMMAND [OPTIONS]
```

**Subcommands:**

#### trash list
List items in trash.

```bash
sle trash list [OPTIONS]
```

Options:
- `--type TYPE` - Filter by type (task/project)
- `--days N` - Items older than N days

#### trash restore
Restore items from trash.

```bash
sle trash restore IDENTIFIER
```

#### trash empty
Permanently delete trash items.

```bash
sle trash empty [OPTIONS]
```

Options:
- `--older-than DAYS` - Only items older than N days
- `--force` - Skip confirmation

**Examples:**
```bash
# List trash contents
sle trash list

# Restore a project
sle trash restore backend

# Empty old items
sle trash empty --older-than 30
```

## Management Commands

### init

Initialize workspace and database.

```bash
sle init [OPTIONS]
```

**Options:**
- `--force` - Overwrite existing setup
- `--workspace PATH` - Custom workspace path

**Examples:**
```bash
# Initialize default workspace
sle init

# Custom workspace location
sle init --workspace /data/sleepless
```

### config

Manage configuration.

```bash
sle config SUBCOMMAND [OPTIONS]
```

**Subcommands:**

#### config show
Display current configuration.

```bash
sle config show [--section SECTION]
```

#### config validate
Validate configuration files.

```bash
sle config validate
```

#### config export
Export configuration.

```bash
sle config export [--output FILE]
```

#### config test
Test configuration components.

```bash
sle config test --component COMPONENT
```

Components: `slack`, `git`, `claude`, `database`

**Examples:**
```bash
# Show all configuration
sle config show

# Show specific section
sle config show --section claude_code

# Validate configuration
sle config validate

# Test Slack connection
sle config test --component slack
```

### migrate

Migrate database schema.

```bash
sle migrate [OPTIONS]
```

**Options:**
- `--target VERSION` - Target schema version
- `--dry-run` - Preview migration

**Examples:**
```bash
# Run migrations
sle migrate

# Preview migration
sle migrate --dry-run
```

## Monitoring Commands

### logs

View and manage logs.

```bash
sle logs [OPTIONS]
```

**Options:**
- `--tail N` - Show last N lines
- `--follow` - Follow log output
- `--level LEVEL` - Filter by log level
- `--task ID` - Filter by task ID
- `--since TIME` - Logs since timestamp

**Examples:**
```bash
# View recent logs
sle logs --tail 100

# Follow logs in real-time
sle logs --follow

# Filter errors only
sle logs --level ERROR

# Task-specific logs
sle logs --task 42
```

### metrics

View performance metrics.

```bash
sle metrics [OPTIONS]
```

**Options:**
- `--period PERIOD` - Time period (hour/day/week)
- `--export FILE` - Export to file
- `--json` - JSON output

**Examples:**
```bash
# Current metrics
sle metrics

# Daily metrics
sle metrics --period day

# Export metrics
sle metrics --export metrics.json --json
```

### health

System health check.

```bash
sle health [OPTIONS]
```

**Options:**
- `--verbose` - Detailed health information
- `--component NAME` - Check specific component

**Examples:**
```bash
# Basic health check
sle health

# Verbose health check
sle health --verbose

# Check specific component
sle health --component database
```

## Utility Commands

### test-slack

Test Slack connection.

```bash
sle test-slack [OPTIONS]
```

**Options:**
- `--verbose` - Show detailed test results
- `--channel CHANNEL` - Test specific channel

**Examples:**
```bash
# Basic Slack test
sle test-slack

# Verbose test
sle test-slack --verbose
```

### clean

Clean up workspaces and old data.

```bash
sle clean [OPTIONS]
```

**Options:**
- `--workspaces` - Clean task workspaces
- `--logs` - Clean old logs
- `--results` - Clean old results
- `--older-than DAYS` - Items older than N days
- `--dry-run` - Preview cleanup

**Examples:**
```bash
# Clean old workspaces
sle clean --workspaces --older-than 7

# Preview full cleanup
sle clean --workspaces --logs --results --dry-run
```

### export

Export data from the system.

```bash
sle export TYPE [OPTIONS]
```

**Types:**
- `tasks` - Export task data
- `reports` - Export reports
- `metrics` - Export metrics

**Options:**
- `--format FORMAT` - Output format (csv/json/excel)
- `--output FILE` - Output file
- `--since DATE` - Start date
- `--until DATE` - End date

**Examples:**
```bash
# Export tasks as CSV
sle export tasks --format csv --output tasks.csv

# Export last week's reports
sle export reports --since 2024-10-17 --until 2024-10-24
```

### import

Import tasks from file.

```bash
sle import FILE [OPTIONS]
```

**Options:**
- `--format FORMAT` - Input format (csv/json)
- `--project NAME` - Assign to project
- `--dry-run` - Preview import

**Examples:**
```bash
# Import tasks from CSV
sle import tasks.csv --format csv

# Import to specific project
sle import tasks.json --project backend
```

## Interactive Mode

### shell

Start interactive shell.

```bash
sle shell
```

**Features:**
- Command history
- Tab completion
- Direct database queries
- Real-time status

**Example session:**
```bash
$ sle shell
Sleepless Agent v0.1.0
>>> check
System Status: ACTIVE
>>> think "New task from shell"
Task created: ID 43
>>> exit
```

## Advanced Options

### Debug Mode

Enable debug output:

```bash
SLEEPLESS_LOG_LEVEL=DEBUG sle daemon
```

### Custom Configuration

Use custom config file:

```bash
sle --config custom.yaml daemon
```

### Database Operations

Direct database access:

```bash
# Backup database
sle db backup --output backup.db

# Query database
sle db query "SELECT * FROM tasks WHERE status='pending'"

# Vacuum database
sle db vacuum
```

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | General error |
| 2 | Configuration error |
| 3 | Database error |
| 4 | Connection error |
| 5 | Authentication error |
| 10 | Task failed |
| 11 | Task timeout |
| 20 | Resource limit |

## Environment Variables

Commands respect these environment variables:

- `SLEEPLESS_CONFIG` - Config file path
- `SLEEPLESS_LOG_LEVEL` - Log level
- `SLEEPLESS_WORKSPACE` - Workspace directory
- `SLEEPLESS_DB_PATH` - Database path
- `NO_COLOR` - Disable colored output

## Tips & Tricks

### Aliases

Add to your shell profile:

```bash
alias sla="sle daemon"
alias slc="sle check"
alias slt="sle think"
alias slr="sle report"
```

### Completion

Enable tab completion:

```bash
# Bash
eval "$(_SLE_COMPLETE=bash_source sle)"

# Zsh
eval "$(_SLE_COMPLETE=zsh_source sle)"
```

### Watch Status

Monitor status continuously:

```bash
watch -n 5 sle check
```

### Quick Task Submission

```bash
# Function for quick tasks
task() {
    sle think "$@"
}

# Usage
task "Quick thought about caching"
```

## See Also

- [Slack Commands](slack-commands.md) - Slack slash commands
- [Python API](python-api.md) - Programmatic access
- [Configuration](../configuration.md) - Configuration reference
- [Examples](../../examples/basic-usage.md) - Usage examples