"""Rich TUI for TaskTrack — all screen logic lives here."""

from __future__ import annotations

import sys
from datetime import date, datetime
from enum import Enum, auto
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table
from rich.text import Text

import readchar

from src.storage import Storage
from src import ocr as ocr_module


class Screen(Enum):
    TASK_LIST = auto()
    ARCHIVE = auto()
    OCR_IMPORT = auto()


# ──────────────────────────────────────────── helpers ────────────────────────


_PRIORITY_STYLE = {
    "High": "[bold red]HIGH[/bold red]",
    "Medium": "[bold yellow]MED[/bold yellow]",
    "Low": "[bold green]LOW[/bold green]",
}

_FOOTER_MAIN = (
    "[dim][a]dd  [e]dit  [d]elete  [c]omplete  "
    "[s]creenshot  [f]ilter  [v]archive  [q]uit[/dim]"
)
_FOOTER_ARCHIVE = "[dim][r]estore  [x]delete  [q]back[/dim]"


def _due_date_style(task: dict) -> str:
    """Return Rich style string for the due date cell."""
    days = Storage.days_until_due(task)
    if days is None:
        return ""
    if days < 0:
        return "bold red"
    if days <= 2:
        return "yellow"
    return ""


def _parse_date(raw: str) -> str:
    """Parse many date formats; return ISO 8601 string or raise ValueError."""
    raw = raw.strip()
    today = date.today()

    if raw.lower() == "today":
        return today.isoformat()
    if raw.lower() == "tomorrow":
        from datetime import timedelta
        return (today + timedelta(days=1)).isoformat()

    formats = [
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%m/%d/%y",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            pass

    # MM/DD — assume current year, advance to next year if already passed
    try:
        parsed = datetime.strptime(raw, "%m/%d").date().replace(year=today.year)
        if parsed < today:
            parsed = parsed.replace(year=today.year + 1)
        return parsed.isoformat()
    except ValueError:
        pass

    raise ValueError(f"Unrecognised date: {raw!r}")


# ────────────────────────────────────────── render functions ─────────────────


def _render_task_table(
    tasks: list[dict],
    selected: int,
    filter_class: Optional[str],
) -> Table:
    table = Table(
        show_header=True,
        header_style="bold cyan",
        border_style="bright_black",
        expand=True,
    )
    table.add_column("#", width=4, justify="right")
    table.add_column("Class", min_width=10)
    table.add_column("Task Name", min_width=20)
    table.add_column("Due Date", width=12)
    table.add_column("Priority", width=10)

    filtered = tasks
    if filter_class:
        filtered = [t for t in tasks if t.get("class_name", "").lower() == filter_class.lower()]

    if not filtered:
        table.add_row(
            "", "", "[dim italic]No tasks[/dim italic]", "", ""
        )
        return table

    for idx, task in enumerate(filtered):
        row_style = "reverse" if idx == selected else ""
        due_style = _due_date_style(task)
        due_text = Text(task.get("due_date", ""), style=due_style)
        prio = task.get("priority", "Medium")
        prio_markup = _PRIORITY_STYLE.get(prio, prio)

        table.add_row(
            str(idx + 1),
            task.get("class_name", ""),
            task.get("name", ""),
            due_text,
            prio_markup,
            style=row_style,
        )

    return table


def _render_archive_table(tasks: list[dict], selected: int) -> Table:
    table = Table(
        show_header=True,
        header_style="bold cyan",
        border_style="bright_black",
        expand=True,
    )
    table.add_column("#", width=4, justify="right")
    table.add_column("Class", min_width=10)
    table.add_column("Task Name", min_width=20)
    table.add_column("Completed", width=20)
    table.add_column("Priority", width=10)

    if not tasks:
        table.add_row("", "", "[dim italic]Archive is empty[/dim italic]", "", "")
        return table

    for idx, task in enumerate(tasks):
        row_style = "reverse" if idx == selected else ""
        completed = task.get("completed_at", "")
        if completed:
            try:
                completed = datetime.fromisoformat(completed).strftime("%Y-%m-%d %H:%M")
            except ValueError:
                pass
        prio = task.get("priority", "Medium")
        prio_markup = _PRIORITY_STYLE.get(prio, prio)

        table.add_row(
            str(idx + 1),
            task.get("class_name", ""),
            task.get("name", ""),
            completed,
            prio_markup,
            style=row_style,
        )

    return table


def _make_layout(
    screen: Screen,
    tasks: list[dict],
    archive: list[dict],
    selected: int,
    filter_class: Optional[str],
    status_msg: str,
) -> Panel:
    if screen == Screen.TASK_LIST:
        header = Text("TaskTrack", style="bold cyan")
        if filter_class:
            header.append(f"  [filter: {filter_class}]", style="dim yellow")
        body = _render_task_table(tasks, selected, filter_class)
        footer = _FOOTER_MAIN
    elif screen == Screen.ARCHIVE:
        header = Text("Archive", style="bold magenta")
        body = _render_archive_table(archive, selected)
        footer = _FOOTER_ARCHIVE
    else:
        header = Text("OCR Import", style="bold green")
        body = Panel("[dim]Initialising OCR…[/dim]", border_style="green")
        footer = ""

    from rich.console import Group  # type: ignore

    content = Group(
        header,
        body,
        Text(status_msg, style="dim italic") if status_msg else Text(""),
        Text.from_markup(footer),
    )
    return Panel(content, border_style="bright_black")


# ────────────────────────────────────────────── App ──────────────────────────


class App:
    def __init__(self, storage: Storage) -> None:
        self.storage = storage
        self.console = Console()
        self.screen = Screen.TASK_LIST
        self.selected = 0
        self.filter_class: Optional[str] = None
        self.status_msg = ""
        self._live: Optional[Live] = None

    # ---------------------------------------------------------------- helpers

    def _tasks(self) -> list[dict]:
        tasks = self.storage.load_tasks()
        if self.filter_class:
            return [t for t in tasks if t.get("class_name", "").lower() == self.filter_class.lower()]
        return tasks

    def _archive(self) -> list[dict]:
        return self.storage.load_archive()

    def _clamp(self, idx: int, length: int) -> int:
        if length == 0:
            return 0
        return max(0, min(idx, length - 1))

    def _render(self) -> Panel:
        return _make_layout(
            self.screen,
            self._tasks(),
            self._archive(),
            self.selected,
            self.filter_class,
            self.status_msg,
        )

    def _stop_live(self) -> None:
        if self._live:
            self._live.stop()

    def _start_live(self) -> None:
        if self._live:
            self._live.start()

    # ──────────────────────────────────────── form helpers ───────────────────

    def _ask_class(self, current: Optional[str] = None) -> str:
        """Show MRU class menu + option to type new. Returns chosen class name."""
        known = self.storage.get_known_classes()
        if known:
            self.console.print("\n[bold]Known classes:[/bold]")
            for i, cls in enumerate(known, 1):
                marker = " [cyan](current)[/cyan]" if cls == current else ""
                self.console.print(f"  {i}. {cls}{marker}")
            self.console.print(f"  {len(known) + 1}. Type a new class name")
            choice = Prompt.ask(
                "Choose class",
                default=str(
                    known.index(current) + 1 if current in known else str(len(known) + 1)
                ),
            )
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(known):
                    return known[idx]
            except ValueError:
                pass
        return Prompt.ask("Class name", default=current or "")

    def _ask_due_date(self, current: Optional[str] = None) -> str:
        """Prompt for due date; re-ask on invalid input."""
        hint = current or date.today().isoformat()
        while True:
            raw = Prompt.ask(
                "Due date [YYYY-MM-DD, MM/DD, today, tomorrow]",
                default=hint,
            )
            try:
                return _parse_date(raw)
            except ValueError:
                self.console.print(f"[red]Invalid date: {raw!r}. Try again.[/red]")

    def _ask_priority(self, current: Optional[str] = None) -> str:
        """[H]igh / [M]edium / [L]ow prompt."""
        default_char = {"High": "H", "Medium": "M", "Low": "L"}.get(current or "Medium", "M")
        while True:
            raw = Prompt.ask(
                "[H]igh / [M]edium / [L]ow",
                default=default_char,
            ).strip().upper()
            if raw.startswith("H"):
                return "High"
            if raw.startswith("M"):
                return "Medium"
            if raw.startswith("L"):
                return "Low"
            self.console.print("[red]Enter H, M, or L.[/red]")

    # ──────────────────────────────────────── task actions ───────────────────

    def _action_add(self) -> None:
        self._stop_live()
        self.console.print("\n[bold cyan]── Add Task ──[/bold cyan]")
        name = Prompt.ask("Task name")
        if not name.strip():
            self.status_msg = "Cancelled."
            self._start_live()
            return
        class_name = self._ask_class()
        due_date = self._ask_due_date()
        priority = self._ask_priority()
        self.storage.add_task(name.strip(), class_name, due_date, priority)
        if class_name:
            self.storage.add_known_class(class_name)
        tasks = self._tasks()
        self.selected = self._clamp(len(tasks) - 1, len(tasks))
        self.status_msg = f"Added: {name.strip()}"
        self._start_live()

    def _action_edit(self) -> None:
        tasks = self._tasks()
        if not tasks:
            return
        task = tasks[self._clamp(self.selected, len(tasks))]
        self._stop_live()
        self.console.print(f"\n[bold cyan]── Edit Task: {task['name']} ──[/bold cyan]")
        name = Prompt.ask("Task name", default=task.get("name", ""))
        if not name.strip():
            self.status_msg = "Cancelled."
            self._start_live()
            return
        class_name = self._ask_class(task.get("class_name"))
        due_date = self._ask_due_date(task.get("due_date"))
        priority = self._ask_priority(task.get("priority"))
        self.storage.update_task(
            task["id"],
            name=name.strip(),
            class_name=class_name,
            due_date=due_date,
            priority=priority,
        )
        if class_name:
            self.storage.add_known_class(class_name)
        self.status_msg = f"Updated: {name.strip()}"
        self._start_live()

    def _action_delete(self) -> None:
        tasks = self._tasks()
        if not tasks:
            return
        task = tasks[self._clamp(self.selected, len(tasks))]
        self._stop_live()
        confirmed = Confirm.ask(f"Delete '{task['name']}'?", default=False)
        if confirmed:
            self.storage.delete_task(task["id"])
            tasks = self._tasks()
            self.selected = self._clamp(self.selected, len(tasks))
            self.status_msg = "Deleted."
        else:
            self.status_msg = "Cancelled."
        self._start_live()

    def _action_complete(self) -> None:
        tasks = self._tasks()
        if not tasks:
            return
        task = tasks[self._clamp(self.selected, len(tasks))]
        self._stop_live()
        confirmed = Confirm.ask(f"Mark '{task['name']}' complete?", default=True)
        if confirmed:
            self.storage.complete_task(task["id"])
            tasks = self._tasks()
            self.selected = self._clamp(self.selected, len(tasks))
            self.status_msg = "Completed!"
        else:
            self.status_msg = "Cancelled."
        self._start_live()

    def _action_filter(self) -> None:
        self._stop_live()
        raw = Prompt.ask("Filter by class (blank = clear)", default="")
        self.filter_class = raw.strip() or None
        self.selected = 0
        self.status_msg = (
            f"Filtering: {self.filter_class}" if self.filter_class else "Filter cleared."
        )
        self._start_live()

    def _action_screenshot(self) -> None:
        self._stop_live()
        self.console.print(
            Panel(
                "[bold]Drag your Teams Assignments screenshot here and press Enter[/bold]\n"
                "[dim](or paste the file path)[/dim]",
                title="Screenshot OCR",
                border_style="green",
            )
        )

        api_key = self.storage.get_claude_api_key()
        if not api_key:
            self.console.print(
                "[yellow]No Claude API key set. "
                "For best results, set one:[/yellow]"
            )
            new_key = Prompt.ask("Claude API key (blank to skip)", default="", password=True)
            if new_key.strip():
                self.storage.set_claude_api_key(new_key.strip())

        raw_path = Prompt.ask("Screenshot path")
        if not raw_path.strip():
            self.status_msg = "Cancelled."
            self._start_live()
            return

        cleaned = raw_path.strip().strip("'\"")
        path = Path(cleaned)
        if not path.exists():
            self.console.print(f"[red]File not found: {cleaned}[/red]")
            self.status_msg = "File not found."
            self._start_live()
            return

        self.console.print("[dim]Extracting assignments…[/dim]")
        try:
            results = ocr_module.extract_from_screenshot(cleaned, self.storage)
        except Exception as exc:
            self.console.print(f"[red]OCR error: {exc}[/red]")
            self.status_msg = "OCR failed."
            self._start_live()
            return

        if not results:
            self.console.print("[yellow]No assignments found in screenshot.[/yellow]")
            self.status_msg = "No assignments found."
            self._start_live()
            return

        imported = 0
        for result in results:
            self.console.print(
                f"\n  [cyan]Task:[/cyan] {result.task_name}\n"
                f"  [cyan]Class:[/cyan] {result.class_name or '(unknown)'}\n"
                f"  [cyan]Due:[/cyan]   {result.due_date or '(unknown)'}"
            )
            # Resolve missing fields interactively
            class_name = result.class_name or self._ask_class()
            due_date = result.due_date or self._ask_due_date()
            priority = self._ask_priority()

            if Confirm.ask("Import this task?", default=True):
                self.storage.add_task(result.task_name, class_name, due_date, priority)
                if class_name:
                    self.storage.add_known_class(class_name)
                imported += 1

        self.status_msg = f"Imported {imported} task(s) from screenshot."
        self._start_live()

    # ──────────────────────────────────────── archive actions ────────────────

    def _action_restore(self) -> None:
        archive = self._archive()
        if not archive:
            return
        task = archive[self._clamp(self.selected, len(archive))]
        self._stop_live()
        confirmed = Confirm.ask(f"Restore '{task['name']}'?", default=True)
        if confirmed:
            self.storage.restore_task(task["id"])
            archive = self._archive()
            self.selected = self._clamp(self.selected, len(archive))
            self.status_msg = "Restored."
        else:
            self.status_msg = "Cancelled."
        self._start_live()

    def _action_delete_archived(self) -> None:
        archive = self._archive()
        if not archive:
            return
        task = archive[self._clamp(self.selected, len(archive))]
        self._stop_live()
        confirmed = Confirm.ask(
            f"Permanently delete '{task['name']}'?", default=False
        )
        if confirmed:
            self.storage.delete_archived(task["id"])
            archive = self._archive()
            self.selected = self._clamp(self.selected, len(archive))
            self.status_msg = "Deleted permanently."
        else:
            self.status_msg = "Cancelled."
        self._start_live()

    # ──────────────────────────────────────── key handling ───────────────────

    def _handle_key_task_list(self, key: str) -> bool:
        """Returns False to quit."""
        tasks = self._tasks()
        n = len(tasks)

        if key in (readchar.key.UP, "k"):
            self.selected = self._clamp(self.selected - 1, n)
            self.status_msg = ""
        elif key in (readchar.key.DOWN, "j"):
            self.selected = self._clamp(self.selected + 1, n)
            self.status_msg = ""
        elif key == "a":
            self._action_add()
        elif key == "e":
            self._action_edit()
        elif key == "d":
            self._action_delete()
        elif key == "c":
            self._action_complete()
        elif key == "s":
            self._action_screenshot()
        elif key == "f":
            self._action_filter()
        elif key == "v":
            self.screen = Screen.ARCHIVE
            self.selected = 0
            self.status_msg = ""
        elif key in ("q", readchar.key.CTRL_C, readchar.key.CTRL_D):
            return False
        return True

    def _handle_key_archive(self, key: str) -> bool:
        archive = self._archive()
        n = len(archive)

        if key in (readchar.key.UP, "k"):
            self.selected = self._clamp(self.selected - 1, n)
            self.status_msg = ""
        elif key in (readchar.key.DOWN, "j"):
            self.selected = self._clamp(self.selected + 1, n)
            self.status_msg = ""
        elif key == "r":
            self._action_restore()
        elif key == "x":
            self._action_delete_archived()
        elif key in ("q", readchar.key.CTRL_C, readchar.key.CTRL_D):
            self.screen = Screen.TASK_LIST
            self.selected = 0
            self.status_msg = ""
        return True

    def _handle_key(self, key: str) -> bool:
        if self.screen == Screen.TASK_LIST:
            return self._handle_key_task_list(key)
        elif self.screen == Screen.ARCHIVE:
            return self._handle_key_archive(key)
        return True

    # ──────────────────────────────────────────── run ────────────────────────

    def run(self) -> None:
        with Live(
            self._render(),
            console=self.console,
            refresh_per_second=10,
            screen=False,
        ) as live:
            self._live = live
            running = True
            while running:
                live.update(self._render())
                try:
                    key = readchar.readkey()
                except KeyboardInterrupt:
                    break
                running = self._handle_key(key)

        self.console.print("[dim]Goodbye![/dim]")
