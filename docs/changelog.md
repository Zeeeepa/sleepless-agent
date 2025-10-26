# Changelog

All notable changes to Sleepless Agent will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Comprehensive documentation with MkDocs support
- Project-level task management
- Trash/restore functionality for cancelled tasks
- Real-time usage monitoring dashboard
- Multi-agent workflow support (planner, worker, evaluator)
- Isolated workspace management for parallel execution
- Advanced scheduling with time-based thresholds

### Changed
- Improved logging with Rich console output
- Enhanced Pro plan usage management
- Optimized task queue processing
- Better error handling and recovery

### Fixed
- AttributeError in 'sle check' command
- Task status synchronization issues
- Database locking under high load
- Memory leaks in long-running daemon

## [0.1.0] - 2024-10-24

### Added
- Initial public release
- Core daemon functionality
- Slack bot integration with slash commands
- Claude Code CLI integration via Python Agent SDK
- SQLite-based task persistence
- Git automation (commits and PRs)
- Basic task scheduling
- Pro plan usage tracking
- Daily report generation
- CLI interface (`sle` command)
- Environment-based configuration
- Workspace isolation for tasks
- Basic monitoring and metrics

### Features
- `/think` command for task submission
- `/check` command for status monitoring
- `/cancel` command for task cancellation
- `/report` command for viewing reports
- Automatic thought processing
- Project-based serious task handling
- Time-based usage thresholds (day/night)
- Automatic pause at usage limits

### Documentation
- README with quickstart guide
- Basic installation instructions
- Slack setup guide
- Command reference

## [0.0.9] - 2024-10-20 (Pre-release)

### Added
- Beta testing release
- Core task execution engine
- Basic Slack integration
- Initial Claude Code wrapper

### Changed
- Switched from direct API to Claude Code CLI
- Refactored task queue implementation

### Fixed
- Connection timeout issues
- Task state management bugs

## [0.0.5] - 2024-10-15 (Alpha)

### Added
- Proof of concept implementation
- Basic daemon structure
- Simple task queue
- Direct Anthropic API integration

### Known Issues
- Limited error handling
- No workspace isolation
- Single task execution only
- No usage management

## [0.0.1] - 2024-10-10 (Prototype)

### Added
- Initial prototype
- Basic Slack bot
- Simple task processor
- File-based storage

---

## Version History Summary

| Version | Release Date | Status | Key Features |
|---------|-------------|---------|--------------|
| 0.1.0 | 2024-10-24 | Stable | Full release with all core features |
| 0.0.9 | 2024-10-20 | Beta | Claude Code CLI integration |
| 0.0.5 | 2024-10-15 | Alpha | Basic daemon and queue |
| 0.0.1 | 2024-10-10 | Prototype | Initial concept |

## Upgrade Guide

### From 0.0.x to 0.1.0

1. **Database Migration**:
   ```bash
   # Backup old database
   cp workspace/tasks.db workspace/tasks.db.backup

   # Run migration
   sle migrate
   ```

2. **Configuration Changes**:
   - Rename `ANTHROPIC_API_KEY` to use Claude Code CLI
   - Update `config.yaml` with new structure
   - Add workspace configuration

3. **Slack App Updates**:
   - Add new slash commands (`/trash`)
   - Update bot permissions
   - Enable Socket Mode

### Breaking Changes in 0.1.0

- Removed direct Anthropic API support
- Changed database schema (migration required)
- New configuration file format
- Updated environment variable names

## Roadmap

### Version 0.2.0 (Planned)
- [ ] Web dashboard for monitoring
- [ ] Advanced scheduling algorithms
- [ ] Multi-workspace support
- [ ] Plugin system for custom executors
- [ ] Enhanced Git workflows
- [ ] Team collaboration features

### Version 0.3.0 (Future)
- [ ] Kubernetes deployment support
- [ ] Distributed task execution
- [ ] Advanced analytics and reporting
- [ ] Integration with CI/CD pipelines
- [ ] Custom model support
- [ ] Enterprise features

## Security Updates

### Security Policy

We take security seriously. Please report vulnerabilities to security@sleepless-agent.dev

### Security Fixes

- **0.1.0**: Fixed token exposure in logs
- **0.0.9**: Sanitized user input in Slack commands
- **0.0.5**: Added workspace isolation

## Deprecations

### Deprecated in 0.1.0
- Direct Anthropic API calls (use Claude Code CLI)
- `ANTHROPIC_API_KEY` environment variable
- Legacy task queue format

### Removal Timeline
- 0.2.0: Remove deprecated API methods
- 0.3.0: Remove legacy configuration support

## Contributing

See [CONTRIBUTING.md](https://github.com/context-machine-lab/sleepless-agent/blob/main/CONTRIBUTING.md) for how to contribute to the project.

## License

This project is licensed under the MIT License - see the [LICENSE](https://github.com/context-machine-lab/sleepless-agent/blob/main/LICENSE) file for details.

---

[Unreleased]: https://github.com/context-machine-lab/sleepless-agent/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/context-machine-lab/sleepless-agent/releases/tag/v0.1.0
[0.0.9]: https://github.com/context-machine-lab/sleepless-agent/releases/tag/v0.0.9
[0.0.5]: https://github.com/context-machine-lab/sleepless-agent/releases/tag/v0.0.5
[0.0.1]: https://github.com/context-machine-lab/sleepless-agent/releases/tag/v0.0.1