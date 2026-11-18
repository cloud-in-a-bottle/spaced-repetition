"""Courses and texts. Not part of the sync protocol: the reader works online (it needs the dictionary anyway)."""

import json
import sqlite3

import attr

from srs.domain.errors import InvalidRequest
from srs.domain.errors import NotFound
from srs.domain.ids import new_id
from srs.reader.text_formats import Block


@attr.s(auto_attribs=True, frozen=True)
class Course:
    id: str
    title: str
    language: str
    description: str
    created_at: int
    updated_at: int


@attr.s(auto_attribs=True, frozen=True)
class Text:
    id: str
    course_id: str
    title: str
    position: int
    format: str
    blocks: list[Block]
    created_at: int
    updated_at: int
    read_at: int | None


def _course(row: sqlite3.Row) -> Course:
    return Course(**{k: row[k] for k in row.keys()})  # noqa: SIM118 - sqlite3.Row


def _text(row: sqlite3.Row) -> Text:
    fields = {k: row[k] for k in row.keys()}  # noqa: SIM118
    fields["blocks"] = [Block(**b) for b in json.loads(fields["blocks"])]
    return Text(**fields)


def list_courses(conn: sqlite3.Connection) -> list[Course]:
    return [_course(r) for r in conn.execute("SELECT * FROM courses ORDER BY title")]


def get_course(conn: sqlite3.Connection, course_id: str) -> Course:
    row = conn.execute("SELECT * FROM courses WHERE id = ?", (course_id,)).fetchone()
    if row is None:
        raise NotFound(f"course {course_id}")
    return _course(row)


def save_course(
    conn: sqlite3.Connection, course_id: str | None, title: str, language: str, description: str, now: int
) -> Course:
    if not title.strip() or not language.strip():
        raise InvalidRequest("a course needs a title and a language")
    existing = (
        None if course_id is None else conn.execute("SELECT 1 FROM courses WHERE id = ?", (course_id,)).fetchone()
    )
    cid = course_id or new_id()
    if existing:
        conn.execute(
            "UPDATE courses SET title = ?, language = ?, description = ?, updated_at = ? WHERE id = ?",
            (title.strip(), language.strip(), description, now, cid),
        )
    else:
        conn.execute(
            "INSERT INTO courses (id, title, language, description, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (cid, title.strip(), language.strip(), description, now, now),
        )
    return get_course(conn, cid)


def delete_course(conn: sqlite3.Connection, course_id: str) -> None:
    get_course(conn, course_id)
    conn.execute("DELETE FROM texts WHERE course_id = ?", (course_id,))
    conn.execute("DELETE FROM courses WHERE id = ?", (course_id,))


def texts_of(conn: sqlite3.Connection, course_id: str) -> list[Text]:
    rows = conn.execute("SELECT * FROM texts WHERE course_id = ? ORDER BY position, title", (course_id,))
    return [_text(r) for r in rows]


def get_text(conn: sqlite3.Connection, text_id: str) -> Text:
    row = conn.execute("SELECT * FROM texts WHERE id = ?", (text_id,)).fetchone()
    if row is None:
        raise NotFound(f"text {text_id}")
    return _text(row)


def save_text(
    conn: sqlite3.Connection,
    text_id: str | None,
    course_id: str,
    title: str,
    position: int | None,
    fmt: str | None,
    blocks: list[Block] | None,
    now: int,
) -> Text:
    """Create a text (format and blocks required) or update one (None keeps the current value)."""
    get_course(conn, course_id)
    if not title.strip():
        raise InvalidRequest("a text needs a title")
    row = None if text_id is None else conn.execute("SELECT * FROM texts WHERE id = ?", (text_id,)).fetchone()
    if position is None:
        position = (
            row["position"]
            if row
            else (
                conn.execute(
                    "SELECT coalesce(max(position), 0) + 1 FROM texts WHERE course_id = ?", (course_id,)
                ).fetchone()[0]
            )
        )
    if row is None:
        if fmt is None or blocks is None:
            raise InvalidRequest("a new text needs content")
        tid = text_id or new_id()
        conn.execute(
            "INSERT INTO texts (id, course_id, title, position, format, blocks, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (tid, course_id, title.strip(), position, fmt, _encode(blocks), now, now),
        )
        return get_text(conn, tid)
    conn.execute(
        "UPDATE texts SET course_id = ?, title = ?, position = ?, format = coalesce(?, format), "
        "blocks = coalesce(?, blocks), updated_at = ? WHERE id = ?",
        (course_id, title.strip(), position, fmt, None if blocks is None else _encode(blocks), now, row["id"]),
    )
    return get_text(conn, row["id"])


def _encode(blocks: list[Block]) -> str:
    return json.dumps([{k: v for k, v in attr.asdict(b).items() if v is not None} for b in blocks], ensure_ascii=False)


def delete_text(conn: sqlite3.Connection, text_id: str) -> None:
    get_text(conn, text_id)
    conn.execute("DELETE FROM texts WHERE id = ?", (text_id,))


def mark_read(conn: sqlite3.Connection, text_id: str, now: int | None) -> None:
    get_text(conn, text_id)
    conn.execute("UPDATE texts SET read_at = ? WHERE id = ?", (now, text_id))
