# TaskTrack

A beautiful terminal todo app for tracking school assignments.

## Quick Start

```bash
git clone <repo-url>
cd TodoList
python todo.py
```

That's it — missing packages install automatically on first run.

## Features

- **TUI task list** — sorted by due date, color-coded for overdue / due-soon
- **Add / edit / delete / complete** assignments with class, due date, priority
- **Self-learning class names** — MRU suggestions cut typing after the first entry
- **OCR screenshot import** — drag a Teams Assignments screenshot into the terminal; Claude API extracts task data automatically; Tesseract is the fallback
- **Launch-time banner** — shows upcoming deadlines before the TUI starts
- **System notifications** — daily reminders via OS scheduler (optional setup)
- **Archive** — completed tasks are preserved, not deleted

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `↑` / `↓` or `k` / `j` | Navigate |
| `a` | Add task |
| `e` | Edit selected task |
| `d` | Delete selected task |
| `c` | Mark selected task complete |
| `s` | Import from screenshot (OCR) |
| `f` | Filter by class name |
| `v` | View archive |
| `q` | Quit (or back from archive) |

**In archive view:**

| Key | Action |
|-----|--------|
| `r` | Restore task to active list |
| `x` | Permanently delete |
| `q` | Back to task list |

## Date Formats Accepted

When entering due dates, any of these work:

- `2025-01-15` — ISO 8601
- `1/15/2025` or `01/15/25`
- `1/15` — assumes current year (or next year if already past)
- `today` / `tomorrow`

## OCR Screenshot Import

1. Press `s` in the task list
2. Open your Microsoft Teams Assignments tab and take a screenshot
3. Drag the screenshot file into the terminal (or paste the path) and press Enter
4. Review each extracted assignment and confirm import

**For best results**, set a Claude API key when prompted. Without it, Tesseract OCR is used as a fallback.

**Tesseract setup** (required for fallback OCR):
- macOS: `brew install tesseract`
- Windows: [UB-Mannheim installer](https://github.com/UB-Mannheim/tesseract/wiki)
- Ubuntu/Debian: `sudo apt install tesseract-ocr`

## Daily Notifications Setup (Optional)

### macOS
```bash
bash setup_scheduler_mac.sh
```

### Windows
Run `setup_scheduler_windows.bat` as Administrator.

Both scripts register a daily 8 AM notification showing assignments due within 2 days.

## Project Structure

```
TodoList/
├── todo.py          # Entry point + auto-installer
├── scheduler.py     # Standalone daily notification runner
├── requirements.txt
├── src/
│   ├── ui.py        # Rich TUI
│   ├── storage.py   # JSON persistence
│   ├── ocr.py       # Screenshot extraction
│   └── notifications.py
└── data/            # Auto-created, git-ignored
    ├── tasks.json
    ├── archive.json
    └── config.json  # Stores Claude API key (never committed)
```

## Dependencies

All installed automatically by `todo.py`:

- [rich](https://github.com/Textualize/rich) — TUI rendering
- [readchar](https://github.com/magmax/python-readchar) — keyboard input
- [anthropic](https://github.com/anthropics/anthropic-sdk-python) — Claude API for OCR
- [pytesseract](https://github.com/madmaze/pytesseract) + [Pillow](https://python-pillow.org/) — fallback OCR
- [plyer](https://github.com/kivy/plyer) — cross-platform system notifications
