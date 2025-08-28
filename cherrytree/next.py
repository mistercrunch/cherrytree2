"""Next command implementation - get next PR to cherry-pick."""

import json
from typing import Any, Dict, Optional

import typer
from rich.console import Console

from .status import load_release_state
from .utils import format_clickable_commit, format_clickable_pr

console = Console()


def get_next_pr(minor_version: str, skip_open: bool = False) -> Optional[Dict[str, Any]]:
    """Get the next PR to cherry-pick based on git log chronological order."""
    state = load_release_state(minor_version)

    if not state:
        return None

    targeted_prs = state.get("targeted_prs", [])
    if not targeted_prs:
        return None

    # Find first PR that is merged (has SHA) and ready for cherry-pick
    # PRs are already in git log chronological order from sync
    for pr in targeted_prs:
        if pr.get("is_merged", False) and pr.get("master_sha"):
            # This is a merged PR with SHA - ready for cherry-pick
            return pr
        elif not skip_open and not pr.get("is_merged", False):
            # This is an open PR - needs merge first
            return pr

    return None


def display_next_command(
    minor_version: str, verbose: bool = False, skip_open: bool = False, format_type: str = "text"
) -> None:
    """Display next PR to work on."""
    # Load release state
    state = load_release_state(minor_version)

    if not state:
        console.print(f"[red]No sync data found for {minor_version}[/red]")
        console.print(f"[yellow]Run: ct minor sync {minor_version}[/yellow]")
        raise typer.Exit(1)

    next_pr = get_next_pr(minor_version, skip_open)

    if not next_pr:
        console.print(f"[green]No PRs to process for {minor_version}[/green]")
        return

    pr_number = next_pr.get("pr_number", "")
    master_sha = next_pr.get("master_sha", "")
    is_merged = next_pr.get("is_merged", False)
    title = next_pr.get("title", "")
    author = next_pr.get("author", "")

    if format_type == "json":
        # JSON output for programmatic use
        output = {
            "next_sha": master_sha[:8] if master_sha else "",
            "pr_number": pr_number,
            "title": title,
            "author": author,
            "is_merged": is_merged,
            "action_needed": "cherry-pick" if is_merged else "merge_first",
            "cherry_pick_command": f"git cherry-pick -x {master_sha[:8]}" if master_sha else "",
            "github_pr_url": f"https://github.com/apache/superset/pull/{pr_number}",
            "github_commit_url": f"https://github.com/apache/superset/commit/{master_sha}"
            if master_sha
            else "",
        }
        console.print(json.dumps(output, indent=2))
        return

    if not verbose:
        # Basic output - just the SHA
        if is_merged and master_sha:
            console.print(master_sha[:8])
        else:
            console.print(f"PR #{pr_number} needs merge first")
        return

    # Verbose output with full details
    if is_merged and master_sha:
        console.print("[green]Next SHA to cherry-pick:[/green]")
        console.print(f"SHA: {format_clickable_commit(master_sha)}")
        console.print(f"PR: {format_clickable_pr(pr_number)}")
        console.print(f"Title: {title}")
        console.print(f"Author: {author}")
        console.print("\n[bold]Command:[/bold]")
        console.print(f"git cherry-pick -x {master_sha[:8]}")
    else:
        console.print("[yellow]Next PR needs merge first:[/yellow]")
        console.print(f"PR: {format_clickable_pr(pr_number)}")
        console.print(f"Title: {title}")
        console.print(f"Author: {author}")
        console.print("Status: Open (needs merge)")
        console.print("\n[bold]Action needed:[/bold]")
        console.print(f"Merge PR #{pr_number} first, then run sync")
