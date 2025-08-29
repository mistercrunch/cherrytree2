"""GitHub CLI interface for cherrytree operations."""

import os
import subprocess
from typing import List, Optional

import typer
from rich.console import Console


class GitHubError(Exception):
    """GitHub API operation failed."""

    pass


class GitHubInterface:
    """
    Consolidated interface for GitHub CLI operations.

    Handles authentication, token management, and GitHub CLI command execution.
    """

    def __init__(self, console: Optional[Console] = None):
        """Initialize GitHubInterface with optional console."""
        self.console = console or Console()

    def run_gh_command(self, args: List[str]) -> str:
        """Execute gh CLI command and return stdout."""
        try:
            result = subprocess.run(["gh"] + args, capture_output=True, text=True, check=True)
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            raise GitHubError(
                f"GitHub CLI command failed: gh {' '.join(args)}\nError: {e.stderr}"
            ) from e

    def get_github_token(self) -> str:
        """Get GitHub token from gh CLI or environment."""
        # Try to get token from gh CLI first
        try:
            token = self.run_gh_command(["auth", "token"])
            return token.strip()
        except GitHubError:
            # Fall back to environment variable
            env_token: str | None = os.getenv("GITHUB_TOKEN")
            if not env_token:
                self.console.print("[red]Error: No GitHub authentication found[/red]")
                self.console.print("Run: gh auth login")
                self.console.print("Or set GITHUB_TOKEN environment variable")
                raise typer.Exit(1) from None
            return env_token  # Type checked: env_token is not None due to check above

    def check_auth(self) -> None:
        """Check if GitHub CLI is authenticated."""
        try:
            self.run_gh_command(["auth", "status"])
        except GitHubError:
            self.console.print("[red]Error: GitHub CLI not authenticated[/red]")
            self.console.print("Run: gh auth login")
            raise typer.Exit(1) from None

    def is_authenticated(self) -> bool:
        """Check if GitHub CLI is authenticated (no exception)."""
        try:
            self.run_gh_command(["auth", "status"])
            return True
        except GitHubError:
            return False
