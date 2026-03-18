#!/usr/bin/env python3
"""TaskTrack — Standalone daily notification runner.

Designed to be invoked by OS task schedulers (Windows Task Scheduler /
macOS launchd) from any working directory.

Usage:
    python /path/to/TodoList/scheduler.py
"""

import json
import sys
from pathlib import Path

# Locate repo root relative to this file and add to sys.path
REPO_ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(REPO_ROOT))

TASKS_FILE = REPO_ROOT / "data" / "tasks.json"


def _load_tasks() -> list[dict]:
    if not TASKS_FILE.exists():
        return []
    with open(TASKS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def main() -> None:
    from src.notifications import get_upcoming_tasks, send_system_notification

    tasks = _load_tasks()
    upcoming = get_upcoming_tasks(tasks, days=2)

    if not upcoming:
        return

    max_show = 3
    names = [t["name"] for t in upcoming[:max_show]]
    extra = len(upcoming) - max_show

    if extra > 0:
        body = ", ".join(names) + f" and {extra} more"
    else:
        body = ", ".join(names)

    title = f"TaskTrack: {len(upcoming)} assignment(s) due soon"
    send_system_notification(title, body)


if __name__ == "__main__":
    main()
