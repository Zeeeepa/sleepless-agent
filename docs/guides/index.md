# Guides

Step-by-step guides for configuring and using Sleepless Agent effectively.

## Setup Guides

### 📱 [Slack Setup](slack-setup.md)
Complete guide to setting up Slack integration.

- Create and configure Slack app
- Set up slash commands
- Configure permissions
- Test the integration

### 🔧 [Environment Setup](environment-setup.md)
Configure environment variables and settings.

- Environment variables
- Configuration files
- Security best practices
- Environment-specific settings

### 🔗 [Git Integration](git-integration.md)
Set up automated Git workflows.

- Repository configuration
- Commit automation
- Pull request creation
- Multi-repo management

## Advanced Guides

### 📁 Project Management
*Coming soon* - Organize tasks into projects.

- Project structure
- Task grouping
- Milestone tracking
- Progress reporting

### 🎯 Custom Prompts
*Coming soon* - Create custom task prompts.

- Prompt engineering
- Template system
- Context injection
- Performance optimization

### 🚀 Deployment
*Coming soon* - Deploy to production.

- System requirements
- Deployment strategies
- Monitoring setup
- Scaling considerations

## Quick Setup Checklist

Follow this order for initial setup:

- [ ] Install Sleepless Agent
- [ ] Configure environment variables
- [ ] Set up Slack application
- [ ] Configure Git integration
- [ ] Test with first task
- [ ] Set up monitoring
- [ ] Configure projects

## Common Workflows

### Basic Setup
```bash
# 1. Install
pip install sleepless-agent

# 2. Configure
cp .env.example .env
nano .env

# 3. Start
sle daemon
```

### Slack Integration
1. Create Slack app
2. Enable Socket Mode
3. Add slash commands
4. Install to workspace
5. Add tokens to `.env`

### Git Workflow
1. Configure Git user
2. Authenticate GitHub CLI
3. Set repository URL
4. Enable auto-commits

## Configuration Priority

Understanding configuration precedence:

1. **Command-line arguments** (highest priority)
2. **Environment variables**
3. **`.env` file**
4. **`config.yaml`**
5. **Default values** (lowest priority)

## Best Practices

### Security
- Store secrets in environment variables
- Use `.env` file with proper permissions
- Never commit sensitive data
- Rotate tokens regularly

### Performance
- Adjust thresholds based on usage
- Configure appropriate timeouts
- Monitor resource usage
- Clean up old workspaces

### Reliability
- Set up proper monitoring
- Configure error notifications
- Regular backup of database
- Test disaster recovery

## Troubleshooting

Common setup issues:

| Issue | Solution | Guide |
|-------|----------|-------|
| Slack bot not responding | Check Socket Mode | [Slack Setup](slack-setup.md#troubleshooting) |
| Tasks not executing | Verify Claude CLI | [Environment Setup](environment-setup.md#validation) |
| Git commits failing | Check authentication | [Git Integration](git-integration.md#troubleshooting) |

## Getting Help

- Check the [FAQ](../faq.md) first
- Review [Troubleshooting](../troubleshooting.md)
- Join [Discord](https://discord.gg/74my3Wkn)
- Open an [issue](https://github.com/context-machine-lab/sleepless-agent/issues)