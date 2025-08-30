"""Sync validation utilities for cherrytree operations."""

from typing import Optional

import typer
from rich.console import Console

from .minor import Minor


def check_sync_and_offer_resync(minor_version: str, console: Optional[Console] = None) -> bool:
    """
    Check if sync is current and offer to re-sync if not.

    Returns:
        True if sync is current or user chose to continue
        False if operation should be cancelled
    """
    if console is None:
        console = Console()

    minor = Minor.from_yaml(minor_version)
    if not minor:
        console.print(f"[red]No sync data found for {minor_version}[/red]")
        console.print(f"[yellow]Run 'ct sync {minor_version}' first[/yellow]")
        return False

    # Simple check - is HEAD in sync?
    if minor.is_head_in_sync():
        return True  # All good

    # Not in sync - warn and offer options
    console.print(f"[yellow]⚠️  Branch {minor_version} has moved since last sync[/yellow]")

    if typer.confirm("Sync now?", default=True):
        # Actually perform the sync
        try:
            from .sync import sync_command

            console.print(f"[cyan]Syncing {minor_version}...[/cyan]")
            sync_command(minor_version, "apache/superset", "releases", False)
            console.print(f"[green]✓ Sync completed for {minor_version}[/green]")
            return True  # Sync successful, continue with operation
        except Exception as e:
            console.print(f"[red]Sync failed: {str(e)}[/red]")
            console.print(f"[yellow]Run manually: ct sync {minor_version}[/yellow]")
            return False  # Sync failed, cancel operation
    else:
        console.print("[yellow]⚠️  Continuing with potentially stale data[/yellow]")
        return True
