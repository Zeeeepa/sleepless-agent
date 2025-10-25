"""Integrate with project backlog systems (GitHub issues, etc.)"""

from typing import Optional, List

from sleepless_agent.logging import get_logger
logger = get_logger(__name__)


class BacklogIntegrator:
    """Integrate with project backlog systems"""

    def __init__(self, github_token: Optional[str] = None, github_repo: Optional[str] = None):
        """Initialize backlog integrator

        Args:
            github_token: GitHub personal access token
            github_repo: Repository in format "owner/repo"
        """
        self.github_token = github_token
        self.github_repo = github_repo
        self._client = None

    def _get_github_client(self):
        """Lazy load GitHub client"""
        if self._client is None and self.github_token:
            try:
                from github import Github

                self._client = Github(self.github_token)
            except ImportError:
                logger.error("PyGithub package not installed. Install with: pip install PyGithub")
                return None
        return self._client

    def get_issue_from_github(self, labels: Optional[List[str]] = None) -> Optional[str]:
        """Get an issue from GitHub

        Args:
            labels: List of labels to filter by (e.g., ["good first issue", "help wanted"])

        Returns:
            Task description from a GitHub issue
        """
        if not self.github_repo or not self.github_token:
            logger.debug("GitHub repo or token not configured")
            return None

        client = self._get_github_client()
        if not client:
            return None

        try:
            repo = client.get_repo(self.github_repo)

            # Build label filter
            label_query = ""
            if labels:
                label_query = " ".join([f"label:{label}" for label in labels])

            # Search for open issues
            issues = repo.get_issues(state="open", labels=labels if labels else None, sort="updated")

            # Get the first issue
            for issue in issues:
                if not issue.pull_request:  # Skip PRs
                    task_desc = f"GitHub Issue #{issue.number}: {issue.title}\n{issue.body[:200] if issue.body else ''}"
                    return task_desc

            return None

        except Exception as e:
            logger.debug(f"Failed to fetch GitHub issue: {e}")
            return None

    def get_issues_list(self, limit: int = 10, labels: Optional[List[str]] = None) -> List[dict]:
        """Get list of open issues from GitHub

        Args:
            limit: Maximum number of issues to return
            labels: List of labels to filter by

        Returns:
            List of issue dictionaries
        """
        if not self.github_repo or not self.github_token:
            return []

        client = self._get_github_client()
        if not client:
            return []

        try:
            repo = client.get_repo(self.github_repo)
            issues = []

            for issue in repo.get_issues(state="open", labels=labels if labels else None):
                if issue.pull_request:  # Skip PRs
                    continue

                issues.append(
                    {
                        "number": issue.number,
                        "title": issue.title,
                        "body": issue.body[:200] if issue.body else "",
                        "labels": [label.name for label in issue.labels],
                        "updated_at": str(issue.updated_at),
                    }
                )

                if len(issues) >= limit:
                    break

            return issues

        except Exception as e:
            logger.debug(f"Failed to fetch issues list: {e}")
            return []

    def format_issue_as_task(self, issue_number: int) -> Optional[str]:
        """Format a specific GitHub issue as a task description"""
        if not self.github_repo or not self.github_token:
            return None

        client = self._get_github_client()
        if not client:
            return None

        try:
            repo = client.get_repo(self.github_repo)
            issue = repo.get_issue(issue_number)

            task = f"Resolve GitHub Issue #{issue.number}: {issue.title}"
            if issue.body:
                task += f"\n\nDetails: {issue.body[:150]}..."

            return task

        except Exception as e:
            logger.debug(f"Failed to fetch issue #{issue_number}: {e}")
            return None