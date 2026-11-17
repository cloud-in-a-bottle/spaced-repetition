import sqlite3

import attr

from srs.domain.errors import NotFound
from srs.domain.kinds import ItemKind
from srs.domain.kinds import Skill


@attr.s(auto_attribs=True, frozen=True)
class Template:
    """How to turn an item of `kind` into a card that exercises `skill`. `front`/`back` are jinja templates."""

    id: str
    name: str
    kind: ItemKind
    skill: Skill
    front: str
    back: str
    css: str
    default_enabled: bool
    deleted: bool
    seq: int


def _from_row(row: sqlite3.Row) -> Template:
    return Template(
        id=row["id"],
        name=row["name"],
        kind=ItemKind(row["kind"]),
        skill=Skill(row["skill"]),
        front=row["front"],
        back=row["back"],
        css=row["css"],
        default_enabled=bool(row["default_enabled"]),
        deleted=bool(row["deleted"]),
        seq=row["seq"],
    )


def get_template(conn: sqlite3.Connection, template_id: str) -> Template:
    row = conn.execute("SELECT * FROM templates WHERE id = ? AND deleted = 0", (template_id,)).fetchone()
    if row is None:
        raise NotFound(f"template {template_id}")
    return _from_row(row)


def list_templates(conn: sqlite3.Connection) -> list[Template]:
    return [_from_row(r) for r in conn.execute("SELECT * FROM templates WHERE deleted = 0 ORDER BY kind, name")]


def count_templates(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT COUNT(*) FROM templates").fetchone()[0])


def upsert_template(conn: sqlite3.Connection, t: Template) -> None:
    conn.execute(
        "INSERT INTO templates (id, name, kind, skill, front, back, css, default_enabled, deleted, seq) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT (id) DO UPDATE SET name = excluded.name, "
        "kind = excluded.kind, skill = excluded.skill, front = excluded.front, back = excluded.back, "
        "css = excluded.css, default_enabled = excluded.default_enabled, deleted = excluded.deleted, seq = excluded.seq",
        (t.id, t.name, t.kind, t.skill, t.front, t.back, t.css, int(t.default_enabled), int(t.deleted), t.seq),
    )
