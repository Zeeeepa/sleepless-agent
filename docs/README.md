# Sleepless Agent Documentation

This documentation provides comprehensive guides, references, and tutorials for the Sleepless Agent - a 24/7 AI automation system powered by Claude Code.

## Documentation Structure

```
docs/
├── index.md                    # Main landing page
├── quickstart.md               # 5-minute getting started
├── installation.md             # Detailed installation guide
├── faq.md                      # Frequently asked questions
├── troubleshooting.md          # Common issues and solutions
├── changelog.md                # Version history
├── mkdocs.yml                  # MkDocs configuration
│
├── concepts/                   # Core concepts and architecture
│   ├── index.md               # Concepts overview
│   ├── architecture.md        # System architecture
│   ├── task-lifecycle.md      # How tasks flow through system
│   ├── workspace-isolation.md # Isolation and security model
│   ├── scheduling.md          # Task scheduling algorithms
│   └── pro-plan-management.md # Claude Pro usage optimization
│
├── guides/                     # Step-by-step guides
│   ├── index.md               # Guides overview
│   ├── slack-setup.md         # Complete Slack configuration
│   ├── environment-setup.md   # Environment variables and config
│   └── git-integration.md     # Git automation setup
│
├── reference/                  # Technical reference
│   └── api/
│       └── cli-commands.md    # CLI command reference
│
└── assets/                     # Images and diagrams
```

## Documentation Highlights

### 🚀 Quick Start
- **[Quickstart Guide](quickstart.md)** - Get running in 5 minutes
- **[Installation](installation.md)** - Platform-specific setup instructions
- **[FAQ](faq.md)** - Answers to common questions

### 🧠 Core Concepts
- **[Architecture](concepts/architecture.md)** - Understand system design
- **[Task Lifecycle](concepts/task-lifecycle.md)** - Task execution flow
- **[Workspace Isolation](concepts/workspace-isolation.md)** - Security model
- **[Pro Plan Management](concepts/pro-plan-management.md)** - Usage optimization

### 📖 Configuration Guides
- **[Slack Setup](guides/slack-setup.md)** - Complete Slack integration
- **[Environment Setup](guides/environment-setup.md)** - Configuration management
- **[Git Integration](guides/git-integration.md)** - Automated version control

### 📋 Reference
- **[CLI Commands](reference/api/cli-commands.md)** - Complete command reference
- **[Troubleshooting](troubleshooting.md)** - Solve common problems

## Key Features Documented

### System Architecture
- Modular, event-driven design
- Parallel task execution
- Isolated workspace management
- Resource optimization

### Slack Integration
- Step-by-step app creation
- Socket Mode configuration
- Slash command setup
- Permission management

### Git Automation
- Automatic commits for tasks
- Pull request creation
- Multi-repository support
- Security best practices

### Pro Plan Management
- Intelligent usage tracking
- Time-based thresholds (day/night)
- Automatic pausing at limits
- Usage optimization strategies

### Task Management
- Priority-based scheduling
- Project organization
- Dependency handling
- Result storage

## Building the Documentation

### Prerequisites

```bash
pip install mkdocs mkdocs-material
```

### Local Development

```bash
# Serve documentation locally
cd docs
mkdocs serve

# View at http://localhost:8000
```

### Build Static Site

```bash
# Build documentation
mkdocs build

# Output in site/ directory
```

### Deploy to GitHub Pages

```bash
# Deploy to gh-pages branch
mkdocs gh-deploy
```

## Documentation Standards

### Writing Style
- Clear, concise language
- Step-by-step instructions
- Code examples for every concept
- Visual diagrams where helpful

### Structure
- Progressive disclosure (simple → complex)
- Consistent formatting
- Cross-references between related topics
- Complete examples

### Content Types
- **Concepts** - Explain how things work
- **Guides** - Show how to do things
- **Tutorials** - Learn by doing
- **Reference** - Complete specifications

## Contributing to Documentation

### Adding New Content

1. Choose appropriate section (concepts/guides/tutorials/reference)
2. Follow existing naming conventions
3. Update navigation in mkdocs.yml
4. Include code examples
5. Add cross-references

### Style Guide

- Use ATX-style headers (`#`, not underlines)
- Include code language in fenced blocks
- Use tables for structured data
- Add admonitions for important notes

### Example Structure

```markdown
# Page Title

Brief introduction paragraph.

## Overview

High-level explanation.

## Details

### Subsection

Detailed content with examples:

\`\`\`python
# Code example
def example():
    return "example"
\`\`\`

## Best Practices

- Bullet points for lists
- **Bold** for emphasis
- `code` for inline code

## See Also

- [Related Topic](link.md)
```

## Documentation Coverage

### ✅ Completed
- Core documentation structure
- All concept documents (5/5)
- Essential guides (3/5+)
- Root documentation files
- MkDocs configuration
- CLI commands reference

### 🚧 Planned Additions
- Remaining guides (project management, custom prompts, deployment)
- Tutorial documents (first task, workflows, monitoring, reports)
- API reference (Slack commands, Python API)
- Configuration reference
- Database schema reference
- Example code and workflows

## Quick Links

- [Main Documentation](index.md)
- [Quickstart](quickstart.md)
- [Slack Setup](guides/slack-setup.md)
- [Architecture](concepts/architecture.md)
- [CLI Reference](reference/api/cli-commands.md)

## Support

- **Documentation Issues**: Open an issue with the `documentation` label
- **Discord**: Join our community for help
- **Contributing**: See CONTRIBUTING.md for guidelines

---

*This documentation follows the style and structure of professional open-source projects like ContextAgent, providing comprehensive coverage of all aspects of the Sleepless Agent system.*