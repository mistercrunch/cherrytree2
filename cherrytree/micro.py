"""Micro release management commands."""

from pathlib import Path
from typing import Any, Dict, List, Optional

import typer
from rich.console import Console

from .git_utils import GitError, run_git_command
from .status import create_pr_table, load_release_state

console = Console()


def get_commits_in_range(repo_path: Path, start_sha: str, end_sha: str) -> List[Dict[str, Any]]:
    """Get commits between two SHAs."""
    try:
        # Get commits in range start_sha..end_sha
        log_output = run_git_command(
            ["log", f"{start_sha}..{end_sha}", "--format=%h|%s|%an|%ci"], repo_path
        )

        commits = []
        for line in log_output.split("\n"):
            if not line.strip():
                continue

            parts = line.split("|", 3)
            if len(parts) >= 4:
                sha, message, author, date = parts

                # Extract PR number from commit message using the same logic as sync
                from .git_parser import parse_pr_from_commit_message

                pr_number = parse_pr_from_commit_message(message)

                commits.append(
                    {
                        "sha": sha,
                        "message": message,
                        "author": author,
                        "date": date,
                        "pr_number": pr_number,
                    }
                )

        return commits

    except GitError as e:
        console.print(f"[red]Error getting commits: {e}[/red]")
        return []


def get_prs_in_micro(
    minor_version: str, micro_version: str, repo_path: str
) -> List[Dict[str, Any]]:
    """Get PRs that are included in a specific micro release."""
    state = load_release_state(minor_version)

    if not state:
        return []

    # Find the micro release
    micro_releases = state.get("micro_releases", [])
    target_micro = None
    for micro in micro_releases:
        if micro.get("version") == micro_version:
            target_micro = micro
            break

    if not target_micro:
        return []

    # Get commits in this micro release
    repo_path_obj = Path(repo_path).resolve()
    target_sha = target_micro.get("tag_sha", "")
    base_sha = state.get("base_sha", "")

    # Find previous micro or use base SHA
    sorted_micros = sorted(micro_releases, key=lambda x: x.get("tag_date", ""))
    target_index = next(i for i, m in enumerate(sorted_micros) if m.get("version") == micro_version)

    if target_index == 0:
        # First micro - compare with base SHA
        prev_sha = base_sha
    else:
        # Compare with previous micro
        prev_sha = sorted_micros[target_index - 1].get("tag_sha", base_sha)

    # Get commits between previous and current
    commits_in_micro = get_commits_in_range(repo_path_obj, prev_sha, target_sha)

    # Map commits to PRs (include all commits with PR numbers, not just targeted ones)
    targeted_prs = state.get("targeted_prs", [])
    pr_lookup = {pr.get("pr_number"): pr for pr in targeted_prs}

    prs_in_micro = []
    for commit in commits_in_micro:
        pr_number = commit.get("pr_number")
        if pr_number:
            # Use PR data from targeted_prs if available, otherwise create basic data
            if pr_number in pr_lookup:
                pr_data = pr_lookup[pr_number]
            else:
                # PR not in targeted list (might not have v4.0 label)
                pr_data = {
                    "pr_number": pr_number,
                    "title": commit.get("message", "").split(f"(#{pr_number})")[0].strip(),
                    "author": commit.get("author", ""),
                    "master_sha": "",  # Don't know master SHA
                    "is_merged": True,  # If it's in the branch, it was merged
                }

            prs_in_micro.append(
                {
                    **pr_data,
                    "commit_sha_in_micro": commit.get("sha"),  # SHA in the micro release
                    "commit_date": commit.get("date"),
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
