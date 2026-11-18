import sqlite3

import attr

from srs.domain.errors import NotFound


@attr.s(auto_attribs=True, frozen=True)
class Deck:
    id: str
    name: str
    created_at: int
    deleted: bool
    seq: int
    # a review set: studied, but its items aren't part of what the knowledge service reports
    ephemeral: bool = False
    # where a review set's "add to main deck" copies items; None picks the main deck with most items in the language
    promote_to: str | None = None


def _from_row(row: sqlite3.Row) -> Deck:
    return Deck(
        id=row["id"],
        name=row["name"],
        created_at=row["created_at"],
        deleted=bool(row["deleted"]),
        seq=row["seq"],
        ephemeral=bool(row["ephemeral"]),
        promote_to=row["promote_to"],
    )


def get_deck(conn: sqlite3.Connection, deck_id: str) -> Deck:
    row = conn.execute("SELECT * FROM decks WHERE id = ? AND deleted = 0", (deck_id,)).fetchone()
    if row is None:
        raise NotFound(f"deck {deck_id}")
    return _from_row(row)


def find_deck_by_name(conn: sqlite3.Connection, name: str) -> Deck | None:
    row = conn.execute("SELECT * FROM decks WHERE name = ? AND deleted = 0", (name,)).fetchone()
    return None if row is None else _from_row(row)


def list_decks(conn: sqlite3.Connection) -> list[Deck]:
    return [_from_row(r) for r in conn.execute("SELECT * FROM decks WHERE deleted = 0 ORDER BY name")]


def decks_changed_since(conn: sqlite3.Connection, seq: int) -> list[Deck]:
    return [_from_row(r) for r in conn.execute("SELECT * FROM decks WHERE seq > ? ORDER BY seq", (seq,))]


def insert_deck(conn: sqlite3.Connection, deck: Deck) -> None:
    conn.execute(
        "INSERT INTO decks (id, name, created_at, deleted, seq, ephemeral, promote_to) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (deck.id, deck.name, deck.created_at, int(deck.deleted), deck.seq, int(deck.ephemeral), deck.promote_to),
    )


def update_deck(conn: sqlite3.Connection, deck: Deck) -> None:
    conn.execute(
        "UPDATE decks SET name = ?, deleted = ?, seq = ?, ephemeral = ?, promote_to = ? WHERE id = ?",
        (deck.name, int(deck.deleted), deck.seq, int(deck.ephemeral), deck.promote_to, deck.id),
    )


def largest_main_deck(conn: sqlite3.Connection, language: str | None) -> str | None:
    """The main deck (not a review set) with the most words (lexemes) in `language`: where new words go by default.
    Counting words, not items, so a deck of conjugations doesn't win."""
    row = conn.execute(
        "SELECT items.deck_id FROM items JOIN decks ON decks.id = items.deck_id "
        "WHERE items.deleted = 0 AND decks.deleted = 0 AND decks.ephemeral = 0 AND items.language IS ? "
        "AND items.kind = 'lexeme' "
        "GROUP BY items.deck_id ORDER BY count(*) DESC LIMIT 1",
        (language,),
    ).fetchone()
    return None if row is None else str(row["deck_id"])
