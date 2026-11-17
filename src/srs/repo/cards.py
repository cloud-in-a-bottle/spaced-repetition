import sqlite3

import attr

from srs.domain.errors import NotFound
from srs.domain.schedule import CardState
from srs.domain.schedule import Schedule


@attr.s(auto_attribs=True, frozen=True)
class Card:
    id: str
    item_id: str
    template_id: str
    created_at: int
    suspended: bool
    deleted: bool
    front_html: str
    back_html: str
    schedule: Schedule
    seq: int


def card_from_row(row: sqlite3.Row) -> Card:
    return Card(
        id=row["id"],
        item_id=row["item_id"],
        template_id=row["template_id"],
        created_at=row["created_at"],
        suspended=bool(row["suspended"]),
        deleted=bool(row["deleted"]),
        front_html=row["front_html"],
        back_html=row["back_html"],
        schedule=Schedule(
            state=CardState(row["state"]),
            step=row["step"],
            stability=row["stability"],
            difficulty=row["difficulty"],
            due=row["due"],
            last_review=row["last_review"],
            reps=row["reps"],
            lapses=row["lapses"],
        ),
        seq=row["seq"],
    )


def get_card(conn: sqlite3.Connection, card_id: str) -> Card:
    row = conn.execute("SELECT * FROM cards WHERE id = ?", (card_id,)).fetchone()
    if row is None:
        raise NotFound(f"card {card_id}")
    return card_from_row(row)


def cards_for_items(conn: sqlite3.Connection, item_ids: list[str]) -> list[Card]:
    """All cards of the given items, including deleted ones (a deleted card keeps its id and review history)."""
    if not item_ids:
        return []
    placeholders = ",".join("?" * len(item_ids))
    return [card_from_row(r) for r in conn.execute(f"SELECT * FROM cards WHERE item_id IN ({placeholders})", item_ids)]


def cards_for_template(conn: sqlite3.Connection, template_id: str) -> list[Card]:
    return [card_from_row(r) for r in conn.execute("SELECT * FROM cards WHERE template_id = ?", (template_id,))]


def all_card_ids(conn: sqlite3.Connection) -> list[str]:
    return [r[0] for r in conn.execute("SELECT id FROM cards")]


def upsert_card(conn: sqlite3.Connection, card: Card) -> None:
    s = card.schedule
    conn.execute(
        "INSERT INTO cards (id, item_id, template_id, created_at, suspended, deleted, front_html, back_html, state, "
        "step, stability, difficulty, due, last_review, reps, lapses, seq) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT (id) DO UPDATE SET "
        "suspended = excluded.suspended, deleted = excluded.deleted, front_html = excluded.front_html, "
        "back_html = excluded.back_html, state = excluded.state, step = excluded.step, "
        "stability = excluded.stability, difficulty = excluded.difficulty, due = excluded.due, "
        "last_review = excluded.last_review, reps = excluded.reps, lapses = excluded.lapses, seq = excluded.seq",
        (
            card.id,
            card.item_id,
            card.template_id,
            card.created_at,
            int(card.suspended),
            int(card.deleted),
            card.front_html,
            card.back_html,
            s.state,
            s.step,
            s.stability,
            s.difficulty,
            s.due,
            s.last_review,
            s.reps,
            s.lapses,
            card.seq,
        ),
    )
