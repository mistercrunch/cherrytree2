"""Core git operations interface."""

import subprocess
from pathlib import Path
from typing import List, Optional, Tuple

from rich.console import Console


class GitError(Exception):
    """Custom exception for git operation errors."""

    pass


class GitBasicInterface:
    """
    Core git operations interface providing basic git functionality.

    This class handles fundamental git operations like running commands,
    checking branches, and basic repository queries. It serves as the
    foundation for more specialized git analysis classes.
    """

    def __init__(self, repo_path: Optional[Path] = None, console: Optional[Console] = None):
        """Initialize GitBasicInterface with repository path and console."""
        self.repo_path = repo_path or Path.cwd()
        self.console = console or Console()

        # Ensure repo_path is a Path object
        if isinstance(self.repo_path, str):
            self.repo_path = Path(self.repo_path)

        # Check if it's a git repository
        if not (self.repo_path / ".git").exists():
            raise GitError(f"Not a git repository: {self.repo_path}")

    def run_command(self, args: List[str]) -> str:
        """Execute git command and return stdout."""
        try:
            result = subprocess.run(
                ["git"] + args, cwd=self.repo_path, capture_output=True, text=True, check=True
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            raise GitError(f"Git command failed: git {' '.join(args)}\nError: {e.stderr}") from e

    def run_command_binary_safe(self, args: List[str], allow_failure: bool = False) -> str:
        """Execute git command and return stdout, safely handling binary content."""
        try:
            result = subprocess.run(
                ["git"] + args, cwd=self.repo_path, capture_output=True, check=not allow_failure
            )

            # For merge-tree, exit code 1 means conflicts exist (not an error)
            if allow_failure and result.returncode == 1 and args[0] == "merge-tree":
                # This is expected for merge-tree with conflicts
                pass
            elif allow_failure and result.returncode != 0:
                # Other non-zero exit codes are real errors
                try:
                    stderr = result.stderr.decode("utf-8") if result.stderr else ""
                except UnicodeDecodeError:
                    stderr = str(result.stderr) if result.stderr else ""
                raise GitError(f"Git command failed: git {' '.join(args)}\nError: {stderr}")

            # Try UTF-8 decode first
            try:
                return result.stdout.decode("utf-8").strip()
            except UnicodeDecodeError:
                # Handle binary content by using errors='replace' or 'ignore'
                decoded = result.stdout.decode("utf-8", errors="replace").strip()
                # For merge-tree output with binary files, we can still parse the textual parts
                return decoded

        except subprocess.CalledProcessError as e:
            # Try to decode stderr for error message
            try:
                stderr = e.stderr.decode("utf-8") if e.stderr else ""
            except UnicodeDecodeError:
                stderr = str(e.stderr) if e.stderr else ""
            raise GitError(f"Git command failed: git {' '.join(args)}\nError: {stderr}") from e

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

    def get_current_branch(self) -> str:
        """Get the name of the current branch."""
        try:
            return self.run_command(["rev-parse", "--abbrev-ref", "HEAD"])
        except GitError as e:
            raise GitError(f"Failed to get current branch: {e}") from e

    def get_branch_head(self, branch: str) -> str:
        """Get the HEAD SHA of specified branch."""
        try:
            return self.run_command(["rev-parse", f"refs/heads/{branch}"])
        except GitError as e:
            raise GitError(f"Failed to get branch head for {branch}: {e}") from e

    def get_merge_base(self, branch: str, base_branch: str = "master") -> Tuple[str, str]:
        """Get merge-base SHA and date between branch and base_branch."""
        try:
            # Get merge-base commit SHA
            merge_base_sha = self.run_command(["merge-base", base_branch, branch])

            # Get the date of the merge-base commit
            merge_base_date = self.run_command(["log", "-1", "--format=%ci", merge_base_sha])

            return merge_base_sha[:8], merge_base_date  # Return 8-digit SHA

        except GitError as e:
            raise GitError(
                f"Failed to find merge-base between {base_branch} and {branch}: {e}"
            ) from e

    def verify_pr_sha_exists(self, sha: str) -> bool:
        """Check if a commit SHA exists in the repository."""
        try:
            self.run_command(["cat-file", "-e", sha])
            return True
        except GitError:
            return False

    def fetch_and_checkout_branch(self, branch: str) -> None:
        """Fetch latest remotes and checkout branch from origin."""
        self.console.print("[dim]Fetching latest from origin...[/dim]")
        self.run_command(["fetch", "origin"])

        if not self.check_branch_exists(branch):
            if self.check_remote_branch_exists(branch):
                self.console.print(
                    f"[dim]Creating local branch {branch} from origin/{branch}[/dim]"
                )
                self.run_command(["checkout", "-b", branch, f"origin/{branch}"])
            else:
                raise GitError(f"Branch {branch} does not exist locally or on origin")
        else:
            self.console.print(f"[dim]Checking out existing branch {branch}[/dim]")
            self.run_command(["checkout", branch])

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
