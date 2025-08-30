"""Next command implementation - get next PR to cherry-pick."""

import json
from typing import Any, Dict, Optional

import typer
from rich.console import Console

from .minor import Minor
from .pull_request import PullRequest

console = Console()


def get_next_pr(minor_version: str, skip_open: bool = False) -> Optional[Dict[str, Any]]:
    """Get the next PR to cherry-pick based on git log chronological order."""
    minor = Minor.from_yaml(minor_version)
    if not minor:
        return None

    result = minor.get_next_pr(skip_open, as_object=False)
    # Type assertion: as_object=False guarantees dict return type
    assert result is None or isinstance(result, dict)
    return result


def display_next_command(
    minor_version: str, verbose: bool = False, skip_open: bool = False, format_type: str = "text"
) -> None:
    """Display next PR to work on."""
    # Check sync status first
    from .sync_validation import check_sync_and_offer_resync

    if not check_sync_and_offer_resync(minor_version, console):
        raise typer.Exit(1)

    # Load minor release (we know it exists from sync check)
    minor = Minor.from_yaml(minor_version)
    assert minor is not None

    next_pr = minor.get_next_pr(skip_open, as_object=False)

    if not next_pr:
        console.print(f"[green]No PRs to process for {minor_version}[/green]")
        return

    # Convert to PullRequest object for type-safe access
    # next_pr is guaranteed to be Dict since as_object=False
    assert isinstance(next_pr, dict)
    pr = PullRequest.from_dict(next_pr)

    if format_type == "json":
        # JSON output for programmatic use
        output = {
            "next_sha": pr.short_sha,
            "pr_number": pr.pr_number,
            "title": pr.title,
            "author": pr.author,
            "is_merged": pr.is_merged,
            "action_needed": "cherry-pick" if pr.is_merged else "merge_first",
            "cherry_pick_command": f"git cherry-pick -x {pr.short_sha}" if pr.master_sha else "",
            "github_pr_url": pr.github_url(),
            "github_commit_url": pr.commit_url() if pr.master_sha else "",
        }
        console.print(json.dumps(output, indent=2))
        return

    if not verbose:
        # Basic output - just the SHA
        if pr.is_ready_for_cherry_pick():
            console.print(pr.short_sha)
        else:
            console.print(f"PR #{pr.pr_number} needs merge first")
        return

    # Verbose output with full details
    if pr.is_ready_for_cherry_pick():
        console.print("[green]Next SHA to cherry-pick:[/green]")
        console.print(f"SHA: {pr.format_clickable_commit()}")
        console.print(f"PR: {pr.format_clickable_pr()}")
        console.print(f"Title: {pr.title}")
        console.print(f"Author: {pr.author}")
        console.print("\n[bold]Command:[/bold]")
        console.print(f"git cherry-pick -x {pr.short_sha}")
    else:
        console.print("[yellow]Next PR needs merge first:[/yellow]")
        console.print(f"PR: {pr.format_clickable_pr()}")
        console.print(f"Title: {pr.title}")
        console.print(f"Author: {pr.author}")
        console.print("Status: Open (needs merge)")
        console.print("\n[bold]Action needed:[/bold]")
        console.print(f"Merge PR #{pr.pr_number} first, then run sync")
