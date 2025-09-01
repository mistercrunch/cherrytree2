"""Git blame and attribution analysis functionality."""

import re
from typing import Any, Dict, List

from .git_basic import GitBasicInterface, GitError


class GitBlameAnalyzer:
    """
    Specialized analyzer for git blame operations and commit attribution.

    This class provides clean, reusable methods for analyzing who last touched
    specific lines or files, with enhanced commit complexity analysis.
    """

    def __init__(self, git_basic: GitBasicInterface):
        """Initialize with a GitBasicInterface instance."""
        self.git = git_basic
        self.console = git_basic.console

    def get_blame_details(
        self, sha: str, file_path: str, line_from: int, line_to: int, verbose: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Get git blame information for specific line range with commit complexity analysis.

        Args:
            sha: Commit SHA or branch name to blame against
            file_path: File to analyze
            line_from: Start line number (1-based)
            line_to: End line number (1-based)
            verbose: Show detailed output

        Returns:
            List of commits that touched the specified line range, with complexity analysis
        """
        try:
            if verbose:
                self.console.print(
                    f"[dim]Getting blame for {file_path} lines {line_from}-{line_to}[/dim]"
                )

            # Run git blame with line range
            blame_output = self.git.run_command(
                ["blame", "--line-porcelain", f"-L{line_from},{line_to}", sha, "--", file_path]
            )

            # Parse blame output
            range_commits = self._parse_blame_porcelain(blame_output, line_from, line_to, verbose)

            # Enhance with complexity analysis
            enhanced_commits = self._enhance_commits_with_analysis(range_commits, verbose)

            return enhanced_commits

        except GitError:
            return []
        except Exception:
            return []

    def analyze_sha(self, commit_sha: str, verbose: bool = False) -> Dict[str, Any]:
        """
        Analyze a specific commit SHA to determine its complexity and scope.

        Returns information about files touched, lines changed, and commit metadata.
        Useful for dependency analysis and understanding commit impact.
        """
        try:
            if not self.git.verify_pr_sha_exists(commit_sha):
                raise GitError(f"Commit '{commit_sha}' does not exist in this repository")

            from git import Repo

            repo = Repo(self.git.repo_path)
            commit = repo.commit(commit_sha)

            if verbose:
                self.console.print(f"[dim]Analyzing commit complexity for {commit_sha}[/dim]")

            # Calculate commit diff statistics
            files_touched = 0
            lines_added = 0
            lines_removed = 0

            if len(commit.parents) > 0:
                parent = commit.parents[0]
                diff = parent.diff(commit, create_patch=True)
                files_touched = len(diff)

                # Count lines added/removed
                for diff_item in diff:
                    try:
                        lines_changed = self._count_diff_lines_safely(diff_item)
                        if diff_item.new_file:
                            lines_added += lines_changed
                        elif diff_item.deleted_file:
                            lines_removed += lines_changed
                        else:
                            # Modified file - rough estimate
                            lines_added += lines_changed // 2
                            lines_removed += lines_changed // 2
                    except Exception:
                        lines_added += 10  # Rough estimate

            total_lines_changed = lines_added + lines_removed

            # Classify complexity
            if files_touched >= 20 or total_lines_changed >= 500:
                complexity = "complex"
            elif files_touched >= 5 or total_lines_changed >= 100:
                complexity = "moderate"
            elif files_touched >= 1 or total_lines_changed >= 1:
                complexity = "simple"
            else:
                complexity = "minimal"

            # Extract PR number from commit message
            pr_matches = re.findall(r"#(\d+)", commit.message)
            pr_number = int(pr_matches[-1]) if pr_matches else None

            result = {
                "commit_sha": commit_sha[:8],
                "full_commit_sha": commit.hexsha,
                "files_touched": files_touched,
                "lines_added": lines_added,
                "lines_removed": lines_removed,
                "total_lines_changed": total_lines_changed,
                "complexity": complexity,
                "commit_info": {
                    "author": str(commit.author),
                    "date": commit.committed_datetime.isoformat(),
                    "message": commit.message.strip(),
                    "pr_number": pr_number,
                },
            }

            if verbose:
                self.console.print(
                    f"[dim]Complexity: {complexity} ({files_touched}f, {total_lines_changed}l)[/dim]"
                )

            return result

        except Exception as e:
            return {
                "commit_sha": commit_sha[:8],
                "error": str(e),
                "complexity": "error",
                "files_touched": 0,
                "total_lines_changed": 0,
            }

    def get_file_contributors(
        self, sha: str, file_path: str, max_commits: int = 5, verbose: bool = False
    ) -> List[Dict[str, Any]]:
        """Get all contributors to a file with their impact and complexity analysis."""
        try:
            # Run blame for entire file
            blame_output = self.git.run_command(["blame", "--line-porcelain", sha, "--", file_path])

            # Parse and enhance
            file_commits = self._parse_blame_porcelain(blame_output, 1, 999999, verbose)
            enhanced_commits = self._enhance_commits_with_analysis(file_commits, verbose)

            # Sort by impact and limit results
            enhanced_commits.sort(key=lambda x: x.get("lines_in_range", 0), reverse=True)
            return enhanced_commits[:max_commits]

        except GitError:
            return []
        except Exception:
            return []

    # Private helper methods
    def _parse_blame_porcelain(
        self, blame_output: str, line_from: int, line_to: int, verbose: bool = False
    ) -> Dict[str, Dict[str, Any]]:
        """Parse git blame --line-porcelain output into commit information."""
        range_commits = {}
        current_commit = None
        current_author = None
        current_date = None

        if verbose:
            lines = blame_output.split("\n")
            self.console.print(f"[dim]Parsing blame output: {len(lines)} lines[/dim]")

        for line in blame_output.split("\n"):
            # SHA line format: "ddeb6124298995f8e327e5789720d9208ff8d3da 115 115 1"
            if line and " " in line and not line.startswith("\t"):
                parts = line.split(" ")
                potential_sha = parts[0]
                # Valid git SHA is 40 hex characters
                if len(potential_sha) == 40 and all(
                    c in "0123456789abcdef" for c in potential_sha.lower()
                ):
                    current_commit = potential_sha
                    if verbose and len(range_commits) <= 3:
                        self.console.print(f"[dim]Found commit: {current_commit[:8]}[/dim]")

            elif line.startswith("author ") and current_commit:
                current_author = line[7:]  # Remove 'author ' prefix

            elif line.startswith("author-time ") and current_commit:
                # Parse unix timestamp
                try:
                    import datetime

                    timestamp = int(line[12:])
                    current_date = datetime.datetime.fromtimestamp(timestamp).isoformat()
                except (ValueError, OSError):
                    current_date = "unknown"

            elif line.startswith("\t") and current_commit:
                # Content line - add/update commit info
                if current_commit not in range_commits:
                    range_commits[current_commit] = {
                        "sha": current_commit[:8],
                        "full_sha": current_commit,
                        "author": current_author or "unknown",
                        "date": current_date or "unknown",
                        "line_range": f"{line_from}-{line_to}",
                        "lines_in_range": 0,
                    }
                    if verbose and len(range_commits) <= 3:
                        self.console.print(
                            f"[dim]Added commit {current_commit[:8]}: {current_author}[/dim]"
                        )

                range_commits[current_commit]["lines_in_range"] += 1

        if verbose:
            self.console.print(f"[dim]Final parsed commits: {len(range_commits)}[/dim]")

        return range_commits

    def _enhance_commits_with_analysis(
        self, range_commits: Dict[str, Dict[str, Any]], verbose: bool = False
    ) -> List[Dict[str, Any]]:
        """Enhance blame commits with complexity analysis using analyze_sha."""
        enhanced_commits = []

        for commit_info in range_commits.values():
            if commit_info["lines_in_range"] >= 1:  # Analyze all commits
                try:
                    # Get complexity analysis
                    sha_analysis = self.analyze_sha(commit_info["full_sha"], verbose=False)

                    # Merge blame info with complexity
                    enhanced_info = commit_info.copy()
                    enhanced_info.update(
                        {
                            "files_touched": sha_analysis.get("files_touched", 0),
                            "total_lines_changed": sha_analysis.get("total_lines_changed", 0),
                            "complexity": sha_analysis.get("complexity", "unknown"),
                            "pr_number": sha_analysis.get("commit_info", {}).get("pr_number"),
                        }
                    )
                    enhanced_commits.append(enhanced_info)

                    if verbose:
                        complexity = enhanced_info.get("complexity", "unknown")
                        files = enhanced_info.get("files_touched", 0)
                        self.console.print(
                            f"[dim]Enhanced {commit_info['sha']}: {complexity} ({files}f)[/dim]"
                        )

                except Exception as e:
                    if verbose:
                        self.console.print(
                            f"[dim red]Enhancement failed for {commit_info['sha']}: {str(e)}[/dim red]"
                        )
                    enhanced_commits.append(commit_info)
            else:
                enhanced_commits.append(commit_info)

        # Sort by impact
        enhanced_commits.sort(key=lambda x: x.get("lines_in_range", 0), reverse=True)
        return enhanced_commits

    def _count_diff_lines_safely(self, diff_item) -> int:
        """Safely count lines changed in a diff item, handling binary files."""
        try:
            if diff_item.a_blob and diff_item.b_blob:
                # Modified file
                a_data = diff_item.a_blob.data_stream.read()
                b_data = diff_item.b_blob.data_stream.read()

                if b"\x00" in a_data[:1024] or b"\x00" in b_data[:1024]:
                    return 50  # Binary file

                try:
                    a_text = a_data.decode("utf-8")
                    b_text = b_data.decode("utf-8")
                    return abs(b_text.count("\n") - a_text.count("\n"))
                except UnicodeDecodeError:
                    return 25

            elif diff_item.new_file or diff_item.deleted_file:
                # New or deleted file
                blob = diff_item.b_blob or diff_item.a_blob
                if blob:
                    data = blob.data_stream.read()
                    if b"\x00" in data[:1024]:
                        return 40
                    try:
                        text = data.decode("utf-8")
                        return text.count("\n")
                    except UnicodeDecodeError:
                        return 30

            return 5

        except Exception:
            return 10
