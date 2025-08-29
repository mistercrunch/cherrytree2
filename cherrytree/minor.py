"""Minor release management class and utilities."""

from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

import yaml
from packaging import version

from .commit import Commit
from .config import load_config
from .formatting import format_short_date
from .micro_release import Micro
from .pull_request import PullRequest


class Minor:
    """
    Represents a minor release version with all its associated data and operations.

    Attributes match the YAML structure exactly for consistency and easy serialization.
    """

    def __init__(
        self,
        minor_version: str,
        branch_name: Optional[str] = None,
        base_sha: str = "",
        base_date: str = "",
        targeted_prs: Optional[List[Dict[str, Any]]] = None,
        commits_in_branch: Optional[List[Dict[str, Any]]] = None,
        micro_releases: Optional[List[Dict[str, Any]]] = None,
        last_synced: str = "",
        synced_from_repo: str = "",
    ):
        """Initialize Minor release object with YAML-aligned attributes."""
        # Core attributes - match YAML structure exactly
        self.minor_version = minor_version
        self.branch_name = branch_name or minor_version
        self.base_sha = base_sha
        self.base_date = base_date
        self.targeted_prs = targeted_prs or []
        self.commits_in_branch = commits_in_branch or []
        self.micro_releases = micro_releases or []
        self.last_synced = last_synced
        self.synced_from_repo = synced_from_repo

    @classmethod
    def from_yaml(cls, minor_version: str, releases_dir: Optional[str] = None) -> Optional["Minor"]:
        """Load a Minor instance from a YAML file."""
        if not releases_dir:
            config = load_config()
            releases_dir = config.get("default", {}).get("releases_dir", "releases")

        release_file = Path(releases_dir) / f"{minor_version}.yml"

        if not release_file.exists():
            return None

        try:
            with open(release_file) as f:
                data = yaml.safe_load(f)
        except Exception:
            return None

        if not data or "release_branch" not in data:
            return None

        return cls.from_dict(data["release_branch"])

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Minor":
        """Create a Minor instance from a dictionary (e.g., from YAML data)."""
        return cls(
            minor_version=data.get("minor_version", ""),
            branch_name=data.get("branch_name", ""),
            base_sha=data.get("base_sha", ""),
            base_date=data.get("base_date", ""),
            targeted_prs=data.get("targeted_prs", []),
            commits_in_branch=data.get("commits_in_branch", []),
            micro_releases=data.get("micro_releases", []),
            last_synced=data.get("last_synced", ""),
            synced_from_repo=data.get("synced_from_repo", ""),
        )

    def to_yaml(self, output_dir: Optional[str] = None) -> Path:
        """Save this Minor instance to a YAML file."""
        if not output_dir:
            config = load_config()
            output_dir = config.get("default", {}).get("releases_dir", "releases")

        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        output_file = output_path / f"{self.minor_version}.yml"

        # Convert to the expected YAML structure
        yaml_data = {"release_branch": self.to_dict()}

        with open(output_file, "w") as f:
            yaml.dump(yaml_data, f, default_flow_style=False, sort_keys=False)

        return output_file

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation matching YAML structure."""
        return {
            "minor_version": self.minor_version,
            "branch_name": self.branch_name,
            "base_sha": self.base_sha,
            "base_date": self.base_date,
            "targeted_prs": self.targeted_prs,
            "commits_in_branch": self.commits_in_branch,
            "micro_releases": self.micro_releases,
            "last_synced": self.last_synced,
            "synced_from_repo": self.synced_from_repo,
        }

    def get_prs(self) -> List[PullRequest]:
        """Get all targeted PRs as PullRequest objects."""
        return [PullRequest.from_dict(pr_data) for pr_data in self.targeted_prs]

    def get_merged_prs_objects(self) -> List[PullRequest]:
        """Get all merged PRs as PullRequest objects."""
        return [pr for pr in self.get_prs() if pr.is_merged]

    def get_open_prs_objects(self) -> List[PullRequest]:
        """Get all open PRs as PullRequest objects."""
        return [pr for pr in self.get_prs() if pr.is_open]

    def get_micros(self) -> List[Micro]:
        """Get all micro releases as Micro objects."""
        return [Micro.from_dict(micro_data) for micro_data in self.micro_releases]

    def get_stable_micros(self) -> List[Micro]:
        """Get only stable micro releases (no RCs)."""
        return [micro for micro in self.get_micros() if micro.is_stable]

    def get_rc_micros(self) -> List[Micro]:
        """Get only release candidate micros."""
        return [micro for micro in self.get_micros() if micro.is_rc]

    def get_latest_micro(self, stable_only: bool = True) -> Optional[Micro]:
        """Get the most recent micro release as Micro object."""
        micros = self.get_stable_micros() if stable_only else self.get_micros()
        return max(micros, key=lambda m: version.parse(m.version)) if micros else None

    def get_commits(self) -> List[Commit]:
        """Get all branch commits as Commit objects."""
        return [Commit.from_dict(commit_data) for commit_data in self.commits_in_branch]

    def get_commits_with_prs(self) -> List[Commit]:
        """Get only commits that are associated with PRs."""
        return [commit for commit in self.get_commits() if commit.has_pr]

    def get_commits_since_release(self) -> List[Commit]:
        """Get commits added since the last release as Commit objects."""
        if not self.micro_releases or not self.commits_in_branch:
            return self.get_commits()

        latest_micro = self.get_latest_micro(stable_only=False)
        if not latest_micro:
            return self.get_commits()

        latest_release_sha = latest_micro.tag_sha

        # Find release commit index
        release_commit_index = None
        for i, commit_data in enumerate(self.commits_in_branch):
            if commit_data.get("sha", "").startswith(latest_release_sha):
                release_commit_index = i
                break

        if release_commit_index is None:
            return self.get_commits()

        # Return commits before the release (newer commits)
        unreleased_commit_data = self.commits_in_branch[:release_commit_index]
        return [Commit.from_dict(data) for data in unreleased_commit_data]

    def get_pr_counts(self) -> Dict[str, int]:
        """Count PRs that are released vs unreleased on the branch."""
        # Get merged PRs only
        merged_prs = [pr for pr in self.targeted_prs if pr.get("is_merged", False)]

        if not self.micro_releases or not self.commits_in_branch:
            # No releases yet or no commit data - all merged PRs are unreleased
            return {"released": 0, "unreleased": len(merged_prs), "total": len(merged_prs)}

        # Find the most recent release tag SHA using Micro objects
        latest_micro = self.get_latest_micro(stable_only=False)
        if not latest_micro:
            return {"released": 0, "unreleased": len(merged_prs), "total": len(merged_prs)}

        latest_release_sha = latest_micro.tag_sha
        if not latest_release_sha:
            return {"released": 0, "unreleased": len(merged_prs), "total": len(merged_prs)}

        # Use Commit objects for cleaner logic
        commits = self.get_commits()

        # Find the position of the latest release in commits
        release_commit_index = None
        for i, commit in enumerate(commits):
            if commit.sha.startswith(latest_release_sha):
                release_commit_index = i
                break

        if release_commit_index is None:
            # Release SHA not found in branch commits - treat all as unreleased
            return {"released": 0, "unreleased": len(merged_prs), "total": len(merged_prs)}

        # PRs in commits after the release are unreleased
        # PRs in commits at or before the release are released
        unreleased_pr_numbers = set()
        released_pr_numbers = set()

        for i, commit in enumerate(commits):
            if commit.has_pr:
                if i < release_commit_index:  # Commits before release (newer commits)
                    unreleased_pr_numbers.add(commit.pr_number)
                else:  # Commits at or after release (older commits)
                    released_pr_numbers.add(commit.pr_number)

        # Count how many of our targeted merged PRs fall into each category
        released_count = 0
        unreleased_count = 0

        for pr in merged_prs:
            pr_number = pr.get("pr_number")
            if pr_number in released_pr_numbers:
                released_count += 1
            elif pr_number in unreleased_pr_numbers:
                unreleased_count += 1
            else:
                # PR not found in branch commits - likely not cherry-picked yet
                unreleased_count += 1

        return {
            "released": released_count,
            "unreleased": unreleased_count,
            "total": released_count + unreleased_count,
        }

    def get_releases(self, include_rcs: bool = True) -> List[str]:
        """Get list of micro release versions as strings, sorted newest first."""
        micros = self.get_micros()
        if not include_rcs:
            micros = [m for m in micros if m.is_stable]

        # Sort by version (newest first) and return version strings
        sorted_micros = sorted(micros, key=lambda m: version.parse(m.version), reverse=True)
        return [m.version for m in sorted_micros]

    def get_latest_release(self, stable_only: bool = True) -> Optional[str]:
        """Get the most recent release version."""
        releases = self.get_releases(include_rcs=not stable_only)
        return releases[0] if releases else None

    def has_sync_file(self) -> bool:
        """Check if this minor has a corresponding sync file."""
        return bool(self.base_sha)  # If loaded from YAML, base_sha will be populated

    def get_next_pr(
        self, skip_open: bool = False, as_object: bool = False
    ) -> Union[Dict[str, Any], PullRequest, None]:
        """Get the next PR to cherry-pick based on git log chronological order."""
        if not self.targeted_prs:
            return None

        # Find first PR that is merged (has SHA) and ready for cherry-pick
        # PRs are already in git log chronological order from sync
        for pr_data in self.targeted_prs:
            pr = PullRequest.from_dict(pr_data)

            if pr.is_ready_for_cherry_pick():
                # This is a merged PR with SHA - ready for cherry-pick
                return pr.to_dict() if not as_object else pr
            elif not skip_open and pr.is_open:
                # This is an open PR and we're not skipping open PRs
                return pr.to_dict() if not as_object else pr

        return None

    def get_next_pr_object(self, skip_open: bool = False) -> Optional[PullRequest]:
        """Get the next PR as a PullRequest object."""
        result = self.get_next_pr(skip_open, as_object=True)
        return result if isinstance(result, PullRequest) else None

    def get_overview(self) -> Dict[str, Any]:
        """Get overview information for this minor version."""
        if not self.has_sync_file():
            return {
                "minor_version": self.minor_version,
                "merge_base_sha": "",
                "merge_base_date": "",
                "most_recent_release": "",
                "unreleased_prs": "",
                "released_prs": "",
                "details": f"ct minor sync {self.minor_version}",
                "has_sync_file": False,
            }

        pr_counts = self.get_pr_counts()
        latest_release = self.get_latest_release(stable_only=True) or ""
        stable_releases = self.get_releases(include_rcs=False)
        details = ", ".join(stable_releases) if stable_releases else "None"

        return {
            "minor_version": self.minor_version,
            "merge_base_sha": self.base_sha,
            "merge_base_date": self.get_base_date_short(),
            "most_recent_release": latest_release,
            "unreleased_prs": pr_counts["unreleased"],
            "released_prs": pr_counts["released"],
            "pr_counts_detailed": pr_counts,  # For JSON output
            "details": details,
            "has_sync_file": True,
        }

    # Properties for commonly accessed computed values
    @property
    def unreleased_count(self) -> int:
        """Number of unreleased PRs."""
        return self.get_pr_counts()["unreleased"]

    @property
    def released_count(self) -> int:
        """Number of released PRs."""
        return self.get_pr_counts()["released"]

    @property
    def latest_stable_release(self) -> Optional[str]:
        """Latest stable release (no RCs)."""
        return self.get_latest_release(stable_only=True)

    def get_base_date_short(self) -> str:
        """Get formatted base date for display (short format)."""
        return format_short_date(self.base_date)

    def __repr__(self) -> str:
        """String representation."""
        return f"Minor('{self.minor_version}', releases={len(self.get_releases())}, prs={len(self.targeted_prs)})"

    def __str__(self) -> str:
        """Human-readable string representation."""
        pr_counts = self.get_pr_counts()
        latest = self.get_latest_release() or "None"
        return f"Minor {self.minor_version}: {latest} ({pr_counts['unreleased']}+{pr_counts['released']} PRs)"

    @classmethod
    def sync_from_github(
        cls,
        repo_path: Path,
        minor_version: str,
        github_repo: str = "apache/superset",
        get_github_token_func: Optional[Callable[[], str]] = None,
        console: Any = None,
    ) -> "Minor":
        """Build complete release branch state from git and GitHub."""
        from .git_interface import GitInterface

        console.print(f"[blue]Analyzing release branch {minor_version}...[/blue]")

        # Create GitInterface for all git operations
        git = GitInterface(repo_path, console)
        branch_name = minor_version

        # Phase 1: Git repository analysis
        console.print(f"[dim]Finding merge-base for {branch_name}...[/dim]")
        base_sha, base_date = git.get_merge_base(branch_name)
        console.print(f"[dim]Base SHA: {base_sha[:8]} ({base_date})[/dim]")

        console.print(f"[dim]Getting commits in {branch_name} branch...[/dim]")
        branch_commits = git.get_branch_commits(branch_name, base_sha)
        console.print(f"[dim]Found {len(branch_commits)} commits in branch[/dim]")

        # Phase 2: Git tag collection for micro releases
        console.print(f"[dim]Getting tags for {minor_version} micro releases...[/dim]")
        release_tags = git.get_release_tags(minor_version)

        # Phase 3: GitHub API collection
        if get_github_token_func is None:
            raise ValueError("get_github_token_func is required")
        label = f"v{minor_version}"
        console.print(f"[dim]Querying GitHub for PRs with label '{label}'...[/dim]")
        labeled_prs = PullRequest.fetch_labeled_prs(
            github_repo, label, get_github_token_func, console
        )
        console.print(f"[dim]Found {len(labeled_prs)} PRs labeled {label}[/dim]")

        # Phase 4: Build PR-to-SHA mapping from git log
        console.print("[dim]Building PR-to-SHA mapping from git log...[/dim]")
        pr_numbers = [pr.pr_number for pr in labeled_prs]
        pr_to_sha, pr_chronological_order = git.build_pr_sha_mapping(pr_numbers)

        # Create lookup for faster access
        pr_lookup = {pr.pr_number: pr for pr in labeled_prs}

        # Build targeted PRs in chronological order from git log
        targeted_prs_dict = []

        # First, add PRs that are in git log (in chronological order)
        for pr_number in pr_chronological_order:
            pr = pr_lookup.get(pr_number)
            if not pr:
                continue  # Shouldn't happen, but be safe
            # Get the actual merge commit SHA from git log parsing
            git_sha = pr_to_sha.get(pr.pr_number, "")

            # These PRs are in git log, so they're merged
            targeted_prs_dict.append(
                {
                    "pr_number": pr.pr_number,
                    "title": pr.title,
                    "master_sha": git_sha,
                    "author": pr.author,
                    "is_merged": True,  # All PRs in git log are merged
                }
            )

        # Then, add any open PRs (not in git log yet) at the end
        for pr in labeled_prs:
            if not pr.is_merged and pr.pr_number not in pr_to_sha:
                targeted_prs_dict.append(
                    {
                        "pr_number": pr.pr_number,
                        "title": pr.title,
                        "master_sha": "",  # No SHA yet, not merged
                        "author": pr.author,
                        "is_merged": False,  # Open PRs need merge first
                    }
                )

        # Count abandoned PRs (closed but not in git log)
        abandoned_count = 0
        for pr in labeled_prs:
            if pr.is_merged and pr.pr_number not in pr_to_sha:
                abandoned_count += 1

        console.print(
            f"[dim]Filtered to {len(targeted_prs_dict)} actionable PRs ({abandoned_count} abandoned)[/dim]"
        )

        # Convert branch commits to dict format
        commits_dict = []
        for commit in branch_commits:
            commits_dict.append(
                {
                    "sha": commit.sha,
                    "message": commit.message,
                    "date": commit.date,
                    "pr_number": commit.pr_number,
                }
            )

        # Convert tag data to dict format
        micro_releases_dict = []
        for tag in release_tags:
            micro_releases_dict.append(
                {
                    "version": tag.version,
                    "tag_sha": tag.tag_sha,
                    "tag_date": tag.tag_date,  # When tag was created (release date)
                    "commit_date": tag.commit_date,  # When code was written
                    # TODO: Add included_prs by analyzing commit range for each tag
                }
            )

        return cls(
            minor_version=minor_version,
            branch_name=branch_name,
            base_sha=base_sha,
            base_date=base_date,
            targeted_prs=targeted_prs_dict,
            commits_in_branch=commits_dict,
            micro_releases=micro_releases_dict,
            last_synced=datetime.now().isoformat(),
            synced_from_repo=github_repo,
        )
