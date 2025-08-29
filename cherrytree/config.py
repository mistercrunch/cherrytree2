"""Configuration management for cherrytree."""

import json
from pathlib import Path
from typing import Any, Dict, Optional

import typer
import yaml
from rich.console import Console

console = Console()


def get_config_dir() -> Path:
    """Get cherrytree configuration directory."""
    config_dir = Path.home() / ".cherrytree"
    config_dir.mkdir(exist_ok=True)
    return config_dir


def get_config_file() -> Path:
    """Get configuration file path."""
    return get_config_dir() / "config.yml"


def load_config() -> Dict[str, Any]:
    """Load configuration from file."""
    config_file = get_config_file()
    if not config_file.exists():
        return {
            "default": {"repo_path": None, "github_repo": None, "releases_dir": "releases"},
            "github": {"default_repo": "apache/superset"},
            "preferences": {"default_format": "table"},
        }

    with open(config_file) as f:
        return yaml.safe_load(f) or {}


def save_config(config: Dict[str, Any]) -> None:
    """Save configuration to file."""
    config_file = get_config_file()
    with open(config_file, "w") as f:
        yaml.dump(config, f, default_flow_style=False)


def set_repo_command(repo_path: str) -> None:
    """Set the repository path."""
    # Expand ~ to home directory
    expanded_path = Path(repo_path).expanduser().resolve()

    if not expanded_path.exists():
        console.print(f"[red]Error: Path does not exist: {expanded_path}[/red]")
        raise typer.Exit(1)

    if not (expanded_path / ".git").exists():
        console.print(f"[red]Error: Not a git repository: {expanded_path}[/red]")
        raise typer.Exit(1)

    config = load_config()
    config.setdefault("default", {})["repo_path"] = str(expanded_path)
    save_config(config)

    console.print(f"[green]✅ Repository path set to: {expanded_path}[/green]")


def set_github_command(github_repo: str) -> None:
    """Set the GitHub repository."""
    config = load_config()
    config.setdefault("default", {})["github_repo"] = github_repo
    save_config(config)

    console.print(f"[green]✅ GitHub repository set to: {github_repo}[/green]")


def show_config_command(format_type: str = "table") -> None:
    """Show current configuration."""
    config = load_config()

    repo_path = config.get("default", {}).get("repo_path")
    github_repo = config.get("default", {}).get("github_repo") or "apache/superset (default)"

    if format_type == "json":
        output = {
            "repo_path": repo_path,
            "github_repo": github_repo,
            "config_file": str(get_config_file()),
        }
        console.print(json.dumps(output, indent=2))
    else:
        console.print("[bold]Cherrytree Configuration[/bold]")
        console.print(f"Repository: {repo_path or '[red]Not set[/red]'}")
        console.print(f"GitHub: {github_repo}")
        console.print(f"Config file: {get_config_file()}")

        if not repo_path:
            console.print(
                "\n[yellow]Run cherrytree from within your Superset repository directory[/yellow]"
            )


def get_repo_path() -> Optional[str]:
    """Get configured repository path."""
    config = load_config()
    default_config = config.get("default", {})
    if isinstance(default_config, dict):
        repo_path = default_config.get("repo_path")
        return repo_path if isinstance(repo_path, str) else None
    return None


def get_github_repo() -> str:
    """Get configured GitHub repository."""
    config = load_config()
    return config.get("default", {}).get("github_repo") or "apache/superset"
