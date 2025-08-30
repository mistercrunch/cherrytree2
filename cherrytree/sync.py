"""Sync command implementation - build release branch state from git and GitHub."""

from pathlib import Path
from typing import Dict

import typer
from rich.console import Console

from .github_interface import GitHubInterface
from .minor import Minor

console = Console()


def sync_command(
    minor_version: str,
    github_repo: str = "apache/superset",
    output_dir: str = "releases",
    dry_run: bool = False,
) -> None:
    """Sync release branch state from git and GitHub."""
    try:
        repo_path_obj = Path.cwd().resolve()
        # GitInterface will check if it's a git repo
    except Exception:
        console.print("[red]Error: Current directory is not a git repository[/red]")
        console.print("[yellow]Please run cherrytree from within a git repository.[/yellow]")
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
        absolute_path = output_path.resolve()

        console.print()
        console.print(f"[green]✅ Successfully synced {minor_version} release branch[/green]")
        console.print(f"[cyan]📄 YAML file saved to: {absolute_path}[/cyan]")
        console.print()
        console.print("[bold]Summary:[/bold]")
        console.print(f"├── Base SHA: {state.base_sha}")
        console.print(f"├── Branch HEAD: {state.branch_head_sha}")
        console.print(f"├── Work queue: {len(state.targeted_prs)} PRs need action")
        console.print(f"├── Branch commits: {len(state.commits_in_branch)} total")
        console.print(f"└── Micro releases: {len(state.micro_releases)} tags")
        console.print()
        console.print(f"[dim]Next: Run 'ct status {minor_version}' to see actionable PRs[/dim]")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1) from None
