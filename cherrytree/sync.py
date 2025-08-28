"""Sync command implementation - build release branch state from git and GitHub."""

import os
import re
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import typer
import yaml
from github import Github
from rich.console import Console

from .git_parser import build_pr_sha_mapping, get_release_tags

console = Console()


@dataclass
class PRInfo:
    """Information about a PR from GitHub API."""

    pr_number: int
    title: str
    author: str
    master_sha: str
    pr_state: str  # "open", "closed"
    is_merged: bool


@dataclass
class CommitInfo:
    """Information about a commit from git log."""

    sha: str
    message: str
    date: str
    pr_number: Optional[int] = None


@dataclass
class ReleaseBranchState:
    """Complete state of a release branch."""

    minor_version: str
    branch_name: str
    base_sha: str
    base_date: str
    targeted_prs: List[Dict[str, Any]]  # Only open or merged PRs
    commits_in_branch: List[Dict[str, Any]]
    micro_releases: List[Dict[str, Any]]  # Git tags for micro versions
    last_synced: str
    synced_from_repo: str


from .git_utils import GitError, run_git_command


class GitHubError(Exception):
    """GitHub API operation failed."""

    pass


def run_gh_command(args: List[str]) -> str:
    """Execute gh CLI command and return stdout."""
    try:
        result = subprocess.run(["gh"] + args, capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        raise GitHubError(f"GitHub CLI command failed: gh {' '.join(args)}\nError: {e.stderr}")


def check_branch_exists(repo_path: Path, branch: str) -> bool:
    """Check if branch exists locally."""
    try:
        run_git_command(["rev-parse", "--verify", f"refs/heads/{branch}"], repo_path)
        return True
    except GitError:
        return False


def check_remote_branch_exists(repo_path: Path, branch: str) -> bool:
    """Check if branch exists on origin remote."""
    try:
        run_git_command(["rev-parse", "--verify", f"refs/remotes/origin/{branch}"], repo_path)
        return True
    except GitError:
        return False


def fetch_and_checkout_branch(repo_path: Path, branch: str) -> None:
    """Fetch latest remotes and checkout branch from origin."""
    console.print("[dim]Fetching latest from origin...[/dim]")
    run_git_command(["fetch", "origin"], repo_path)

    console.print(f"[dim]Creating local branch {branch} from origin/{branch}...[/dim]")
    run_git_command(["checkout", "-b", branch, f"origin/{branch}"], repo_path)


def get_merge_base(repo_path: Path, branch: str) -> tuple[str, str]:
    """Get merge-base SHA and date where branch diverged from master."""
    # Check if branch exists locally
    if not check_branch_exists(repo_path, branch):
        # Check if branch exists on remote
        console.print("[dim]Checking remote branches...[/dim]")
        run_git_command(["fetch", "origin"], repo_path)

        if check_remote_branch_exists(repo_path, branch):
            console.print(f"[yellow]Branch {branch} not found locally.[/yellow]")
            console.print(f"[yellow]Found origin/{branch} on remote.[/yellow]")
            console.print(f"[dim]Need to run: git checkout -b {branch} origin/{branch}[/dim]")

            # Prompt user
            create_branch = typer.confirm("Want me to run this command for you?")
            if create_branch:
                fetch_and_checkout_branch(repo_path, branch)
            else:
                console.print("[red]Cannot proceed without local branch.[/red]")
                console.print(
                    f"[yellow]Run manually: git checkout -b {branch} origin/{branch}[/yellow]"
                )
                raise typer.Exit(1)
        else:
            # Show available remote branches
            try:
                remote_branches = run_git_command(
                    ["branch", "-r", "--format=%(refname:short)"], repo_path
                )
                release_branches = [
                    b.replace("origin/", "")
                    for b in remote_branches.split("\n")
                    if b.startswith("origin/")
                    and b.replace("origin/", "").replace(".", "").replace("-", "").isdigit()
                ]

                console.print(f"[red]Error: Branch {branch} not found locally or on remote.[/red]")
                if release_branches:
                    console.print(
                        f"[yellow]Available release branches: {', '.join(release_branches)}[/yellow]"
                    )
                else:
                    console.print("[yellow]No release branches found.[/yellow]")
                raise typer.Exit(1)
            except GitError:
                console.print(f"[red]Error: Branch {branch} not found.[/red]")
                raise typer.Exit(1)

    # Get merge-base and abbreviate to 8 digits
    full_base_sha = run_git_command(["merge-base", "master", branch], repo_path)
    base_sha = full_base_sha[:8]  # Truncate to 8 digits
    base_date = run_git_command(["show", "--format=%ci", "-s", full_base_sha], repo_path)
    return base_sha, base_date


def get_branch_commits(repo_path: Path, branch: str, base_sha: str) -> List[CommitInfo]:
    """Get all commits in branch since merge-base."""
    # Get commits that are in branch but not in the merge-base (use full SHA for range)
    # Need to expand base_sha back to full SHA for git log range
    full_base_sha = run_git_command(["rev-parse", base_sha], repo_path)

    log_output = run_git_command(
        [
            "log",
            f"{full_base_sha}..{branch}",
            "--oneline",
            "--format=%h|%s|%ci",  # %h = 8-digit abbreviated SHA
        ],
        repo_path,
    )

    commits = []
    for line in log_output.split("\n"):
        if not line.strip():
            continue

        parts = line.split("|", 2)
        if len(parts) >= 3:
            sha, message, date = parts
            # Extract PR number from commit message if present
            pr_match = re.search(r"#(\d+)", message)
            pr_number = int(pr_match.group(1)) if pr_match else None

            commits.append(CommitInfo(sha=sha, message=message, date=date, pr_number=pr_number))

    return commits


def get_github_token() -> str:
    """Get GitHub token from gh CLI or environment."""
    # Try to get token from gh CLI first
    try:
        token = run_gh_command(["auth", "token"])
        return token.strip()
    except GitHubError:
        # Fall back to environment variable
        token = os.getenv("GITHUB_TOKEN")
        if not token:
            console.print("[red]Error: No GitHub authentication found[/red]")
            console.print("Run: gh auth login")
            console.print("Or set GITHUB_TOKEN environment variable")
            raise typer.Exit(1)
        return token


def get_labeled_prs(github_repo: str, label: str) -> List[PRInfo]:
    """Get open and merged PRs with specified label from GitHub API."""
    try:
        # Get GitHub token and create client
        token = get_github_token()
        g = Github(token)

        prs = []

        # Search 1: Open PRs with the label
        open_query = f"repo:{github_repo} is:pr label:{label} base:master is:open"
        console.print(f"[dim]Searching for open PRs: {open_query}[/dim]")
        open_issues = g.search_issues(open_query)

        count = 0
        for issue in open_issues:
            count += 1
            if count % 50 == 0:
                console.print(f"[dim]  Processed {count} open PRs...[/dim]")

            prs.append(
                PRInfo(
                    pr_number=issue.number,
                    title=issue.title,
                    author=issue.user.login,
                    master_sha="",
                    pr_state="open",
                    is_merged=False,
                )
            )

        console.print(f"[dim]Found {count} open PRs[/dim]")

        # Search 2: Merged PRs with the label
        merged_query = f"repo:{github_repo} is:pr label:{label} base:master is:merged"
        console.print(f"[dim]Searching for merged PRs: {merged_query}[/dim]")
        merged_issues = g.search_issues(merged_query)

        merged_count = 0
        for issue in merged_issues:
            merged_count += 1
            if merged_count % 50 == 0:
                console.print(f"[dim]  Processed {merged_count} merged PRs...[/dim]")

            prs.append(
                PRInfo(
                    pr_number=issue.number,
                    title=issue.title,
                    author=issue.user.login,
                    master_sha="",  # Will get from git log
                    pr_state="closed",  # Merged PRs show as closed
                    is_merged=True,
                )
            )

        console.print(f"[dim]Found {merged_count} merged PRs[/dim]")
        return prs

    except Exception as e:
        raise GitHubError(f"Failed to query GitHub API: {e}")


def build_release_state(
    repo_path: Path, minor_version: str, github_repo: str = "apache/superset"
) -> ReleaseBranchState:
    """Build complete release branch state."""
    console.print(f"[blue]Analyzing release branch {minor_version}...[/blue]")

    branch_name = minor_version

    # Phase 1: Git repository analysis
    console.print(f"[dim]Finding merge-base for {branch_name}...[/dim]")
    base_sha, base_date = get_merge_base(repo_path, branch_name)
    console.print(f"[dim]Base SHA: {base_sha[:8]} ({base_date})[/dim]")

    console.print(f"[dim]Getting commits in {branch_name} branch...[/dim]")
    branch_commits = get_branch_commits(repo_path, branch_name, base_sha)
    console.print(f"[dim]Found {len(branch_commits)} commits in branch[/dim]")

    # Phase 2: Git tag collection for micro releases
    console.print(f"[dim]Getting tags for {minor_version} micro releases...[/dim]")
    release_tags = get_release_tags(repo_path, minor_version)

    # Phase 3: GitHub API collection
    label = f"v{minor_version}"
    console.print(f"[dim]Querying GitHub for PRs with label '{label}'...[/dim]")
    labeled_prs = get_labeled_prs(github_repo, label)
    console.print(f"[dim]Found {len(labeled_prs)} PRs labeled {label}[/dim]")

    # Phase 4: Git log parsing for PR → SHA mapping
    pr_numbers = [pr.pr_number for pr in labeled_prs]
    pr_to_sha, pr_chronological_order = build_pr_sha_mapping(repo_path, pr_numbers)

    # Create lookup for GitHub PR data
    pr_lookup = {pr.pr_number: pr for pr in labeled_prs}

    # Build targeted_prs in git log chronological order
    targeted_prs_dict = []
    abandoned_count = 0

    # First, add PRs that are in git log (in chronological order)
    for pr_number in pr_chronological_order:
        pr = pr_lookup.get(pr_number)
        if not pr:
            continue  # Shouldn't happen, but be safe
        # Get the actual merge commit SHA from git log parsing
        git_sha = pr_to_sha.get(pr.pr_number, "")

        # These PRs are in git log, so they're merged
        targeted_prs_dict.append(
            {
                "pr_number": pr.pr_number,
                "title": pr.title,
                "master_sha": git_sha,
                "author": pr.author,
                "is_merged": True,  # All PRs in git log are merged
            }
        )

    # Then, add any open PRs (not in git log yet) at the end
    for pr in labeled_prs:
        if pr.pr_state == "open" and pr.pr_number not in pr_to_sha:
            targeted_prs_dict.append(
                {
                    "pr_number": pr.pr_number,
                    "title": pr.title,
                    "master_sha": "",  # No SHA yet, not merged
                    "author": pr.author,
                    "is_merged": False,  # Open PRs need merge first
                }
            )

    # Count abandoned PRs (closed but not in git log)
    for pr in labeled_prs:
        if pr.pr_state == "closed" and pr.pr_number not in pr_to_sha:
            abandoned_count += 1

    console.print(
        f"[dim]Filtered to {len(targeted_prs_dict)} actionable PRs ({abandoned_count} abandoned)[/dim]"
    )

    commits_dict = []
    for commit in branch_commits:
        commits_dict.append(
            {
                "sha": commit.sha,
                "message": commit.message,
                "date": commit.date,
                "pr_number": commit.pr_number,
            }
        )

    # Convert tag data to dict format
    micro_releases_dict = []
    for tag in release_tags:
        micro_releases_dict.append(
            {
                "version": tag.name,
                "tag_sha": tag.sha,
                "tag_date": tag.date,  # When tag was created (release date)
                "commit_date": tag.commit_date,  # When code was written
                # TODO: Add included_prs by analyzing commit range for each tag
            }
        )

    return ReleaseBranchState(
        minor_version=minor_version,
        branch_name=branch_name,
        base_sha=base_sha,
        base_date=base_date,
        targeted_prs=targeted_prs_dict,
        commits_in_branch=commits_dict,
        micro_releases=micro_releases_dict,
        last_synced=datetime.now().isoformat(),
        synced_from_repo=github_repo,
    )


def save_release_state(state: ReleaseBranchState, output_dir: Path) -> Path:
    """Save release state to YAML file."""
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"{state.minor_version}.yml"

    # Convert to dict for YAML serialization
    yaml_data = {"release_branch": asdict(state)}

    with open(output_file, "w") as f:
        yaml.dump(yaml_data, f, default_flow_style=False, sort_keys=False)

    return output_file


def check_gh_auth() -> None:
    """Check if GitHub CLI is authenticated."""
    try:
        run_gh_command(["auth", "status"])
    except GitHubError:
        console.print("[red]Error: GitHub CLI not authenticated[/red]")
        console.print("Run: gh auth login")
        raise typer.Exit(1)


def sync_command(
    minor_version: str,
    repo_path: Optional[str] = typer.Option(None, "--repo", help="Local repository path"),
    github_repo: str = typer.Option("apache/superset", "--github-repo", help="GitHub repository"),
    output_dir: str = typer.Option("releases", "--output", help="Output directory for YAML files"),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would be done without writing files"
    ),
) -> None:
    """Sync release branch state from git and GitHub."""

    if not repo_path:
        console.print("[red]Error: --repo path is required[/red]")
        console.print("Set with: cherrytree config set-repo /path/to/superset")
        console.print("Or use: cherrytree sync 5.0 --repo /path/to/superset")
        raise typer.Exit(1)

    repo_path_obj = Path(repo_path).resolve()
    if not repo_path_obj.exists():
        console.print(f"[red]Error: Repository path does not exist: {repo_path_obj}[/red]")
        raise typer.Exit(1)

    if not (repo_path_obj / ".git").exists():
        console.print(f"[red]Error: Not a git repository: {repo_path_obj}[/red]")
        raise typer.Exit(1)

    try:
        # Check GitHub CLI authentication before starting
        check_gh_auth()

        # Build complete release state
        state = build_release_state(repo_path_obj, minor_version, github_repo)

        if dry_run:
            # Count PRs by status
            status_counts = {}
            for pr in state.targeted_prs:
                status = pr.get("status", "unknown")
                status_counts[status] = status_counts.get(status, 0) + 1

            console.print(f"[yellow]DRY RUN - Would create {minor_version}.yml with:[/yellow]")
            console.print(f"  Base SHA: {state.base_sha}")
            console.print(f"  Micro releases: {len(state.micro_releases)} tags")
            for micro in state.micro_releases[:3]:  # Show first 3 tags
                console.print(f"    {micro['version']}: {micro['tag_sha']}")
            if len(state.micro_releases) > 3:
                console.print(f"    ... and {len(state.micro_releases) - 3} more")
            console.print(f"  Targeted PRs: {len(state.targeted_prs)} (actionable only)")
            for status, count in status_counts.items():
                console.print(f"    {status}: {count}")
            console.print(f"  Branch commits: {len(state.commits_in_branch)}")
            return

        # Save to file
        output_path = save_release_state(state, Path(output_dir))

        console.print(f"[green]✅ Synced {minor_version} release branch[/green]")
        console.print(f"[dim]Written to: {output_path}[/dim]")
        console.print(f"[dim]Base SHA: {state.base_sha}[/dim]")
        console.print(f"[dim]Targeted PRs: {len(state.targeted_prs)} (open or merged)[/dim]")
        console.print(f"[dim]Branch commits: {len(state.commits_in_branch)}[/dim]")

    except (GitError, GitHubError) as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Unexpected error: {e}[/red]")
        raise typer.Exit(1)
