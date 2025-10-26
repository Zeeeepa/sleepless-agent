# Workspace Isolation

Workspace isolation is a fundamental security and reliability feature that ensures tasks execute independently without interference.

## Overview

Each task runs in a completely isolated filesystem environment:

```
workspace/
├── tasks/              # Random thought workspaces
│   ├── task_1/        # Complete isolation
│   ├── task_2/        # Parallel execution
│   └── task_3/        # No conflicts
├── projects/          # Serious task workspaces
│   ├── backend/       # Project workspace
│   └── frontend/      # Separate project
└── shared/            # Shared resources (read-only)
```

## Isolation Principles

### 1. Complete Separation

Each task operates in its own sandbox:

```python
# Task 1 workspace
workspace/tasks/task_1/
├── main.py           # Task 1's files
├── data.json
└── output/

# Task 2 workspace (completely separate)
workspace/tasks/task_2/
├── script.js         # Task 2's files
├── config.yaml
└── results/
```

**Key Benefits:**
- No file conflicts between tasks
- Parallel execution without race conditions
- Clean environment for each task
- Easy cleanup and management

### 2. Restricted Access

Tasks cannot access:
- Other task workspaces
- System directories
- Parent workspace folders
- Sensitive configuration files

```python
# Enforced restrictions
FORBIDDEN_PATHS = [
    '/etc',
    '/usr',
    '/System',
    '../..',
    workspace_root + '/data',  # Database location
    workspace_root + '/.env'    # Secrets
]
```

### 3. Clean State

Each workspace starts fresh:

```python
def create_workspace(task_id):
    workspace_path = f"workspace/tasks/task_{task_id}"

    # Create clean directory
    os.makedirs(workspace_path, exist_ok=True)

    # Initialize with task context
    with open(f"{workspace_path}/context.json", "w") as f:
        json.dump({
            "task_id": task_id,
            "created_at": datetime.now().isoformat(),
            "environment": "isolated"
        }, f)

    return workspace_path
```

## Workspace Types

### 1. Task Workspaces

For individual random thoughts:

```
workspace/tasks/task_42/
├── .env              # Task-specific environment
├── context.json      # Task metadata
├── prompt.md         # Input prompt
├── claude_output.md  # Raw output
├── files/           # Generated files
├── logs/            # Execution logs
└── .gitignore       # Exclude sensitive files
```

**Characteristics:**
- Temporary (deleted after completion)
- Minimal size (< 100MB typical)
- No persistence between runs
- Read-only access to shared resources

### 2. Project Workspaces

For serious, long-running tasks:

```
workspace/projects/backend/
├── .git/            # Git repository
├── src/             # Source code
├── tests/           # Test files
├── docs/            # Documentation
├── .env.example     # Environment template
├── README.md        # Project documentation
└── tasks/           # Sub-task workspaces
    ├── task_101/
    └── task_102/
```

**Characteristics:**
- Persistent across tasks
- Git version controlled
- Shared by related tasks
- Larger size allowance (GBs)

### 3. Shared Resources

Read-only resources available to all tasks:

```
workspace/shared/
├── templates/       # Code templates
├── libraries/       # Common libraries
├── datasets/        # Reference data
└── configs/         # Shared configurations
```

**Access Rules:**
- Read-only access for all tasks
- Managed by administrators
- Version controlled separately
- Cached for performance

## Security Model

### 1. Filesystem Permissions

```python
def setup_workspace_security(workspace_path):
    # Restrict permissions
    os.chmod(workspace_path, 0o755)

    # Set ownership
    os.chown(workspace_path, agent_uid, agent_gid)

    # Create .gitignore for sensitive files
    with open(f"{workspace_path}/.gitignore", "w") as f:
        f.write("*.env\n*.key\n*.pem\n*.secret\n")
```

### 2. Path Traversal Prevention

```python
def validate_path(requested_path, workspace_root):
    # Resolve to absolute path
    abs_path = os.path.abspath(requested_path)

    # Ensure within workspace
    if not abs_path.startswith(workspace_root):
        raise SecurityError(f"Access denied: {requested_path}")

    # Check against forbidden patterns
    if any(forbidden in abs_path for forbidden in FORBIDDEN_PATTERNS):
        raise SecurityError(f"Forbidden path: {requested_path}")

    return abs_path
```

### 3. Resource Limits

```python
# Per-workspace limits
WORKSPACE_LIMITS = {
    'max_size_mb': 1024,        # 1GB max
    'max_files': 10000,          # File count limit
    'max_processes': 10,         # Process limit
    'max_memory_mb': 2048,       # Memory limit
    'max_cpu_percent': 50,       # CPU limit
    'timeout_seconds': 3600      # 1 hour max
}
```

## Parallel Execution

### 1. Conflict-Free Operation

Multiple tasks can run simultaneously:

```
Time →
Task 1: [====Create Files====][====Process====][==Output==]
Task 2:     [==Setup==][========Long Running Process========]
Task 3:         [=Quick Task=]
Task 4:                     [====Another Task====]
```

No conflicts because each uses separate workspace.

### 2. Resource Allocation

```python
class WorkspaceManager:
    def __init__(self, max_parallel=5):
        self.semaphore = Semaphore(max_parallel)
        self.active_workspaces = {}

    async def allocate_workspace(self, task):
        async with self.semaphore:
            workspace = create_workspace(task.id)
            self.active_workspaces[task.id] = workspace
            return workspace
```

### 3. Load Balancing

```python
def get_workspace_disk_usage():
    """Monitor disk usage across workspaces"""
    usage = {}
    for task_dir in os.listdir("workspace/tasks"):
        path = f"workspace/tasks/{task_dir}"
        usage[task_dir] = get_directory_size(path)
    return usage

def should_defer_task():
    """Check if we should defer new tasks"""
    total_usage = sum(get_workspace_disk_usage().values())
    return total_usage > MAX_TOTAL_WORKSPACE_SIZE
```

## Lifecycle Management

### 1. Workspace Creation

```python
def initialize_task_workspace(task):
    # Create directory structure
    workspace = create_workspace(task.id)

    # Copy task context
    copy_task_metadata(task, workspace)

    # Set up environment
    create_task_environment(workspace)

    # Initialize Git (if needed)
    if task.use_git:
        init_git_repo(workspace)

    return workspace
```

### 2. During Execution

```python
def monitor_workspace(workspace_path):
    """Monitor workspace during execution"""

    while task_running:
        # Check size limits
        if get_directory_size(workspace_path) > MAX_SIZE:
            log_warning("Workspace size exceeded")

        # Check file count
        if count_files(workspace_path) > MAX_FILES:
            log_warning("Too many files created")

        # Monitor for suspicious activity
        detect_suspicious_patterns(workspace_path)

        sleep(MONITOR_INTERVAL)
```

### 3. Cleanup Strategy

```python
def cleanup_workspace(task):
    workspace_path = f"workspace/tasks/task_{task.id}"

    if task.status == 'completed':
        # Archive important results
        archive_results(workspace_path, task.id)

        # Remove workspace
        shutil.rmtree(workspace_path)

    elif task.status == 'failed':
        # Keep for debugging (temporary)
        mark_for_cleanup(workspace_path, days=7)

    # Update metrics
    log_workspace_cleanup(task.id)
```

## Data Sharing

### 1. Inter-Task Communication

When tasks need to share data:

```python
# Option 1: Through database
def share_via_database(source_task, data):
    result = Result(
        task_id=source_task.id,
        data=json.dumps(data),
        shareable=True
    )
    db.session.add(result)
    db.session.commit()

# Option 2: Through shared workspace
def share_via_filesystem(source_task, file_path):
    shared_path = f"workspace/shared/inter_task/{source_task.id}/"
    os.makedirs(shared_path, exist_ok=True)
    shutil.copy(file_path, shared_path)
```

### 2. Project Continuity

For project-based tasks:

```python
def get_project_workspace(project_name, task):
    """Get or create project workspace"""
    project_path = f"workspace/projects/{project_name}"

    if not os.path.exists(project_path):
        # First task in project
        create_project_workspace(project_path)

    # Create task subdirectory
    task_path = f"{project_path}/tasks/task_{task.id}"
    os.makedirs(task_path, exist_ok=True)

    return task_path
```

## Performance Considerations

### 1. Disk I/O Optimization

```python
# Use memory-mapped files for large data
def use_memory_mapped_file(file_path):
    with open(file_path, 'r+b') as f:
        mmapped = mmap.mmap(f.fileno(), 0)
        # Fast access to file content
        return mmapped

# Batch small file operations
def batch_file_operations(operations):
    with temporary_directory() as temp:
        for op in operations:
            op.execute(temp)
        commit_to_workspace(temp)
```

### 2. Caching Strategy

```python
class WorkspaceCache:
    """Cache frequently accessed workspace data"""

    def __init__(self):
        self.cache = LRUCache(maxsize=100)

    def get_workspace_metadata(self, task_id):
        if task_id in self.cache:
            return self.cache[task_id]

        metadata = load_metadata(f"workspace/tasks/task_{task_id}")
        self.cache[task_id] = metadata
        return metadata
```

### 3. Cleanup Scheduling

```python
def schedule_cleanup():
    """Regular cleanup of old workspaces"""

    # Clean completed task workspaces
    for task_dir in glob("workspace/tasks/task_*"):
        age = get_directory_age(task_dir)
        if age > CLEANUP_AGE_DAYS:
            shutil.rmtree(task_dir)

    # Compress old project workspaces
    for project in glob("workspace/projects/*"):
        if is_inactive(project, days=30):
            compress_project(project)
```

## Monitoring & Debugging

### 1. Workspace Metrics

```python
def collect_workspace_metrics():
    return {
        'total_workspaces': count_workspaces(),
        'active_workspaces': count_active(),
        'total_size_gb': get_total_size() / 1024**3,
        'largest_workspace': find_largest(),
        'oldest_workspace': find_oldest(),
        'avg_workspace_size_mb': calculate_average_size()
    }
```

### 2. Debugging Access

```python
def debug_workspace(task_id):
    """Provide debug access to workspace"""
    workspace = f"workspace/tasks/task_{task_id}"

    # Create debug snapshot
    snapshot = {
        'structure': get_directory_structure(workspace),
        'file_sizes': get_file_sizes(workspace),
        'recent_modifications': get_recent_changes(workspace),
        'logs': read_logs(workspace)
    }

    return snapshot
```

## Best Practices

### 1. Workspace Design
- Keep workspaces minimal
- Use shared resources for common data
- Clean up temporary files during execution
- Document workspace structure

### 2. Security
- Never store secrets in workspaces
- Validate all file paths
- Use read-only mounts where possible
- Regular security audits

### 3. Performance
- Monitor workspace sizes
- Implement aggressive cleanup
- Use compression for archives
- Cache frequently accessed data

### 4. Reliability
- Handle workspace creation failures
- Implement workspace recovery
- Log all workspace operations
- Regular integrity checks

This isolation model ensures safe, reliable, and efficient parallel task execution while maintaining security and performance.