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

app = typer.Typer(
    name="cherrytree",
    help="Intelligent AI-assisted release management and cherry-picking for Apache Superset",
    no_args_is_help=True,
)

console = Console()


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
    minor_version: str = typer.Argument(help="Minor version to sync (e.g., 5.0, 4.2)"),
    repo_path: Optional[str] = typer.Option(None, "--repo", help="Local repository path"),
    github_repo: str = typer.Option("apache/superset", "--github-repo", help="GitHub repository"),
    output_dir: str = typer.Option("releases", "--output", help="Output directory for YAML files"),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would be done without writing files"
    ),
) -> None:
    """Sync release branch state from git and GitHub."""
    # Use configured repo path if not provided
    if not repo_path:
        repo_path = get_repo_path()

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
