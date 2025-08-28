"""Git commit message parsing to extract PR → SHA mappings."""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from rich.console import Console

from .git_utils import GitError, run_git_command

console = Console()


@dataclass
class GitTag:
    """Information about a git tag."""

    name: str
    sha: str
    date: str  # Tag creation date
    commit_date: str = ""  # Commit date


@dataclass
class GitCommit:
    """Information about a git commit."""

    sha: str
    message: str
    author: str
    date: str
    pr_number: Optional[int] = None


def parse_pr_from_commit_message(message: str) -> Optional[int]:
    """Extract PR number from commit message.

    Common patterns in Superset:
    - "Fix dashboard bug (#12345)"
    - "Merge pull request #12345 from user/branch"
    - "Revert 'fix: something (#28363)' (#28567)" - want the last/outer PR
    """
    # Pattern 1: (#12345) - find ALL matches and take the LAST one
    # This handles revert commits where we want the outer PR, not the inner one
    matches = re.findall(r"\(#(\d+)\)", message)
    if matches:
        return int(matches[-1])  # Take the last match (outer PR for reverts)

    # Pattern 2: Merge pull request #12345
    match = re.search(r"Merge pull request #(\d+)", message)
    if match:
        return int(match.group(1))

    # Pattern 3: [12345] at beginning
    match = re.search(r"^\[(\d+)\]", message)
    if match:
        return int(match.group(1))

    # Pattern 4: #12345 anywhere (fallback)
    match = re.search(r"#(\d+)", message)
    if match:
        return int(match.group(1))

    return None


def get_recent_commits(
    repo_path: Path, branch: str = "master", limit: int = 1000
) -> List[GitCommit]:
    """Get recent commits from specified branch."""
    try:
        # Get recent commits with format: 8-digit-SHA|message|author|date
        git_output = run_git_command(
            [
                "log",
                branch,
                f"--max-count={limit}",
                "--format=%h|%s|%an|%ci",  # %h = abbreviated hash (7-8 digits)
            ],
            repo_path,
        )

        commits = []
        for line in git_output.split("\n"):
            if not line.strip():
                continue

            parts = line.split("|", 3)
            if len(parts) >= 4:
                sha, message, author, date = parts
                pr_number = parse_pr_from_commit_message(message)

                commits.append(
                    GitCommit(
                        sha=sha, message=message, author=author, date=date, pr_number=pr_number
                    )
                )

        return commits

    except GitError as e:
        console.print(f"[red]Error getting git commits: {e}[/red]")
        return []


def build_pr_sha_mapping(
    repo_path: Path, target_pr_numbers: List[int]
) -> tuple[Dict[int, str], List[int]]:
    """Build mapping of PR number → merge commit SHA by parsing git log.

    Args:
        repo_path: Path to git repository
        target_pr_numbers: List of PR numbers we need SHAs for

    Returns:
        Tuple of (mapping dict, ordered list of PR numbers by git log chronology)
    """
    console.print(f"[dim]Parsing git log to find SHAs for {len(target_pr_numbers)} PRs...[/dim]")

    # Get recent commits (limit to reasonable number to avoid performance issues)
    commits = get_recent_commits(repo_path, "master", limit=5000)

    console.print(f"[dim]Analyzing {len(commits)} recent commits...[/dim]")

    # Build mapping and chronological order for target PRs
    pr_to_sha = {}
    pr_chronological_order = []  # PRs in order they appear in git log
    target_pr_set = set(target_pr_numbers)

    found_count = 0
    for commit in commits:
        if commit.pr_number and commit.pr_number in target_pr_set:
            if commit.pr_number not in pr_to_sha:  # Avoid duplicates
                pr_to_sha[commit.pr_number] = commit.sha
                pr_chronological_order.append(commit.pr_number)  # Order from git log
                found_count += 1

            # Stop early if we found all target PRs
            if found_count >= len(target_pr_numbers):
                break

    console.print(f"[dim]Found SHAs for {len(pr_to_sha)}/{len(target_pr_numbers)} PRs[/dim]")

    # Only show missing PRs if there are many (might indicate a real problem)
    missing_prs = target_pr_set - set(pr_to_sha.keys())
    if len(missing_prs) > len(target_pr_numbers) * 0.1:  # More than 10% missing
        missing_list = sorted(list(missing_prs))[:5]  # Show first 5
        more_text = f" and {len(missing_prs) - 5} more" if len(missing_prs) > 5 else ""
        console.print(f"[yellow]Many PRs without SHAs: {missing_list}{more_text}[/yellow]")
        console.print("[yellow](This might indicate closed/abandoned PRs)[/yellow]")

    return pr_to_sha, pr_chronological_order


def get_release_tags(repo_path: Path, minor_version: str) -> List[GitTag]:
    """Get all tags for a specific minor release (e.g., 4.0.0, 4.0.1, 4.0.2)."""
    try:
        # Get all tags matching the minor version pattern, sorted by version
        tag_pattern = f"{minor_version}.*"
        tag_output = run_git_command(
            [
                "tag",
                "-l",
                tag_pattern,
                "--sort=-version:refname",  # Sort newest first
            ],
            repo_path,
        )

        if not tag_output.strip():
            console.print(f"[dim]No tags found for {minor_version}[/dim]")
            return []

        tags = []
        tag_names = tag_output.split("\n")
        console.print(f"[dim]Found {len(tag_names)} tags for {minor_version}[/dim]")

        for tag_name in tag_names:
            if not tag_name.strip():
                continue

            try:
                # Get tag SHA (abbreviated to 8 digits)
                tag_sha = run_git_command(["rev-parse", "--short=8", tag_name], repo_path)

                # Get tag creation date (when the tag was created)
                try:
                    # Try to get annotated tag date first
                    tag_date = run_git_command(
                        ["for-each-ref", "--format=%(creatordate:iso)", f"refs/tags/{tag_name}"],
                        repo_path,
                    )
                except GitError:
                    # Fall back to commit date if it's a lightweight tag
                    tag_date = run_git_command(["log", "-1", "--format=%ci", tag_sha], repo_path)

                # Get commit date (when the code was written)
                commit_date = run_git_command(["log", "-1", "--format=%ci", tag_sha], repo_path)

                tags.append(
                    GitTag(name=tag_name, sha=tag_sha, date=tag_date, commit_date=commit_date)
                )

            except GitError:
                console.print(f"[yellow]Warning: Could not get details for tag {tag_name}[/yellow]")
                continue

        return tags

    except GitError as e:
        console.print(f"[red]Error getting release tags: {e}[/red]")
        return []
