# Architecture Overview

Sleepless Agent is built as a modular, event-driven system that processes tasks autonomously while managing resources efficiently.

## System Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    User Interface Layer                  │
├──────────────────────┬───────────────────────────────────┤
│    Slack Bot (bot.py)│        CLI (cli.py)               │
└──────────────────────┴───────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│                    Core Engine Layer                     │
├──────────────────────────────────────────────────────────┤
│         Daemon (daemon.py) - Event Loop                  │
│              ├── Scheduler (scheduler.py)                │
│              ├── Queue Manager (queue.py)                │
│              └── Task Runtime (task_runtime.py)          │
└─────────────────────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│                   Execution Layer                        │
├──────────────────────────────────────────────────────────┤
│         Executor (executor.py)                           │
│              ├── Claude Code CLI Integration             │
│              ├── Workspace Manager                       │
│              └── Timeout Manager                         │
└─────────────────────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│                    Storage Layer                         │
├──────────────────────────────────────────────────────────┤
│    SQLite DB       Git Repos      File System           │
│   (tasks.db)     (projects/)    (results/)              │
└─────────────────────────────────────────────────────────┘
```

## Core Components

### 1. User Interface Layer

#### Slack Bot (`interfaces/bot.py`)
- Receives slash commands from Slack
- Parses user input and creates tasks
- Sends status updates and notifications
- Manages real-time Socket Mode connection

#### CLI Interface (`interfaces/cli.py`)
- Provides local command-line access
- Mirrors Slack commands functionality
- Useful for debugging and automation
- Direct database access for queries

### 2. Core Engine Layer

#### Daemon (`core/daemon.py`)
The heart of the system - an event loop that:
- Continuously monitors the task queue
- Dispatches tasks to executors
- Manages system resources
- Handles graceful shutdown

```python
# Simplified daemon loop
while running:
    task = queue.get_next_task()
    if task and can_execute(task):
        executor.run(task)
    await sleep(poll_interval)
```

#### Scheduler (`scheduling/scheduler.py`)
Intelligent task scheduling based on:
- Task priority (serious vs random)
- Claude usage quotas
- Time of day (day/night thresholds)
- System resources
- Task dependencies

#### Queue Manager (`core/queue.py`)
- FIFO queue with priority support
- Persistent storage in SQLite
- Atomic operations for consistency
- Status tracking and updates

### 3. Execution Layer

#### Executor (`core/executor.py`)
Manages task execution lifecycle:
- Creates isolated workspaces
- Invokes Claude Code CLI
- Monitors execution progress
- Handles timeouts and failures
- Captures output and results

#### Workspace Isolation
Each task runs in its own directory:
```
workspace/
├── tasks/
│   ├── task_1/     # Isolated environment
│   ├── task_2/     # Parallel execution
│   └── task_3/     # No conflicts
├── projects/       # Serious task workspaces
└── shared/         # Shared resources
```

### 4. Storage Layer

#### SQLite Database (`storage/sqlite.py`)
Primary data store for:
- Task queue and metadata
- Task history and results
- System configuration
- Performance metrics

#### Git Integration (`storage/git.py`)
Automated version control:
- Commits for random thoughts
- Feature branches for serious tasks
- Pull request creation
- Conflict resolution

#### File System (`storage/results.py`)
Persistent storage for:
- Task outputs and logs
- Generated reports
- Workspace snapshots
- Temporary files

## Data Flow

### Task Lifecycle

1. **Task Creation**
   ```
   User Input → Parser → Task Object → Database
   ```

2. **Task Scheduling**
   ```
   Queue → Scheduler → Priority Check → Execution Queue
   ```

3. **Task Execution**
   ```
   Executor → Workspace → Claude CLI → Output Capture
   ```

4. **Result Storage**
   ```
   Output → Results Manager → Database + Files → Git Commit
   ```

## Key Design Principles

### 1. Isolation
- Each task runs in complete isolation
- No shared state between tasks
- Prevents conflicts and data corruption
- Enables true parallel execution

### 2. Persistence
- All state stored in database
- Survives daemon restarts
- Full audit trail
- Recovery from failures

### 3. Modularity
- Clear separation of concerns
- Pluggable components
- Easy to extend
- Testable units

### 4. Resilience
- Graceful error handling
- Automatic retries
- Timeout protection
- State recovery

## Communication Patterns

### Event-Driven Architecture
```
Event Producer → Event Queue → Event Consumer
     ↓               ↓              ↓
Slack Command   Task Created   Task Executed
```

### Message Flow
1. **Synchronous**: CLI commands with immediate response
2. **Asynchronous**: Slack commands with background processing
3. **Polling**: Daemon checking queue for new tasks
4. **Webhooks**: Git notifications and status updates

## Resource Management

### Claude Usage Optimization
```python
def can_execute_task(task):
    usage = get_claude_usage()
    threshold = get_threshold_for_time()
    return usage < threshold
```

### Memory Management
- Isolated workspaces prevent memory leaks
- Automatic cleanup of old workspaces
- Streaming output for large results
- Database connection pooling

### Concurrent Execution
- Configurable max parallel tasks
- Resource-based scheduling
- Priority queue management
- Deadlock prevention

## Security Considerations

### Token Management
- Secrets never logged
- Environment variable isolation
- Secure storage in `.env`
- No hardcoded credentials

### Workspace Isolation
- Each task has restricted filesystem access
- No access to system directories
- Clean environment for each execution
- Sanitized user input

### Git Security
- SSH key authentication
- Private repository support
- Secret scanning before commits
- Protected branch policies

## Monitoring & Observability

### Logging System
```
Application → Logger → Formatter → Output
                ↓          ↓          ↓
            Structured   Rich      Files
              JSON     Console   & Stdout
```

### Metrics Collection
- Task execution times
- Success/failure rates
- Claude usage statistics
- Queue depth and latency

### Health Checks
- Daemon status monitoring
- Database connectivity
- Claude CLI availability
- Disk space and memory

## Extension Points

### Custom Executors
```python
class CustomExecutor(BaseExecutor):
    def execute(self, task):
        # Custom execution logic
        pass
```

### Plugin System
- Hook into task lifecycle
- Custom storage backends
- Alternative AI providers
- Notification integrations

### API Integration
- RESTful API endpoints
- WebSocket for real-time updates
- GraphQL for complex queries
- Webhook receivers

## Performance Characteristics

### Scalability
- Handles 100+ tasks in queue
- Parallel execution up to system limits
- Efficient database queries
- Lazy loading of resources

### Response Times
- Task creation: < 100ms
- Queue polling: 250ms interval
- Execution start: < 1 second
- Status updates: Real-time

### Resource Usage
- Memory: ~200MB base + task overhead
- CPU: < 5% idle, varies during execution
- Disk: 1GB minimum, grows with tasks
- Network: Minimal, only for Slack/Git

## Future Architecture Goals

### Planned Enhancements
1. Distributed task execution
2. Multi-agent coordination
3. Advanced caching layer
4. Stream processing pipeline
5. Machine learning optimization

### Scalability Roadmap
- Horizontal scaling with multiple daemons
- Task sharding across workers
- Centralized queue management
- Load balancing algorithms

This architecture provides a robust foundation for 24/7 autonomous task processing while maintaining flexibility for future enhancements.