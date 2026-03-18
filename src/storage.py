"""JSON persistence layer for TaskTrack."""

import json
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Optional

# Locate data/ relative to repo root (two levels up from src/)
_REPO_ROOT = Path(__file__).parent.parent
DATA_DIR = _REPO_ROOT / "data"


def _ensure_data_dir() -> None:
    DATA_DIR.mkdir(exist_ok=True)


def _tasks_path() -> Path:
    return DATA_DIR / "tasks.json"


def _archive_path() -> Path:
    return DATA_DIR / "archive.json"


def _config_path() -> Path:
    return DATA_DIR / "config.json"


def _read_json(path: Path) -> list:
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: Path, data: list | dict) -> None:
    _ensure_data_dir()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _read_config() -> dict:
    if not _config_path().exists():
        return {"known_classes": [], "claude_api_key": None}
    with open(_config_path(), "r", encoding="utf-8") as f:
        return json.load(f)


def _write_config(config: dict) -> None:
    _ensure_data_dir()
    with open(_config_path(), "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


class Storage:
    """All reads parse fresh from disk — avoids state-sync bugs."""

    # ------------------------------------------------------------------ tasks

    def load_tasks(self) -> list[dict]:
        tasks = _read_json(_tasks_path())
        return sorted(tasks, key=lambda t: t.get("due_date", "9999-99-99"))

    def save_tasks(self, tasks: list[dict]) -> None:
        _write_json(_tasks_path(), tasks)

    def add_task(
        self,
        name: str,
        class_name: str,
        due_date: str,
        priority: str = "Medium",
    ) -> dict:
        task: dict = {
            "id": uuid.uuid4().hex,
            "name": name,
            "class_name": class_name,
            "due_date": due_date,
            "priority": priority,
            "created_at": datetime.now().isoformat(),
            "completed_at": None,
        }
        tasks = _read_json(_tasks_path())
        tasks.append(task)
        _write_json(_tasks_path(), tasks)
        return task

    def delete_task(self, task_id: str) -> bool:
        tasks = _read_json(_tasks_path())
        new_tasks = [t for t in tasks if t["id"] != task_id]
        if len(new_tasks) == len(tasks):
            return False
        _write_json(_tasks_path(), new_tasks)
        return True

    def update_task(self, task_id: str, **fields) -> bool:
        tasks = _read_json(_tasks_path())
        for task in tasks:
            if task["id"] == task_id:
                task.update(fields)
                _write_json(_tasks_path(), tasks)
                return True
        return False

    def complete_task(self, task_id: str) -> bool:
        tasks = _read_json(_tasks_path())
        target = next((t for t in tasks if t["id"] == task_id), None)
        if target is None:
            return False
        target["completed_at"] = datetime.now().isoformat()
        new_tasks = [t for t in tasks if t["id"] != task_id]
        _write_json(_tasks_path(), new_tasks)
        archive = _read_json(_archive_path())
        archive.append(target)
        _write_json(_archive_path(), archive)
        return True

    # ---------------------------------------------------------------- archive

    def load_archive(self) -> list[dict]:
        archive = _read_json(_archive_path())
        return sorted(archive, key=lambda t: t.get("completed_at", ""), reverse=True)

    def restore_task(self, task_id: str) -> bool:
        archive = _read_json(_archive_path())
        target = next((t for t in archive if t["id"] == task_id), None)
        if target is None:
            return False
        target["completed_at"] = None
        new_archive = [t for t in archive if t["id"] != task_id]
        _write_json(_archive_path(), new_archive)
        tasks = _read_json(_tasks_path())
        tasks.append(target)
        _write_json(_tasks_path(), tasks)
        return True

    def delete_archived(self, task_id: str) -> bool:
        archive = _read_json(_archive_path())
        new_archive = [t for t in archive if t["id"] != task_id]
        if len(new_archive) == len(archive):
            return False
        _write_json(_archive_path(), new_archive)
        return True

    # ----------------------------------------------------------------- config

    def add_known_class(self, name: str) -> None:
        config = _read_config()
        known: list[str] = config.get("known_classes", [])
        # Remove existing occurrence (case-insensitive dedup)
        known = [c for c in known if c.lower() != name.lower()]
        # Prepend for MRU order, cap at 20
        known.insert(0, name)
        known = known[:20]
        config["known_classes"] = known
        _write_config(config)

    def get_known_classes(self) -> list[str]:
        return _read_config().get("known_classes", [])

    def get_claude_api_key(self) -> Optional[str]:
        return _read_config().get("claude_api_key")

    def set_claude_api_key(self, key: str) -> None:
        config = _read_config()
        config["claude_api_key"] = key
        _write_config(config)

    # ----------------------------------------------------------------- helpers

    @staticmethod
    def is_overdue(task: dict) -> bool:
        try:
            return date.fromisoformat(task["due_date"]) < date.today()
        except (KeyError, ValueError):
            return False

    @staticmethod
    def days_until_due(task: dict) -> Optional[int]:
        try:
            delta = date.fromisoformat(task["due_date"]) - date.today()
            return delta.days
        except (KeyError, ValueError):
            return None
