"""Micro release class for type-safe micro release handling."""

import re
from typing import Any, Dict

from packaging import version

from .formatting import format_short_date, format_short_sha


class Micro:
    """
    Represents a micro release with type-safe access to fields.

    Attributes match the YAML structure exactly for consistency.
    """

    def __init__(
        self,
        version: str,
        tag_sha: str,
        tag_date: str,
        commit_date: str,
    ):
        """Initialize Micro with required fields from YAML structure."""
        self.version = version
        self.tag_sha = tag_sha
        self.tag_date = tag_date
        self.commit_date = commit_date

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Micro":
        """Create a Micro from a dictionary (e.g., from YAML data)."""
        return cls(
            version=data.get("version", ""),
            tag_sha=data.get("tag_sha", ""),
            tag_date=data.get("tag_date", ""),
            commit_date=data.get("commit_date", ""),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for YAML serialization."""
        return {
            "version": self.version,
            "tag_sha": self.tag_sha,
            "tag_date": self.tag_date,
            "commit_date": self.commit_date,
        }

    def github_tag_url(self, repo: str = "apache/superset") -> str:
        """Generate GitHub tag URL."""
        return f"https://github.com/{repo}/releases/tag/{self.version}"

    def commit_url(self, repo: str = "apache/superset") -> str:
        """Generate GitHub commit URL for this micro release."""
        return f"https://github.com/{repo}/commit/{self.tag_sha}"

    def format_clickable_tag(self, repo: str = "apache/superset") -> str:
        """Format version as clickable tag link using Rich markup."""
        url = self.github_tag_url(repo)
        return f"[link={url}]{self.version}[/link]"

    def format_clickable_commit(self, repo: str = "apache/superset") -> str:
        """Format tag SHA as clickable commit link using Rich markup."""
        url = self.commit_url(repo)
        return f"[link={url}]{self.short_sha}[/link]"

    def compare_version(self, other: "Micro") -> int:
        """Compare versions. Returns -1 if self < other, 0 if equal, 1 if self > other."""
        try:
            self_ver = version.parse(self.version)
            other_ver = version.parse(other.version)
            if self_ver < other_ver:
                return -1
            elif self_ver > other_ver:
                return 1
            return 0
        except Exception:
            # Fall back to string comparison
            if self.version < other.version:
                return -1
            elif self.version > other.version:
                return 1
            return 0

    # Properties for common access patterns
    @property
    def is_rc(self) -> bool:
        """Whether this is a release candidate."""
        return "rc" in self.version.lower()

    @property
    def is_stable(self) -> bool:
        """Whether this is a stable release (not RC)."""
        return not self.is_rc

    @property
    def short_sha(self) -> str:
        """8-character abbreviated SHA for display."""
        return format_short_sha(self.tag_sha)

    @property
    def short_date(self) -> str:
        """Short date format (YYYY-MM-DD) for table display."""
        return format_short_date(self.tag_date)

    @property
    def major_minor(self) -> str:
        """Extract major.minor version (e.g., '6.0.0rc1' -> '6.0')."""
        try:
            # Match patterns like "6.0.0rc1" -> "6.0"
            match = re.match(r"(\d+\.\d+)", self.version)
            if match:
                return match.group(1)
            return self.version
        except Exception:
            return self.version

    def __repr__(self) -> str:
        """String representation."""
        return f"Micro('{self.version}', {self.short_sha}, {'rc' if self.is_rc else 'stable'})"

    def __str__(self) -> str:
        """Human-readable string representation."""
        status = "RC" if self.is_rc else "Stable"
        return f"{self.version} ({status}, {self.short_date})"

    def __eq__(self, other: object) -> bool:
        """Check equality with another Micro instance."""
        if not isinstance(other, Micro):
            return False
        return self.version == other.version and self.tag_sha == other.tag_sha

    def __lt__(self, other: "Micro") -> bool:
        """Support sorting by version."""
        return self.compare_version(other) < 0
