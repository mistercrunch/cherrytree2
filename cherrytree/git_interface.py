"""Consolidated git operations interface for cherrytree."""

import re
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import typer
from rich.console import Console

from .commit import Commit
from .micro_release import Micro


class GitError(Exception):
    """Git operation failed."""

    pass


class GitInterface:
    """
    Consolidated interface for all git operations.

    Provides a clean, object-oriented interface to git operations,
    consolidating functionality from git_utils.py, git_parser.py,
    and scattered functions in sync.py.
    """

    def __init__(self, repo_path: Path, console: Optional[Console] = None):
        """Initialize GitInterface with repository path and optional console."""
        self.repo_path = repo_path.resolve()
        self.console = console or Console()

    def run_command(self, args: List[str]) -> str:
        """Execute git command and return stdout."""
        try:
            result = subprocess.run(
                ["git"] + args, cwd=self.repo_path, capture_output=True, text=True, check=True
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            raise GitError(f"Git command failed: git {' '.join(args)}\nError: {e.stderr}") from e

    # Branch Management Operations
    def check_branch_exists(self, branch: str) -> bool:
        """Check if branch exists locally."""
        try:
            self.run_command(["rev-parse", "--verify", f"refs/heads/{branch}"])
            return True
        except GitError:
            return False

    def check_remote_branch_exists(self, branch: str) -> bool:
        """Check if branch exists on origin remote."""
        try:
            self.run_command(["rev-parse", "--verify", f"refs/remotes/origin/{branch}"])
            return True
        except GitError:
            return False

    def fetch_and_checkout_branch(self, branch: str) -> None:
        """Fetch latest remotes and checkout branch from origin."""
        self.console.print("[dim]Fetching latest from origin...[/dim]")
        self.run_command(["fetch", "origin"])

        self.console.print(f"[dim]Creating local branch {branch} from origin/{branch}...[/dim]")
        self.run_command(["checkout", "-b", branch, f"origin/{branch}"])

    def get_merge_base(self, branch: str, base_branch: str = "master") -> Tuple[str, str]:
        """Get merge-base SHA and date where branch diverged from base_branch."""
        # Check if branch exists locally
        if not self.check_branch_exists(branch):
            # Check if branch exists on remote
            self.console.print("[dim]Checking remote branches...[/dim]")
            self.run_command(["fetch", "origin"])

            if self.check_remote_branch_exists(branch):
                self.console.print(f"[yellow]Branch {branch} not found locally.[/yellow]")
                self.console.print(f"[yellow]Found origin/{branch} on remote.[/yellow]")
                self.console.print(
                    f"[dim]Need to run: git checkout -b {branch} origin/{branch}[/dim]"
                )

                # Prompt user
                create_branch = typer.confirm("Want me to run this command for you?")
                if create_branch:
                    self.fetch_and_checkout_branch(branch)
                else:
                    self.console.print("[red]Cannot proceed without local branch.[/red]")
                    self.console.print(
                        f"[yellow]Run manually: git checkout -b {branch} origin/{branch}[/yellow]"
                    )
                    raise typer.Exit(1) from None
            else:
                # Show available remote branches
                try:
                    remote_branches = self.run_command(
                        ["branch", "-r", "--format=%(refname:short)"]
                    )
                    release_branches = [
                        b.replace("origin/", "")
                        for b in remote_branches.split("\n")
                        if b.startswith("origin/")
                        and b.replace("origin/", "").replace(".", "").replace("-", "").isdigit()
                    ]

                    self.console.print(
                        f"[red]Error: Branch {branch} not found locally or on remote.[/red]"
                    )
                    if release_branches:
                        self.console.print(
                            f"[yellow]Available release branches: {', '.join(release_branches)}[/yellow]"
                        )
                    else:
                        self.console.print("[yellow]No release branches found.[/yellow]")
                    raise typer.Exit(1) from None
                except GitError:
                    self.console.print(f"[red]Error: Branch {branch} not found.[/red]")
                    raise typer.Exit(1) from None

        # Get merge-base and abbreviate to 8 digits
        full_base_sha = self.run_command(["merge-base", base_branch, branch])
        base_sha = full_base_sha[:8]  # Truncate to 8 digits
        base_date = self.run_command(["show", "--format=%ci", "-s", full_base_sha])
        return base_sha, base_date

    # Commit Operations
    def get_branch_commits(self, branch: str, base_sha: str) -> List[Commit]:
        """Get all commits in branch since merge-base."""
        # Get commits that are in branch but not in the merge-base (use full SHA for range)
        # Need to expand base_sha back to full SHA for git log range
        full_base_sha = self.run_command(["rev-parse", base_sha])

        log_output = self.run_command(
            [
                "log",
                f"{full_base_sha}..{branch}",
                "--oneline",
                "--format=%h|%s|%ci",  # %h = 8-digit abbreviated SHA
            ]
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

                commits.append(Commit(sha=sha, message=message, date=date, pr_number=pr_number))

        return commits

    # Tag Operations
    def get_release_tags(self, minor_version: str) -> List[Micro]:
        """Get git tags for micro releases of a minor version."""
        try:
            # Get all tags that match the minor version pattern
            tag_pattern = f"{minor_version}.*"
            tags_output = self.run_command(
                ["tag", "--list", tag_pattern, "--sort=-version:refname"]
            )

            if not tags_output:
                return []

            tags = []
            for tag_name in tags_output.split("\n"):
                if not tag_name.strip():
                    continue

                # Get tag SHA and date
                try:
                    tag_sha = self.run_command(["rev-list", "-n", "1", tag_name])[:8]  # 8-digit SHA
                    tag_date = self.run_command(["log", "-1", "--format=%ci", tag_name])

                    # Get commit date (when the code was written, not when tag was created)
                    commit_date = self.run_command(["log", "-1", "--format=%ci", tag_sha])

                    tags.append(
                        Micro(
                            version=tag_name,
                            tag_sha=tag_sha,
                            tag_date=tag_date,
                            commit_date=commit_date,
                        )
                    )
                except GitError:
                    # Skip tags that can't be processed
                    continue

            return tags

        except GitError:
            return []

    # PR Mapping Operations
    def build_pr_sha_mapping(self, pr_numbers: List[int]) -> Tuple[Dict[int, str], List[int]]:
        """Build mapping of PR number → merge commit SHA by parsing git log."""
        try:
            # Get commits from master branch that mention PR numbers
            log_output = self.run_command(
                [
                    "log",
                    "master",
                    "--oneline",
                    "--format=%h|%s",
                    "--grep=#[0-9]",
                    "--extended-regexp",
                ]
            )

            pr_to_sha = {}
            pr_chronological_order = []

            for line in log_output.split("\n"):
                if not line.strip():
                    continue

                parts = line.split("|", 1)
                if len(parts) != 2:
                    continue

                sha, message = parts

                # Extract all PR numbers from commit message
                pr_matches = re.findall(r"#(\d+)", message)
                for pr_match in pr_matches:
                    pr_number = int(pr_match)

                    # Only include PRs we're looking for
                    if pr_number in pr_numbers and pr_number not in pr_to_sha:
                        pr_to_sha[pr_number] = sha[:8]  # 8-digit SHA
                        pr_chronological_order.append(pr_number)

            return pr_to_sha, pr_chronological_order

        except GitError as e:
            self.console.print(f"[yellow]Warning: Failed to parse git log: {e}[/yellow]")
            return {}, []

    def get_release_branches(self) -> List[str]:
        """Get all release branches from git repository."""
        try:
            # Get remote branches that look like version numbers
            branches_output = self.run_command(["branch", "-r", "--format=%(refname:short)"])

            release_branches = []
            for branch in branches_output.split("\n"):
                if branch.startswith("origin/"):
                    branch_name = branch.replace("origin/", "")
                    # Check if it looks like a version (e.g., "4.0", "4.1", "5.0")
                    parts = branch_name.split(".")
                    if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                        release_branches.append(branch_name)

            return release_branches

        except GitError:
            return []

    def get_tags_for_overview(self) -> List[str]:
        """Get list of minor versions by scanning git tags."""
        try:
            # Get all tags that match version pattern
            tags_output = self.run_command(["tag", "--list"])
            if not tags_output:
                return []

            tags = tags_output.split("\n")

            # Extract minor versions from tags (e.g., "6.0.0rc1" -> "6.0", "4.1.2" -> "4.1")
            minor_versions = set()
            version_pattern = re.compile(r"^(\d+\.\d+)\..*")

            for tag in tags:
                match = version_pattern.match(tag.strip())
                if match:
                    minor_version = match.group(1)
                    minor_versions.add(minor_version)

            return list(minor_versions)

        except GitError:
            return []

    def get_commits_in_range(self, start_sha: str, end_sha: str) -> List[Commit]:
        """Get commits between two SHAs."""
        try:
            # Get commits in range start_sha..end_sha
            log_output = self.run_command(
                ["log", f"{start_sha}..{end_sha}", "--format=%h|%s|%an|%ci"]
            )

            commits = []
            for line in log_output.split("\n"):
                if not line.strip():
                    continue

                parts = line.split("|", 3)
                if len(parts) >= 4:
                    sha, message, author, date = parts

                    # Extract PR number from commit message
                    pr_match = re.search(r"#(\d+)", message)
                    pr_number = int(pr_match.group(1)) if pr_match else None

                    commits.append(
                        Commit(
                            sha=sha, message=message, author=author, date=date, pr_number=pr_number
                        )
                    )

            return commits

        except GitError:
            return []
