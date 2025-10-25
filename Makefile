.PHONY: help setup run dev logs clean test db db-reset

help:
	@echo "Sleepless Agent - Commands"
	@echo ""
	@echo "setup              Install dependencies"
	@echo "run                Run agent daemon"
	@echo "dev                Run with debug logging"
	@echo "logs               Follow live logs"
	@echo "test               Run basic tests"
	@echo "db                 Query database"
	@echo "db-reset           Clear database"
	@echo "clean              Clean cache and logs"
	@echo "install-service    Install as systemd service (Linux)"
	@echo "install-launchd    Install as launchd service (macOS)"

setup:
	python -m venv venv
	./venv/bin/pip install -e .
	cp .env.example .env
	@echo "✓ Setup complete. Edit .env with your tokens"

run:
	sle daemon

dev:
	PYTHONUNBUFFERED=1 sle daemon

logs:
	tail -f workspace/data/agent.log

test:
	@echo "Testing imports..."
	python -c "from sleepless_agent.runtime import SleeplessAgent; print('✓ Imports OK')"

db:
	sqlite3 workspace/data/tasks.db "SELECT id, description, status, priority FROM tasks LIMIT 10;"

db-reset:
	rm -f workspace/data/tasks.db workspace/data/*.db
	@echo "✓ Database cleared"

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache
	@echo "✓ Cache cleaned"

install-service:
	@echo "Installing systemd service..."
	sudo cp src/sleepless_agent/deployment/sleepless-agent.service /etc/systemd/system/
	sudo systemctl daemon-reload
	sudo systemctl enable sleepless-agent
	@echo "✓ Service installed. Start with: sudo systemctl start sleepless-agent"

install-launchd:
	@echo "Installing launchd service..."
	@echo "Note: Update WorkingDirectory in src/sleepless_agent/deployment/com.sleepless-agent.plist first!"
	cp src/sleepless_agent/deployment/com.sleepless-agent.plist ~/Library/LaunchAgents/
	launchctl load ~/Library/LaunchAgents/com.sleepless-agent.plist
	@echo "✓ Service installed and running"

uninstall-service:
	sudo systemctl stop sleepless-agent
	sudo systemctl disable sleepless-agent
	sudo rm /etc/systemd/system/sleepless-agent.service
	sudo systemctl daemon-reload
	@echo "✓ Service uninstalled"

uninstall-launchd:
	launchctl unload ~/Library/LaunchAgents/com.sleepless-agent.plist
	rm ~/Library/LaunchAgents/com.sleepless-agent.plist
	@echo "✓ Service uninstalled"

stats:
	@echo "=== Performance Metrics (last 24h) ==="
	@tail -1000 workspace/data/metrics.jsonl 2>/dev/null | jq -s 'length as $$count | [.[] | select(.success == true)] | {total: $$count, successful: length, failed: ($$count - length), avg_duration: (map(.duration_seconds) | add / length | round | . as $$t | if $$t > 60 then "\($$t / 60 | floor)m\($$t % 60)s" else "\($$t)s" end)}' || echo "No metrics available"

status:
	@echo "=== Agent Status ==="
	@pgrep -f "sleepless_agent" > /dev/null && echo "✓ Daemon running" || echo "✗ Daemon not running"
	@test -f .env && echo "✓ .env configured" || echo "✗ .env missing"
	@test -f workspace/data/tasks.db && echo "✓ Database exists" || echo "✗ Database missing"
	@echo ""
	@echo "Queue status:"
	@sqlite3 workspace/data/tasks.db "SELECT status, COUNT(*) FROM tasks GROUP BY status;" 2>/dev/null || echo "(no database)"

backup:
	@mkdir -p backups
	@tar czf backups/sleepless-agent-$$(date +%Y%m%d-%H%M%S).tar.gz workspace/data/
	@echo "✓ Backup created"
