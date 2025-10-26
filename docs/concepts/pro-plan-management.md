# Pro Plan Management

Intelligent management of your Claude Code Pro subscription to maximize value and prevent service interruptions.

## Overview

Claude Code Pro plans have usage limits that reset every 5 hours. Sleepless Agent intelligently manages these limits to ensure continuous operation while preserving capacity for manual usage.

```
Claude Pro Plan
├── 5-hour window
├── Message limit (e.g., 40 messages)
├── Automatic reset
└── Usage tracking
```

## Usage Tracking

### 1. Real-Time Monitoring

```python
class ProPlanMonitor:
    def __init__(self):
        self.current_usage = None
        self.last_check = None
        self.reset_time = None

    def update_usage(self):
        """Get current usage from Claude CLI"""
        result = subprocess.run(
            ['claude', '/usage'],
            capture_output=True,
            text=True
        )

        # Parse output: "23/40 messages (resets at 18:59:00)"
        usage_data = self.parse_usage_output(result.stdout)

        self.current_usage = {
            'used': usage_data['used'],
            'limit': usage_data['limit'],
            'percent': (usage_data['used'] / usage_data['limit']) * 100,
            'remaining': usage_data['limit'] - usage_data['used'],
            'reset_time': usage_data['reset_time']
        }

        self.last_check = datetime.now()
        return self.current_usage
```

### 2. Usage History

```python
def track_usage_history():
    """Record usage patterns for optimization"""

    usage_entry = {
        'timestamp': datetime.now(),
        'window_start': get_window_start(),
        'messages_used': get_current_usage()['used'],
        'tasks_completed': count_completed_tasks(),
        'efficiency': calculate_efficiency()
    }

    # Store in database
    db.session.add(UsageHistory(**usage_entry))
    db.session.commit()

    # Analyze patterns
    return analyze_usage_patterns()
```

### 3. Usage Prediction

```python
class UsagePredictor:
    def __init__(self):
        self.historical_data = load_usage_history()

    def predict_remaining_capacity(self):
        """Predict how many tasks can still run"""
        current = get_current_usage()
        remaining_messages = current['limit'] - current['used']

        # Average messages per task
        avg_messages_per_task = self.calculate_average_usage()

        # Predicted capacity
        return remaining_messages // avg_messages_per_task

    def predict_reset_availability(self):
        """Predict usage after reset"""
        reset_time = self.get_next_reset()
        historical_usage = self.get_usage_at_time(reset_time)

        return {
            'reset_at': reset_time,
            'expected_availability': 100.0,
            'recommended_tasks': self.recommend_tasks_for_window()
        }
```

## Time-Based Thresholds

### 1. Day/Night Configuration

```yaml
claude_code:
  # Nighttime: Maximum automation (8 PM - 8 AM)
  night_start_hour: 20
  night_end_hour: 8
  threshold_night: 80.0  # Use up to 80% at night

  # Daytime: Preserve for manual use (8 AM - 8 PM)
  day_start_hour: 8
  day_end_hour: 20
  threshold_day: 20.0   # Only use 20% during day
```

### 2. Threshold Logic

```python
def get_current_threshold():
    """Get threshold based on time of day"""
    hour = datetime.now().hour
    config = load_config()

    # Check if nighttime
    if hour >= config['night_start_hour'] or hour < config['night_end_hour']:
        return config['threshold_night']
    else:
        return config['threshold_day']

def should_pause_tasks():
    """Check if we should pause task generation"""
    usage = get_current_usage()
    threshold = get_current_threshold()

    if usage['percent'] >= threshold:
        log.warning(f"Usage at {usage['percent']}%, pausing (threshold: {threshold}%)")
        return True

    return False
```

### 3. Adaptive Thresholds

```python
class AdaptiveThresholdManager:
    def __init__(self):
        self.usage_patterns = {}
        self.threshold_adjustments = {}

    def analyze_usage_pattern(self, day_of_week, hour):
        """Analyze historical usage for time slot"""
        historical = self.get_historical_usage(day_of_week, hour)

        return {
            'avg_manual_usage': historical['manual_usage'].mean(),
            'avg_automated_usage': historical['auto_usage'].mean(),
            'peak_usage': historical['total_usage'].max(),
            'recommended_threshold': self.calculate_optimal_threshold(historical)
        }

    def adjust_threshold_dynamically(self):
        """Dynamically adjust thresholds based on patterns"""
        current_slot = self.get_time_slot()
        pattern = self.analyze_usage_pattern(*current_slot)

        if pattern['avg_manual_usage'] < 10:
            # Low manual usage - increase automation
            return min(90, get_current_threshold() + 10)
        elif pattern['avg_manual_usage'] > 30:
            # High manual usage - reduce automation
            return max(10, get_current_threshold() - 10)

        return get_current_threshold()
```

## Window Management

### 1. Reset Detection

```python
class ResetDetector:
    def __init__(self):
        self.last_known_usage = None
        self.reset_callbacks = []

    def detect_reset(self):
        """Detect when usage window resets"""
        current = get_current_usage()

        if self.last_known_usage:
            if current['used'] < self.last_known_usage['used']:
                # Reset detected
                self.handle_reset()
                return True

        self.last_known_usage = current
        return False

    def handle_reset(self):
        """Handle window reset event"""
        log.info("Usage window reset detected")

        # Execute callbacks
        for callback in self.reset_callbacks:
            callback()

        # Resume paused tasks
        resume_paused_tasks()

        # Optimize for new window
        optimize_task_queue()
```

### 2. Window Planning

```python
def plan_window_usage():
    """Plan task execution for current window"""

    window_end = get_window_end_time()
    available_messages = get_remaining_messages()
    threshold = get_current_threshold()

    # Calculate safe usage
    safe_messages = int(available_messages * (threshold / 100))

    # Get pending tasks
    tasks = get_pending_tasks()

    # Plan execution
    plan = []
    used_messages = 0

    for task in tasks:
        estimated_usage = estimate_task_messages(task)
        if used_messages + estimated_usage <= safe_messages:
            plan.append(task)
            used_messages += estimated_usage
        else:
            break

    return {
        'window_end': window_end,
        'planned_tasks': plan,
        'estimated_usage': used_messages,
        'buffer_remaining': safe_messages - used_messages
    }
```

### 3. Grace Period

```python
def handle_window_boundaries():
    """Handle transitions around reset time"""

    # Add grace period after reset
    GRACE_PERIOD_MINUTES = 1

    if just_reset():
        # Wait for grace period
        log.info(f"Window reset - waiting {GRACE_PERIOD_MINUTES} minute grace period")
        time.sleep(GRACE_PERIOD_MINUTES * 60)

    # Check if approaching reset
    if minutes_until_reset() < 5:
        # Avoid starting new tasks close to reset
        log.info("Approaching reset - deferring new tasks")
        return False

    return True
```

## Usage Optimization

### 1. Task Batching

```python
def optimize_task_batching():
    """Batch tasks to minimize message usage"""

    tasks = get_similar_tasks()
    batches = []

    for group in tasks:
        if len(group) > 1:
            # Combine into single prompt
            batched = create_batch_task(group)
            batches.append(batched)

            # Calculate savings
            individual_cost = sum(estimate_messages(t) for t in group)
            batch_cost = estimate_messages(batched)
            savings = individual_cost - batch_cost

            log.info(f"Batching {len(group)} tasks - saving {savings} messages")

    return batches
```

### 2. Prompt Optimization

```python
class PromptOptimizer:
    def __init__(self):
        self.prompt_cache = {}

    def optimize_prompt(self, task):
        """Optimize prompt to reduce message usage"""

        # Remove redundant information
        optimized = self.remove_redundancy(task.prompt)

        # Use references for repeated content
        optimized = self.use_references(optimized)

        # Compress instructions
        optimized = self.compress_instructions(optimized)

        # Cache common patterns
        if task.type in self.prompt_cache:
            optimized = self.apply_cached_optimization(optimized)

        return optimized

    def estimate_savings(self, original, optimized):
        """Estimate message savings from optimization"""
        original_tokens = count_tokens(original)
        optimized_tokens = count_tokens(optimized)

        # Rough estimate: 1 message per 2000 tokens
        original_messages = math.ceil(original_tokens / 2000)
        optimized_messages = math.ceil(optimized_tokens / 2000)

        return original_messages - optimized_messages
```

### 3. Intelligent Queueing

```python
def intelligent_queue_management():
    """Manage queue based on usage patterns"""

    current_usage = get_current_usage()
    threshold = get_current_threshold()
    time_until_reset = get_time_until_reset()

    # Priority adjustments
    if current_usage['percent'] > threshold - 10:
        # Approaching threshold - only high priority
        filter_queue(priority='high')

    elif time_until_reset < 30 and current_usage['percent'] < 50:
        # Window ending with capacity - process more
        boost_queue_processing()

    elif is_idle_period():
        # Idle period - generate tasks
        generate_auto_tasks()

    return get_queue_status()
```

## Monitoring & Alerts

### 1. Usage Dashboard

```python
def generate_usage_dashboard():
    """Generate usage statistics dashboard"""

    current = get_current_usage()
    threshold = get_current_threshold()
    history = get_usage_history(days=7)

    dashboard = {
        'current_status': {
            'usage': f"{current['used']}/{current['limit']}",
            'percent': current['percent'],
            'threshold': threshold,
            'status': 'PAUSED' if current['percent'] >= threshold else 'ACTIVE'
        },
        'window_info': {
            'reset_time': current['reset_time'],
            'time_remaining': get_time_until_reset(),
            'messages_remaining': current['remaining']
        },
        'statistics': {
            'tasks_this_window': count_window_tasks(),
            'avg_messages_per_task': calculate_average_usage(),
            'efficiency_rate': calculate_efficiency()
        },
        'projections': {
            'tasks_until_threshold': predict_remaining_capacity(),
            'estimated_pause_time': predict_pause_time()
        }
    }

    return dashboard
```

### 2. Alert System

```python
class UsageAlertManager:
    def __init__(self):
        self.alert_thresholds = [50, 70, 85, 95]
        self.alerted = set()

    def check_alerts(self):
        """Check and send usage alerts"""
        usage = get_current_usage()['percent']

        for threshold in self.alert_thresholds:
            if usage >= threshold and threshold not in self.alerted:
                self.send_alert(threshold, usage)
                self.alerted.add(threshold)

        # Reset alerts after window reset
        if usage < min(self.alert_thresholds):
            self.alerted.clear()

    def send_alert(self, threshold, current_usage):
        """Send usage alert"""
        if threshold >= 85:
            level = 'WARNING'
        elif threshold >= 95:
            level = 'CRITICAL'
        else:
            level = 'INFO'

        message = f"{level}: Claude usage at {current_usage}% (threshold: {threshold}%)"

        # Send to configured channels
        send_slack_notification(message)
        log_alert(message)
```

### 3. Usage Reports

```python
def generate_usage_report(period='daily'):
    """Generate detailed usage report"""

    if period == 'daily':
        start = datetime.now() - timedelta(days=1)
    elif period == 'weekly':
        start = datetime.now() - timedelta(weeks=1)
    else:
        start = datetime.now() - timedelta(days=30)

    report = {
        'period': period,
        'start': start,
        'end': datetime.now(),
        'summary': {
            'total_messages': sum_messages_used(start),
            'total_tasks': count_tasks(start),
            'success_rate': calculate_success_rate(start),
            'avg_efficiency': calculate_average_efficiency(start)
        },
        'by_window': analyze_by_window(start),
        'by_task_type': analyze_by_task_type(start),
        'optimization_opportunities': find_optimization_opportunities(start),
        'recommendations': generate_recommendations(start)
    }

    return report
```

## Best Practices

### 1. Configuration
- Set conservative daytime thresholds
- Allow higher nighttime usage
- Adjust based on usage patterns
- Monitor and optimize regularly

### 2. Task Planning
- Batch similar tasks together
- Schedule heavy tasks for night
- Use task priorities effectively
- Plan around reset windows

### 3. Monitoring
- Check usage dashboard regularly
- Set up appropriate alerts
- Track efficiency metrics
- Analyze usage patterns

### 4. Optimization
- Optimize prompts for efficiency
- Combine related tasks
- Use caching where possible
- Clean up failed tasks quickly

This comprehensive Pro plan management system ensures maximum value from your Claude Code subscription while maintaining availability for manual usage when needed.