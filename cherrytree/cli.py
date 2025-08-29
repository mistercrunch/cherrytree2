"""Cherrytree CLI - AI-assisted release management and cherry-picking."""

from typing import Optional

import typer
from rich import print
from rich.console import Console

from . import __version__
from .config import get_repo_path, set_github_command, set_repo_command, show_config_command
from .micro import display_micro_status
from .next import display_next_command
from .status import display_minor_status
from .sync import sync_command
from .tables import display_minors_overview

app = typer.Typer(
    name="cherrytree",
    help="Intelligent AI-assisted release management and cherry-picking for Apache Superset",
)

console = Console()


@app.callback(invoke_without_command=True)
def main_callback(ctx: typer.Context) -> None:
    """Main callback that shows overview when no command is provided."""
    if ctx.invoked_subcommand is None:
        # Show the overview table
        display_minors_overview()
        # Show help after the overview
        print(ctx.get_help())
        raise typer.Exit()


# Create minor subcommand group
minor_app = typer.Typer(name="minor", help="Manage minor release branches", no_args_is_help=True)
app.add_typer(minor_app)

# Create micro subcommand group
micro_app = typer.Typer(
    name="micro", help="Manage micro releases within minor versions", no_args_is_help=True
)
app.add_typer(micro_app)


@minor_app.command("sync")
def minor_sync(
    minor_version: Optional[str] = typer.Argument(
        None, help="Minor version to sync (e.g., 5.0, 4.2). Use --all to sync all valid minors"
    ),
    repo_path: Optional[str] = typer.Option(None, "--repo", help="Local repository path"),
    github_repo: str = typer.Option("apache/superset", "--github-repo", help="GitHub repository"),
    output_dir: str = typer.Option("releases", "--output", help="Output directory for YAML files"),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would be done without writing files"
    ),
    sync_all: bool = typer.Option(
        False, "--all", "-a", help="Sync all valid minor release branches"
    ),
) -> None:
    """Sync release branch state from git and GitHub."""
    # Use configured repo path if not provided
    if not repo_path:
        repo_path = get_repo_path()

    # Validate arguments
    if sync_all and minor_version:
        console.print("[red]Error: Cannot specify both minor version and --all flag[/red]")
        raise typer.Exit(1)

    if not sync_all and not minor_version:
        console.print("[red]Error: Must specify either a minor version or use --all flag[/red]")
        raise typer.Exit(1)

    if sync_all:
        # Import here to avoid circular imports
        from .tables import get_available_minors

        # Get all valid minor versions and sync them
        minors = get_available_minors()
        if not minors:
            console.print("[yellow]No valid minor versions found to sync[/yellow]")
            return

        console.print(f"[bold]Syncing {len(minors)} minor versions: {', '.join(minors)}[/bold]")
        console.print()

        for i, minor in enumerate(minors, 1):
            console.print(f"[bold cyan]({i}/{len(minors)}) Syncing {minor}...[/bold cyan]")
            try:
                sync_command(minor, repo_path, github_repo, output_dir, dry_run)
                console.print(f"[green]✅ Successfully synced {minor}[/green]")
            except Exception as e:
                console.print(f"[red]❌ Failed to sync {minor}: {e}[/red]")
            console.print()
    else:
        assert minor_version is not None  # Validated above
        sync_command(minor_version, repo_path, github_repo, output_dir, dry_run)


@minor_app.command("status")
def minor_status(
    minor_version: str = typer.Argument(help="Minor version to show status for (e.g., 5.0, 4.2)"),
    format_type: str = typer.Option("table", "--format", help="Output format: table or json"),
    repo_path: Optional[str] = typer.Option(None, "--repo", help="Local repository path"),
) -> None:
    """Show status of minor release branch."""
    # Use configured repo path if not provided
    if not repo_path:
        repo_path = get_repo_path()

    display_minor_status(minor_version, format_type, repo_path)


@minor_app.command("next")
def minor_next(
    minor_version: str = typer.Argument(help="Minor version to get next PR for (e.g., 5.0, 4.2)"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed PR information"),
    skip_open: bool = typer.Option(
        False, "--skip-open", help="Skip open PRs, only show merged PRs"
    ),
    format_type: str = typer.Option("text", "--format", help="Output format: text or json"),
) -> None:
    """Get next PR to cherry-pick in chronological order."""
    display_next_command(minor_version, verbose, skip_open, format_type)


@micro_app.command("status")
def micro_status(
    micro_version: str = typer.Argument(
        help="Micro version to show status for (e.g., 6.0.1, 4.0.2rc1)"
    ),
    format_type: str = typer.Option("table", "--format", help="Output format: table or json"),
    repo_path: Optional[str] = typer.Option(None, "--repo", help="Local repository path"),
) -> None:
    """Show PRs included in a specific micro release."""
    # Use configured repo path if not provided
    if not repo_path:
        repo_path = get_repo_path()

    display_micro_status(micro_version, format_type, repo_path)


# Create config subcommand group
config_app = typer.Typer(name="config", help="Manage cherrytree configuration")
app.add_typer(config_app)


@config_app.command("set-repo")
def set_repo(repo_path: str = typer.Argument(help="Path to local git repository")) -> None:
    """Set the local repository path."""
    set_repo_command(repo_path)


@config_app.command("set-github")
def set_github(
    github_repo: str = typer.Argument(help="GitHub repository (e.g., apache/superset)"),
) -> None:
    """Set the GitHub repository."""
    set_github_command(github_repo)


@config_app.command("show")
def show(
    format_type: str = typer.Option("table", "--format", help="Output format: table or json"),
) -> None:
    """Show current configuration."""
    show_config_command(format_type)


@app.command()
def version() -> None:
    """Show version information."""
    print(f"Cherrytree version: [bold]{__version__}[/bold]")


def main() -> None:
    """Main entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
