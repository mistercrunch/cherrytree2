"""Micro release management commands."""

from pathlib import Path
from typing import Any, Dict, List, Optional

import typer
from rich.console import Console

from .commit import Commit
from .git_interface import GitInterface
from .micro_release import Micro
from .minor import Minor
from .tables import create_pr_table

console = Console()


def get_commits_in_range(repo_path: Path, start_sha: str, end_sha: str) -> List[Dict[str, Any]]:
    """Get commits between two SHAs."""
    try:
        git = GitInterface(repo_path, console)
        commits = git.get_commits_in_range(start_sha, end_sha)

        # Convert to dict format for backward compatibility
        commits_dict = []
        for commit in commits:
            commits_dict.append(commit.to_dict())

        return commits_dict

    except Exception as e:
        console.print(f"[red]Error getting commits: {e}[/red]")
        return []


def get_prs_in_micro(
    minor_version: str, micro_version: str, repo_path: str
) -> List[Dict[str, Any]]:
    """Get PRs that are included in a specific micro release."""
    minor = Minor.from_yaml(minor_version)

    if not minor:
        return []

    # Find the micro release using Micro objects
    target_micro = None
    for micro_data in minor.micro_releases:
        micro = Micro.from_dict(micro_data)
        if micro.version == micro_version:
            target_micro = micro
            break

    if not target_micro:
        return []

    # Get commits in this micro release
    repo_path_obj = Path(repo_path).resolve()
    target_sha = target_micro.tag_sha
    base_sha = minor.base_sha

    # Find previous micro or use base SHA
    micro_objects = [Micro.from_dict(data) for data in minor.micro_releases]
    sorted_micros = sorted(micro_objects, key=lambda x: x.tag_date)
    target_index = next(i for i, m in enumerate(sorted_micros) if m.version == micro_version)

    if target_index == 0:
        # First micro - compare with base SHA
        prev_sha = base_sha
    else:
        # Compare with previous micro
        prev_sha = sorted_micros[target_index - 1].tag_sha

    # Get commits between previous and current
    commits_in_micro = get_commits_in_range(repo_path_obj, prev_sha, target_sha)

    # Map commits to PRs (include all commits with PR numbers, not just targeted ones)
    pr_lookup = {pr.get("pr_number"): pr for pr in minor.targeted_prs}

    prs_in_micro = []
    for commit_data in commits_in_micro:
        commit = Commit.from_dict(commit_data)

        if commit.has_pr:
            # Use PR data from targeted_prs if available, otherwise create basic data
            if commit.pr_number in pr_lookup:
                pr_data = pr_lookup[commit.pr_number]
            else:
                # PR not in targeted list (might not have v4.0 label)
                pr_data = {
                    "pr_number": commit.pr_number,
                    "title": commit.extract_title(),
                    "author": commit.author,
                    "master_sha": "",  # Don't know master SHA
                    "is_merged": True,  # If it's in the branch, it was merged
                }

            prs_in_micro.append(
                {
                    **pr_data,
                    "commit_sha_in_micro": commit.sha,  # SHA in the micro release
                    "commit_date": commit.date,
                }
            )

    return prs_in_micro


def display_micro_status(
    micro_version: str, format_type: str = "table", repo_path: Optional[str] = None
) -> None:
    """Display status of a specific micro release."""
    # Extract minor version from micro (e.g., "6.0.1" -> "6.0")
    parts = micro_version.split(".")
    if len(parts) < 2:
        console.print(f"[red]Invalid micro version format: {micro_version}[/red]")
        console.print("[yellow]Use format like: 6.0.1 or 4.0.2rc1[/yellow]")
        raise typer.Exit(1)

    minor_version = f"{parts[0]}.{parts[1]}"

    if not repo_path:
        console.print("[red]Repository path required for micro status[/red]")
        console.print("[yellow]Use: ct micro status 6.0.1 --repo /path/to/superset[/yellow]")
        raise typer.Exit(1)

    # Get PRs in this micro release
    prs_in_micro = get_prs_in_micro(minor_version, micro_version, repo_path)

    if format_type == "json":
        import json

        output = {
            "micro_version": micro_version,
            "minor_version": minor_version,
            "prs_in_micro": prs_in_micro,
        }
        console.print(json.dumps(output, indent=2))
        return

    # Rich table display
    if not prs_in_micro:
        console.print(f"[yellow]No PRs found in micro release {micro_version}[/yellow]")
        console.print("[dim]This might be an initial release or contain only non-PR commits[/dim]")
        return

    console.print(f"[bold]Micro Release: {micro_version}[/bold]")
    console.print(f"└── {len(prs_in_micro)} PRs included\n")

    # Use reusable PR table
    pr_table = create_pr_table(prs_in_micro, f"PRs in {micro_version}")
    console.print(pr_table)
