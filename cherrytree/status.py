"""Minor release status command implementation."""

import json
from pathlib import Path
from typing import Any, Dict, Optional

import typer
import yaml
from rich.console import Console
from rich.table import Table

console = Console()


def load_release_state(
    minor_version: str, releases_dir: str = "releases"
) -> Optional[Dict[str, Any]]:
    """Load release state from YAML file."""
    yaml_file = Path(releases_dir) / f"{minor_version}.yml"

    if not yaml_file.exists():
        return None

    try:
        with open(yaml_file) as f:
            data = yaml.safe_load(f)
            return data.get("release_branch", {})
    except Exception as e:
        console.print(f"[red]Error reading {yaml_file}: {e}[/red]")
        return None


def display_minor_status(
    minor_version: str, format_type: str = "table", repo_path: Optional[str] = None
) -> None:
    """Display status of minor release branch."""
    # Load release state
    state = load_release_state(minor_version)

    if not state:
        console.print(f"[red]No sync data found for {minor_version}[/red]")
        console.print(f"[yellow]Run: ct minor sync {minor_version}[/yellow]")
        raise typer.Exit(1)

    if format_type == "json":
        # Output JSON for programmatic use
        output = {
            "minor_version": state.get("minor_version"),
            "base_sha": state.get("base_sha"),
            "micro_releases": state.get("micro_releases", []),
            "targeted_prs": state.get("targeted_prs", []),
            "branch_commits": len(state.get("commits_in_branch", [])),
            "last_synced": state.get("last_synced"),
        }
        console.print(json.dumps(output, indent=2))
        return

    # Rich table format for humans
    base_sha = state.get("base_sha", "unknown")
    base_date = state.get("base_date", "unknown")
    last_synced = state.get("last_synced", "unknown")

    # Release overview
    console.print(f"[bold]Minor Release: {minor_version}[/bold]")
    console.print(f"├── Base SHA: {base_sha} ({base_date})")
    console.print(f"└── Last synced: {last_synced}")
    console.print("")

    # Micro releases table with commit counts
    micro_releases = state.get("micro_releases", [])
    if micro_releases:
        table = Table(title=f"Micro Releases for {minor_version}")
        table.add_column("Version", style="cyan")
        table.add_column("Tag Date", style="blue")
        table.add_column("SHA", style="green")
        table.add_column("Commit Date", style="white")
        table.add_column("Commits", style="yellow")

        # Sort by tag date (oldest first) for correct chronological order
        sorted_micros = sorted(micro_releases, key=lambda x: x.get("tag_date", ""))
        base_sha = state.get("base_sha", "")

        for i, micro in enumerate(sorted_micros):
            tag_sha = micro.get("tag_sha", "")
            tag_date = micro.get("tag_date", "")
            commit_date = micro.get("commit_date", "")

            # Calculate commits since previous release (or base for first release)
            if i == 0:
                # First release - count from base SHA to first tag
                prev_sha = base_sha
            else:
                # Subsequent releases - count from previous tag
                prev_sha = sorted_micros[i - 1].get("tag_sha", base_sha)

            if repo_path:
                try:
                    from pathlib import Path

                    from .git_utils import run_git_command

                    # Count commits in range prev_sha..current_sha
                    repo_path_obj = Path(repo_path).resolve()
                    commit_count_output = run_git_command(
                        ["rev-list", "--count", f"{prev_sha}..{tag_sha}"], repo_path_obj
                    )
                    count = int(commit_count_output.strip())
                    commit_count = f"{count} 🍒" if count > 0 else "0"
                except Exception:
                    commit_count = "?"
            else:
                commit_count = "? (no repo path)"

            table.add_row(
                micro.get("version", ""),
                tag_date[:10] if tag_date else "",  # Tag creation date
                tag_sha,
                commit_date[:10] if commit_date else "",  # Commit date
                commit_count,
            )

        console.print(table)
    else:
        console.print("[yellow]No micro releases found[/yellow]")

    # Targeted PRs summary
    targeted_prs = state.get("targeted_prs", [])
    if targeted_prs:
        merged_count = sum(1 for pr in targeted_prs if pr.get("is_merged", False))
        open_count = len(targeted_prs) - merged_count

        console.print("\n[bold]Pending Work:[/bold]")
        console.print(f"├── Merged PRs ready for cherry-pick: {merged_count}")
        console.print(f"└── Open PRs needing merge: {open_count}")
        console.print(f"    Total: {len(targeted_prs)} actionable PRs")
    else:
        console.print(f"\n[green]No pending PRs for {minor_version}[/green]")
