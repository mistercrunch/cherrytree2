"""Minor release status command implementation."""

import json
from typing import List, Optional

import typer
from rich.console import Console
from rich.table import Table

from .git_interface import GitInterface
from .micro_release import Micro
from .minor import Minor
from .tables import create_pr_table
from .utils import format_clickable_commit

console = Console()


def get_release_branches() -> List[str]:
    """Get all release branches from git repository."""
    try:
        git = GitInterface()
        return git.get_release_branches()

    except Exception:
        return []


# Removed load_release_state - now handled by Minor.from_yaml()


def display_minor_status(
    minor_version: str, format_type: str = "table", limit: Optional[int] = None
) -> None:
    """Display status of minor release branch."""
    # Check sync status first
    from .sync_validation import check_sync_and_offer_resync

    if not check_sync_and_offer_resync(minor_version, console):
        raise typer.Exit(1)

    # Load minor release (we know it exists from sync check)
    minor = Minor.from_yaml(minor_version)
    assert minor is not None

    # Convert to dict for backward compatibility with existing display logic
    state = minor.to_dict()

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

    # Release overview with cherry count
    commits_count = len(state.get("commits_in_branch", []))
    commits_with_prs = [c for c in state.get("commits_in_branch", []) if c.get("pr_number")]
    cherry_count = len(commits_with_prs)

    console.print(f"[bold]Minor Release: {minor_version}[/bold]")
    console.print(f"├── Base SHA: {base_sha} ({base_date})")
    console.print(f"├── Commits since merge-base: {commits_count} ({cherry_count} 🍒)")
    console.print(f"└── Last synced: {last_synced}")
    console.print("")

    # Micro releases table with commit counts
    micro_releases = state.get("micro_releases", [])
    if micro_releases:
        table = Table(title=f"Micro Releases for {minor_version}")
        table.add_column("Version", style="cyan")
        table.add_column("Tag Date", style="bright_cyan")
        table.add_column("SHA", style="green")
        table.add_column("Commit Date", style="white")
        table.add_column("Commits", style="yellow")

        # Sort by tag date (oldest first) for correct chronological order using Micro objects
        micro_objects = [Micro.from_dict(data) for data in micro_releases]
        sorted_micros = sorted(micro_objects, key=lambda x: x.tag_date)
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
            # Calculate commits since previous release (or base for first release)
            if i == 0:
                # First release - count from base SHA to first tag
                prev_sha = base_sha
            else:
                # Subsequent releases - count from previous tag
                prev_sha = sorted_micros[i - 1].tag_sha

            try:
                from .git_interface import GitInterface

                # Count commits in range prev_sha..current_sha
                git = GitInterface()
                commit_count_output = git.run_command(
                    ["rev-list", "--count", f"{prev_sha}..{micro.tag_sha}"]
                )
                count = int(commit_count_output.strip())
                commit_count = f"{count} 🍒" if count > 0 else "0"
            except Exception:
                commit_count = "?"

            table.add_row(
                micro.format_clickable_tag(),  # Clickable tag link
                micro.short_date,  # Tag creation date
                micro.format_clickable_commit(),  # Clickable commit link
                micro.short_date,  # Commit date (usually same as tag date)
                commit_count,
            )

        console.print(table)
    else:
        console.print("[yellow]No micro releases found[/yellow]")

    # Get enriched PRs with merge dates
    enriched_prs = minor.get_prs()
    if enriched_prs:
        merged_count = sum(1 for pr in enriched_prs if pr.is_merged)
        open_count = len(enriched_prs) - merged_count

        # Apply limit if specified
        display_prs = enriched_prs
        if limit is not None and limit > 0:
            display_prs = enriched_prs[:limit]
            console.print(
                f"\n[bold]PRs to Process ({len(display_prs)} of {len(enriched_prs)} shown):[/bold]"
            )
        else:
            console.print(f"\n[bold]PRs to Process ({len(enriched_prs)} total):[/bold]")

        # Convert enriched PullRequest objects back to dict for table
        enriched_prs_data = [pr.to_dict() for pr in display_prs]

        # Create and display PRs table using reusable function
        pr_table = create_pr_table(enriched_prs_data, f"PRs Labeled for {minor_version}")
        console.print(pr_table)

        # Summary
        console.print("\n[bold]Summary:[/bold]")
        console.print(f"├── Merged PRs ready for cherry-pick: {merged_count}")
        console.print(f"└── Open PRs needing merge: {open_count}")
    else:
        console.print(f"\n[green]No pending PRs for {minor_version}[/green]")
