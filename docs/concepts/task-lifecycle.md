# Task Lifecycle

Understanding how tasks move through the Sleepless Agent system is crucial for effective usage and troubleshooting.

## Task States

Every task progresses through a defined set of states:

```
    [Created]
        ↓
    [Pending] ←──────┐
        ↓            │
    [Scheduled]      │
        ↓            │
    [In Progress]    │
        ↓            │
    ┌───┴───┐        │
    ↓        ↓       │
[Completed] [Failed]─┘
    ↓        ↓
[Archived] [Retried]
```

### State Definitions

| State | Description | Duration |
|-------|-------------|----------|
| **Created** | Task just submitted, not yet queued | < 1 second |
| **Pending** | In queue, waiting for execution | Variable |
| **Scheduled** | Selected for execution, checking resources | < 5 seconds |
| **In Progress** | Actively executing | Minutes to hours |
| **Completed** | Successfully finished | Terminal state |
| **Failed** | Execution failed | Can be retried |
| **Archived** | Moved to long-term storage | Permanent |

## Task Creation

### 1. Input Sources

Tasks can be created from multiple sources:

#### Slack Command
```
/think Research async patterns in Python
         ↓
    Parse Input
         ↓
    Create Task
         ↓
    Store in DB
```

#### CLI Command
```bash
sle think "Implement caching layer" -p backend
         ↓
    Parse Arguments
         ↓
    Create Task Object
         ↓
    Queue Task
```

#### Auto-Generation
```python
# System generates tasks based on schedule
if is_idle_time() and has_capacity():
    task = generate_refinement_task()
    queue.add(task)
```

### 2. Task Properties

Each task is created with:

```python
task = {
    'id': auto_increment,
    'description': user_input,
    'priority': 'serious' | 'random',
    'project': project_name | null,
    'created_at': timestamp,
    'created_by': 'slack' | 'cli' | 'system',
    'metadata': {
        'estimated_time': seconds,
        'retry_count': 0,
        'parent_task': task_id | null
    }
}
```

## Task Scheduling

### 1. Queue Management

Tasks enter a priority queue:

```python
def get_next_task():
    # Priority order:
    # 1. Serious tasks with projects
    # 2. Serious standalone tasks
    # 3. Random thoughts
    # 4. Auto-generated tasks

    return queue.pop_highest_priority()
```

### 2. Execution Eligibility

Before execution, tasks must pass checks:

```python
def can_execute(task):
    checks = [
        has_available_claude_usage(),
        within_time_threshold(),
        has_system_resources(),
        no_workspace_conflicts(),
        dependencies_completed()
    ]
    return all(checks)
```

### 3. Resource Allocation

```
Task Selected
     ↓
Check Claude Usage → Over Limit → Queue (wait)
     ↓
Check Time Window → Wrong Time → Defer
     ↓
Allocate Workspace → Conflict → Wait
     ↓
Start Execution
```

## Task Execution

### 1. Workspace Setup

Each task gets an isolated environment:

```bash
workspace/tasks/task_42/
├── .env           # Task-specific environment
├── context.json   # Task metadata
├── input.txt      # Task description
├── output/        # Generated files
└── logs/          # Execution logs
```

### 2. Claude Code Invocation

```python
def execute_task(task):
    # 1. Change to workspace
    os.chdir(task.workspace_path)

    # 2. Prepare prompt
    prompt = format_prompt(task)

    # 3. Invoke Claude Code CLI
    result = subprocess.run(
        ['claude'],
        input=prompt,
        capture_output=True
    )

    # 4. Process output
    return process_result(result)
```

### 3. Multi-Phase Execution

Complex tasks may involve multiple phases:

```
Planning Phase
     ↓
Implementation Phase
     ↓
Testing Phase
     ↓
Review Phase
     ↓
Completion
```

### 4. Progress Monitoring

Real-time status updates:

```python
# Status updates during execution
task.update_status("Starting implementation")
task.update_progress(25)  # 25% complete
task.log_output(chunk)     # Stream output
```

## Result Handling

### 1. Output Capture

All task outputs are captured:

```
Claude Output → Parse Response → Extract Files → Store Results
                      ↓               ↓              ↓
                   Markdown       Code Files    Database Entry
```

### 2. Result Storage

```
workspace/data/results/
├── 2024-10-24/
│   ├── task_42_result.json
│   ├── task_42_output.md
│   └── task_42_files/
│       ├── main.py
│       └── test.py
```

### 3. Success Criteria

Task marked as completed when:
- Claude execution returns successfully
- No critical errors in output
- Required files generated
- Tests pass (if applicable)

## Error Handling

### 1. Failure Types

| Type | Description | Action |
|------|-------------|--------|
| **Timeout** | Execution exceeds limit | Kill process, mark failed |
| **Claude Error** | CLI returns error | Log error, retry if transient |
| **Resource Error** | Out of disk/memory | Clean up, defer task |
| **Validation Error** | Output doesn't meet criteria | Mark failed, notify user |

### 2. Retry Logic

```python
def handle_failure(task, error):
    if is_transient_error(error):
        if task.retry_count < MAX_RETRIES:
            task.retry_count += 1
            task.status = 'pending'
            task.scheduled_for = calculate_backoff(task.retry_count)
        else:
            task.status = 'failed'
            notify_permanent_failure(task)
    else:
        task.status = 'failed'
        log_error(task, error)
```

### 3. Recovery Mechanisms

- **Automatic retry** for transient failures
- **Exponential backoff** to prevent thundering herd
- **Dead letter queue** for persistent failures
- **Manual intervention** options via CLI/Slack

## Post-Execution

### 1. Git Integration

Based on task type:

#### Random Thoughts
```bash
git checkout thought-ideas
git add .
git commit -m "Random thought: <description>"
git push origin thought-ideas
```

#### Serious Tasks
```bash
git checkout -b feature/task-description
git add .
git commit -m "Implement: <description>"
git push origin feature/task-description
gh pr create --title "<description>" --body "<details>"
```

### 2. Notifications

```python
def notify_completion(task):
    channels = []

    if task.source == 'slack':
        channels.append(slack_notification)

    if task.priority == 'serious':
        channels.append(email_notification)

    for channel in channels:
        channel.send(task.get_summary())
```

### 3. Cleanup

After successful completion:
```python
def cleanup_task(task):
    if task.keep_workspace:
        archive_workspace(task)
    else:
        remove_workspace(task)

    update_metrics(task)
    generate_report(task)
```

## Task Dependencies

### 1. Dependency Graph

Tasks can depend on others:

```
Task A ─────┬──→ Task C
            │
Task B ─────┘
```

### 2. Dependency Resolution

```python
def can_start_task(task):
    if not task.dependencies:
        return True

    for dep_id in task.dependencies:
        dep = get_task(dep_id)
        if dep.status != 'completed':
            return False

    return True
```

## Monitoring & Observability

### 1. Task Metrics

Tracked for each task:
- Queue time (pending duration)
- Execution time (in_progress duration)
- Resource usage (CPU, memory, disk)
- Success rate (per task type)
- Retry attempts

### 2. Lifecycle Events

All state transitions are logged:

```json
{
    "timestamp": "2024-10-24T15:30:00Z",
    "task_id": 42,
    "event": "state_change",
    "from_state": "pending",
    "to_state": "in_progress",
    "metadata": {
        "queue_time": 120,
        "executor": "claude-code"
    }
}
```

### 3. Performance Analysis

```sql
-- Average execution time by task type
SELECT
    priority,
    AVG(TIMESTAMPDIFF(SECOND, started_at, completed_at)) as avg_duration
FROM tasks
WHERE status = 'completed'
GROUP BY priority;
```

## Advanced Lifecycle Features

### 1. Task Chaining

Create follow-up tasks automatically:

```python
@on_task_complete
def chain_tasks(completed_task):
    if completed_task.has_chain():
        next_task = completed_task.get_next_in_chain()
        queue.add(next_task)
```

### 2. Conditional Execution

```python
def should_execute(task):
    conditions = task.get_conditions()
    return all([
        evaluate_condition(c) for c in conditions
    ])
```

### 3. Task Templates

Reusable task patterns:

```yaml
templates:
  code_review:
    phases:
      - analyze
      - suggest_improvements
      - generate_report
    timeout: 1800
    retries: 2
```

## Best Practices

### 1. Task Sizing
- Keep tasks focused and atomic
- Break large tasks into subtasks
- Estimate execution time accurately

### 2. Priority Management
- Use projects for related serious tasks
- Reserve serious priority for important work
- Let random thoughts fill idle time

### 3. Error Recovery
- Write idempotent tasks when possible
- Include validation in task descriptions
- Monitor retry patterns for issues

### 4. Resource Optimization
- Schedule heavy tasks during low-usage periods
- Clean up workspaces regularly
- Archive old results periodically

This complete lifecycle ensures reliable, efficient task processing while maintaining system stability and resource optimization.