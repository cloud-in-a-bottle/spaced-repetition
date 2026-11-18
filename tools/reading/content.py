"""Library and analysis: put texts in the reader, and see which of their words you know."""

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from tools.reading.client import SrsClient


def read_file(path: Path) -> tuple[str, str]:
    """(format, content) for a .srt or plain-text file."""
    content = path.read_text(encoding="utf-8-sig")
    return ("srt" if path.suffix.lower() == ".srt" else "text"), content


def ensure_course(client: SrsClient, course_id: str, title: str, language: str, description: str = "") -> Any:
    return client.put(
        f"/library/courses/{course_id}", {"title": title, "language": language, "description": description}
    )


def add_text(
    client: SrsClient, text_id: str, course_id: str, title: str, path: Path, position: int | None = None
) -> Any:
    """Create or replace a text (ids are ours to pick, so re-running updates in place)."""
    fmt, content = read_file(path)
    return client.put(
        f"/library/texts/{text_id}",
        {"course_id": course_id, "title": title, "position": position, "format": fmt, "content": content},
    )


def analyze(client: SrsClient, language: str, path: Path) -> list[dict[str, Any]]:
    """Every distinct word with its count and status (known / learning / new / name / ignored), most frequent first.
    Statuses come from the app, so they match what the reader highlights."""
    fmt, content = read_file(path)
    return list(client.post("/reader/analyze", {"language": language, "format": fmt, "content": content}))


def to_learn(words: Iterable[dict[str, Any]], include_learning: bool = True) -> list[dict[str, Any]]:
    wanted = {"new", "learning"} if include_learning else {"new"}
    return [w for w in words if w["status"] in wanted]


def print_report(words: list[dict[str, Any]], top: int = 60) -> None:
    total = sum(w["count"] for w in words)
    by_status: dict[str, int] = {}
    for w in words:
        by_status[w["status"]] = by_status.get(w["status"], 0) + w["count"]
    print(f"{len(words)} distinct words, {total} in all")
    for status, n in sorted(by_status.items(), key=lambda kv: -kv[1]):
        print(f"  {status:9} {n:6}  {100 * n / total:5.1f}%")
    for status in ("learning", "new"):
        rows = [w for w in words if w["status"] == status][:top]
        print(f"\nmost frequent {status}:")
        print("  " + "  ".join(f"{w['key']}×{w['count']}" for w in rows))
