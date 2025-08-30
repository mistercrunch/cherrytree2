"""Table creation and data display functionality for cherrytree CLI."""

import json
import re
from pathlib import Path
from typing import Any, Dict, List

from packaging import version
from rich.console import Console
from rich.table import Table

from .config import get_repo_path, load_config
from .git_interface import GitInterface
from .minor import Minor

console = Console()


def get_releases_dir() -> Path:
    """Get the releases directory path."""
    config = load_config()
    releases_dir = config.get("default", {}).get("releases_dir", "releases")
    return Path(releases_dir)


# Removed load_release_data - now handled by Minor.from_yaml()


def get_valid_minor_versions(minor_versions: List[str]) -> List[str]:
    """Filter out invalid minor versions (like 2020.51 and 0.*) and return valid ones."""
    valid_minors = []
    for minor in minor_versions:
        try:
            # Split version into major.minor
            parts = minor.split(".")
            if len(parts) >= 2:
                major = int(parts[0])
                # Filter out versions with major version > 100 (excludes things like 2020.51)
                # and major version 0 (excludes 0.* pre-release versions)
                if 1 <= major <= 100:
                    valid_minors.append(minor)
        except ValueError:
            # Skip if we can't parse the version numbers
            continue

    return valid_minors


def get_minors_from_git_tags() -> List[str]:
    """Get list of minor versions by scanning git tags."""
    repo_path_str = get_repo_path()
    if not repo_path_str:
        return []

    repo_path = Path(repo_path_str)
    if not repo_path.exists():
        return []

    try:
        git = GitInterface(repo_path)
        minor_versions = git.get_tags_for_overview()

        # Filter out invalid versions and sort in descending order
        valid_minors = get_valid_minor_versions(minor_versions)
        return sorted(valid_minors, key=lambda v: version.parse(v), reverse=True)

    except Exception:
        # Fall back to scanning release files if git fails
        return get_available_minors_from_files()


def get_available_minors_from_files() -> List[str]:
    """Get list of available minor versions by scanning release files."""
    releases_dir = get_releases_dir()

    if not releases_dir.exists():
        return []

    minors = []
    for yml_file in releases_dir.glob("*.yml"):
        # Extract minor version from filename (e.g., "6.0.yml" -> "6.0")
        minor_version = yml_file.stem
        minors.append(minor_version)

    # Sort versions in descending order using packaging.version (newest first)
    return sorted(minors, key=lambda v: version.parse(v), reverse=True)


def get_available_minors() -> List[str]:
    """Get list of available minor versions, preferring git tags over files."""
    # First try to get from git tags
    minors_from_git = get_minors_from_git_tags()
    if minors_from_git:
        return minors_from_git

    # Fall back to file scanning
    return get_available_minors_from_files()


def get_minor_overview(minor_version: str) -> Dict[str, Any]:
    """Get overview information for a specific minor version."""
    # Try to load as Minor object, fall back to missing sync file
    minor = Minor.from_yaml(minor_version)
    if minor is None:
        # Create a Minor object without sync data for consistent interface
        minor = Minor(minor_version)

    # Get overview with sync command for missing files
    overview = minor.get_overview()
    if not minor.has_sync_file():
        overview["details"] = f"[yellow]ct minor sync {minor_version}[/yellow]"

    return overview


def display_minors_overview(format_type: str = "table") -> None:
    """Display overview table of all available minors."""
    available_minors = get_available_minors()

    if not available_minors:
        if format_type == "json":
            console.print(json.dumps({"minors": []}, indent=2))
        else:
            console.print("[yellow]No minor release tags found in git repository[/yellow]")
        return

    # Collect data for all minors
    overview_data = []
    for minor in available_minors:
        overview = get_minor_overview(minor)
        overview_data.append(overview)

    if format_type == "json":
        # Clean up rich markup for JSON output
        clean_data = []
        for overview in overview_data:
            clean_overview = overview.copy()
            # Remove rich markup from values for JSON output
            for key, value in clean_overview.items():
                if isinstance(value, str):
                    # Remove rich markup tags like [red]...[/red]
                    clean_value = re.sub(r"\[/?[a-zA-Z0-9_]+\]", "", value)
                    clean_overview[key] = clean_value
            clean_data.append(clean_overview)
        console.print(json.dumps({"minors": clean_data}, indent=2))
        return

    # Create rich table
    table = Table(title="[bold]Available Minor Releases[/bold]", show_header=True)
    table.add_column("Minor", style="bold cyan")
    table.add_column("Merge Base", style="dim")
    table.add_column("Date", style="dim")
    table.add_column("Latest", style="green")
    table.add_column("⏳", justify="center", style="yellow")  # Unreleased PRs
    table.add_column("✅", justify="center", style="green")  # Released PRs
    table.add_column("Details", style="dim")

    for overview in overview_data:
        table.add_row(
            overview["minor_version"],
            overview["merge_base_sha"],
            overview["merge_base_date"],
            overview["most_recent_release"],
            str(overview["unreleased_prs"]),
            str(overview["released_prs"]),
            overview["details"],
        )

    console.print(table)
    console.print()  # Add spacing before help


def create_pr_table(prs_data: list, title: str, include_conflicts: bool = False) -> Table:
    """Create a reusable PR table with consistent formatting.

    Args:
        prs_data: List of PR data (either PR dicts or conflict analysis dicts)
        title: Table title
        include_conflicts: If True, adds Size/Conflicts/Complexity columns for analysis
    """
    pr_table = Table(title=title, expand=True)

    # Core PR columns (consistent between status and analyze)
    pr_table.add_column("SHA", style="green", width=10)
    pr_table.add_column("Merged", style="dim", width=12, justify="center")
    pr_table.add_column("PR", style="cyan", width=8)
    pr_table.add_column("Title", style="white", overflow="ellipsis", min_width=30)
    pr_table.add_column("Author", style="dim", width=15)
    pr_table.add_column(
        "DB", style="red", width=3, justify="center"
    )  # Database migration indicator

    # Add conflict analysis columns if requested
    if include_conflicts:
        pr_table.add_column("Size", style="dim", width=8, justify="center")
        pr_table.add_column("Conflicts", style="bold", width=10, justify="center")
        pr_table.add_column("Complexity", style="", width=10)
    else:
        pr_table.add_column("Status", style="yellow", width=8)

    for pr_data in prs_data:
        if include_conflicts:
            # Handle conflict analysis data
            _add_conflict_analysis_row(pr_table, pr_data)
        else:
            # Handle basic PR data
            _add_basic_pr_row(pr_table, pr_data)

    return pr_table


def _add_basic_pr_row(pr_table: Table, pr_data: dict) -> None:
    """Add a basic PR row for status display."""
    from .pull_request import PullRequest

    pr = PullRequest.from_dict(pr_data)

    # Database migration indicator
    db_indicator = "🗄️" if pr.has_database_migration else ""

    pr_table.add_row(
        pr.format_clickable_commit() if pr.master_sha else "",
        pr.display_merge_date(),
        pr.format_clickable_pr(),
        pr.short_title(),
        pr.display_author(),
        db_indicator,
        pr.status_text,
    )


def _add_conflict_analysis_row(pr_table: Table, analysis: dict) -> None:
    """Add a conflict analysis row with merge intelligence."""
    pr_number = analysis.get("pr_number")
    pr_title = analysis.get("pr_title", "")
    commit_sha = analysis.get("commit_sha", "")
    merge_date = analysis.get("merge_date", "")

    # Get commit size info (actual files and lines changed in the commit)
    files_changed = analysis.get("files_changed", 0)
    lines_changed = analysis.get("lines_changed", 0)

    # Get conflict info (files and lines that would conflict during cherry-pick)
    conflict_count = analysis.get("conflict_count", 0)
    complexity = analysis.get("complexity", "error")

    # Format columns consistently with status table
    pr_link = (
        f"[link=https://github.com/apache/superset/pull/{pr_number}]#{pr_number}[/link]"
        if pr_number
        else ""
    )
    sha_link = (
        f"[link=https://github.com/apache/superset/commit/{commit_sha}]{commit_sha}[/link]"
        if commit_sha
        else ""
    )

    # Format merge date (extract just the date part)
    merge_date_display = ""
    if merge_date:
        try:
            # Handle format like "2025-08-18 14:04:26 -0700" -> "2025-08-18"
            merge_date_display = merge_date.split()[0] if " " in merge_date else merge_date[:10]
        except Exception:
            merge_date_display = str(merge_date)[:10]

    # Format size column (original commit size)
    size_display = (
        f"{files_changed}f/{lines_changed}l" if files_changed > 0 or lines_changed > 0 else "0f/0l"
    )

    # Format conflicts column (cherry-pick conflicts)
    conflicts_display = f"{conflict_count} files" if conflict_count > 0 else "clean"

    # Format complexity with color
    complexity_display = complexity
    if complexity == "clean":
        complexity_display = "[green]clean[/green]"
    elif complexity == "simple":
        complexity_display = "[yellow]simple[/yellow]"
    elif complexity == "moderate":
        complexity_display = "[orange1]moderate[/orange1]"
    elif complexity == "complex":
        complexity_display = "[red]complex[/red]"
    elif complexity == "repo_error":
        complexity_display = "[dim]wrong repo[/dim]"
    elif complexity == "error":
        complexity_display = "[red]error[/red]"

    # Get author from analysis or try to extract from title/data
    author = analysis.get("author", analysis.get("pr_author", ""))

    # Database migration indicator (from analysis data)
    has_db_migration = analysis.get("has_database_migration", False)
    db_indicator = "🗄️" if has_db_migration else ""

    pr_table.add_row(
        sha_link,
        merge_date_display,
        pr_link,
        pr_title,
        author,
        db_indicator,
        size_display,
        conflicts_display,
        complexity_display,
    )
