"""Conflict analysis for cherry-pick operations."""

import json
from typing import Any, Dict

from rich.console import Console
from rich.table import Table

from .git_interface import GitInterface
from .minor import Minor


def analyze_next_pr_conflicts(minor_version: str, format_type: str = "table") -> None:
    """Analyze potential conflicts for the next PR to cherry-pick."""
    console = Console()

    try:
        # Load minor release data
        minor = Minor.from_yaml(minor_version)
        if not minor:
            console.print(
                f"[red]No sync data found for {minor_version}. Run `ct minor sync {minor_version}` first.[/red]"
            )
            return

        # Get next PR to cherry-pick
        next_pr = minor.get_next_pr_object(skip_open=True)
        if not next_pr:
            console.print(
                f"[yellow]No merged PRs available for cherry-pick in {minor_version}[/yellow]"
            )
            return

        if not next_pr.master_sha:
            console.print(
                f"[red]Next PR #{next_pr.pr_number} has no SHA - likely not merged yet[/red]"
            )
            return

        # Initialize git interface
        git = GitInterface(console=console)

        # Analyze conflicts
        console.print(
            f"[blue]Analyzing conflicts for cherry-pick of PR #{next_pr.pr_number}...[/blue]"
        )
        analysis = git.analyze_cherry_pick_conflicts(minor_version, next_pr.master_sha)

        # Display results
        if format_type == "json":
            _display_json_output(analysis, next_pr)
        else:
            _display_table_output(analysis, next_pr, console)

    except Exception as e:
        console.print(f"[red]Error analyzing conflicts: {e}[/red]")


def _display_table_output(analysis: Dict[str, Any], next_pr: Any, console: Console) -> None:
    """Display conflict analysis in table format."""

    # Main status table
    table = Table(title=f"Cherry-Pick Conflict Analysis: PR #{next_pr.pr_number}")
    table.add_column("Property", style="bold")
    table.add_column("Value", style="")

    # Add basic info with clickable links
    pr_link = f"[link=https://github.com/apache/superset/pull/{next_pr.pr_number}]#{next_pr.pr_number}[/link]"
    sha_link = f"[link=https://github.com/apache/superset/commit/{analysis['commit_sha']}]{analysis['commit_sha']}[/link]"

    table.add_row("PR Number", pr_link)
    table.add_row("Title", next_pr.title)
    table.add_row("Author", next_pr.author)
    table.add_row("Commit SHA", sha_link)
    table.add_row("Target Branch", analysis["target_branch"])

    # Status and complexity
    if analysis.get("error"):
        table.add_row("Status", f"[red]Error: {analysis['error']}[/red]")
    elif analysis["has_conflicts"]:
        complexity = analysis["complexity"]
        color = {"simple": "yellow", "moderate": "orange3", "complex": "red"}.get(complexity, "red")

        table.add_row("Status", f"[{color}]🚨 Conflicts detected ({complexity})[/{color}]")
        table.add_row("Conflict Count", str(analysis["conflict_count"]))
    else:
        table.add_row("Status", "[green]✅ Clean cherry-pick[/green]")

    console.print(table)

    # Detailed conflicts table if conflicts exist
    if analysis["has_conflicts"] and analysis["conflicts"]:
        console.print()

        conflicts_table = Table(title="Conflict Details")
        conflicts_table.add_column("File", style="bold")
        conflicts_table.add_column("Regions", justify="center")
        conflicts_table.add_column("Total Lines", justify="right")
        conflicts_table.add_column("Line Ranges", style="dim")
        conflicts_table.add_column("Recent Changes", style="dim")

        for conflict in analysis["conflicts"]:
            # Build line ranges display
            line_ranges = ""
            if conflict.get("conflict_regions"):
                ranges = []
                for region in conflict["conflict_regions"]:
                    start = region["start_line"]
                    end = region.get("end_line", start)
                    if start == end:
                        ranges.append(str(start))
                    else:
                        ranges.append(f"{start}-{end}")
                line_ranges = ", ".join(ranges)

            # Build recent changes display with clickable links
            recent_changes = ""
            if conflict.get("blame_commits"):
                changes_list = []
                for blame in conflict["blame_commits"]:
                    # Create clickable SHA link (assuming github.com/apache/superset)
                    sha_link = f"[link=https://github.com/apache/superset/commit/{blame['sha']}]{blame['sha']}[/link]"

                    # Create clickable PR link if available
                    if blame["pr_number"]:
                        pr_link = f"[link=https://github.com/apache/superset/pull/{blame['pr_number']}]#{blame['pr_number']}[/link]"
                        commit_text = f"{sha_link} ({pr_link})"
                    else:
                        commit_text = sha_link

                    changes_list.append(f"{commit_text}: {blame['message']}")
                recent_changes = "\n".join(changes_list)

            conflicts_table.add_row(
                conflict["file"],
                str(conflict.get("region_count", 1)),
                str(conflict.get("conflicted_lines", "?")),
                line_ranges or "unknown",
                recent_changes or "No recent changes found",
            )

        console.print(conflicts_table)

    # Recommendations
    _display_recommendations(analysis, console)


def run_cherry_pick_chain(
    minor_version: str, auto_clean: bool = False, max_picks: int = 10
) -> None:
    """Run interactive cherry-pick chain with conflict analysis."""
    console = Console()

    try:
        # Load minor release data
        minor = Minor.from_yaml(minor_version)
        if not minor:
            console.print(
                f"[red]No sync data found for {minor_version}. Run `ct minor sync {minor_version}` first.[/red]"
            )
            return

        # Initialize git interface
        git = GitInterface(console=console)

        # Check current branch
        current_branch = git.get_current_branch()
        if current_branch != minor_version:
            console.print(
                f"[red]⚠️  Warning: You're on branch '{current_branch}' but targeting '{minor_version}'[/red]"
            )
            console.print(
                f"[yellow]Cherry-picks will be applied to the current branch: {current_branch}[/yellow]"
            )

            import typer

            if not typer.confirm(f"Continue cherry-picking to '{current_branch}'?"):
                console.print("[yellow]Cancelled. Switch to the correct branch first.[/yellow]")
                console.print(f"[dim]Run: git checkout {minor_version}[/dim]")
                return

        # Check if we're already in a cherry-pick
        status = git.get_cherry_pick_status()
        if status["in_progress"]:
            console.print("[yellow]⚠️  Git is in the middle of a cherry-pick operation[/yellow]")
            console.print(f"[dim]Conflicted files: {len(status['conflicted_files'])}[/dim]")
            console.print(f"[dim]Staged files: {len(status['staged_files'])}[/dim]")

            if not status["can_continue"]:
                console.print(
                    "[red]Please resolve conflicts or abort current cherry-pick first[/red]"
                )
                console.print("[dim]Run: git cherry-pick --abort[/dim]")
                return

        console.print(f"[bold cyan]🍒 Starting cherry-pick chain for {minor_version}[/bold cyan]")
        console.print(f"[dim]Auto-clean mode: {'enabled' if auto_clean else 'disabled'}[/dim]")
        console.print(f"[dim]Max picks: {max_picks}[/dim]")
        console.print()

        picks_attempted = 0
        picks_successful = 0
        picks_skipped = 0

        while picks_attempted < max_picks:
            # Reload minor data to get fresh next PR (in case we completed some)
            minor = Minor.from_yaml(minor_version)
            if not minor:
                console.print("[red]Failed to reload minor data[/red]")
                break

            # Get next PR to cherry-pick
            next_pr = minor.get_next_pr_object(skip_open=True)
            if not next_pr:
                console.print("[green]🎉 No more PRs to cherry-pick![/green]")
                break

            if not next_pr.master_sha:
                console.print(
                    f"[yellow]⏭️  Skipping PR #{next_pr.pr_number} - no SHA (not merged)[/yellow]"
                )
                picks_skipped += 1
                picks_attempted += 1
                continue

            picks_attempted += 1

            # Show progress
            console.print(
                f"[bold]📋 ({picks_attempted}/{max_picks}) PR #{next_pr.pr_number}[/bold]"
            )
            console.print(f"[dim]Title: {next_pr.title}[/dim]")
            console.print(f"[dim]Author: {next_pr.author}[/dim]")
            console.print(f"[dim]SHA: {next_pr.master_sha}[/dim]")

            # Verify SHA is in sync
            if not _verify_pr_sync(git, next_pr, console):
                picks_skipped += 1
                continue

            # Analyze conflicts
            console.print("[blue]🔍 Analyzing conflicts...[/blue]")
            analysis = git.analyze_cherry_pick_conflicts(minor_version, next_pr.master_sha)

            if analysis.get("error"):
                console.print(f"[red]❌ Analysis error: {analysis['error']}[/red]")
                if not _prompt_continue_on_error():
                    break
                picks_skipped += 1
                continue

            # Display conflict status
            _display_chain_analysis(analysis, console)

            # Interactive decision menu
            while True:
                action = _prompt_action_menu(analysis, next_pr, auto_clean, git)

                if action == "proceed":
                    break  # Continue with cherry-pick
                elif action == "skip":
                    console.print("[yellow]⏭️  Skipping this PR[/yellow]")
                    picks_skipped += 1
                    console.print()
                    break  # Skip to next PR
                elif action == "abort":
                    console.print("[yellow]🛑 Aborting cherry-pick chain[/yellow]")
                    return  # Exit completely
                elif action == "diff":
                    _show_raw_diff(git, next_pr.master_sha, console)
                    continue  # Show menu again
                # Loop back to show menu again

            # If we broke out with skip or abort, handle accordingly
            if action == "skip":
                continue
            elif action == "abort":
                return

            # Execute cherry-pick
            console.print(f"[blue]🍒 Executing: git cherry-pick {analysis['commit_sha']}[/blue]")
            result = git.execute_cherry_pick(next_pr.master_sha)

            if result["success"]:
                console.print("[green]✅ Cherry-pick successful![/green]")
                picks_successful += 1
            else:
                console.print(f"[red]❌ Cherry-pick failed: {result['message']}[/red]")

                if result.get("conflict"):
                    console.print(
                        f"[yellow]Conflicted files: {', '.join(result.get('conflicted_files', []))}[/yellow]"
                    )
                    console.print(
                        "[dim]Resolve conflicts manually and run 'git cherry-pick --continue'[/dim]"
                    )
                    console.print("[dim]Or run 'git cherry-pick --abort' to cancel[/dim]")

                    # Ask user what to do
                    action = _prompt_conflict_action()
                    if action == "abort":
                        if git.abort_cherry_pick():
                            console.print("[yellow]Cherry-pick aborted[/yellow]")
                        else:
                            console.print("[red]Failed to abort cherry-pick[/red]")
                    elif action == "stop":
                        console.print(
                            "[yellow]Stopping chain. Resolve conflicts manually.[/yellow]"
                        )
                        break
                    # For "continue", we just move on and let user handle it

                picks_skipped += 1

            console.print()

            # Ask if user wants to continue
            if not _prompt_continue_chain():
                break

        # Summary
        console.print("[bold cyan]🏁 Cherry-pick chain completed[/bold cyan]")
        console.print(f"[green]✅ Successful: {picks_successful}[/green]")
        console.print(f"[yellow]⏭️  Skipped: {picks_skipped}[/yellow]")
        console.print(f"[blue]📊 Total attempted: {picks_attempted}[/blue]")

        if picks_successful > 0:
            console.print(f"[dim]Consider running: ct minor sync {minor_version}[/dim]")

    except Exception as e:
        console.print(f"[red]Error in cherry-pick chain: {e}[/red]")


def _display_chain_analysis(analysis: Dict[str, Any], console: Console) -> None:
    """Display compact analysis for chain mode."""
    if analysis["has_conflicts"]:
        complexity = analysis["complexity"]
        color = {"simple": "yellow", "moderate": "orange3", "complex": "red"}.get(complexity, "red")

        total_lines = sum(c.get("conflicted_lines", 0) for c in analysis["conflicts"])
        console.print(
            f"[{color}]🚨 {analysis['conflict_count']} files, {total_lines} lines ({complexity})[/{color}]"
        )

        # Show detailed file breakdown
        if analysis["conflicts"]:
            for conflict in analysis["conflicts"][:3]:  # Show top 3 files
                regions = conflict.get("region_count", 1)
                lines = conflict.get("conflicted_lines", "?")
                file_display = conflict["file"]

                # Don't truncate filenames - let terminal wrap naturally

                console.print(f"[dim]  • {file_display}: {regions} region(s), {lines} lines[/dim]")

                # Show all blame commits with proper indentation and clickable links
                if conflict.get("blame_commits"):
                    for blame in conflict["blame_commits"]:
                        # Create clickable links
                        sha_link = f"[link=https://github.com/apache/superset/commit/{blame['sha']}]{blame['sha']}[/link]"

                        if blame["pr_number"]:
                            pr_link = f"[link=https://github.com/apache/superset/pull/{blame['pr_number']}]#{blame['pr_number']}[/link]"
                            commit_info = f"{sha_link} ({pr_link})"
                        else:
                            commit_info = sha_link

                        # Show commit details with indentation - no truncation
                        console.print(f"[dim]    └─ {commit_info}: {blame['message']}[/dim]")
                        console.print(f"[dim]       by {blame['author']} on {blame['date']}[/dim]")

            if len(analysis["conflicts"]) > 3:
                remaining = len(analysis["conflicts"]) - 3
                console.print(f"[dim]  • ... and {remaining} more file(s)[/dim]")
    else:
        console.print("[green]✅ No conflicts detected[/green]")


def _prompt_action_menu(analysis: Dict[str, Any], next_pr: Any, auto_clean: bool, git: Any) -> str:
    """Show interactive menu for cherry-pick decision."""
    import typer
    from rich.console import Console

    console = Console()

    # For clean commits with auto_clean enabled, proceed automatically
    if not analysis["has_conflicts"] and auto_clean:
        console.print("[green]✅ Auto-picking clean commit[/green]")
        return "proceed"

    console.print()
    console.print("[bold yellow]What would you like to do?[/bold yellow]")

    # Generate git command that would be executed
    git_cmd = f"git cherry-pick {analysis['commit_sha']}"

    console.print(f"[dim]1.[/dim] [green]Proceed[/green] - Execute: {git_cmd}")
    console.print("[dim]2.[/dim] [blue]Show diff[/blue] - View raw changes before deciding")
    console.print("[dim]3.[/dim] [yellow]Skip[/yellow] - Skip this PR and continue to next")
    console.print("[dim]4.[/dim] [red]Abort[/red] - Stop the cherry-pick chain")

    while True:
        choice = typer.prompt("Choose option (1-4)", default="1")

        if choice in ["1", "proceed", "p"]:
            return "proceed"
        elif choice in ["2", "diff", "d", "show"]:
            return "diff"
        elif choice in ["3", "skip", "s"]:
            return "skip"
        elif choice in ["4", "abort", "a", "exit", "quit"]:
            return "abort"
        else:
            console.print(
                "[red]Invalid choice. Please enter 1-4, or use keywords like 'proceed', 'skip', etc.[/red]"
            )


def _show_raw_diff(git: Any, commit_sha: str, console: Console) -> None:
    """Display the raw diff for the commit."""
    console.print()
    console.print(f"[bold blue]📄 Raw diff for {commit_sha}:[/bold blue]")
    console.print()

    diff_output = git.get_cherry_pick_diff(commit_sha)

    # Use a pager-like display for long diffs
    if len(diff_output.split("\n")) > 50:
        console.print(
            "[dim]Diff is long, showing first 50 lines. Press Enter to see more, 'q' to quit...[/dim]"
        )
        lines = diff_output.split("\n")

        i = 0
        while i < len(lines):
            # Show 20 lines at a time
            for j in range(20):
                if i + j < len(lines):
                    console.print(lines[i + j])

            i += 20
            if i >= len(lines):
                break

            # Prompt to continue
            import typer

            continue_viewing = typer.prompt("Continue? (Enter/q)", default="", show_default=False)
            if continue_viewing.lower() in ["q", "quit", "exit"]:
                break
    else:
        # Short diff, show it all
        console.print(diff_output)

    console.print()
    console.print("[dim]Press Enter to return to menu...[/dim]")
    input()


def _prompt_cherry_pick(analysis: Dict[str, Any], question: str, default: bool = True) -> bool:
    """Legacy function - kept for compatibility but now unused."""
    import typer

    return typer.confirm(question, default=default)


def _prompt_continue_chain() -> bool:
    """Prompt user whether to continue the chain."""
    import typer

    return typer.confirm("Continue with next PR?", default=True)


def _prompt_continue_on_error() -> bool:
    """Prompt user whether to continue after analysis error."""
    import typer

    return typer.confirm("Analysis failed. Skip this PR and continue?", default=True)


def _prompt_conflict_action() -> str:
    """Prompt user for action when cherry-pick has conflicts."""
    import typer

    console = Console()
    console.print("[yellow]Cherry-pick resulted in conflicts. What would you like to do?[/yellow]")
    console.print("[dim]1. Continue chain (leave conflicts for manual resolution)[/dim]")
    console.print("[dim]2. Abort this cherry-pick and continue chain[/dim]")
    console.print("[dim]3. Stop chain and resolve conflicts now[/dim]")

    while True:
        choice = typer.prompt("Choose action (continue/abort/stop)", default="continue")
        if choice.lower() in ["continue", "abort", "stop"]:
            return choice.lower()
        console.print("[red]Invalid choice. Please enter: continue, abort, or stop[/red]")


def _verify_pr_sync(git: Any, next_pr: Any, console: Console) -> bool:
    """Verify that the PR's SHA in YAML matches what's actually in git."""
    # Check if the SHA from YAML exists in git
    if not git.verify_pr_sha_exists(next_pr.master_sha):
        console.print(f"[red]❌ SHA {next_pr.master_sha} not found in git repository[/red]")
        console.print("[yellow]This indicates the sync data is stale[/yellow]")

        # Try to find the actual SHA for this PR
        actual_sha = git.get_actual_pr_sha(next_pr.pr_number)
        if actual_sha:
            console.print(f"[yellow]Found actual SHA: {actual_sha}[/yellow]")
            if actual_sha != next_pr.master_sha:
                console.print(
                    f"[red]⚠️  Mismatch: YAML has {next_pr.master_sha}, git has {actual_sha}[/red]"
                )
        else:
            console.print(f"[red]❌ Could not find PR #{next_pr.pr_number} in git log[/red]")

        console.print("[dim]Please run: ct minor sync to update sync data[/dim]")

        import typer

        skip_pr = typer.confirm("Skip this PR due to sync mismatch?", default=True)
        return not skip_pr

    # SHA exists - check if it's the most recent for this PR
    actual_sha = git.get_actual_pr_sha(next_pr.pr_number)
    if actual_sha and actual_sha != next_pr.master_sha:
        console.print("[yellow]⚠️  SHA mismatch detected[/yellow]")
        console.print(f"[dim]YAML: {next_pr.master_sha}, Git: {actual_sha}[/dim]")
        console.print("[dim]Consider running: ct minor sync to update[/dim]")

        import typer

        if not typer.confirm("Continue with YAML SHA anyway?", default=False):
            return False

    return True


def _display_json_output(analysis: Dict[str, Any], next_pr: Any) -> None:
    """Display conflict analysis in JSON format."""
    output = {
        "pr_number": next_pr.pr_number,
        "pr_title": next_pr.title,
        "pr_author": next_pr.author,
        "analysis": analysis,
    }
    print(json.dumps(output, indent=2))


def _display_recommendations(analysis: Dict[str, Any], console: Console) -> None:
    """Display recommendations based on conflict analysis."""
    console.print()

    if analysis.get("error"):
        console.print("[red]❌ Cannot analyze conflicts due to error[/red]")
        console.print("[dim]Check that both the target branch and commit exist[/dim]")
        return

    if not analysis["has_conflicts"]:
        console.print("[green]🎯 Recommendation: Safe to cherry-pick[/green]")
        console.print(f"[dim]Run: git cherry-pick {analysis['commit_sha']}[/dim]")
        return

    complexity = analysis["complexity"]

    if complexity == "simple":
        console.print("[yellow]⚠️  Recommendation: Manual resolution recommended[/yellow]")
        console.print("[dim]Conflicts are limited and should be straightforward to resolve[/dim]")
        console.print(f"[dim]Run: git cherry-pick {analysis['commit_sha']}[/dim]")
        console.print("[dim]Then resolve conflicts manually and commit[/dim]")

    elif complexity == "moderate":
        console.print("[orange3]🤔 Recommendation: Consider dependencies[/orange3]")
        console.print("[dim]Moderate conflicts may indicate missing prerequisite commits[/dim]")
        console.print(
            "[dim]Consider checking if related commits should be cherry-picked first[/dim]"
        )
        console.print(
            f"[dim]Or attempt manual resolution: git cherry-pick {analysis['commit_sha']}[/dim]"
        )

    else:  # complex
        console.print("[red]🛑 Recommendation: Investigate dependencies[/red]")
        console.print("[dim]Complex conflicts likely require prerequisite commits[/dim]")
        console.print("[dim]Use dependency analysis tools or consider skipping this PR[/dim]")
        console.print("[dim]Manual resolution not recommended without deeper analysis[/dim]")


def analyze_commit_conflicts(
    minor_version: str, commit_sha: str, repo_path: str, format_type: str = "table"
) -> None:
    """Analyze conflicts for a specific commit SHA."""
    console = Console()

    try:
        # Initialize git interface
        git = GitInterface(console=console)

        # Analyze conflicts
        console.print(f"[blue]Analyzing conflicts for cherry-pick of {commit_sha}...[/blue]")
        analysis = git.analyze_cherry_pick_conflicts(minor_version, commit_sha)

        # Display results
        if format_type == "json":
            print(json.dumps(analysis, indent=2))
        else:
            _display_commit_analysis(analysis, console)

    except Exception as e:
        console.print(f"[red]Error analyzing conflicts: {e}[/red]")


def _display_commit_analysis(analysis: Dict[str, Any], console: Console) -> None:
    """Display commit conflict analysis in table format."""

    # Main status table
    table = Table(title=f"Cherry-Pick Conflict Analysis: {analysis['commit_sha']}")
    table.add_column("Property", style="bold")
    table.add_column("Value", style="")

    # Add commit info
    table.add_row("Commit SHA", analysis["commit_sha"])
    table.add_row("Message", analysis.get("commit_message", "Unknown"))
    table.add_row("Author", analysis.get("commit_author", "Unknown"))
    table.add_row("Target Branch", analysis["target_branch"])

    # Status and complexity
    if analysis.get("error"):
        table.add_row("Status", f"[red]Error: {analysis['error']}[/red]")
    elif analysis["has_conflicts"]:
        complexity = analysis["complexity"]
        color = {"simple": "yellow", "moderate": "orange3", "complex": "red"}.get(complexity, "red")

        table.add_row("Status", f"[{color}]🚨 Conflicts detected ({complexity})[/{color}]")
        table.add_row("Conflict Count", str(analysis["conflict_count"]))
    else:
        table.add_row("Status", "[green]✅ Clean cherry-pick[/green]")

    console.print(table)

    # Detailed conflicts if they exist
    if analysis["has_conflicts"] and analysis["conflicts"]:
        console.print()

        conflicts_table = Table(title="Conflict Details")
        conflicts_table.add_column("File", style="bold")
        conflicts_table.add_column("Type", style="")
        conflicts_table.add_column("Lines", justify="right")
        conflicts_table.add_column("Description", style="dim")

        for conflict in analysis["conflicts"]:
            conflicts_table.add_row(
                conflict["file"],
                conflict["type"],
                str(conflict.get("conflicted_lines", "?")),
                conflict["description"],
            )

        console.print(conflicts_table)

    # Recommendations
    _display_recommendations(analysis, console)
