"""Sync command implementation - build release branch state from git and GitHub."""

from pathlib import Path
from typing import Dict, Optional

import typer
from rich.console import Console

from .github_interface import GitHubInterface
from .minor import Minor

console = Console()


def sync_command(
    minor_version: str,
    repo_path: Optional[str] = typer.Option(None, "--repo", help="Local repository path"),
    github_repo: str = typer.Option("apache/superset", "--github-repo", help="GitHub repository"),
    output_dir: str = typer.Option("releases", "--output", help="Output directory for YAML files"),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would be done without writing files"
    ),
) -> None:
    """Sync release branch state from git and GitHub."""

    if not repo_path:
        console.print("[red]Error: --repo path is required[/red]")
        console.print("Set with: cherrytree config set-repo /path/to/superset")
        console.print("Or use: cherrytree sync 5.0 --repo /path/to/superset")
        raise typer.Exit(1) from None

    repo_path_obj = Path(repo_path).resolve()
    if not repo_path_obj.exists():
        console.print(f"[red]Error: Repository path does not exist: {repo_path_obj}[/red]")
        raise typer.Exit(1) from None

    if not (repo_path_obj / ".git").exists():
        console.print(f"[red]Error: Not a git repository: {repo_path_obj}[/red]")
        raise typer.Exit(1) from None

    try:
        # Create GitHub interface for authentication and token management
        github = GitHubInterface(console)

        # Check GitHub CLI authentication before starting
        github.check_auth()

        # Build complete release state using class method with interfaces
        state = Minor.sync_from_github(
            repo_path=repo_path_obj,
            minor_version=minor_version,
            github_repo=github_repo,
            get_github_token_func=github.get_github_token,
            console=console,
        )

        if dry_run:
            # Count PRs by status
            status_counts: Dict[str, int] = {}
            for pr in state.targeted_prs:
                status = pr.get("status", "unknown")
                status_counts[status] = status_counts.get(status, 0) + 1

            console.print(f"[yellow]DRY RUN - Would create {minor_version}.yml with:[/yellow]")
            console.print(f"  Base SHA: {state.base_sha}")
            console.print(f"  Micro releases: {len(state.micro_releases)} tags")
            for micro in state.micro_releases[:3]:  # Show first 3 tags
                console.print(f"    {micro['version']}: {micro['tag_sha']}")
            if len(state.micro_releases) > 3:
                console.print(f"    ... and {len(state.micro_releases) - 3} more")
            console.print(f"  Targeted PRs: {len(state.targeted_prs)} (actionable only)")
            for status, count in status_counts.items():
                console.print(f"    {status}: {count}")
            console.print(f"  Branch commits: {len(state.commits_in_branch)}")
            return

        # Save to file using Minor's to_yaml method
        output_path = state.to_yaml(output_dir)

        console.print(f"[green]✅ Synced {minor_version} release branch[/green]")
        console.print(f"[dim]Written to: {output_path}[/dim]")
        console.print(f"[dim]Base SHA: {state.base_sha}[/dim]")
        console.print(f"[dim]Targeted PRs: {len(state.targeted_prs)} (open or merged)[/dim]")
        console.print(f"[dim]Branch commits: {len(state.commits_in_branch)}[/dim]")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1) from None
