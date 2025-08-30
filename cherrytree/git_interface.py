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

    def run_command_binary_safe(self, args: List[str], allow_failure: bool = False) -> str:
        """Execute git command and return stdout, safely handling binary content."""
        try:
            result = subprocess.run(
                ["git"] + args, cwd=self.repo_path, capture_output=True, check=not allow_failure
            )

            # For merge-tree, exit code 1 means conflicts exist (not an error)
            if allow_failure and result.returncode == 1 and args[0] == "merge-tree":
                # This is expected for merge-tree with conflicts
                pass
            elif allow_failure and result.returncode != 0:
                # Other non-zero exit codes are real errors
                try:
                    stderr = result.stderr.decode("utf-8") if result.stderr else ""
                except UnicodeDecodeError:
                    stderr = str(result.stderr) if result.stderr else ""
                raise GitError(f"Git command failed: git {' '.join(args)}\nError: {stderr}")

            # Try UTF-8 decode first
            try:
                return result.stdout.decode("utf-8").strip()
            except UnicodeDecodeError:
                # Handle binary content by using errors='replace' or 'ignore'
                decoded = result.stdout.decode("utf-8", errors="replace").strip()
                # For merge-tree output with binary files, we can still parse the textual parts
                return decoded

        except subprocess.CalledProcessError as e:
            # Try to decode stderr for error message
            try:
                stderr = e.stderr.decode("utf-8") if e.stderr else ""
            except UnicodeDecodeError:
                stderr = str(e.stderr) if e.stderr else ""
            raise GitError(f"Git command failed: git {' '.join(args)}\nError: {stderr}") from e

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
                # Use findall to get all PR numbers, take the last one (handles reverts)
                pr_matches = re.findall(r"#(\d+)", message)
                pr_number = int(pr_matches[-1]) if pr_matches else None

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
    def build_pr_sha_mapping(
        self, pr_numbers: List[int]
    ) -> Tuple[Dict[int, str], List[int], Dict[int, str]]:
        """Build mapping of PR number → merge commit SHA by parsing git log."""
        try:
            # Get commits from master branch that mention PR numbers
            # Use --reverse to get oldest commits first (better for dependency order)
            log_output = self.run_command(
                [
                    "log",
                    "master",
                    "--oneline",
                    "--format=%h|%s|%ci",  # Add commit date
                    "--grep=#[0-9]",
                    "--extended-regexp",
                    "--reverse",  # Oldest commits first for proper dependency order
                ]
            )

            pr_to_sha = {}
            pr_to_date = {}  # Add date mapping
            pr_chronological_order = []

            for line in log_output.split("\n"):
                if not line.strip():
                    continue

                parts = line.split("|", 2)
                if len(parts) != 3:
                    continue

                sha, message, date = parts

                # Extract all PR numbers from commit message
                pr_matches = re.findall(r"#(\d+)", message)
                for pr_match in pr_matches:
                    pr_number = int(pr_match)

                    # Only include PRs we're looking for
                    if pr_number in pr_numbers and pr_number not in pr_to_sha:
                        pr_to_sha[pr_number] = sha[:8]  # 8-digit SHA
                        pr_to_date[pr_number] = date  # Merge date
                        pr_chronological_order.append(pr_number)

            return pr_to_sha, pr_chronological_order, pr_to_date

        except GitError as e:
            self.console.print(f"[yellow]Warning: Failed to parse git log: {e}[/yellow]")
            return {}, [], {}

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
                    # Use findall to get all PR numbers, take the last one (handles reverts)
                    pr_matches = re.findall(r"#(\d+)", message)
                    pr_number = int(pr_matches[-1]) if pr_matches else None

                    commits.append(
                        Commit(
                            sha=sha, message=message, author=author, date=date, pr_number=pr_number
                        )
                    )

            return commits

        except GitError:
            return []

    # Conflict Analysis Operations
    def analyze_cherry_pick_conflicts(
        self, target_branch: str, commit_sha: str, base_sha: str = None, verbose: bool = False
    ) -> Dict[str, Any]:
        """
        Analyze potential conflicts from cherry-picking a commit to target branch using git merge-tree.

        Cherry-pick applies the diff from commit_parent→commit onto the target branch.
        To simulate this accurately, we use git merge-tree with the commit's parent as merge-base:

        git merge-tree --write-tree --merge-base=<commit_parent> <target_branch> <commit>

        This approach:
        1. Gets the commit's parent to understand what changes the commit introduces
        2. Uses merge-tree to simulate applying those specific changes to target branch
        3. Only shows conflicts in files the commit actually modifies (realistic)
        4. Avoids false conflicts from unrelated repository evolution

        Args:
            target_branch: Branch to cherry-pick into (e.g., "6.0")
            commit_sha: Commit to cherry-pick (e.g., "54af1cb2")
            base_sha: Unused - we calculate the commit's parent automatically
            verbose: Show detailed merge-tree output and commands
        """
        try:
            # Check if target branch exists first
            if not self.check_branch_exists(target_branch):
                raise GitError(f"Branch '{target_branch}' does not exist in this repository")

            # Check if commit SHA exists
            if not self.verify_pr_sha_exists(commit_sha):
                raise GitError(f"Commit '{commit_sha}' does not exist in this repository")

            # Get the commit's parent to use as merge-base for accurate cherry-pick simulation
            commit_parent = self.run_command(["rev-parse", f"{commit_sha}^"])

            if verbose and hasattr(self, "console") and self.console:
                self.console.print(f"[dim]Commit parent (merge-base): {commit_parent}[/dim]")

            # Show the exact command if verbose
            if verbose and hasattr(self, "console") and self.console:
                merge_tree_cmd = f"git merge-tree --write-tree --name-only --messages --merge-base={commit_parent} {target_branch} {commit_sha}"
                self.console.print(f"[dim cyan]Running: {merge_tree_cmd}[/dim cyan]")

            merge_tree_output = self.run_command_binary_safe(
                [
                    "merge-tree",
                    "--write-tree",
                    "--name-only",
                    "--messages",
                    f"--merge-base={commit_parent}",
                    target_branch,
                    commit_sha,
                ],
                allow_failure=True,
            )

            # Show raw merge-tree output if verbose
            if verbose and hasattr(self, "console") and self.console:
                self.console.print(
                    f"[dim yellow]Raw merge-tree output for {commit_sha}:[/dim yellow]"
                )
                if merge_tree_output.strip():
                    # Show first 50 lines to avoid overwhelming output
                    lines = merge_tree_output.split("\n")[:50]
                    for i, line in enumerate(lines):
                        self.console.print(f"[dim]{i+1:3}: {line}[/dim]")
                    if len(merge_tree_output.split("\n")) > 50:
                        remaining = len(merge_tree_output.split("\n")) - 50
                        self.console.print(f"[dim]... and {remaining} more lines[/dim]")
                else:
                    self.console.print("[dim green]No merge-tree output (clean merge)[/dim green]")
                self.console.print()

            # Parse modern merge-tree --write-tree output for conflict information
            if verbose and hasattr(self, "console") and self.console:
                self.console.print(
                    f"[dim]merge_tree_output length: {len(merge_tree_output)} chars[/dim]"
                )
                self.console.print(
                    f"[dim]Number of output lines: {len(merge_tree_output.split(chr(10))) if merge_tree_output else 0}[/dim]"
                )

            conflict_info = self._parse_modern_merge_tree_output(merge_tree_output)

            if verbose and hasattr(self, "console") and self.console:
                self.console.print(
                    f"[dim]Parsed conflicts: {len(conflict_info.get('conflicts', []))}[/dim]"
                )
                self.console.print(
                    f"[dim]Has conflicts: {conflict_info.get('has_conflicts', False)}[/dim]"
                )

            from git import Repo

            # Use GitPython for structured access to get commit info
            repo = Repo(self.repo_path)

            # Get commit objects
            cherry_commit = repo.commit(commit_sha)

            # Get commit size (files and lines changed)
            files_changed = 0
            lines_changed = 0
            if len(cherry_commit.parents) > 0:
                parent_commit = cherry_commit.parents[0]
                commit_diff = parent_commit.diff(cherry_commit)
                files_changed = len(commit_diff)

                # Count lines changed with better binary file handling
                for diff_item in commit_diff:
                    try:
                        lines_changed += self._count_diff_lines_safely(diff_item)
                    except Exception:
                        # Skip problematic diff items
                        lines_changed += 15  # Estimate

            # Get commit details
            commit_info = {
                "commit_sha": commit_sha[:8],
                "full_commit_sha": cherry_commit.hexsha,
                "commit_message": cherry_commit.message.strip(),
                "commit_author": str(cherry_commit.author),
                "commit_date": cherry_commit.committed_datetime.isoformat(),
                "target_branch": target_branch,
                "files_changed": files_changed,
                "lines_changed": lines_changed,
            }

            # Use the conflicts from merge-tree analysis (real conflicts)
            conflicts = conflict_info.get("conflicts", [])

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

        except GitError as e:
            # Repository context error - provide helpful message
            error_msg = str(e)
            if "does not exist in this repository" in error_msg:
                if hasattr(self, "console") and self.console:
                    self.console.print(
                        "[yellow]⚠️  Conflict analysis requires running in the target repository[/yellow]"
                    )
                    if verbose:
                        self.console.print(
                            f"[dim red]Git error for {commit_sha}: {error_msg}[/dim red]"
                        )
                        self.console.print(f"[dim]Current repo: {self.repo_path}[/dim]")

            return {
                "commit_sha": commit_sha[:8],
                "target_branch": target_branch,
                "error": error_msg,
                "has_conflicts": None,
                "conflict_count": 0,
                "conflicts": [],
                "complexity": "repo_error",
                "files_changed": 0,
                "lines_changed": 0,
            }
        except Exception as e:
            # Other unexpected errors
            if hasattr(self, "console") and self.console:
                self.console.print(
                    f"[dim red]Debug: Conflict analysis failed for {commit_sha}: {str(e)}[/dim red]"
                )

            return {
                "commit_sha": commit_sha[:8],
                "target_branch": target_branch,
                "error": str(e),
                "has_conflicts": None,
                "conflict_count": 0,
                "conflicts": [],
                "complexity": "error",
                "files_changed": 0,
                "lines_changed": 0,
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

    def _count_diff_lines_safely(self, diff_item) -> int:
        """Safely count lines changed in a diff item, handling binary files."""
        try:
            if diff_item.a_blob and diff_item.b_blob:
                # Modified file - count difference
                a_data = diff_item.a_blob.data_stream.read()
                b_data = diff_item.b_blob.data_stream.read()

                # Check for binary content
                if b"\x00" in a_data[:1024] or b"\x00" in b_data[:1024]:
                    return 50  # Binary file estimate

                try:
                    a_text = a_data.decode("utf-8")
                    b_text = b_data.decode("utf-8")
                    return abs(b_text.count("\n") - a_text.count("\n"))
                except UnicodeDecodeError:
                    return 25  # Binary file fallback

            elif diff_item.new_file or diff_item.deleted_file:
                # New or deleted file
                blob = diff_item.b_blob or diff_item.a_blob
                if blob:
                    data = blob.data_stream.read()
                    if b"\x00" in data[:1024]:
                        return 40  # Binary file
                    try:
                        text = data.decode("utf-8")
                        return text.count("\n")
                    except UnicodeDecodeError:
                        return 30  # Binary file

            return 5  # Unknown case

        except Exception:
            return 10  # Safe fallback

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
        """Execute git cherry-pick with -x flag and return result status."""
        try:
            # Attempt cherry-pick with -x to record original commit
            result = self.run_command(["cherry-pick", "-x", commit_sha])

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

    def get_branch_head(self, branch: str) -> str:
        """Get the current HEAD SHA of a specific branch."""
        try:
            return self.run_command(["rev-parse", branch])
        except GitError as e:
            raise GitError(f"Failed to get HEAD for branch {branch}: {e}") from e

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

    def _parse_modern_merge_tree_output(self, merge_tree_output: str) -> Dict[str, Any]:
        """Parse modern git merge-tree --write-tree output to extract conflict information."""
        if not merge_tree_output.strip():
            return {"conflicts": [], "has_conflicts": False}

        lines = merge_tree_output.strip().split("\n")
        if not lines:
            return {"conflicts": [], "has_conflicts": False}

        # First line is the tree OID (or tree OID + status info)
        # tree_line = lines[0]  # Unused variable

        # Check if there are conflicts by looking at the output structure
        # Clean merge: just one line with tree OID
        # Conflicted merge: tree OID + conflicted files + messages

        conflicts = []
        conflicted_files = []
        informational_messages = []

        # Parse the sections
        current_section = "tree"
        for i, line in enumerate(lines):
            if i == 0:
                continue  # Skip tree OID line

            if not line.strip():
                # Empty line separates sections
                current_section = "messages"
                continue

            if current_section == "tree" or current_section == "files":
                # This section contains conflicted file names (due to --name-only)
                if line.strip():
                    conflicted_files.append(line.strip())
                    current_section = "files"
            elif current_section == "messages":
                # Informational messages about conflicts
                informational_messages.append(line)

        # Build conflict structures from conflicted files
        for file_path in conflicted_files:
            conflicts.append(
                {
                    "file": file_path,
                    "type": "merge_conflict",
                    "conflicted_lines": 1,  # We don't have line counts with --name-only
                    "region_count": 1,
                    "conflict_regions": [{"start_line": 1, "line_count": 1, "end_line": 1}],
                    "description": f"Conflict in {file_path}",
                    # Note: We'd need additional git blame calls to get recent commits
                    "blame_commits": [],
                }
            )

        return {
            "conflicts": conflicts,
            "has_conflicts": len(conflicts) > 0,
            "informational_messages": informational_messages,
        }

    def _parse_merge_tree_output(self, merge_tree_output: str) -> Dict[str, Any]:
        """Parse git merge-tree output to extract conflict information."""
        if not merge_tree_output.strip():
            # No conflicts detected
            return {"conflicts": [], "has_conflicts": False}

        conflicts = []
        conflict_files = {}

        # Split output into lines and process
        lines = merge_tree_output.split("\n")
        current_file = None
        conflict_lines = 0

        for line in lines:
            # Look for conflict markers and file headers
            if (
                line.startswith("<<<<<<<")
                or line.startswith("=======")
                or line.startswith(">>>>>>>")
            ):
                conflict_lines += 1
            elif line.startswith("@@"):
                # Hunk header - indicates a conflict region
                if current_file:
                    if current_file not in conflict_files:
                        conflict_files[current_file] = {"lines": 0, "regions": 0}
                    conflict_files[current_file]["regions"] += 1
            elif line.startswith("+++") or line.startswith("---"):
                # File header
                if line.startswith("+++"):
                    # Extract filename from +++ b/filename
                    parts = line.split("\t")[0].split(" ")
                    if len(parts) > 1 and parts[1].startswith("b/"):
                        current_file = parts[1][2:]  # Remove 'b/' prefix
            elif current_file and (line.startswith("+") or line.startswith("-")):
                # Count actual conflict lines
                if current_file not in conflict_files:
                    conflict_files[current_file] = {"lines": 0, "regions": 0}
                conflict_files[current_file]["lines"] += 1

        # Convert to conflict structure
        for file_path, info in conflict_files.items():
            conflicts.append(
                {
                    "file": file_path,
                    "type": "merge_conflict",
                    "conflicted_lines": info["lines"],
                    "region_count": max(1, info["regions"]),
                    "conflict_regions": [
                        {"start_line": 1, "line_count": info["lines"], "end_line": info["lines"]}
                    ],
                    "description": f"Merge conflict in {file_path}",
                }
            )

        return {"conflicts": conflicts, "has_conflicts": len(conflicts) > 0}
