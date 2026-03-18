"""Two-tier notification system for TaskTrack.

Tier 1: Launch-time Rich panel (printed before TUI starts).
Tier 2: OS-level system notifications (used by scheduler.py).
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


def check_on_launch(tasks: list[dict]) -> None:
    """Print a Rich panel for tasks due within 2 days.

    Called before Live starts so it doesn't interfere with the TUI.
    """
    try:
        from rich.console import Console
        from rich.panel import Panel
        from rich.text import Text
    except ImportError:
        return

    today = date.today()
    urgent: list[dict] = []
    for task in tasks:
        try:
            due = date.fromisoformat(task["due_date"])
            days = (due - today).days
            if days <= 2:
                urgent.append((task, days))
        except (KeyError, ValueError):
            pass

    if not urgent:
        return

    console = Console()
    lines = Text()
    for task, days in urgent:
        if days < 0:
            label = f"OVERDUE ({abs(days)}d ago)"
            style = "bold red"
        elif days == 0:
            label = "DUE TODAY"
            style = "bold red"
        elif days == 1:
            label = "due tomorrow"
            style = "bold yellow"
        else:
            label = f"due in {days} days"
            style = "yellow"

        lines.append(f"  • {task['name']}", style=style)
        lines.append(f"  [{task['class_name']}]  ", style="dim")
        lines.append(f"{label}\n", style=style)

    console.print(
        Panel(lines, title="[bold]Upcoming Deadlines", border_style="yellow")
    )


def send_system_notification(title: str, message: str) -> None:
    """Send an OS-level notification. Silently ignores failures."""
    import platform

    system = platform.system()

    if system == "Windows":
        # Try win10toast first, fall back to plyer
        try:
            from win10toast import ToastNotifier  # type: ignore

            toaster = ToastNotifier()
            toaster.show_toast(title, message, duration=8, threaded=True)
            return
        except Exception:
            pass

    elif system == "Darwin":
        # Try pync first, fall back to plyer
        try:
            import pync  # type: ignore

            pync.notify(message, title=title)
            return
        except Exception:
            pass

    # Universal fallback
    try:
        from plyer import notification  # type: ignore

        notification.notify(
            title=title,
            message=message,
            app_name="TaskTrack",
            timeout=10,
        )
    except Exception:
        pass


def get_upcoming_tasks(tasks: list[dict], days: int = 2) -> list[dict]:
    """Return tasks due within `days` days (including overdue)."""
    today = date.today()
    result = []
    for task in tasks:
        try:
            due = date.fromisoformat(task["due_date"])
            if (due - today).days <= days:
                result.append(task)
        except (KeyError, ValueError):
            pass
    return result
