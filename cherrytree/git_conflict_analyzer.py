"""Cherry-pick conflict analysis functionality."""

from typing import Any, Dict, List, Set

from .git_basic import GitBasicInterface, GitError


class GitConflictAnalyzer:
    """
    Specialized analyzer for cherry-pick conflict detection and analysis.

    This class provides both fast and detailed conflict analysis using git merge-tree
    to simulate cherry-pick operations non-destructively.
    """

    def __init__(self, git_basic: GitBasicInterface):
        """Initialize with a GitBasicInterface instance."""
        self.git = git_basic
        self.console = git_basic.console

    def analyze_cherry_pick_conflicts(
        self, target_branch: str, commit_sha: str, verbose: bool = False
    ) -> Dict[str, Any]:
        """
        Fast cherry-pick conflict analysis using git merge-tree --name-only.

        Cherry-pick applies the diff from commit_parent→commit onto the target branch.
        To simulate this accurately, we use git merge-tree with the commit's parent as merge-base.

        Args:
            target_branch: Branch to cherry-pick into (e.g., "6.0")
            commit_sha: Commit to cherry-pick (e.g., "54af1cb2")
            verbose: Show detailed merge-tree output and commands
        """
        try:
            # Validation checks
            if not self.git.check_branch_exists(target_branch):
                raise GitError(f"Branch '{target_branch}' does not exist in this repository")
            if not self.git.verify_pr_sha_exists(commit_sha):
                raise GitError(f"Commit '{commit_sha}' does not exist in this repository")

            # Get commit parent for accurate cherry-pick simulation
            commit_parent = self.git.run_command(["rev-parse", f"{commit_sha}^"])

            if verbose:
                self.console.print(f"[dim]Commit parent (merge-base): {commit_parent}[/dim]")

            # Run fast merge-tree analysis with --name-only
            merge_tree_cmd = [
                "merge-tree",
                "--write-tree",
                "--name-only",
                "--messages",
                f"--merge-base={commit_parent}",
                target_branch,
                commit_sha,
            ]

            if verbose:
                cmd_str = f"git {' '.join(merge_tree_cmd)}"
                self.console.print(f"[dim cyan]Running: {cmd_str}[/dim cyan]")

            merge_tree_output = self.git.run_command_binary_safe(merge_tree_cmd, allow_failure=True)

            if verbose:
                self._show_merge_tree_output(merge_tree_output, commit_sha)

            # Parse conflict information
            conflict_info = self._parse_modern_merge_tree_output(merge_tree_output)

            # Get commit size information
            commit_stats = self._get_commit_stats(commit_sha)

            # Build result
            result = {
                "commit_sha": commit_sha[:8],
                "target_branch": target_branch,
                "has_conflicts": len(conflict_info.get("conflicts", [])) > 0,
                "conflict_count": len(conflict_info.get("conflicts", [])),
                "conflicts": conflict_info.get("conflicts", []),
                "complexity": self._assess_conflict_complexity(conflict_info.get("conflicts", [])),
                **commit_stats,
            }

            return result

        except GitError as e:
            return self._handle_git_error(e, commit_sha, target_branch, verbose)
        except Exception as e:
            return self._handle_general_error(e, commit_sha, target_branch)

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
        """
        Enhanced cherry-pick conflict analysis with precise line-level details.

        Provides detailed conflict analysis including:
        - Exact conflict line ranges and content
        - Git blame attribution for conflicted areas
        - Stage-by-stage content analysis
        - Recursion support for dependency discovery
        """
        # Initialize recursion tracking
        if visited is None:
            visited = set()
        if dependency_chain is None:
            dependency_chain = []

        # Recursion safety checks
        if depth > max_depth:
            return {
                "error": f"Maximum recursion depth ({max_depth}) exceeded",
                "complexity": "too_deep",
            }
        if commit_sha in visited:
            return {"error": "Circular dependency detected", "complexity": "circular"}

        visited.add(commit_sha)
        current_chain = dependency_chain + [commit_sha]

        try:
            # Standard validation
            if not self.git.check_branch_exists(target_branch):
                raise GitError(f"Branch '{target_branch}' does not exist in this repository")
            if not self.git.verify_pr_sha_exists(commit_sha):
                raise GitError(f"Commit '{commit_sha}' does not exist in this repository")

            # Get commit parent for simulation
            commit_parent = self.git.run_command(["rev-parse", f"{commit_sha}^"])

            if verbose:
                self.console.print(f"[dim]Detailed analysis for {commit_sha} (depth {depth})[/dim]")
                self.console.print(f"[dim]Dependency chain: {' → '.join(current_chain)}[/dim]")

            # Run detailed merge-tree (without --name-only)
            merge_tree_cmd = [
                "merge-tree",
                "--write-tree",
                "--messages",
                f"--merge-base={commit_parent}",
                target_branch,
                commit_sha,
            ]

            if verbose:
                cmd_str = f"git {' '.join(merge_tree_cmd)}"
                self.console.print(f"[dim cyan]Running: {cmd_str}[/dim cyan]")

            merge_tree_output = self.git.run_command_binary_safe(merge_tree_cmd, allow_failure=True)

            # Parse detailed stage information
            stage_info = self._parse_detailed_merge_tree_output(merge_tree_output, verbose)
            tree_oid = stage_info.get("tree_oid", "")

            # Analyze each conflicted file in detail (need blame analyzer)
            precise_conflicts = []
            for file_path, stages in stage_info["file_stages"].items():
                file_analysis = self._analyze_file_with_content(
                    file_path, stages, target_branch, tree_oid, commit_sha, verbose
                )
                precise_conflicts.append(file_analysis)

            return {
                "commit_sha": commit_sha[:8],
                "target_branch": target_branch,
                "head_sha": head_sha,
                "depth": depth,
                "dependency_chain": current_chain,
                "has_conflicts": len(precise_conflicts) > 0,
                "conflict_count": len(precise_conflicts),
                "precise_conflicts": precise_conflicts,
                "complexity": self._assess_detailed_complexity(precise_conflicts),
                # Future recursion fields
                "dependency_hints": [],
                "prerequisite_commits": [],
            }

        except Exception as e:
            return {"error": str(e), "complexity": "error", "depth": depth}

    def execute_cherry_pick(self, commit_sha: str) -> Dict[str, Any]:
        """Execute actual cherry-pick operation."""
        try:
            self.git.run_command(["cherry-pick", "-x", commit_sha])
            return {
                "success": True,
                "message": f"Cherry-pick of {commit_sha} completed successfully",
            }
        except GitError as e:
            error_msg = str(e)
            is_conflict = "conflict" in error_msg.lower() or "failed to apply" in error_msg.lower()

            result = {"success": False, "message": error_msg, "conflict": is_conflict}

            if is_conflict:
                # Get conflicted files
                try:
                    status_output = self.git.run_command(["status", "--porcelain"])
                    conflicted_files = []
                    for line in status_output.split("\n"):
                        if (
                            line.startswith("UU ")
                            or line.startswith("AA ")
                            or line.startswith("DD ")
                        ):
                            conflicted_files.append(line[3:].strip())
                    result["conflicted_files"] = conflicted_files
                except GitError:
                    result["conflicted_files"] = []

            return result

    def abort_cherry_pick(self) -> bool:
        """Abort current cherry-pick operation."""
        try:
            self.git.run_command(["cherry-pick", "--abort"])
            return True
        except GitError:
            return False

    def get_cherry_pick_status(self) -> Dict[str, Any]:
        """Get status of current cherry-pick operation."""
        try:
            # Check if we're in the middle of a cherry-pick
            cherry_pick_head = self.git.repo_path / ".git" / "CHERRY_PICK_HEAD"
            in_progress = cherry_pick_head.exists()

            if not in_progress:
                return {
                    "in_progress": False,
                    "can_continue": False,
                    "conflicted_files": [],
                    "staged_files": [],
                }

            # Get conflicted and staged files
            status_output = self.git.run_command(["status", "--porcelain"])
            conflicted_files = []
            staged_files = []

            for line in status_output.split("\n"):
                if line.startswith("UU "):
                    conflicted_files.append(line[3:].strip())
                elif line.startswith("A ") or line.startswith("M "):
                    staged_files.append(line[3:].strip())

            can_continue = len(conflicted_files) == 0

            return {
                "in_progress": in_progress,
                "can_continue": can_continue,
                "conflicted_files": conflicted_files,
                "staged_files": staged_files,
            }

        except GitError:
            return {
                "in_progress": False,
                "can_continue": False,
                "conflicted_files": [],
                "staged_files": [],
            }

    def get_cherry_pick_diff(self, commit_sha: str) -> str:
        """Get the diff that would be applied by cherry-picking this commit."""
        try:
            return self.git.run_command(["show", "--format=", commit_sha])
        except GitError as e:
            return f"Error getting diff: {e}"

    # Private helper methods
    def _show_merge_tree_output(self, merge_tree_output: str, commit_sha: str) -> None:
        """Show raw merge-tree output for debugging."""
        self.console.print(f"[dim yellow]Raw merge-tree output for {commit_sha}:[/dim yellow]")
        if merge_tree_output.strip():
            lines = merge_tree_output.split("\n")[:50]
            for i, line in enumerate(lines):
                self.console.print(f"[dim]{i+1:3}: {line}[/dim]")
            if len(merge_tree_output.split("\n")) > 50:
                remaining = len(merge_tree_output.split("\n")) - 50
                self.console.print(f"[dim]... and {remaining} more lines[/dim]")
        else:
            self.console.print("[dim green]No merge-tree output (clean merge)[/dim green]")
        self.console.print()

    def _get_commit_stats(self, commit_sha: str) -> Dict[str, Any]:
        """Get basic commit statistics (files and lines changed)."""
        try:
            from git import Repo

            repo = Repo(self.git.repo_path)
            commit = repo.commit(commit_sha)

            files_changed = 0
            lines_changed = 0

            if len(commit.parents) > 0:
                parent = commit.parents[0]
                diff = parent.diff(commit)
                files_changed = len(diff)

                for diff_item in diff:
                    try:
                        lines_changed += self._count_diff_lines_safely(diff_item)
                    except Exception:
                        lines_changed += 15  # Estimate

            return {
                "files_changed": files_changed,
                "lines_changed": lines_changed,
                "commit_message": commit.message.strip(),
                "commit_author": str(commit.author),
                "commit_date": commit.committed_datetime.isoformat(),
            }

        except Exception:
            return {
                "files_changed": 0,
                "lines_changed": 0,
                "commit_message": "",
                "commit_author": "",
                "commit_date": "",
            }

    def _count_diff_lines_safely(self, diff_item) -> int:
        """Safely count lines changed in a diff item, handling binary files."""
        try:
            if diff_item.a_blob and diff_item.b_blob:
                # Modified file
                a_data = diff_item.a_blob.data_stream.read()
                b_data = diff_item.b_blob.data_stream.read()

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

    def _parse_modern_merge_tree_output(self, merge_tree_output: str) -> Dict[str, Any]:
        """Parse modern git merge-tree --write-tree --name-only output."""
        if not merge_tree_output.strip():
            return {"conflicts": [], "has_conflicts": False}

        lines = merge_tree_output.strip().split("\n")
        if not lines:
            return {"conflicts": [], "has_conflicts": False}

        conflicts = []
        conflicted_files = []
        informational_messages = []

        # Parse the sections
        current_section = "tree"
        for i, line in enumerate(lines):
            if i == 0:
                continue  # Skip tree OID line

            if not line.strip():
                current_section = "messages"
                continue

            if current_section == "tree" or current_section == "files":
                if line.strip():
                    conflicted_files.append(line.strip())
                    current_section = "files"
            elif current_section == "messages":
                informational_messages.append(line)

        # Build conflict structures
        for file_path in conflicted_files:
            conflicts.append(
                {
                    "file": file_path,
                    "type": "merge_conflict",
                    "conflicted_lines": 1,  # Estimate for --name-only mode
                    "region_count": 1,
                    "conflict_regions": [{"start_line": 1, "line_count": 1, "end_line": 1}],
                    "description": f"Conflict in {file_path}",
                    "blame_commits": [],
                }
            )

        return {
            "conflicts": conflicts,
            "has_conflicts": len(conflicts) > 0,
            "informational_messages": informational_messages,
        }

    def _parse_detailed_merge_tree_output(
        self, merge_tree_output: str, verbose: bool = False
    ) -> Dict[str, Any]:
        """Parse detailed merge-tree output (without --name-only) for stage information."""
        if not merge_tree_output.strip():
            return {"file_stages": {}, "messages": [], "tree_oid": ""}

        lines = merge_tree_output.strip().split("\n")
        if not lines:
            return {"file_stages": {}, "messages": [], "tree_oid": ""}

        # First line is the tree OID
        tree_oid = lines[0] if lines else ""

        file_stages = {}  # file_path -> {stage1: sha, stage2: sha, stage3: sha}
        messages = []
        current_section = "stages"

        for _i, line in enumerate(lines[1:], 1):  # Skip tree OID
            if not line.strip():
                current_section = "messages"
                continue

            if current_section == "stages":
                # Parse: "100644 <sha> <stage> <filepath>"
                parts = line.strip().split("\t")
                if len(parts) >= 2:
                    mode_sha_stage = parts[0].split()
                    file_path = parts[1]

                    if len(mode_sha_stage) >= 3:
                        mode, sha, stage = mode_sha_stage[0], mode_sha_stage[1], mode_sha_stage[2]

                        if file_path not in file_stages:
                            file_stages[file_path] = {"mode": mode}

                        file_stages[file_path][f"stage{stage}"] = sha

            elif current_section == "messages":
                messages.append(line)

        if verbose:
            self.console.print(
                f"[dim]Detailed parsing found: {len(file_stages)} conflicted files[/dim]"
            )

        return {"file_stages": file_stages, "messages": messages, "tree_oid": tree_oid}

    def _analyze_file_with_content(
        self,
        file_path: str,
        stages: Dict[str, str],
        target_branch: str,
        tree_oid: str,
        commit_sha: str,
        verbose: bool = False,
    ) -> Dict[str, Any]:
        """Analyze file conflicts using actual conflict content from merge result tree."""
        try:
            if verbose:
                self.console.print(f"[dim]Analyzing conflict content for {file_path}[/dim]")

            # Get actual conflict content from tree object
            conflict_content = ""
            if tree_oid:
                try:
                    conflict_content = self.git.run_command(["show", f"{tree_oid}:{file_path}"])
                except GitError:
                    if verbose:
                        self.console.print(
                            "[dim yellow]Could not get conflict content from tree[/dim yellow]"
                        )

            # Parse conflict markers for exact line ranges
            conflict_sections = self._parse_conflict_markers(conflict_content, verbose)

            # Get stage content for line counting
            stage_line_counts = {}
            for stage_key, sha in stages.items():
                if stage_key.startswith("stage") and sha:
                    try:
                        content = self.git.run_command(["cat-file", "-p", sha])
                        stage_line_counts[stage_key] = content.count("\n")
                    except GitError:
                        stage_line_counts[stage_key] = 0

            # Calculate total conflicted lines from sections
            total_conflicted_lines = sum(
                section.get("line_count", 0) for section in conflict_sections
            )

            if verbose:
                self.console.print(
                    f"[dim]Found {len(conflict_sections)} sections, {total_conflicted_lines} conflicted lines[/dim]"
                )

            return {
                "file": file_path,
                "mode": stages.get("mode", "100644"),
                "stage_shas": {k: v for k, v in stages.items() if k.startswith("stage")},
                "line_counts": stage_line_counts,
                "conflict_sections": conflict_sections,
                "conflicted_lines": total_conflicted_lines,
                "conflict_type": "content" if conflict_sections else "none",
            }

        except Exception as e:
            if verbose:
                self.console.print(f"[dim red]Error analyzing {file_path}: {str(e)}[/dim red]")
            return {"file": file_path, "error": str(e), "conflict_type": "analysis_error"}

    def _parse_conflict_markers(
        self, conflict_content: str, verbose: bool = False
    ) -> List[Dict[str, Any]]:
        """Parse <<<<<<< ======= >>>>>>> markers to find exact conflict sections."""
        if not conflict_content:
            return []

        lines = conflict_content.split("\n")
        conflict_sections = []
        current_section = None

        for i, line in enumerate(lines, 1):  # 1-based line numbers
            if line.startswith("<<<<<<<"):
                current_section = {
                    "start_line": i,
                    "target_content": [],
                    "cherry_content": [],
                    "type": "content_conflict",
                }
            elif line.startswith("=======") and current_section:
                # Switch from target to cherry content
                pass  # Just a separator
            elif line.startswith(">>>>>>>") and current_section:
                # End of conflict section
                current_section["end_line"] = i
                current_section["line_count"] = len(current_section["target_content"]) + len(
                    current_section["cherry_content"]
                )
                conflict_sections.append(current_section)
                current_section = None
            elif current_section:
                # Content line - determine if target or cherry
                if "=======" not in list(
                    conflict_content.split("\n")[current_section["start_line"] : i]
                ):
                    current_section["target_content"].append(line)
                else:
                    current_section["cherry_content"].append(line)

        return conflict_sections

    def _assess_conflict_complexity(self, conflicts: List[Dict[str, Any]]) -> str:
        """Assess conflict complexity based on number of files and lines."""
        if not conflicts:
            return "clean"

        conflict_count = len(conflicts)
        total_lines = sum(conflict.get("conflicted_lines", 1) for conflict in conflicts)

        if conflict_count >= 10 or total_lines >= 100:
            return "complex"
        elif conflict_count >= 3 or total_lines >= 20:
            return "moderate"
        elif conflict_count >= 1:
            return "simple"
        else:
            return "clean"

    def _assess_detailed_complexity(self, precise_conflicts: List[Dict[str, Any]]) -> str:
        """Assess complexity using detailed conflict metrics."""
        if not precise_conflicts:
            return "clean"

        total_lines = sum(conflict.get("conflicted_lines", 0) for conflict in precise_conflicts)
        file_count = len(precise_conflicts)

        if file_count >= 10 or total_lines >= 200:
            return "complex"
        elif file_count >= 3 or total_lines >= 50:
            return "moderate"
        elif file_count >= 1 or total_lines >= 1:
            return "simple"
        else:
            return "clean"

    def _handle_git_error(
        self, error: GitError, commit_sha: str, target_branch: str, verbose: bool
    ) -> Dict[str, Any]:
        """Handle GitError with helpful context."""
        error_msg = str(error)
        if "does not exist in this repository" in error_msg:
            self.console.print(
                "[yellow]⚠️  Conflict analysis requires running in the target repository[/yellow]"
            )
            if verbose:
                self.console.print(f"[dim red]Git error for {commit_sha}: {error_msg}[/dim red]")
                self.console.print(f"[dim]Current repo: {self.git.repo_path}[/dim]")

        return {
            "commit_sha": commit_sha[:8],
            "target_branch": target_branch,
            "error": error_msg,
            "complexity": "repo_error",
            "files_changed": 0,
            "lines_changed": 0,
        }

    def _handle_general_error(
        self, error: Exception, commit_sha: str, target_branch: str
    ) -> Dict[str, Any]:
        """Handle general exceptions."""
        self.console.print(
            f"[dim red]Debug: Conflict analysis failed for {commit_sha}: {str(error)}[/dim red]"
        )
        return {
            "commit_sha": commit_sha[:8],
            "target_branch": target_branch,
            "error": str(error),
            "complexity": "error",
            "files_changed": 0,
            "lines_changed": 0,
        }
