"""Bulk conflict analysis functions for ct analyze command."""

import json
from typing import Any, Dict, List

from rich.console import Console


def _display_bulk_table_output(
    analyses: List[Dict[str, Any]], minor_version: str, console: Console
) -> None:
    """Display bulk conflict analysis in table format matching IDEAS.md specification."""

    # Count PRs by complexity
    complexity_counts = {"clean": 0, "simple": 0, "moderate": 0, "complex": 0}
    for analysis in analyses:
        complexity = analysis.get("complexity", "error")
        if complexity in complexity_counts:
            complexity_counts[complexity] += 1

    # Show summary header
    total_prs = len(analyses)
    console.print()
    console.print(f"[bold cyan]Cherry-Pick Analysis: {minor_version}[/bold cyan]")
    console.print(
        f"Total PRs: {total_prs} | Clean: {complexity_counts['clean']} | "
        + f"Simple: {complexity_counts['simple']} | "
        + f"Moderate: {complexity_counts['moderate']} | "
        + f"Complex: {complexity_counts['complex']}"
    )
    console.print()

    # Use unified table creation with conflict analysis columns
    from .tables import create_pr_table

    table = create_pr_table(analyses, "", include_conflicts=True)

    # Table creation and population is now handled by the unified create_pr_table function

    console.print(table)


def _display_bulk_json_output(analyses: List[Dict[str, Any]], minor_version: str) -> None:
    """Display bulk conflict analysis in JSON format."""
    # Count PRs by complexity
    complexity_counts = {"clean": 0, "simple": 0, "moderate": 0, "complex": 0}
    for analysis in analyses:
        complexity = analysis.get("complexity", "error")
        if complexity in complexity_counts:
            complexity_counts[complexity] += 1

    output = {
        "minor_version": minor_version,
        "total_prs": len(analyses),
        "complexity_summary": complexity_counts,
        "analyses": analyses,
    }
    print(json.dumps(output, indent=2))
