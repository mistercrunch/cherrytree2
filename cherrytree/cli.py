"""Cherrytree CLI - AI-assisted release management and cherry-picking."""

from typing import Optional

import typer
from rich import print
from rich.console import Console

from . import __version__
from .branch_detection import ensure_release_branch
from .config import set_github_command, show_config_command
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


@app.command("overview")
def overview() -> None:
    """Show overview of all minor releases."""
    display_minors_overview()


# Create micro subcommand group
micro_app = typer.Typer(
    name="micro", help="Manage micro releases within minor versions", no_args_is_help=True
)
app.add_typer(micro_app)


@app.command("sync")
def sync(
    minor_version: Optional[str] = typer.Argument(
        None,
        help="Minor version to sync (e.g., 5.0, 4.2). Use --all to sync all valid minors. If not provided, uses current branch",
    ),
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
    # Validate arguments
    if sync_all and minor_version:
        console.print("[red]Error: Cannot specify both minor version and --all flag[/red]")
        raise typer.Exit(1)

    # If no minor version provided and not --all, detect from current branch
    if not sync_all and not minor_version:
        minor_version = ensure_release_branch(console)

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
                sync_command(minor, github_repo, output_dir, dry_run)
                console.print(f"[green]✅ Successfully synced {minor}[/green]")
            except Exception as e:
                console.print(f"[red]❌ Failed to sync {minor}: {e}[/red]")
            console.print()
    else:
        assert minor_version is not None  # Validated above
        sync_command(minor_version, github_repo, output_dir, dry_run)


@app.command("status")
def status(
    minor_version: Optional[str] = typer.Argument(
        None,
        help="Minor version to show status for (e.g., 5.0, 4.2). If not provided, uses current branch",
    ),
    format_type: str = typer.Option("table", "--format", help="Output format: table or json"),
    limit: Optional[int] = typer.Option(
        None, "--limit", "-l", help="Maximum number of PRs to display"
    ),
) -> None:
    """Show status of minor release branch."""
    # If no minor version provided, detect from current branch
    if not minor_version:
        minor_version = ensure_release_branch(console)

    display_minor_status(minor_version, format_type, limit)


@app.command("next")
def next_pr(
    minor_version: Optional[str] = typer.Argument(
        None,
        help="Minor version to get next PR for (e.g., 5.0, 4.2). If not provided, uses current branch",
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed PR information"),
    skip_open: bool = typer.Option(
        False, "--skip-open", help="Skip open PRs, only show merged PRs"
    ),
    format_type: str = typer.Option("text", "--format", help="Output format: text or json"),
) -> None:
    """Get next PR to cherry-pick in chronological order."""
    # If no minor version provided, detect from current branch
    if not minor_version:
        minor_version = ensure_release_branch(console)

    display_next_command(minor_version, verbose, skip_open, format_type)


@app.command("analyze")
def analyze(
    minor_version: Optional[str] = typer.Argument(
        None,
        help="Minor version to analyze all PRs for (e.g., 5.0, 4.2). If not provided, uses current branch",
    ),
    format_type: str = typer.Option("table", "--format", help="Output format: table or json"),
    complexity_filter: Optional[str] = typer.Option(
        None, "--complexity", help="Filter by complexity: clean,simple,moderate,complex"
    ),
    limit: int = typer.Option(50, "--limit", "-l", help="Maximum number of PRs to analyze"),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Show raw merge-tree output for debugging"
    ),
) -> None:
    """Bulk conflict analysis showing predictions for all PRs in a sortable table."""
    from .conflict_analysis import analyze_all_pr_conflicts

    # If no minor version provided, detect from current branch
    if not minor_version:
        minor_version = ensure_release_branch(console)

    analyze_all_pr_conflicts(minor_version, format_type, complexity_filter, limit, verbose)


@app.command("analyze-next")
def analyze_next(
    minor_version: Optional[str] = typer.Argument(
        None,
        help="Minor version to analyze next PR for (e.g., 5.0, 4.2). If not provided, uses current branch",
    ),
    format_type: str = typer.Option("table", "--format", help="Output format: table or json"),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Show raw merge-tree output for debugging"
    ),
) -> None:
    """Analyze potential conflicts for the next PR to cherry-pick."""
    from .conflict_analysis import analyze_next_pr_conflicts

    # If no minor version provided, detect from current branch
    if not minor_version:
        minor_version = ensure_release_branch(console)

    analyze_next_pr_conflicts(minor_version, format_type, verbose)


@app.command("chain")
def chain(
    minor_version: Optional[str] = typer.Argument(
        None,
        help="Minor version to cherry-pick chain for (e.g., 5.0, 4.2). If not provided, uses current branch",
    ),
    auto_clean: bool = typer.Option(
        False, "--auto-clean", help="Automatically cherry-pick clean commits without prompting"
    ),
    max_picks: int = typer.Option(10, "--max", help="Maximum number of cherry-picks to attempt"),
) -> None:
    """Interactive cherry-pick chain with conflict analysis."""
    from .conflict_analysis import run_cherry_pick_chain

    # If no minor version provided, detect from current branch
    if not minor_version:
        minor_version = ensure_release_branch(console)

    run_cherry_pick_chain(minor_version, auto_clean, max_picks)


@micro_app.command("status")
def micro_status(
    micro_version: str = typer.Argument(
        help="Micro version to show status for (e.g., 6.0.1, 4.0.2rc1)"
    ),
    format_type: str = typer.Option("table", "--format", help="Output format: table or json"),
) -> None:
    """Show PRs included in a specific micro release."""
    display_micro_status(micro_version, format_type)


# Create config subcommand group
config_app = typer.Typer(name="config", help="Manage cherrytree configuration")
app.add_typer(config_app)


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
