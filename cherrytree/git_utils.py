"""Git utility functions."""

import subprocess
from pathlib import Path


class GitError(Exception):
    """Git operation failed."""

    pass


def run_git_command(args: list, repo_path: Path) -> str:
    """Execute git command and return stdout."""
    try:
        result = subprocess.run(
            ["git"] + args, cwd=repo_path, capture_output=True, text=True, check=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        raise GitError(f"Git command failed: git {' '.join(args)}\nError: {e.stderr}")
