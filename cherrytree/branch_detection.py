"""Branch detection and validation utilities for automatic release branch management."""

import re
from typing import List, Optional

import typer
from rich.console import Console

from .git_interface import GitError, GitInterface


def is_release_branch(branch_name: str) -> bool:
    """Check if a branch name matches the release pattern (X.Y)."""
    if not branch_name:
        return False

    # Match pattern like "4.0", "5.1", etc.
    pattern = re.compile(r"^\d+\.\d+$")
    return bool(pattern.match(branch_name))


def get_current_release_branch(console: Optional[Console] = None) -> Optional[str]:
    """
    Get the current release branch if we're on one, otherwise None.

    Returns:
        The release branch name (e.g., "4.0") if on a release branch, None otherwise
    """
    if not console:
        console = Console()

    try:
        git = GitInterface(console=console)
        current_branch = git.get_current_branch()

        if is_release_branch(current_branch):
            return current_branch

        return None
    except GitError as e:
        console.print(f"[red]Error: {e}[/red]")
        console.print("[yellow]Please run cherrytree from within a git repository.[/yellow]")
        raise typer.Exit(1) from None


def get_available_release_branches(console: Optional[Console] = None) -> List[str]:
    """
    Get all available release branches from the repository.

    Returns:
        List of release branch names sorted numerically (e.g., ["4.0", "4.1", "5.0"])
    """
    if not console:
        console = Console()

    try:
        git = GitInterface(console=console)

        # Get both local and remote release branches
        try:
            # Get local branches
            local_branches = git.run_command(["branch", "--format=%(refname:short)"])
            local_release_branches = [
                branch.strip()
                for branch in local_branches.split("\n")
                if is_release_branch(branch.strip())
            ]

            # Get remote branches
            remote_release_branches = git.get_release_branches()

            # Combine and deduplicate
            all_branches = set(local_release_branches + remote_release_branches)

            # Sort numerically by version
            def version_sort_key(branch: str) -> tuple:
                parts = branch.split(".")
                return (int(parts[0]), int(parts[1]))

            return sorted(all_branches, key=version_sort_key, reverse=True)

        except Exception:
            return []

    except GitError as e:
        console.print(f"[red]Error: {e}[/red]")
        console.print("[yellow]Please run cherrytree from within a git repository.[/yellow]")
        raise typer.Exit(1) from None


def ensure_release_branch(console: Optional[Console] = None) -> str:
    """
    Ensure we're on a release branch. If not, prompt user to select one.

    Returns:
        The release branch name to use for operations

    Raises:
        typer.Exit: If user chooses to bail or no release branches available
    """
    if not console:
        console = Console()

    # Check if we're already on a release branch
    current_release = get_current_release_branch(console)
    if current_release:
        return current_release

    # Not on a release branch, get available options
    available_branches = get_available_release_branches(console)

    if not available_branches:
        console.print("[red]No release branches found in the repository.[/red]")
        console.print(
            "[yellow]Release branches should follow the pattern X.Y (e.g., 4.0, 5.1)[/yellow]"
        )
        raise typer.Exit(1)

    # Show current branch for context
    git = GitInterface(console=console)
    current_branch = git.get_current_branch()

    console.print(
        f"[yellow]You are currently on branch '{current_branch}', which is not a release branch.[/yellow]"
    )
    console.print("[yellow]Release management requires being on a minor release branch.[/yellow]")
    console.print()
    console.print("Which release branch would you like me to checkout?")
    console.print()

    # Show numbered options
    choices = ["bail"] + available_branches
    for i, choice in enumerate(choices):
        if choice == "bail":
            console.print(f"  {i + 1}. [red]{choice}[/red] - Exit without making changes")
        else:
            console.print(f"  {i + 1}. [green]{choice}[/green]")

    console.print()

    # Get user choice
    while True:
        try:
            choice_input = typer.prompt("Enter your choice (number)", type=int)
            if 1 <= choice_input <= len(choices):
                selected = choices[choice_input - 1]
                break
            else:
                console.print(f"[red]Please enter a number between 1 and {len(choices)}[/red]")
        except (ValueError, typer.Abort):
            console.print("[red]Invalid input. Please enter a number.[/red]")

    # Handle user choice
    if selected == "bail":
        console.print("[yellow]Exiting without changes.[/yellow]")
        raise typer.Exit(0)

    # User selected a release branch - check out if needed
    if git.check_branch_exists(selected):
        console.print(f"[green]Switching to existing local branch {selected}...[/green]")
        git.run_command(["checkout", selected])
    elif git.check_remote_branch_exists(selected):
        console.print(f"[green]Creating and switching to branch {selected} from origin...[/green]")
        git.fetch_and_checkout_branch(selected)
    else:
        console.print(f"[red]Error: Branch {selected} is not available.[/red]")
        raise typer.Exit(1)

    return selected
