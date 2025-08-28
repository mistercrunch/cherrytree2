"""Minor release status command implementation."""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import typer
import yaml
from packaging import version
from rich.console import Console
from rich.table import Table

from .git_utils import GitError, run_git_command
from .utils import format_clickable_commit, format_clickable_pr

console = Console()


def create_pr_table(prs_data: list, title: str) -> Table:
    """Create a reusable PR table with consistent formatting."""
    pr_table = Table(title=title, expand=True)
    pr_table.add_column("SHA", style="green", width=10)
    pr_table.add_column("PR", style="cyan", width=8)
    pr_table.add_column("Title", style="white")
    pr_table.add_column("Author", style="dim", width=15)
    pr_table.add_column("Status", style="yellow", width=8)

    for pr in prs_data:
        status = "Merged" if pr.get("is_merged", False) else "Open"
        sha = pr.get("master_sha", "")[:8] if pr.get("master_sha") else ""
        pr_number = pr.get("pr_number", "")

        # Truncate long titles with ellipsis
        title_text = pr.get("title", "")
        if len(title_text) > 60:
            title_text = title_text[:57] + "..."

        pr_table.add_row(
            format_clickable_commit(sha) if sha else "",  # Clickable commit link
            format_clickable_pr(pr_number),  # Clickable PR link
            title_text,  # Truncated title with ellipsis
            pr.get("author", "")[:15],
            status,
        )

    return pr_table


def get_release_branches(repo_path: Optional[str]) -> List[str]:
    """Get all release branches from git repository."""
    if not repo_path:
        return []

    try:
        repo_path_obj = Path(repo_path).resolve()
        # Get remote branches that look like version numbers
        branches_output = run_git_command(
            ["branch", "-r", "--format=%(refname:short)"], repo_path_obj
        )

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


def get_latest_minor_in_major(current_minor: str, repo_path: Optional[str]) -> Optional[str]:
    """Find the latest minor version in the same major as current_minor."""
    # Extract major version (e.g., "4.1" -> "4")
    major = current_minor.split(".")[0]

    # Get all release branches
    all_branches = get_release_branches(repo_path)

    # Filter to same major version
    same_major_branches = [b for b in all_branches if b.startswith(f"{major}.")]

    if not same_major_branches:
        return None

    # Find the latest using semantic version comparison
    latest = max(same_major_branches, key=version.parse)

    # Only return if there's a newer minor than current
    if version.parse(latest) > version.parse(current_minor):
        return latest

    return None


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
        table.add_column("Tag Date", style="bright_blue")
        table.add_column("SHA", style="green")
        table.add_column("Commit Date", style="white")
        table.add_column("Commits", style="yellow")

        # Sort by tag date (oldest first) for correct chronological order
        sorted_micros = sorted(micro_releases, key=lambda x: x.get("tag_date", ""))
        base_sha = state.get("base_sha", "")
        base_date = state.get("base_date", "")

        # Add merge-base as first row to show branch cut
        table.add_row(
            "merge-base",
            base_date[:10] if base_date else "",  # Branch cut date
            format_clickable_commit(base_sha),  # Clickable commit link
            base_date[:10] if base_date else "",  # Same date
            "Branch cut",
        )

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
                format_clickable_commit(tag_sha),  # Clickable commit link
                commit_date[:10] if commit_date else "",  # Commit date
                commit_count,
            )

        console.print(table)
    else:
        console.print("[yellow]No micro releases found[/yellow]")

    # Check if there's a newer minor in the same major before showing PRs
    latest_minor = get_latest_minor_in_major(minor_version, repo_path)

    # Targeted PRs table - show PRs that need processing
    targeted_prs = state.get("targeted_prs", [])
    if targeted_prs:
        merged_count = sum(1 for pr in targeted_prs if pr.get("is_merged", False))
        open_count = len(targeted_prs) - merged_count
        major = minor_version.split(".")[0]

        if latest_minor:
            # There's a newer minor - redirect user
            console.print(
                f"\n[yellow]{len(targeted_prs)} 🍒 targeting v{major}.0 are for {latest_minor} (latest minor)[/yellow]"
            )
            console.print(f"[dim]Run `ct minor status {latest_minor}` to view the details[/dim]")
        else:
            # This is the latest minor - show the PRs
            console.print(f"\n[bold]PRs to Process ({len(targeted_prs)} total):[/bold]")

            # Create and display PRs table using reusable function
            pr_table = create_pr_table(targeted_prs, f"PRs Labeled for {minor_version}")
            console.print(pr_table)

            # Summary
            console.print("\n[bold]Summary:[/bold]")
            console.print(f"├── Merged PRs ready for cherry-pick: {merged_count}")
            console.print(f"└── Open PRs needing merge: {open_count}")
    else:
        console.print(f"\n[green]No pending PRs for {minor_version}[/green]")
