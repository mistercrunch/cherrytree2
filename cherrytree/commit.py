"""Commit class for type-safe commit handling."""

import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .formatting import format_short_date, format_short_sha


class Commit:
    """
    Represents a commit with type-safe access to fields.

    Attributes match the YAML structure exactly for consistency.
    """

    def __init__(
        self,
        sha: str,
        message: str,
        date: str,
        pr_number: Optional[int] = None,
        author: str = "",
    ):
        """Initialize Commit with required fields from YAML structure."""
        self.sha = sha
        self.message = message
        self.date = date
        self.pr_number = pr_number
        self.author = author

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Commit":
        """Create a Commit from a dictionary (e.g., from YAML data)."""
        return cls(
            sha=data.get("sha", ""),
            message=data.get("message", ""),
            date=data.get("date", ""),
            pr_number=data.get("pr_number"),
            author=data.get("author", ""),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for YAML serialization."""
        return {
            "sha": self.sha,
            "message": self.message,
            "date": self.date,
            "pr_number": self.pr_number,
            "author": self.author,
        }

    def github_commit_url(self, repo: str = "apache/superset") -> str:
        """Generate GitHub commit URL."""
        return f"https://github.com/{repo}/commit/{self.sha}"

    def format_clickable_commit(self, repo: str = "apache/superset") -> str:
        """Format commit SHA as clickable link using Rich markup."""
        url = self.github_commit_url(repo)
        return f"[link={url}]{self.short_sha}[/link]"

    def extract_title(self) -> str:
        """Extract the main title from commit message (before PR number)."""
        if not self.message:
            return ""

        # Remove PR number if present: "fix: something (#1234)" -> "fix: something"
        if self.pr_number:
            pr_pattern = f"\\(#{self.pr_number}\\)"
            cleaned = re.sub(pr_pattern, "", self.message).strip()
            return cleaned

        return self.message

    # Properties for common access patterns
    @property
    def short_sha(self) -> str:
        """8-character abbreviated SHA for display."""
        return format_short_sha(self.sha)

    @property
    def short_date(self) -> str:
        """Short date format (YYYY-MM-DD) for table display."""
        return format_short_date(self.date)

    @property
    def has_pr(self) -> bool:
        """Whether this commit is associated with a PR."""
        return self.pr_number is not None

    @property
    def short_message(self, max_length: int = 50) -> str:
        """Truncated commit message for display."""
        title = self.extract_title()
        if len(title) > max_length:
            return title[: max_length - 3] + "..."
        return title

    def __repr__(self) -> str:
        """String representation."""
        pr_info = f", PR #{self.pr_number}" if self.pr_number else ""
        return f"Commit('{self.short_sha}', '{self.extract_title()[:30]}...'{pr_info})"

    def __str__(self) -> str:
        """Human-readable string representation."""
        pr_info = f" (PR #{self.pr_number})" if self.pr_number else ""
        return f"{self.short_sha}: {self.extract_title()}{pr_info}"

    def __eq__(self, other: object) -> bool:
        """Check equality with another Commit instance."""
        if not isinstance(other, Commit):
            return False
        return self.sha == other.sha

    def __hash__(self) -> int:
        """Hash based on SHA for use in sets and dicts."""
        return hash(self.sha)

    @classmethod
    def get_branch_commits(
        cls,
        repo_path: Path,
        branch: str,
        base_sha: str,
        run_git_command_func: Callable[[List[str], Path], str],
    ) -> List["Commit"]:
        """Get all commits in branch since merge-base."""
        # Get commits that are in branch but not in the merge-base (use full SHA for range)
        # Need to expand base_sha back to full SHA for git log range
        full_base_sha = run_git_command_func(["rev-parse", base_sha], repo_path)

        log_output = run_git_command_func(
            [
                "log",
                f"{full_base_sha}..{branch}",
                "--oneline",
                "--format=%h|%s|%ci",  # %h = 8-digit abbreviated SHA
            ],
            repo_path,
        )

        commits = []
        for line in log_output.split("\n"):
            if not line.strip():
                continue

            parts = line.split("|", 2)
            if len(parts) >= 3:
                sha, message, date = parts
                # Extract PR number from commit message if present
                pr_match = re.search(r"#(\d+)", message)
                pr_number = int(pr_match.group(1)) if pr_match else None

                commits.append(cls(sha=sha, message=message, date=date, pr_number=pr_number))

        return commits
