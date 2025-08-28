"""Utility functions for cherrytree CLI."""


def get_pr_link(pr_number: int, github_repo: str = "apache/superset") -> str:
    """Generate clickable link for PR number."""
    return f"https://github.com/{github_repo}/pull/{pr_number}"


def get_commit_link(sha: str, github_repo: str = "apache/superset") -> str:
    """Generate clickable link for commit SHA."""
    return f"https://github.com/{github_repo}/commit/{sha}"


def format_clickable_pr(pr_number: int, github_repo: str = "apache/superset") -> str:
    """Format PR number as clickable link using Rich markup."""
    url = get_pr_link(pr_number, github_repo)
    return f"[link={url}]#{pr_number}[/link]"


def format_clickable_commit(sha: str, github_repo: str = "apache/superset") -> str:
    """Format commit SHA as clickable link using Rich markup."""
    url = get_commit_link(sha, github_repo)
    # Use 8-digit abbreviated SHA for display
    display_sha = sha[:8] if len(sha) > 8 else sha
    return f"[link={url}]{display_sha}[/link]"
