"""PullRequest class for type-safe PR handling."""

from typing import Any, Callable, Dict, List

from .formatting import format_short_sha


class PullRequest:
    """
    Represents a pull request with type-safe access to fields.

    Attributes match the YAML structure exactly for consistency.
    """

    def __init__(
        self,
        pr_number: int,
        title: str,
        author: str,
        master_sha: str,
        is_merged: bool,
    ):
        """Initialize PullRequest with required fields from YAML structure."""
        self.pr_number = pr_number
        self.title = title
        self.author = author
        self.master_sha = master_sha
        self.is_merged = is_merged

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PullRequest":
        """Create a PullRequest from a dictionary (e.g., from YAML data)."""
        return cls(
            pr_number=data.get("pr_number", 0),
            title=data.get("title", ""),
            author=data.get("author", ""),
            master_sha=data.get("master_sha", ""),
            is_merged=data.get("is_merged", False),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for YAML serialization."""
        return {
            "pr_number": self.pr_number,
            "title": self.title,
            "author": self.author,
            "master_sha": self.master_sha,
            "is_merged": self.is_merged,
        }

    def github_url(self, repo: str = "apache/superset") -> str:
        """Generate GitHub PR URL."""
        return f"https://github.com/{repo}/pull/{self.pr_number}"

    def commit_url(self, repo: str = "apache/superset") -> str:
        """Generate GitHub commit URL."""
        return f"https://github.com/{repo}/commit/{self.master_sha}"

    def format_clickable_pr(self, repo: str = "apache/superset") -> str:
        """Format PR number as clickable link using Rich markup."""
        url = self.github_url(repo)
        return f"[link={url}]#{self.pr_number}[/link]"

    def format_clickable_commit(self, repo: str = "apache/superset") -> str:
        """Format commit SHA as clickable link using Rich markup."""
        url = self.commit_url(repo)
        return f"[link={url}]{self.short_sha}[/link]"

    def is_ready_for_cherry_pick(self) -> bool:
        """Check if PR is ready for cherry-pick (merged with SHA)."""
        return self.is_merged and bool(self.master_sha)

    # Properties for common access patterns
    @property
    def is_open(self) -> bool:
        """Whether this PR is open (not merged)."""
        return not self.is_merged

    @property
    def short_sha(self) -> str:
        """8-character abbreviated SHA for display."""
        return format_short_sha(self.master_sha)

    def short_title(self, max_length: int = 60) -> str:
        """Truncated title for table display."""
        if len(self.title) > max_length:
            return self.title[: max_length - 3] + "..."
        return self.title

    def display_author(self, max_length: int = 15) -> str:
        """Truncated author for table display."""
        if len(self.author) > max_length:
            return self.author[:max_length]
        return self.author

    @property
    def status_text(self) -> str:
        """Human-readable status."""
        return "Merged" if self.is_merged else "Open"

    def __repr__(self) -> str:
        """String representation."""
        status = "merged" if self.is_merged else "open"
        return f"PullRequest(#{self.pr_number}, '{self.title[:30]}...', {status})"

    def __str__(self) -> str:
        """Human-readable string representation."""
        return f"PR #{self.pr_number}: {self.title} ({self.status_text})"

    @classmethod
    def fetch_labeled_prs(
        cls, github_repo: str, label: str, get_github_token_func: Callable[[], str], console: Any
    ) -> List["PullRequest"]:
        """Get open and merged PRs with specified label from GitHub API."""
        from github import Github

        try:
            # Get GitHub token and create client
            token = get_github_token_func()
            g = Github(token)

            prs = []

            # Search 1: Open PRs with the label
            open_query = f"repo:{github_repo} is:pr label:{label} base:master is:open"
            console.print(f"[dim]Searching for open PRs: {open_query}[/dim]")
            open_issues = g.search_issues(open_query)

            count = 0
            for issue in open_issues:
                count += 1
                if count % 50 == 0:
                    console.print(f"[dim]  Processed {count} open PRs...[/dim]")

                prs.append(
                    cls(
                        pr_number=issue.number,
                        title=issue.title,
                        author=issue.user.login,
                        master_sha="",
                        is_merged=False,
                    )
                )

            console.print(f"[dim]Found {count} open PRs[/dim]")

            # Search 2: Merged PRs with the label
            merged_query = f"repo:{github_repo} is:pr label:{label} base:master is:merged"
            console.print(f"[dim]Searching for merged PRs: {merged_query}[/dim]")
            merged_issues = g.search_issues(merged_query)

            merged_count = 0
            for issue in merged_issues:
                merged_count += 1
                if merged_count % 50 == 0:
                    console.print(f"[dim]  Processed {merged_count} merged PRs...[/dim]")

                prs.append(
                    cls(
                        pr_number=issue.number,
                        title=issue.title,
                        author=issue.user.login,
                        master_sha="",  # Will get from git log
                        is_merged=True,
                    )
                )

            console.print(f"[dim]Found {merged_count} merged PRs[/dim]")
            return prs

        except Exception as e:
            # Import here to avoid circular imports
            class GitHubError(Exception):
                pass

            raise GitHubError(f"Failed to query GitHub API: {e}") from e
