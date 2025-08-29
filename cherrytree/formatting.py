"""Common formatting utilities for cherrytree classes."""

import re


def format_short_date(date_string: str) -> str:
    """
    Extract short date (YYYY-MM-DD) from various git date formats.

    Handles formats like:
    - "2025-08-18 14:04:26 -0700"
    - "2025-08-27 23:19:01 -0700"
    """
    if not date_string:
        return ""

    try:
        # Extract date part from formats like "2025-08-18 14:04:26 -0700"
        date_match = re.match(r"(\d{4}-\d{2}-\d{2})", date_string)
        if date_match:
            return date_match.group(1)
        return date_string[:10]  # Fallback to first 10 characters
    except Exception:
        return date_string[:10] if len(date_string) >= 10 else date_string


def format_short_sha(sha: str) -> str:
    """
    Format SHA to 8-character abbreviated format for display.

    Args:
        sha: Full or partial SHA string

    Returns:
        8-character SHA or original if shorter than 8 chars
    """
    if not sha:
        return ""
    return sha[:8] if len(sha) >= 8 else sha
