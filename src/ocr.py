"""OCR screenshot extraction for TaskTrack.

Priority:
  1. Claude API (vision) — if API key is configured
  2. Tesseract fallback — with regex heuristics
  3. Return [] if both unavailable
"""

from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.storage import Storage


@dataclass
class OCRResult:
    task_name: str
    class_name: str | None = None
    due_date: str | None = None  # ISO 8601 "YYYY-MM-DD" or None


def _clean_path(raw: str) -> str:
    """Strip surrounding quotes and whitespace from a drag-dropped path."""
    return raw.strip().strip("'\"")


def _strip_json_fences(text: str) -> str:
    """Remove ```json ... ``` wrappers that Claude sometimes adds."""
    return re.sub(r"```(?:json)?\s*|\s*```", "", text).strip()


def _extract_via_claude(image_path: str, api_key: str) -> list[OCRResult]:
    """Use Claude vision API to extract assignment data."""
    import anthropic

    with open(image_path, "rb") as f:
        image_bytes = f.read()

    # Detect media type from extension
    ext = Path(image_path).suffix.lower()
    media_map = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }
    media_type = media_map.get(ext, "image/png")

    image_data = base64.standard_b64encode(image_bytes).decode("utf-8")

    client = anthropic.Anthropic(api_key=api_key)

    prompt = (
        "This is a screenshot from Microsoft Teams Assignments tab. "
        "Extract every assignment visible. "
        "Return ONLY a JSON array (no markdown fences, no explanation) with objects: "
        '[{"task_name": "...", "class_name": "...", "due_date": "YYYY-MM-DD"}]. '
        'Use null for fields you cannot determine. '
        "If no assignments are visible, return []."
    )

    message = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=1024,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": image_data,
                        },
                    },
                    {"type": "text", "text": prompt},
                ],
            }
        ],
    )

    raw = message.content[0].text
    cleaned = _strip_json_fences(raw)
    data = json.loads(cleaned)

    results = []
    for item in data:
        results.append(
            OCRResult(
                task_name=item.get("task_name") or "",
                class_name=item.get("class_name"),
                due_date=item.get("due_date"),
            )
        )
    return [r for r in results if r.task_name]


def _extract_via_tesseract(image_path: str) -> list[OCRResult]:
    """Fallback: Tesseract OCR with regex heuristics for Teams Assignments layout."""
    from PIL import Image  # type: ignore
    import pytesseract  # type: ignore

    text = pytesseract.image_to_string(Image.open(image_path))
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    results = []

    # Due date patterns (e.g. "Due Jan 15, 2025", "Due: 01/15/2025", "Due 2025-01-15")
    due_pattern = re.compile(
        r"due[:\s]+(?:"
        r"(\d{4}-\d{2}-\d{2})"                  # ISO
        r"|(\d{1,2}/\d{1,2}/\d{2,4})"            # MM/DD/YY or MM/DD/YYYY
        r"|(\w+ \d{1,2},?\s*\d{4})"              # Month DD, YYYY
        r")",
        re.IGNORECASE,
    )
    # Course label patterns (e.g. "Math 101 |", "Class: Physics")
    class_pattern = re.compile(r"(?:class|course|subject)[:\s]+([^\|]+)", re.IGNORECASE)

    current_task: str | None = None
    current_class: str | None = None
    current_due: str | None = None

    def _flush():
        nonlocal current_task, current_class, current_due
        if current_task:
            results.append(
                OCRResult(
                    task_name=current_task.strip(),
                    class_name=current_class.strip() if current_class else None,
                    due_date=current_due,
                )
            )
        current_task = None
        current_class = None
        current_due = None

    for line in lines:
        due_match = due_pattern.search(line)
        class_match = class_pattern.search(line)

        if due_match:
            raw_date = due_match.group(1) or due_match.group(2) or due_match.group(3)
            current_due = _parse_date_flexible(raw_date)
        elif class_match:
            current_class = class_match.group(1).strip()
        elif line and not due_match:
            # Heuristic: non-date, non-class lines with reasonable length are task names
            if 5 < len(line) < 120 and not line.startswith("http"):
                if current_task:
                    _flush()
                current_task = line

    _flush()
    return [r for r in results if r.task_name]


def _parse_date_flexible(raw: str) -> str | None:
    """Try several date formats; return ISO 8601 string or None."""
    from datetime import datetime, date

    raw = raw.strip()
    formats = [
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%m/%d/%y",
        "%B %d, %Y",
        "%B %d %Y",
        "%b %d, %Y",
        "%b %d %Y",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            pass
    return None


def extract_from_screenshot(image_path: str, storage: "Storage") -> list[OCRResult]:
    """Main entry point. Returns extracted OCRResult list (may be empty)."""
    cleaned = _clean_path(image_path)
    path = Path(cleaned)

    if not path.exists():
        raise FileNotFoundError(f"Image not found: {cleaned}")

    # 1. Try Claude API
    api_key = storage.get_claude_api_key()
    if api_key:
        try:
            return _extract_via_claude(cleaned, api_key)
        except Exception as exc:
            print(f"[yellow]Claude OCR failed ({exc}), trying Tesseract…[/yellow]")

    # 2. Try Tesseract
    try:
        return _extract_via_tesseract(cleaned)
    except ImportError:
        print(
            "[yellow]pytesseract not installed. "
            "Run: pip install pytesseract Pillow[/yellow]"
        )
    except Exception as exc:
        # Catch TesseractNotFoundError by name (avoid hard import)
        if "TesseractNotFoundError" in type(exc).__name__ or "tesseract" in str(exc).lower():
            print(
                "\n[bold red]Tesseract binary not found.[/bold red]\n"
                "Install it:\n"
                "  macOS:   brew install tesseract\n"
                "  Windows: https://github.com/UB-Mannheim/tesseract/wiki\n"
                "  Ubuntu:  sudo apt install tesseract-ocr\n"
            )
        else:
            print(f"[yellow]Tesseract failed: {exc}[/yellow]")

    return []
