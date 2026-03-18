# TaskTrack — AI Assistant Guide

This file is the authoritative reference for Claude Code (and any other AI assistant) working in this repo. Read it before making changes.

---

## Project Overview

**TaskTrack** is a Python terminal todo app for students tracking school assignments. It targets high-school / college students who use Windows at school and Macs at home, and need zero-friction setup.

**Primary goals:**
1. `python todo.py` just works on any machine after `git clone`
2. Rich, keyboard-driven TUI with color-coded urgency
3. OCR import from Microsoft Teams Assignments screenshots
4. Self-learning class name suggestions (MRU)
5. System notifications for upcoming deadlines

---

## File Map

```
TodoList/
├── todo.py                  # Entry point + auto-installer (run this)
├── scheduler.py             # Standalone daily notification runner
├── requirements.txt
├── setup_scheduler_windows.bat
├── setup_scheduler_mac.sh
├── .gitignore               # data/ is always ignored
├── README.md
├── CLAUDE.md                # this file
├── AGENTS.md                # mirrors this file
└── src/
    ├── __init__.py
    ├── ui.py                # All Rich TUI logic
    ├── storage.py           # JSON persistence layer
    ├── ocr.py               # Screenshot extraction
    └── notifications.py     # Launch banner + system notifications

data/                        # Git-ignored, auto-created at runtime
├── tasks.json
├── archive.json
└── config.json
```

---

## Data Model

### `tasks.json` / `archive.json` items
```python
Task = {
    "id": str,           # uuid4 hex (no hyphens), e.g. "a3f8c1d2..."
    "name": str,         # assignment title
    "class_name": str,   # e.g. "AP Chemistry"
    "due_date": str,     # ISO 8601: "YYYY-MM-DD"
    "priority": str,     # "High" | "Medium" | "Low"
    "created_at": str,   # ISO 8601 datetime
    "completed_at": str | None  # set when completed
}
```

### `config.json`
```python
Config = {
    "known_classes": list[str],   # MRU order, max 20
    "claude_api_key": str | None  # stored here, NOT in env vars
}
```

---

## Module Guide

### `src/storage.py`

**Purpose:** All disk I/O. No caching — every method reads fresh from disk.

**Key invariants:**
- Tasks are sorted by `due_date` ascending on every `load_tasks()` call
- `complete_task(id)` moves from `tasks.json` → `archive.json`
- `restore_task(id)` moves from `archive.json` → `tasks.json`, clears `completed_at`
- `add_known_class(name)` is case-insensitively deduped, prepended (MRU), capped at 20

**Where `add_known_class` is called:**
- `ui.py: _action_add()` — after task created
- `ui.py: _action_edit()` — after task updated
- `ui.py: _action_screenshot()` — after OCR import confirmed

**Why no caching:** `scheduler.py` and `todo.py` may both touch `tasks.json`. Fresh reads prevent stale state. Tasks are small (<1 MB), so disk reads are negligible.

---

### `src/ui.py`

**Purpose:** All TUI logic. Screen state machine + Rich Live rendering.

**Screen enum:**
```python
class Screen(Enum):
    TASK_LIST  # main view
    ARCHIVE    # completed tasks
    OCR_IMPORT # (reserved; OCR flow runs inline in TASK_LIST)
```

**Rendering pattern:**
- `rich.live.Live` wraps the whole app loop
- On keypress → mutate `App` state → `live.update(render())`
- For any form input: `live.stop()` → `Prompt.ask(...)` → `live.start()`
  - This is the officially documented Rich pattern; never mix Live + input without stopping

**Key bindings (TASK_LIST):**

| Key | Action |
|-----|--------|
| `↑`/`↓` or `k`/`j` | Navigate |
| `a` | `_action_add()` |
| `e` | `_action_edit()` |
| `d` | `_action_delete()` |
| `c` | `_action_complete()` |
| `s` | `_action_screenshot()` |
| `f` | `_action_filter()` |
| `v` | Switch to ARCHIVE screen |
| `q` / Ctrl-C | Quit |

**Key bindings (ARCHIVE):**

| Key | Action |
|-----|--------|
| `↑`/`↓` | Navigate |
| `r` | `_action_restore()` |
| `x` | `_action_delete_archived()` |
| `q` | Back to TASK_LIST |

**Adding a new screen:**
1. Add variant to `Screen` enum
2. Add `elif key == "X": self.screen = Screen.NEW_SCREEN` in `_handle_key_task_list`
3. Add `_handle_key_new_screen(key)` method
4. Add `elif self.screen == Screen.NEW_SCREEN:` branch in `_handle_key`
5. Add rendering logic in `_make_layout`

**Due date color logic (in `_due_date_style`):**
- `days < 0` → `"bold red"` (overdue)
- `days == 0` or `days == 1` → `"yellow"` (due within 2 days)
- else → no style

---

### `src/ocr.py`

**Purpose:** Extract assignment data from a screenshot. Two paths: Claude API (preferred) and Tesseract (fallback).

**Entry point:**
```python
def extract_from_screenshot(image_path: str, storage: Storage) -> list[OCRResult]
```

**Claude API path:**
- Base64-encodes image, sends as vision message to `claude-opus-4-5`
- Prompt asks for JSON array: `[{"task_name": ..., "class_name": ..., "due_date": "YYYY-MM-DD"}]`
- `_strip_json_fences()` removes ` ```json ``` ` wrappers before `json.loads`
- Catches all exceptions and falls through to Tesseract

**Tesseract fallback:**
- `pytesseract.image_to_string(Image.open(path))`
- Heuristic parsing: due date regex, class label regex, line-length heuristic for task names
- `TesseractNotFoundError` → prints friendly install instructions

**Tuning the Claude prompt:** Edit the `prompt` string in `_extract_via_claude`. Key constraint: response must be pure JSON (no prose). The current prompt instructs this explicitly.

**Tuning Tesseract heuristics:** Improve `due_pattern` and `class_pattern` regexes in `_extract_via_tesseract` based on actual Teams screenshot layouts.

---

### `src/notifications.py`

**Tier 1 — `check_on_launch(tasks)`:**
- Called in `todo.py` before `App.run()` — printed as a static Rich Panel
- Shows tasks due within 2 days
- Does nothing if no upcoming tasks

**Tier 2 — `send_system_notification(title, message)`:**
- Called by `scheduler.py`
- Platform dispatch:
  - Windows: `win10toast` (threaded=True) → `plyer` fallback
  - macOS: `pync` → `plyer` fallback
  - Linux: `plyer` directly
- All wrapped in `try/except`; never raises

**Adding a new notification trigger:**
1. Add logic in `notifications.py`
2. If it's a launch-time notification, call it in `todo.py` before `App(storage).run()`
3. If it's a scheduled notification, call it from `scheduler.py`

---

## Self-Learning Class Names

**Flow:**
1. `Storage.get_known_classes()` returns list in MRU order
2. `ui._ask_class()` shows numbered menu from this list
3. Student picks by number (1 keystroke) or types new name
4. After task is saved, `storage.add_known_class(name)` prepends it → most-used stays at top

**Why MRU:** The student's most recently used class is almost always the one they're adding next.

---

## Coding Conventions

- **Python version:** 3.9+ (use `list[str]`, `dict | None` etc. with `from __future__ import annotations`)
- **Style:** PEP 8, 4-space indent, max line length ~100
- **Types:** Type hints on all public functions
- **Paths:** Always use `pathlib.Path`, never string concatenation
- **Dates:** Always ISO 8601 strings in JSON; `date.fromisoformat()` to parse
- **IDs:** `uuid.uuid4().hex` (no hyphens)
- **No global state:** All state lives on `App` or `Storage` instances
- **No in-memory task cache:** `Storage` reads fresh from disk on every call
- **Imports:** Standard library → third-party → local (`src.*`)

---

## Manual Test Checklist

- [ ] `python todo.py` on fresh clone auto-installs packages and shows TUI
- [ ] Add a task with all fields; verify sorted by due date in `data/tasks.json`
- [ ] Add overdue task → red due date in TUI
- [ ] Add task due in 1 day → yellow due date
- [ ] Edit task → all fields update in JSON
- [ ] Delete task → removed from `tasks.json`
- [ ] Complete task → moves to `archive.json` with `completed_at` set
- [ ] Archive view → restore task → back in `tasks.json`, `completed_at` cleared
- [ ] Archive view → permanently delete → gone from `archive.json`
- [ ] Filter by class → only matching tasks shown; blank clears filter
- [ ] Screenshot import with Claude API key set → tasks extracted and confirmed
- [ ] Screenshot import without API key → Tesseract path (or friendly error)
- [ ] `python scheduler.py` → system notification fires for due-soon tasks
- [ ] `setup_scheduler_mac.sh` → launchd entry visible in `launchctl list`
- [ ] `setup_scheduler_windows.bat` → Task Scheduler entry visible

---

## How to Extend

### Add a new date format
Edit `_parse_date()` in `src/ui.py`. Add new `strptime` format string to `formats` list or add a new special-case branch.

### Add a new priority level
1. Add to `_PRIORITY_STYLE` dict in `src/ui.py`
2. Update `_ask_priority()` prompt and parsing
3. No storage changes needed (priority is a free string)

### Add a new config field
1. Add default to `_read_config()` in `src/storage.py`
2. Add getter/setter methods
3. Update `config.json` shape in this doc and `AGENTS.md`

### Change notification timing
Edit `StartCalendarInterval` in `setup_scheduler_mac.sh` or `/ST HH:MM` in `setup_scheduler_windows.bat`, then re-run the setup script.
