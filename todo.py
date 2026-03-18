#!/usr/bin/env python3
"""TaskTrack — Entry point + auto-installer.

Usage:
    python todo.py
"""

import importlib.util
import subprocess
import sys


# ──────────────────────────────────── auto-installer ─────────────────────────

_REQUIRED_PACKAGES = {
    "rich": "rich",
    "anthropic": "anthropic",
    "pytesseract": "pytesseract",
    "PIL": "Pillow",
    "plyer": "plyer",
    "readchar": "readchar",
}


def _ensure_package(import_name: str, pip_name: str) -> None:
    if importlib.util.find_spec(import_name) is None:
        print(f"Installing {pip_name}…")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", pip_name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def _auto_install() -> None:
    for import_name, pip_name in _REQUIRED_PACKAGES.items():
        try:
            _ensure_package(import_name, pip_name)
        except subprocess.CalledProcessError as exc:
            print(f"Warning: failed to install {pip_name}: {exc}")


# ───────────────────────────────────────────── main ──────────────────────────


def _show_welcome() -> None:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text

    console = Console()

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Key", style="bold cyan", min_width=12)
    table.add_column("Action")

    commands = [
        ("↑ / ↓  or  k / j", "Navigate tasks"),
        ("a", "Add a new task"),
        ("e", "Edit selected task"),
        ("d", "Delete selected task"),
        ("c", "Mark task complete"),
        ("s", "Import from screenshot (OCR)"),
        ("f", "Filter by class name"),
        ("v", "View completed archive"),
        ("q", "Quit"),
        ("", ""),
        ("In archive view:", ""),
        ("r", "Restore task to active list"),
        ("x", "Permanently delete"),
        ("q", "Back to task list"),
    ]
    for key, action in commands:
        table.add_row(key, action)

    console.print()
    console.print(
        Panel(
            table,
            title="[bold cyan]TaskTrack[/bold cyan]  [dim]school assignment tracker[/dim]",
            subtitle="[dim]Press any key to open your tasks…[/dim]",
            border_style="cyan",
            padding=(1, 2),
        )
    )
    # Wait for a keypress before launching the TUI
    import readchar
    readchar.readkey()


def main() -> None:
    _auto_install()

    # Imports deferred until after auto-install
    from src.storage import Storage
    from src import notifications
    from src.ui import App

    _show_welcome()

    storage = Storage()
    tasks = storage.load_tasks()
    notifications.check_on_launch(tasks)
    App(storage).run()


if __name__ == "__main__":
    main()
