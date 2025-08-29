"""Consolidated git operations interface for cherrytree."""

import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import typer
from rich.console import Console

from .commit import Commit
from .micro_release import Micro


class GitError(Exception):
    """Git operation failed."""

    pass


class GitInterface:
    """
    Consolidated interface for all git operations.

    Provides a clean, object-oriented interface to git operations,
    consolidating functionality from git_utils.py, git_parser.py,
    and scattered functions in sync.py.
    """

    def __init__(self, repo_path: Optional[Path] = None, console: Optional[Console] = None):
        """Initialize GitInterface with repository path and optional console."""
        self.repo_path = (repo_path or Path.cwd()).resolve()
        self.console = console or Console()

        # Check if it's a git repository
        if not (self.repo_path / ".git").exists():
            raise GitError(f"Not a git repository: {self.repo_path}")

    def run_command(self, args: List[str]) -> str:
        """Execute git command and return stdout."""
        try:
            result = subprocess.run(
                ["git"] + args, cwd=self.repo_path, capture_output=True, text=True, check=True
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            raise GitError(f"Git command failed: git {' '.join(args)}\nError: {e.stderr}") from e

    # Branch Management Operations
    def check_branch_exists(self, branch: str) -> bool:
        """Check if branch exists locally."""
        try:
            self.run_command(["rev-parse", "--verify", f"refs/heads/{branch}"])
            return True
        except GitError:
            return False

    def check_remote_branch_exists(self, branch: str) -> bool:
        """Check if branch exists on origin remote."""
        try:
            self.run_command(["rev-parse", "--verify", f"refs/remotes/origin/{branch}"])
            return True
        except GitError:
            return False

    def fetch_and_checkout_branch(self, branch: str) -> None:
        """Fetch latest remotes and checkout branch from origin."""
        self.console.print("[dim]Fetching latest from origin...[/dim]")
        self.run_command(["fetch", "origin"])

        self.console.print(f"[dim]Creating local branch {branch} from origin/{branch}...[/dim]")
        self.run_command(["checkout", "-b", branch, f"origin/{branch}"])

    def get_merge_base(self, branch: str, base_branch: str = "master") -> Tuple[str, str]:
        """Get merge-base SHA and date where branch diverged from base_branch."""
        # Check if branch exists locally
        if not self.check_branch_exists(branch):
            # Check if branch exists on remote
            self.console.print("[dim]Checking remote branches...[/dim]")
            self.run_command(["fetch", "origin"])

            if self.check_remote_branch_exists(branch):
                self.console.print(f"[yellow]Branch {branch} not found locally.[/yellow]")
                self.console.print(f"[yellow]Found origin/{branch} on remote.[/yellow]")
                self.console.print(
                    f"[dim]Need to run: git checkout -b {branch} origin/{branch}[/dim]"
                )

                # Prompt user
                create_branch = typer.confirm("Want me to run this command for you?")
                if create_branch:
                    self.fetch_and_checkout_branch(branch)
                else:
                    self.console.print("[red]Cannot proceed without local branch.[/red]")
                    self.console.print(
                        f"[yellow]Run manually: git checkout -b {branch} origin/{branch}[/yellow]"
                    )
                    raise typer.Exit(1) from None
            else:
                # Show available remote branches
                try:
                    remote_branches = self.run_command(
                        ["branch", "-r", "--format=%(refname:short)"]
                    )
                    release_branches = [
                        b.replace("origin/", "")
                        for b in remote_branches.split("\n")
                        if b.startswith("origin/")
                        and b.replace("origin/", "").replace(".", "").replace("-", "").isdigit()
                    ]

                    self.console.print(
                        f"[red]Error: Branch {branch} not found locally or on remote.[/red]"
                    )
                    if release_branches:
                        self.console.print(
                            f"[yellow]Available release branches: {', '.join(release_branches)}[/yellow]"
                        )
                    else:
                        self.console.print("[yellow]No release branches found.[/yellow]")
                    raise typer.Exit(1) from None
                except GitError:
                    self.console.print(f"[red]Error: Branch {branch} not found.[/red]")
                    raise typer.Exit(1) from None

        # Get merge-base and abbreviate to 8 digits
        full_base_sha = self.run_command(["merge-base", base_branch, branch])
        base_sha = full_base_sha[:8]  # Truncate to 8 digits
        base_date = self.run_command(["show", "--format=%ci", "-s", full_base_sha])
        return base_sha, base_date

    # Commit Operations
    def get_branch_commits(self, branch: str, base_sha: str) -> List[Commit]:
        """Get all commits in branch since merge-base."""
        # Get commits that are in branch but not in the merge-base (use full SHA for range)
        # Need to expand base_sha back to full SHA for git log range
        full_base_sha = self.run_command(["rev-parse", base_sha])

        log_output = self.run_command(
            [
                "log",
                f"{full_base_sha}..{branch}",
                "--oneline",
                "--format=%h|%s|%ci",  # %h = 8-digit abbreviated SHA
            ]
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

                commits.append(Commit(sha=sha, message=message, date=date, pr_number=pr_number))

        return commits

    # Tag Operations
    def get_release_tags(self, minor_version: str) -> List[Micro]:
        """Get git tags for micro releases of a minor version."""
        try:
            # Get all tags that match the minor version pattern
            tag_pattern = f"{minor_version}.*"
            tags_output = self.run_command(
                ["tag", "--list", tag_pattern, "--sort=-version:refname"]
            )

            if not tags_output:
                return []

            tags = []
            for tag_name in tags_output.split("\n"):
                if not tag_name.strip():
                    continue

                # Get tag SHA and date
                try:
                    tag_sha = self.run_command(["rev-list", "-n", "1", tag_name])[:8]  # 8-digit SHA
                    tag_date = self.run_command(["log", "-1", "--format=%ci", tag_name])

                    # Get commit date (when the code was written, not when tag was created)
                    commit_date = self.run_command(["log", "-1", "--format=%ci", tag_sha])

                    tags.append(
                        Micro(
                            version=tag_name,
                            tag_sha=tag_sha,
                            tag_date=tag_date,
                            commit_date=commit_date,
                        )
                    )
                except GitError:
                    # Skip tags that can't be processed
                    continue

            return tags

        except GitError:
            return []

    # PR Mapping Operations
    def build_pr_sha_mapping(self, pr_numbers: List[int]) -> Tuple[Dict[int, str], List[int]]:
        """Build mapping of PR number → merge commit SHA by parsing git log."""
        try:
            # Get commits from master branch that mention PR numbers
            # Use --reverse to get oldest commits first (better for dependency order)
            log_output = self.run_command(
                [
                    "log",
                    "master",
                    "--oneline",
                    "--format=%h|%s",
                    "--grep=#[0-9]",
                    "--extended-regexp",
                    "--reverse",  # Oldest commits first for proper dependency order
                ]
            )

            pr_to_sha = {}
            pr_chronological_order = []

            for line in log_output.split("\n"):
                if not line.strip():
                    continue

                parts = line.split("|", 1)
                if len(parts) != 2:
                    continue

                sha, message = parts

                # Extract all PR numbers from commit message
                pr_matches = re.findall(r"#(\d+)", message)
                for pr_match in pr_matches:
                    pr_number = int(pr_match)

                    # Only include PRs we're looking for
                    if pr_number in pr_numbers and pr_number not in pr_to_sha:
                        pr_to_sha[pr_number] = sha[:8]  # 8-digit SHA
                        pr_chronological_order.append(pr_number)

            return pr_to_sha, pr_chronological_order

        except GitError as e:
            self.console.print(f"[yellow]Warning: Failed to parse git log: {e}[/yellow]")
            return {}, []

    def get_release_branches(self) -> List[str]:
        """Get all release branches from git repository."""
        try:
            # Get remote branches that look like version numbers
            branches_output = self.run_command(["branch", "-r", "--format=%(refname:short)"])

            release_branches = []
            for branch in branches_output.split("\n"):
                if branch.startswith("origin/"):
                    branch_name = branch.replace("origin/", "")
                    # Check if it looks like a version (e.g., "4.0", "4.1", "5.0")
                    parts = branch_name.split(".")
                    if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                        release_branches.append(branch_name)

            return release_branches

        except GitError:
            return []

    def get_tags_for_overview(self) -> List[str]:
        """Get list of minor versions by scanning git tags."""
        try:
            # Get all tags that match version pattern
            tags_output = self.run_command(["tag", "--list"])
            if not tags_output:
                return []

            tags = tags_output.split("\n")

            # Extract minor versions from tags (e.g., "6.0.0rc1" -> "6.0", "4.1.2" -> "4.1")
            minor_versions = set()
            version_pattern = re.compile(r"^(\d+\.\d+)\..*")

            for tag in tags:
                match = version_pattern.match(tag.strip())
                if match:
                    minor_version = match.group(1)
                    minor_versions.add(minor_version)

            return list(minor_versions)

        except GitError:
            return []

    def get_commits_in_range(self, start_sha: str, end_sha: str) -> List[Commit]:
        """Get commits between two SHAs."""
        try:
            # Get commits in range start_sha..end_sha
            log_output = self.run_command(
                ["log", f"{start_sha}..{end_sha}", "--format=%h|%s|%an|%ci"]
            )

            commits = []
            for line in log_output.split("\n"):
                if not line.strip():
                    continue

                parts = line.split("|", 3)
                if len(parts) >= 4:
                    sha, message, author, date = parts

                    # Extract PR number from commit message
                    pr_match = re.search(r"#(\d+)", message)
                    pr_number = int(pr_match.group(1)) if pr_match else None

                    commits.append(
                        Commit(
                            sha=sha, message=message, author=author, date=date, pr_number=pr_number
                        )
                    )

            return commits

        except GitError:
            return []

    # Conflict Analysis Operations
    def analyze_cherry_pick_conflicts(self, target_branch: str, commit_sha: str) -> Dict[str, Any]:
        """Analyze potential conflicts from cherry-picking a commit to target branch using GitPython."""
        try:
            from git import Repo

            # Use GitPython for structured access
            repo = Repo(self.repo_path)

            # Get commit objects
            target_commit = repo.commit(target_branch)
            cherry_commit = repo.commit(commit_sha)

            # Get commit details
            commit_info = {
                "commit_sha": commit_sha[:8],
                "full_commit_sha": cherry_commit.hexsha,
                "commit_message": cherry_commit.message.strip(),
                "commit_author": str(cherry_commit.author),
                "commit_date": cherry_commit.committed_datetime.isoformat(),
                "target_branch": target_branch,
            }

            # Use diff to analyze what files will be affected
            # Compare the commit against its parent to see what changed
            if len(cherry_commit.parents) > 0:
                parent_commit = cherry_commit.parents[0]

                # Get the changes this commit makes
                commit_diff = parent_commit.diff(cherry_commit)

                # Now check each changed file against the target branch
                conflicts = []

                for diff_item in commit_diff:
                    file_path = diff_item.a_path or diff_item.b_path
                    if not file_path:
                        continue

                    # Check if this file exists and is different in target branch
                    try:
                        # Get the file content at parent, commit, and target
                        conflict_info = self._analyze_file_conflict(
                            repo, parent_commit, cherry_commit, target_commit, file_path
                        )

                        if conflict_info:
                            # Add blame information for the conflicted file
                            blame_info = self._get_file_blame_info(repo, target_commit, file_path)
                            if blame_info:
                                conflict_info["blame_commits"] = blame_info
                            conflicts.append(conflict_info)

                    except Exception as e:
                        # File might not exist in target or parent - potential conflict
                        conflicts.append(
                            {
                                "file": file_path,
                                "type": "file_change_conflict",
                                "conflicted_lines": 1,
                                "conflict_regions": [
                                    {"start_line": 1, "line_count": 1, "end_line": 1}
                                ],
                                "region_count": 1,
                                "description": f"File modification conflict: {str(e)[:50]}",
                            }
                        )
            else:
                # Root commit - shouldn't happen in practice
                conflicts = [
                    {
                        "file": "unknown",
                        "type": "root_commit",
                        "conflicted_lines": 1,
                        "conflict_regions": [{"start_line": 1, "line_count": 1, "end_line": 1}],
                        "region_count": 1,
                        "description": "Root commit analysis not supported",
                    }
                ]

            result = commit_info.copy()
            result.update(
                {
                    "has_conflicts": len(conflicts) > 0,
                    "conflict_count": len(conflicts),
                    "conflicts": conflicts,
                    "complexity": self._assess_conflict_complexity(conflicts),
                }
            )

            return result

        except Exception as e:
            return {
                "commit_sha": commit_sha[:8],
                "target_branch": target_branch,
                "error": str(e),
                "has_conflicts": None,
                "conflict_count": 0,
                "conflicts": [],
                "complexity": "error",
            }

    def _analyze_file_conflict(self, repo, parent_commit, cherry_commit, target_commit, file_path):
        """Analyze if a specific file will have conflicts when cherry-picked."""
        try:
            # Get file content at different points
            parent_blob = None
            cherry_blob = None
            target_blob = None

            try:
                parent_blob = parent_commit.tree[file_path]
            except KeyError:
                pass  # File didn't exist in parent

            try:
                cherry_blob = cherry_commit.tree[file_path]
            except KeyError:
                pass  # File doesn't exist in cherry commit (deleted)

            try:
                target_blob = target_commit.tree[file_path]
            except KeyError:
                pass  # File doesn't exist in target

            # Determine conflict type and estimate lines
            if parent_blob and cherry_blob and target_blob:
                # All three versions exist - check for content conflicts
                parent_content = parent_blob.data_stream.read().decode("utf-8", errors="ignore")
                cherry_content = cherry_blob.data_stream.read().decode("utf-8", errors="ignore")
                target_content = target_blob.data_stream.read().decode("utf-8", errors="ignore")

                # Simple heuristic: if target differs from parent AND cherry differs from parent
                # in potentially overlapping ways, there might be conflicts
                if target_content != parent_content and cherry_content != parent_content:
                    # Estimate conflict lines by comparing line counts
                    parent_lines = len(parent_content.splitlines())
                    cherry_lines = len(cherry_content.splitlines())
                    target_lines = len(target_content.splitlines())

                    # Rough estimate of affected lines
                    max_change = max(
                        abs(cherry_lines - parent_lines), abs(target_lines - parent_lines)
                    )
                    estimated_conflict_lines = min(
                        max_change, max(cherry_lines, target_lines) // 10
                    )

                    if estimated_conflict_lines == 0:
                        estimated_conflict_lines = 1

                    return {
                        "file": file_path,
                        "type": "content_conflict",
                        "conflicted_lines": estimated_conflict_lines,
                        "conflict_regions": [
                            {
                                "start_line": 1,
                                "line_count": estimated_conflict_lines,
                                "end_line": estimated_conflict_lines,
                            }
                        ],
                        "region_count": 1,
                        "description": f"Estimated {estimated_conflict_lines} conflicting lines",
                    }

            elif cherry_blob and target_blob and not parent_blob:
                # File was added in both branches - likely conflict
                return {
                    "file": file_path,
                    "type": "add_add_conflict",
                    "conflicted_lines": len(
                        cherry_blob.data_stream.read().decode("utf-8", errors="ignore").splitlines()
                    ),
                    "conflict_regions": [{"start_line": 1, "line_count": 10, "end_line": 10}],
                    "region_count": 1,
                    "description": "File added in both branches",
                }

            elif not cherry_blob and target_blob:
                # File deleted in cherry but exists in target
                return {
                    "file": file_path,
                    "type": "delete_modify_conflict",
                    "conflicted_lines": 1,
                    "conflict_regions": [{"start_line": 1, "line_count": 1, "end_line": 1}],
                    "region_count": 1,
                    "description": "File deleted in cherry but modified in target",
                }

            # No conflict detected
            return None

        except Exception:
            # Error analyzing file - assume potential conflict
            return {
                "file": file_path,
                "type": "analysis_error",
                "conflicted_lines": 1,
                "conflict_regions": [{"start_line": 1, "line_count": 1, "end_line": 1}],
                "region_count": 1,
                "description": "Unable to analyze file",
            }

    def _get_file_blame_info(self, repo, target_commit, file_path, max_commits=3):
        """Get blame information showing recent commits that modified this file."""
        try:
            # Get recent commits that modified this file (last 10 commits, return top 3)
            commits_touching_file = list(
                repo.iter_commits(rev=target_commit, paths=file_path, max_count=10)
            )

            blame_commits = []
            seen_shas = set()

            for commit in commits_touching_file:
                if len(blame_commits) >= max_commits:
                    break

                # Avoid duplicates
                short_sha = commit.hexsha[:8]
                if short_sha in seen_shas:
                    continue

                seen_shas.add(short_sha)

                # Extract PR number from commit message if present
                import re

                pr_match = re.search(r"#(\d+)", commit.message)
                pr_number = pr_match.group(1) if pr_match else None

                blame_commits.append(
                    {
                        "sha": short_sha,
                        "message": commit.message.split("\n")[0],  # First line, full message
                        "author": str(commit.author.name),
                        "date": commit.committed_datetime.strftime("%Y-%m-%d"),
                        "pr_number": pr_number,
                    }
                )

            return blame_commits if blame_commits else None

        except Exception:
            return None

    def get_cherry_pick_diff(self, commit_sha: str) -> str:
        """Get the raw diff that would be applied by cherry-picking this commit."""
        try:
            # Show what this commit changed
            diff_output = self.run_command(
                [
                    "show",
                    commit_sha,
                    "--format=fuller",  # Show more commit details
                    "--stat",  # Show file change stats
                    "--color=always",  # Preserve colors if terminal supports it
                ]
            )
            return diff_output
        except GitError as e:
            return f"Error getting diff: {e}"

    def _assess_conflict_complexity(self, conflicts: List[Dict[str, Any]]) -> str:
        """Assess the complexity of conflicts."""
        if not conflicts:
            return "clean"

        total_files = len(conflicts)
        total_lines = sum(c.get("conflicted_lines", 0) for c in conflicts)

        # Simple heuristics for complexity assessment
        if total_files <= 2 and total_lines <= 10:
            return "simple"
        elif total_files <= 5 and total_lines <= 50:
            return "moderate"
        else:
            return "complex"

    # Cherry-pick Operations
    def execute_cherry_pick(self, commit_sha: str) -> Dict[str, Any]:
        """Execute git cherry-pick and return result status."""
        try:
            # Attempt cherry-pick
            result = self.run_command(["cherry-pick", commit_sha])

            return {
                "success": True,
                "commit_sha": commit_sha[:8],
                "message": "Cherry-pick completed successfully",
                "output": result,
            }

        except GitError as e:
            # Check if this was a conflict vs other error
            error_msg = str(e)

            if "conflict" in error_msg.lower() or "merge conflict" in error_msg.lower():
                # Get conflicted files
                try:
                    status_output = self.run_command(["status", "--porcelain"])
                    conflicted_files = []
                    for line in status_output.split("\n"):
                        if (
                            line.startswith("UU ")
                            or line.startswith("AA ")
                            or line.startswith("DD ")
                        ):
                            conflicted_files.append(line[3:].strip())

                    return {
                        "success": False,
                        "commit_sha": commit_sha[:8],
                        "conflict": True,
                        "conflicted_files": conflicted_files,
                        "message": f"Cherry-pick failed with conflicts in {len(conflicted_files)} files",
                        "error": error_msg,
                    }
                except GitError:
                    return {
                        "success": False,
                        "commit_sha": commit_sha[:8],
                        "conflict": True,
                        "conflicted_files": [],
                        "message": "Cherry-pick failed with conflicts",
                        "error": error_msg,
                    }
            else:
                return {
                    "success": False,
                    "commit_sha": commit_sha[:8],
                    "conflict": False,
                    "message": f"Cherry-pick failed: {error_msg}",
                    "error": error_msg,
                }

    def abort_cherry_pick(self) -> bool:
        """Abort current cherry-pick operation."""
        try:
            self.run_command(["cherry-pick", "--abort"])
            return True
        except GitError:
            return False

    def get_cherry_pick_status(self) -> Dict[str, Any]:
        """Check if we're in the middle of a cherry-pick operation."""
        try:
            # Check if .git/CHERRY_PICK_HEAD exists
            cherry_pick_head = self.repo_path / ".git" / "CHERRY_PICK_HEAD"
            if cherry_pick_head.exists():
                # Get conflicted files
                status_output = self.run_command(["status", "--porcelain"])
                conflicted_files = []
                staged_files = []

                for line in status_output.split("\n"):
                    if not line.strip():
                        continue
                    if line.startswith("UU ") or line.startswith("AA ") or line.startswith("DD "):
                        conflicted_files.append(line[3:].strip())
                    elif line.startswith("A  ") or line.startswith("M  "):
                        staged_files.append(line[3:].strip())

                return {
                    "in_progress": True,
                    "conflicted_files": conflicted_files,
                    "staged_files": staged_files,
                    "can_continue": len(conflicted_files) == 0,
                }
            else:
                return {
                    "in_progress": False,
                    "conflicted_files": [],
                    "staged_files": [],
                    "can_continue": False,
                }
        except GitError:
            return {
                "in_progress": False,
                "conflicted_files": [],
                "staged_files": [],
                "can_continue": False,
            }

    def get_current_branch(self) -> str:
        """Get the name of the currently checked out branch."""
        try:
            return self.run_command(["branch", "--show-current"])
        except GitError:
            return ""

    def verify_pr_sha_exists(self, sha: str) -> bool:
        """Verify that a specific SHA exists in the git repository."""
        try:
            self.run_command(["rev-parse", "--verify", f"{sha}^{{commit}}"])
            return True
        except GitError:
            return False

    def get_actual_pr_sha(self, pr_number: int, branch: str = "master") -> Optional[str]:
        """Get the actual SHA for a PR number by searching git log."""
        try:
            # Search for commit messages containing this PR number
            log_output = self.run_command(
                [
                    "log",
                    branch,
                    "--oneline",
                    "--format=%h|%s",
                    f"--grep=#{pr_number}",
                    "--extended-regexp",
                ]
            )

            for line in log_output.split("\n"):
                if not line.strip():
                    continue

                parts = line.split("|", 1)
                if len(parts) != 2:
                    continue

                sha, message = parts

                # Check if this line contains our PR number
                import re

                pr_matches = re.findall(r"#(\d+)", message)
                if str(pr_number) in pr_matches:
                    return sha[:8]  # Return 8-digit SHA

            return None

        except GitError:
            return None
