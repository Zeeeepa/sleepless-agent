# Core Concepts

Understanding the fundamental concepts behind Sleepless Agent will help you use it more effectively.

## Overview

Sleepless Agent is built on several core principles:

1. **Continuous Operation** - Runs 24/7 as a daemon
2. **Workspace Isolation** - Each task executes in isolation
3. **Intelligent Scheduling** - Optimizes task execution
4. **Usage Management** - Maximizes Claude Pro value

## Key Concepts

### 📐 [Architecture](architecture.md)
Learn how the system components work together to process tasks autonomously.

- System components and their responsibilities
- Data flow through the system
- Communication patterns
- Extension points

### 🔄 [Task Lifecycle](task-lifecycle.md)
Understand how tasks move from creation to completion.

- Task states and transitions
- Execution phases
- Error handling and recovery
- Result storage

### 🏗️ [Workspace Isolation](workspace-isolation.md)
Explore how tasks run in isolated environments for safety and parallelism.

- Isolation principles
- Workspace types
- Security model
- Resource management

### ⏰ [Task Scheduling](scheduling.md)
Discover how the scheduler prioritizes and executes tasks.

- Priority system
- Scheduling algorithm
- Queue management
- Resource allocation

### 📊 [Pro Plan Management](pro-plan-management.md)
Learn how the agent optimizes your Claude Pro subscription usage.

- Usage tracking
- Time-based thresholds
- Window management
- Optimization strategies

## Concept Map

```
Sleepless Agent
├── User Input (Slack/CLI)
│   └── Task Creation
│       └── Queue Management
│           └── Scheduling
│               └── Execution
│                   ├── Workspace Isolation
│                   ├── Claude Code CLI
│                   └── Result Storage
├── Resource Management
│   ├── Pro Plan Usage
│   ├── System Resources
│   └── Time Windows
└── Automation
    ├── Git Integration
    ├── PR Creation
    └── Report Generation
```

## Learning Path

### For New Users
1. Start with [Architecture](architecture.md) for system overview
2. Read [Task Lifecycle](task-lifecycle.md) to understand task flow
3. Review [Pro Plan Management](pro-plan-management.md) for usage optimization

### For Developers
1. Deep dive into [Workspace Isolation](workspace-isolation.md)
2. Study [Scheduling](scheduling.md) algorithms
3. Explore extension points in [Architecture](architecture.md)

### For Operators
1. Focus on [Pro Plan Management](pro-plan-management.md)
2. Understand [Scheduling](scheduling.md) for optimization
3. Review monitoring in [Task Lifecycle](task-lifecycle.md)

## Quick Reference

| Concept | Key Points |
|---------|------------|
| **Architecture** | Modular, event-driven, extensible |
| **Task Lifecycle** | Created → Pending → Scheduled → Running → Complete |
| **Workspace** | Isolated, parallel, secure |
| **Scheduling** | Priority-based, resource-aware, fair |
| **Usage** | Time-based thresholds, automatic pausing |

## Related Topics

- [Installation Guide](../installation.md) - Set up the system
- [Configuration Reference](../reference/configuration.md) - Detailed settings
- [First Task Tutorial](../tutorials/first-task.md) - Hands-on experience
- [FAQ](../faq.md) - Common questions