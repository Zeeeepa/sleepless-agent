# Task Scheduling

The Sleepless Agent scheduler intelligently manages task execution based on priorities, resource availability, and usage constraints.

## Scheduling Overview

```
Task Queue → Scheduler → Execution Decision
              ↓     ↓           ↓
          Priority  Resources  Timing
          Analysis  Check      Window
```

The scheduler operates on a continuous loop, evaluating tasks for execution based on multiple factors.

## Priority System

### Task Priority Levels

Tasks are categorized into priority tiers:

```python
PRIORITY_LEVELS = {
    'critical': 100,      # System-critical tasks
    'serious_project': 80,  # Project-based serious tasks
    'serious': 60,          # Standalone serious tasks
    'random': 40,           # Random thoughts
    'auto_generated': 20,   # System-generated tasks
    'background': 10        # Low-priority maintenance
}
```

### Priority Calculation

```python
def calculate_priority(task):
    base_priority = PRIORITY_LEVELS[task.type]

    # Adjust based on age (prevent starvation)
    age_hours = (now() - task.created_at).total_seconds() / 3600
    age_boost = min(age_hours * 2, 20)  # Max 20 point boost

    # Project boost
    project_boost = 10 if task.project else 0

    # User preference boost
    user_boost = task.user_priority * 5

    return base_priority + age_boost + project_boost + user_boost
```

## Scheduling Algorithm

### 1. Task Selection

The scheduler uses a weighted scoring system:

```python
def select_next_task():
    candidates = queue.get_pending_tasks()

    for task in candidates:
        task.score = calculate_task_score(task)

    # Sort by score (highest first)
    candidates.sort(key=lambda t: t.score, reverse=True)

    for task in candidates:
        if can_execute_now(task):
            return task

    return None  # No eligible tasks
```

### 2. Scoring Formula

```python
def calculate_task_score(task):
    score = 0

    # Priority weight (40%)
    score += task.priority * 0.4

    # Wait time weight (30%)
    wait_time = (now() - task.created_at).total_seconds()
    score += normalize(wait_time, max_wait=86400) * 0.3

    # Resource efficiency weight (20%)
    score += calculate_resource_efficiency(task) * 0.2

    # Time window weight (10%)
    score += time_window_score(task) * 0.1

    return score
```

### 3. Resource Availability

```python
def can_execute_now(task):
    checks = {
        'claude_usage': check_claude_availability(),
        'memory': check_memory_available(task.estimated_memory),
        'disk': check_disk_space(task.estimated_disk),
        'cpu': check_cpu_load(),
        'time_window': is_in_execution_window(task)
    }

    return all(checks.values())
```

## Time-Based Scheduling

### 1. Execution Windows

Different thresholds for day and night:

```yaml
scheduling:
  windows:
    night:
      start_hour: 20  # 8 PM
      end_hour: 8     # 8 AM
      usage_threshold: 80  # Use up to 80% at night
      task_types: ['all']  # All task types allowed

    day:
      start_hour: 8   # 8 AM
      end_hour: 20    # 8 PM
      usage_threshold: 20  # Only 20% during day
      task_types: ['critical', 'serious']  # Limited types
```

### 2. Time Window Logic

```python
def is_in_execution_window(task):
    current_hour = datetime.now().hour
    window = get_current_window()

    # Check if task type allowed in this window
    if task.type not in window.task_types and 'all' not in window.task_types:
        return False

    # Check usage threshold
    current_usage = get_claude_usage_percent()
    if current_usage >= window.usage_threshold:
        return False

    # Task-specific time restrictions
    if task.preferred_hours:
        return current_hour in task.preferred_hours

    return True
```

### 3. Usage Optimization

```python
class UsageOptimizer:
    def __init__(self):
        self.usage_history = []
        self.reset_times = []

    def predict_best_execution_time(self, task):
        """Predict optimal execution time"""
        estimated_usage = task.estimated_messages

        # Find next window with enough capacity
        for window in self.get_future_windows():
            predicted_usage = self.predict_usage_at(window.start)
            if predicted_usage + estimated_usage < window.threshold:
                return window.start

        return None  # No suitable window found

    def get_usage_pattern(self):
        """Analyze historical usage patterns"""
        return {
            'peak_hours': self.find_peak_usage_hours(),
            'idle_periods': self.find_idle_periods(),
            'avg_usage_by_hour': self.calculate_hourly_average()
        }
```

## Queue Management

### 1. Queue Structure

```python
class PriorityQueue:
    def __init__(self):
        self.queues = {
            'critical': deque(),
            'high': deque(),
            'normal': deque(),
            'low': deque()
        }

    def add_task(self, task):
        priority_level = self.get_priority_level(task)
        self.queues[priority_level].append(task)
        self.rebalance_if_needed()

    def get_next(self):
        for level in ['critical', 'high', 'normal', 'low']:
            if self.queues[level]:
                return self.queues[level].popleft()
        return None
```

### 2. Queue Rebalancing

Prevent task starvation:

```python
def rebalance_queues():
    """Promote aged tasks to prevent starvation"""

    for level in ['low', 'normal', 'high']:
        aged_tasks = []

        for task in queues[level]:
            age = (now() - task.created_at).total_seconds()
            if age > STARVATION_THRESHOLD:
                aged_tasks.append(task)

        # Promote aged tasks
        next_level = get_next_level(level)
        for task in aged_tasks:
            queues[level].remove(task)
            queues[next_level].append(task)
            log(f"Promoted task {task.id} due to age")
```

### 3. Backpressure Handling

```python
def handle_queue_backpressure():
    """Handle queue overflow conditions"""

    total_pending = sum(len(q) for q in queues.values())

    if total_pending > MAX_QUEUE_SIZE:
        # Defer low-priority tasks
        deferred = []
        while total_pending > MAX_QUEUE_SIZE and queues['low']:
            task = queues['low'].pop()
            task.status = 'deferred'
            deferred.append(task)
            total_pending -= 1

        # Notify about deferred tasks
        if deferred:
            notify_deferred_tasks(deferred)
```

## Resource Management

### 1. Resource Tracking

```python
class ResourceManager:
    def __init__(self):
        self.resources = {
            'cpu': CPUResource(),
            'memory': MemoryResource(),
            'disk': DiskResource(),
            'claude_api': ClaudeAPIResource()
        }

    def check_availability(self, requirements):
        for resource, required in requirements.items():
            if not self.resources[resource].is_available(required):
                return False, resource
        return True, None

    def allocate(self, task_id, requirements):
        for resource, amount in requirements.items():
            self.resources[resource].allocate(task_id, amount)

    def release(self, task_id):
        for resource in self.resources.values():
            resource.release(task_id)
```

### 2. Claude Usage Management

```python
class ClaudeUsageManager:
    def __init__(self):
        self.usage_data = []
        self.last_reset = None

    def get_current_usage(self):
        """Get current Claude usage from CLI"""
        result = subprocess.run(
            ['claude', '/usage'],
            capture_output=True,
            text=True
        )
        return self.parse_usage(result.stdout)

    def can_execute_task(self, task):
        usage = self.get_current_usage()
        window = self.get_current_window()

        # Check against threshold
        usage_percent = (usage['used'] / usage['limit']) * 100
        return usage_percent < window.threshold

    def estimate_task_usage(self, task):
        """Estimate messages needed for task"""
        base_estimate = 3  # Minimum messages

        # Adjust based on task complexity
        if 'complex' in task.description.lower():
            base_estimate *= 2
        if task.project:
            base_estimate += 2

        return base_estimate
```

### 3. Parallel Execution Control

```python
def determine_parallelism():
    """Determine safe parallelism level"""

    # Check system resources
    cpu_cores = multiprocessing.cpu_count()
    available_memory = psutil.virtual_memory().available
    current_load = psutil.cpu_percent()

    # Calculate safe parallelism
    max_parallel = min(
        cpu_cores - 1,  # Leave one core free
        available_memory // TASK_MEMORY_REQUIREMENT,
        MAX_PARALLEL_TASKS
    )

    # Reduce if system is loaded
    if current_load > 70:
        max_parallel = max(1, max_parallel // 2)

    return max_parallel
```

## Advanced Scheduling Features

### 1. Predictive Scheduling

```python
class PredictiveScheduler:
    def __init__(self):
        self.ml_model = load_model('task_duration_predictor')

    def predict_task_duration(self, task):
        features = extract_features(task)
        predicted_seconds = self.ml_model.predict(features)
        return predicted_seconds

    def optimize_schedule(self, tasks):
        """Optimize task order for throughput"""
        predictions = {}

        for task in tasks:
            predictions[task.id] = {
                'duration': self.predict_task_duration(task),
                'usage': self.estimate_claude_usage(task),
                'priority': task.priority
            }

        # Use optimization algorithm
        return self.run_optimization(predictions)
```

### 2. Deadline Awareness

```python
def schedule_with_deadlines(tasks):
    """Schedule tasks considering deadlines"""

    # Separate deadline tasks
    deadline_tasks = [t for t in tasks if t.deadline]
    regular_tasks = [t for t in tasks if not t.deadline]

    # Sort deadline tasks by urgency
    deadline_tasks.sort(key=lambda t: t.deadline)

    # Check feasibility
    for task in deadline_tasks:
        if not can_meet_deadline(task):
            notify_deadline_risk(task)

    # Interleave deadline and regular tasks
    return merge_task_lists(deadline_tasks, regular_tasks)
```

### 3. Batch Processing

```python
def batch_similar_tasks(tasks):
    """Group similar tasks for efficiency"""

    batches = defaultdict(list)

    for task in tasks:
        # Group by similarity
        batch_key = get_batch_key(task)
        batches[batch_key].append(task)

    # Process batches
    for batch_key, batch_tasks in batches.items():
        if len(batch_tasks) >= MIN_BATCH_SIZE:
            execute_batch(batch_tasks)
        else:
            # Execute individually
            for task in batch_tasks:
                execute_single(task)
```

## Scheduling Policies

### 1. Fair Scheduling

```python
class FairScheduler:
    def __init__(self):
        self.user_quotas = {}
        self.project_quotas = {}

    def ensure_fairness(self, task):
        """Ensure fair resource distribution"""

        # Check user quota
        user_usage = self.user_quotas.get(task.user_id, 0)
        if user_usage > USER_QUOTA_LIMIT:
            return False, "User quota exceeded"

        # Check project quota
        if task.project:
            project_usage = self.project_quotas.get(task.project, 0)
            if project_usage > PROJECT_QUOTA_LIMIT:
                return False, "Project quota exceeded"

        return True, None
```

### 2. Quality of Service (QoS)

```python
class QoSManager:
    def __init__(self):
        self.service_levels = {
            'premium': {'priority': 100, 'timeout': 7200},
            'standard': {'priority': 50, 'timeout': 3600},
            'economy': {'priority': 20, 'timeout': 1800}
        }

    def apply_qos(self, task):
        """Apply QoS policies to task"""
        level = task.service_level or 'standard'
        qos = self.service_levels[level]

        task.priority = qos['priority']
        task.timeout = qos['timeout']

        return task
```

## Monitoring & Metrics

### 1. Scheduling Metrics

```python
def collect_scheduling_metrics():
    return {
        'queue_depth': get_queue_depth(),
        'avg_wait_time': calculate_average_wait(),
        'task_throughput': calculate_throughput(),
        'resource_utilization': {
            'cpu': get_cpu_utilization(),
            'memory': get_memory_utilization(),
            'claude': get_claude_utilization()
        },
        'scheduling_efficiency': calculate_efficiency(),
        'fairness_index': calculate_fairness_index()
    }
```

### 2. Performance Analysis

```sql
-- Analyze scheduling performance
SELECT
    DATE(scheduled_at) as date,
    AVG(TIMESTAMPDIFF(SECOND, created_at, scheduled_at)) as avg_wait,
    COUNT(*) as tasks_scheduled,
    SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
    AVG(priority) as avg_priority
FROM tasks
WHERE scheduled_at IS NOT NULL
GROUP BY DATE(scheduled_at)
ORDER BY date DESC;
```

## Best Practices

### 1. Task Design
- Provide accurate resource estimates
- Set realistic priorities
- Use projects for related tasks
- Include preferred execution times

### 2. Queue Management
- Monitor queue depth regularly
- Adjust priorities to prevent starvation
- Clean up stale tasks periodically
- Use batching for similar tasks

### 3. Resource Optimization
- Schedule heavy tasks during off-hours
- Balance load across time windows
- Reserve capacity for critical tasks
- Monitor and adjust thresholds

### 4. Monitoring
- Track scheduling metrics
- Alert on queue backlog
- Analyze wait time patterns
- Optimize based on data

This scheduling system ensures efficient, fair, and intelligent task execution while respecting resource constraints and usage limits.