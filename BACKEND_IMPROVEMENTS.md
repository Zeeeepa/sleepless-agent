# Backend Improvements - Usage Tracking & Project Context

## Overview

This update addresses three major backend improvements:

1. **Project-based Context Management** - Tasks for the same project now share a workspace
2. **Actual API Usage Tracking** - Track real costs instead of estimates
3. **Time-based Budget Scheduling** - Allocate more budget during night, less during daytime

---

## 1. Project-based Context Management

### Problem
Previously, each task ran in an isolated workspace (`task_1`, `task_2`, etc.), which meant:
- No context sharing between related tasks
- Each task started from scratch
- No conversation history for the same project

### Solution
Tasks can now be assigned to a **project**, and all tasks in the same project share:
- A common workspace (`project_{project_id}/` instead of `task_{task_id}/`)
- Git history
- File state

### Usage

**Via Slack:**
```
/task Implement user authentication --project=my-app
/task Add login page --project=my-app
```

Both tasks will share the `workspace/project_my-app/` directory.

**Via Code:**
```python
task = task_queue.add_task(
    description="Add authentication",
    priority=TaskPriority.SERIOUS,
    project_id="my-app",
    project_name="My App"
)
```

### Database Changes
- Added `project_id` field to `Task` model (nullable)
- Added `project_name` field to `Task` model (nullable)

---

## 2. API Usage Tracking with Real Costs

### Problem
Previously, the system used rough estimates for credit tracking (100K tokens ≈ 1 credit), which:
- Wasn't accurate
- Couldn't enforce budgets
- Didn't track actual costs

### Solution
A new `UsageMetric` model tracks **actual API costs** from Claude Code SDK:
- `total_cost_usd` - Real cost in USD (from ResultMessage)
- `duration_ms` - Total execution time
- `duration_api_ms` - API call time
- `num_turns` - Number of conversation turns
- `project_id` - Link to project for aggregation

### How It Works
1. Executor captures cost data from `ResultMessage`
2. Daemon records usage via `scheduler.record_task_usage()`
3. BudgetManager queries `UsageMetric` table for real-time budget status

### Database Changes
- Added new `UsageMetric` table

---

## 3. Time-based Budget Scheduling (90% Night, 10% Day)

### Problem
No way to:
- Control when the agent uses Claude Code API
- Allocate more budget during off-hours
- Prevent daytime budget exhaustion

### Solution
**BudgetManager** with time-based quota allocation:
- **Night (8 PM - 8 AM)**: 90% of daily budget
- **Daytime (8 AM - 8 PM)**: 10% of daily budget
- Default daily budget: $10.00 (configurable)

### Budget Enforcement
The scheduler checks budget before scheduling tasks:
- If budget exhausted → skip scheduling, log warning
- If budget available → schedule up to `max_parallel_tasks`

### Configuration
In `daemon.py`:
```python
self.scheduler = SmartScheduler(
    task_queue=self.task_queue,
    max_parallel_tasks=3,
    daily_budget_usd=10.0,        # $10/day
    night_quota_percent=90.0,     # 90% night, 10% day
)
```

### Checking Budget Status
**Via Slack:**
```
/credits
```

**Response:**
```
💳 Usage & Budget Status

🌙 Night Budget
Remaining: $8.45 / $9.00
Today Total: $2.33

⏱️ Credit Window
Time Remaining: 235m
Tasks Executed: 12

📋 Queue:
Pending: 3
In Progress: 1
Completed: 45
Failed: 2

⚙️ Capacity: 2/3 slots available
```

---

## Implementation Details

### Modified Files

1. **`core/models.py`**
   - Added `project_id` and `project_name` to `Task` model
   - Added new `UsageMetric` model

2. **`core/task_queue.py`**
   - Updated `add_task()` to accept `project_id` and `project_name`

3. **`core/scheduler.py`**
   - Added `TimeOfDay` class (night vs day detection)
   - Added `BudgetManager` class (usage tracking & quota enforcement)
   - Updated `SmartScheduler` to use `BudgetManager`
   - Added `record_task_usage()` method
   - Updated `get_next_tasks()` to enforce budgets
   - Updated `get_credit_status()` to include budget info

4. **`execution/claude_code_executor.py`**
   - Updated `create_task_workspace()` to support project-based workspaces
   - Updated `execute_task()` to accept `project_id` and `project_name`
   - Modified to capture and return usage metrics from `ResultMessage`

5. **`daemon.py`**
   - Updated to pass budget params to `SmartScheduler`
   - Updated `_execute_task()` to pass project info to executor
   - Added call to `scheduler.record_task_usage()` after task completion

6. **`interfaces/bot.py`**
   - Updated `/task` command to support `--project=<name>` flag
   - Updated `_create_task()` to accept and process `project_name`
   - Enhanced `/credits` command to show budget status

### Backward Compatibility

All changes are **backward compatible**:
- `project_id` and `project_name` are nullable
- Tasks without projects use old behavior (task-specific workspaces)
- Legacy credit window tracking still works
- Existing commands work unchanged

---

## Time-based Scheduling Logic

### Night Period (90% of budget)
- **Time**: 8 PM (20:00) - 8 AM (08:00) UTC
- **Budget**: $9.00 (if daily budget is $10)
- **Use case**: Heavy workloads, batch processing

### Daytime Period (10% of budget)
- **Time**: 8 AM (08:00) - 8 PM (20:00) UTC
- **Budget**: $1.00 (if daily budget is $10)
- **Use case**: Emergency fixes, critical tasks only

### How It Works
```python
# In BudgetManager
def get_current_quota(self) -> Decimal:
    is_night = TimeOfDay.is_nighttime()

    if is_night:
        quota = daily_budget * 90%
    else:
        quota = daily_budget * 10%

    return quota

def is_budget_available(self) -> bool:
    remaining = get_remaining_budget()
    return remaining >= estimated_cost  # Default: $0.50
```

Before scheduling:
```python
# In SmartScheduler.get_next_tasks()
if not self.budget_manager.is_budget_available():
    logger.warning("Budget exhausted, skipping scheduling")
    return []
```

---

## Migration Steps

1. **Database will auto-migrate** on first run (SQLAlchemy creates new columns/tables)
2. **No data loss** - existing tasks continue to work
3. **Configure budget** in `daemon.py` if needed (default: $10/day, 90% night)
4. **Use projects** via `--project=<name>` flag (optional)

---

## Examples

### Example 1: Related Tasks in Same Project
```bash
# Task 1: Setup project
/task Create React app boilerplate --project=my-dashboard

# Task 2: Add features (shares workspace with Task 1)
/task Add user authentication to dashboard --project=my-dashboard

# Task 3: More features (still same workspace)
/task Implement data visualization charts --project=my-dashboard
```

All three tasks work in `workspace/project_my-dashboard/`, building on each other's work.

### Example 2: Check Budget During Night
```bash
/credits
```

Response:
```
💳 Usage & Budget Status

🌙 Night Budget
Remaining: $7.23 / $9.00
Today Total: $3.45
```

### Example 3: Budget Exhausted During Day
```bash
/task Fix critical bug
```

If daytime budget ($1.00) is exhausted, the task will be queued but won't execute until:
- Night period starts (more budget available), OR
- Next day (budget resets at midnight UTC)

Agent logs will show:
```
WARNING: Budget exhausted for daytime period (remaining: $0.00). Skipping task scheduling.
```

---

## Benefits

1. **Better Context Continuity**
   - Tasks in same project build on each other
   - No need to re-explain context
   - Conversation history preserved

2. **Accurate Cost Tracking**
   - Real USD costs tracked
   - Project-level cost aggregation possible
   - Better visibility into spending

3. **Smart Resource Allocation**
   - More API usage during night (90%)
   - Conserve budget during daytime (10%)
   - Prevent budget overruns

4. **Budget Control**
   - Hard limits enforced automatically
   - Time-based quota allocation
   - Real-time budget visibility

---

## Configuration Options

### In `daemon.py`:
```python
self.scheduler = SmartScheduler(
    task_queue=self.task_queue,
    max_parallel_tasks=3,           # Concurrency limit
    daily_budget_usd=10.0,          # Daily budget in USD
    night_quota_percent=90.0,       # Night allocation (%)
)
```

### Time Windows (in `scheduler.py`):
```python
class TimeOfDay:
    NIGHT_START_HOUR = 20  # 8 PM
    NIGHT_END_HOUR = 8     # 8 AM
```

To change to different hours (e.g., 10 PM - 6 AM):
```python
NIGHT_START_HOUR = 22  # 10 PM
NIGHT_END_HOUR = 6     # 6 AM
```

---

## Monitoring

### View Budget Status
```bash
/credits  # Shows budget, usage, queue status
```

### View Project Costs (future enhancement)
```sql
-- Query project costs
SELECT project_id, SUM(CAST(total_cost_usd AS DECIMAL)) as total_cost
FROM usage_metrics
WHERE project_id IS NOT NULL
GROUP BY project_id;
```

### Check Daily Spending
```sql
SELECT DATE(created_at) as date, SUM(CAST(total_cost_usd AS DECIMAL)) as daily_cost
FROM usage_metrics
GROUP BY DATE(created_at)
ORDER BY date DESC;
```

---

## Troubleshooting

### "Budget exhausted" but I just started
- Budget resets at midnight UTC
- Check timezone: daytime budget is only 10% ($1.00 by default)
- Solution: Wait for night period or adjust `daily_budget_usd`

### Tasks not sharing workspace
- Ensure using same `--project=<name>` (case-sensitive after slugification)
- Check logs: should show "Using project workspace 'my-project'"
- Verify project_id is set in database

### Budget not enforcing
- Check BudgetManager initialization in daemon
- Verify UsageMetric table exists (`sqlite3 sleepless_agent.db ".tables"`)
- Check logs for usage recording confirmation

---

## Future Enhancements

1. **Project-level budgets** - Separate budgets per project
2. **Weekly/monthly budgets** - Longer time windows
3. **Dynamic quota adjustment** - ML-based budget allocation
4. **Cost alerts** - Slack notifications when budget low
5. **Project analytics** - Dashboard for cost visualization
6. **Multi-timezone support** - User-specific time zones
