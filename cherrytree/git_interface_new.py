"""Refactored GitInterface using composition of specialized analyzers."""

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from rich.console import Console

from .commit import Commit
from .git_basic import GitBasicInterface, GitError
from .git_blame_analyzer import GitBlameAnalyzer
from .git_conflict_analyzer import GitConflictAnalyzer
from .micro_release import Micro


class GitInterface:
    """
    Refactored GitInterface using composition of specialized analyzers.

    This class maintains backward compatibility while delegating operations
    to focused, specialized analyzer classes for better maintainability.
    """

    def __init__(self, repo_path: Optional[Path] = None, console: Optional[Console] = None):
        """Initialize GitInterface with specialized analyzers."""
        # Core git operations
        self.git_basic = GitBasicInterface(repo_path, console)

        # Specialized analyzers
        self.conflict_analyzer = GitConflictAnalyzer(self.git_basic)
        self.blame_analyzer = GitBlameAnalyzer(self.git_basic)

        # Backward compatibility attributes
        self.repo_path = self.git_basic.repo_path
        self.console = self.git_basic.console

    # Delegate core operations to GitBasicInterface
    def run_command(self, args: List[str]) -> str:
        """Execute git command and return stdout."""
        return self.git_basic.run_command(args)

    def run_command_binary_safe(self, args: List[str], allow_failure: bool = False) -> str:
        """Execute git command safely handling binary content."""
        return self.git_basic.run_command_binary_safe(args, allow_failure)

    def check_branch_exists(self, branch: str) -> bool:
        """Check if branch exists locally."""
        return self.git_basic.check_branch_exists(branch)

    def check_remote_branch_exists(self, branch: str) -> bool:
        """Check if branch exists on origin remote."""
        return self.git_basic.check_remote_branch_exists(branch)

    def get_current_branch(self) -> str:
        """Get the name of the current branch."""
        return self.git_basic.get_current_branch()

    def get_branch_head(self, branch: str) -> str:
        """Get the HEAD SHA of specified branch."""
        return self.git_basic.get_branch_head(branch)

    def get_merge_base(self, branch: str, base_branch: str = "master") -> Tuple[str, str]:
        """Get merge-base SHA and date between branch and base_branch."""
        return self.git_basic.get_merge_base(branch, base_branch)

    def verify_pr_sha_exists(self, sha: str) -> bool:
        """Check if a commit SHA exists in the repository."""
        return self.git_basic.verify_pr_sha_exists(sha)

    def fetch_and_checkout_branch(self, branch: str) -> None:
        """Fetch latest remotes and checkout branch from origin."""
        return self.git_basic.fetch_and_checkout_branch(branch)

    def get_release_branches(self) -> List[str]:
        """Get all release branches from git repository."""
        return self.git_basic.get_release_branches()

    # Delegate conflict analysis to GitConflictAnalyzer
    def analyze_cherry_pick_conflicts(
        self, target_branch: str, commit_sha: str, base_sha: str = None, verbose: bool = False
    ) -> Dict[str, Any]:
        """Fast cherry-pick conflict analysis."""
        return self.conflict_analyzer.analyze_cherry_pick_conflicts(
            target_branch, commit_sha, verbose
        )

    def analyze_cherry_pick_conflicts_detailed(
        self,
        target_branch: str,
        commit_sha: str,
        head_sha: str,
        depth: int = 0,
        max_depth: int = 3,
        visited: Set[str] = None,
        dependency_chain: List[str] = None,
        verbose: bool = False,
    ) -> Dict[str, Any]:
        """Enhanced cherry-pick conflict analysis with detailed insights."""
        return self.conflict_analyzer.analyze_cherry_pick_conflicts_detailed(
            target_branch,
            commit_sha,
            head_sha,
            depth,
            max_depth,
            visited,
            dependency_chain,
            verbose,
        )

    def execute_cherry_pick(self, commit_sha: str) -> Dict[str, Any]:
        """Execute actual cherry-pick operation."""
        return self.conflict_analyzer.execute_cherry_pick(commit_sha)

    def abort_cherry_pick(self) -> bool:
        """Abort current cherry-pick operation."""
        return self.conflict_analyzer.abort_cherry_pick()

    def get_cherry_pick_status(self) -> Dict[str, Any]:
        """Get status of current cherry-pick operation."""
        return self.conflict_analyzer.get_cherry_pick_status()

    def get_cherry_pick_diff(self, commit_sha: str) -> str:
        """Get the diff that would be applied by cherry-picking this commit."""
        return self.conflict_analyzer.get_cherry_pick_diff(commit_sha)

    # Delegate blame analysis to GitBlameAnalyzer
    def get_blame_details(
        self, sha: str, file_path: str, line_from: int, line_to: int, verbose: bool = False
    ) -> List[Dict[str, Any]]:
        """Get git blame information for specific line range with complexity analysis."""
        return self.blame_analyzer.get_blame_details(sha, file_path, line_from, line_to, verbose)

    def analyze_sha(self, commit_sha: str, verbose: bool = False) -> Dict[str, Any]:
        """Analyze commit SHA for complexity and scope."""
        return self.blame_analyzer.analyze_sha(commit_sha, verbose)

    def get_file_contributors(
        self, sha: str, file_path: str, max_commits: int = 5, verbose: bool = False
    ) -> List[Dict[str, Any]]:
        """Get all contributors to a file with impact analysis."""
        return self.blame_analyzer.get_file_contributors(sha, file_path, max_commits, verbose)

    # Repository analysis methods (remaining in main class for now)
    def get_branch_commits(self, branch: str, base_sha: str) -> List[Commit]:
        """Get commits in branch since base_sha."""
        try:
            log_output = self.run_command(
                ["log", f"{base_sha}..{branch}", "--format=%h|%s|%an|%ci", "--reverse"]
            )

            commits = []
            for line in log_output.split("\n"):
                if not line.strip():
                    continue

                parts = line.split("|")
                if len(parts) >= 3:
                    sha, message, author, date = parts
                    # Extract PR number from commit message
                    pr_matches = re.findall(r"#(\d+)", message)
                    pr_number = int(pr_matches[-1]) if pr_matches else None

                    commits.append(Commit(sha=sha, message=message, date=date, pr_number=pr_number))

            return commits

        except GitError:
            return []

    def build_pr_sha_mapping(
        self, pr_numbers: List[int]
    ) -> Tuple[Dict[int, str], List[int], Dict[int, str]]:
        """Build mapping of PR number → merge commit SHA by parsing git log."""
        try:
            log_output = self.run_command(
                [
                    "log",
                    "master",
                    "--oneline",
                    "--format=%h|%s|%ci",
                    "--grep=#[0-9]",
                    "--extended-regexp",
                    "--reverse",
                ]
            )

            pr_to_sha = {}
            pr_to_date = {}
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

                    if pr_number in pr_numbers and pr_number not in pr_to_sha:
                        pr_to_sha[pr_number] = sha[:8]  # 8-digit SHA
                        pr_to_date[pr_number] = date
                        pr_chronological_order.append(pr_number)

            return pr_to_sha, pr_chronological_order, pr_to_date

        except GitError as e:
            self.console.print(f"[yellow]Warning: Failed to parse git log: {e}[/yellow]")
            return {}, [], {}

    def get_tags_for_overview(self) -> List[str]:
        """Get list of minor versions by scanning git tags."""
        try:
            tags_output = self.run_command(["tag", "--list"])
            if not tags_output:
                return []

            tags = tags_output.split("\n")
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

    def get_release_tags(self, minor_version: str) -> List[Micro]:
        """Get release tags for a specific minor version."""
        try:
            tags_output = self.run_command(
                ["tag", "--list", f"{minor_version}.*", "--sort=-version:refname"]
            )

            if not tags_output:
                return []

            tags = []
            for tag_name in tags_output.split("\n"):
                if not tag_name.strip():
                    continue

                try:
                    # Get tag information
                    tag_sha = self.run_command(["rev-list", "-n", "1", tag_name])[:8]
                    tag_date = self.run_command(["log", "-1", "--format=%ci", tag_name])
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
                    continue

            return tags

        except GitError:
            return []

    def get_commits_in_range(self, start_sha: str, end_sha: str) -> List[Commit]:
        """Get commits between two SHAs."""
        try:
            log_output = self.run_command(
                ["log", f"{start_sha}..{end_sha}", "--format=%h|%s|%an|%ci", "--reverse"]
            )

            commits = []
            for line in log_output.split("\n"):
                if not line.strip():
                    continue

                parts = line.split("|")
                if len(parts) >= 4:
                    sha, message, author, date = parts

                    # Extract PR number from commit message
                    pr_matches = re.findall(r"#(\d+)", message)
                    pr_number = int(pr_matches[-1]) if pr_matches else None

                    commits.append(
                        Commit(
                            sha=sha, message=message, date=date, pr_number=pr_number, author=author
                        )
                    )

            return commits

        except GitError:
            return []

    def get_actual_pr_sha(self, pr_number: int, branch: str = "master") -> Optional[str]:
        """Find the actual SHA for a PR number by searching git log."""
        try:
            log_output = self.run_command(
                ["log", branch, "--oneline", "--format=%h|%s", f"--grep=#{pr_number}"]
            )

            for line in log_output.split("\n"):
                if not line.strip():
                    continue

                parts = line.split("|", 1)
                if len(parts) == 2:
                    sha, message = parts
                    if f"#{pr_number}" in message:
                        return sha[:8]

            return None

        except GitError:
            return None
