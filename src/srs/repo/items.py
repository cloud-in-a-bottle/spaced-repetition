import json
import sqlite3

import attr

from srs.domain.errors import NotFound
from srs.domain.item_codec import decode_item_data
from srs.domain.item_codec import encode_item_data
from srs.domain.item_data import ItemData
from srs.domain.item_keys import lookup_keys
from srs.domain.kinds import ItemKind


@attr.s(auto_attribs=True, frozen=True)
class Item:
    id: str
    deck_id: str
    kind: ItemKind
    language: str | None
    data: ItemData
    lookup_key: str | None
    lexeme_id: str | None
    tags: list[str]
    created_at: int
    updated_at: int
    deleted: bool
    seq: int


def _from_row(row: sqlite3.Row) -> Item:
    kind = ItemKind(row["kind"])
    return Item(
        id=row["id"],
        deck_id=row["deck_id"],
        kind=kind,
        language=row["language"],
        data=decode_item_data(kind, row["data"]),
        lookup_key=row["lookup_key"],
        lexeme_id=row["lexeme_id"],
        tags=json.loads(row["tags"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        deleted=bool(row["deleted"]),
        seq=row["seq"],
    )


def get_item(conn: sqlite3.Connection, item_id: str) -> Item:
    item = find_item(conn, item_id)
    if item is None or item.deleted:
        raise NotFound(f"item {item_id}")
    return item


def find_item(conn: sqlite3.Connection, item_id: str) -> Item | None:
    """Returns deleted items too, so callers can tell 'new id' apart from 'tombstoned id'."""
    row = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    return None if row is None else _from_row(row)


def list_items(conn: sqlite3.Connection, deck_id: str | None, kind: ItemKind | None, query: str | None) -> list[Item]:
    sql = "SELECT * FROM items WHERE deleted = 0"
    params: list[str] = []
    if deck_id is not None:
        sql += " AND deck_id = ?"
        params.append(deck_id)
    if kind is not None:
        sql += " AND kind = ?"
        params.append(kind)
    if query:
        sql += " AND data LIKE ?"
        params.append(f"%{query}%")
    sql += " ORDER BY created_at DESC"
    return [_from_row(r) for r in conn.execute(sql, params)]


# Restricts an `items` query to main decks (not review sets).
IN_MAIN_DECK = "items.deck_id NOT IN (SELECT id FROM decks WHERE ephemeral = 1)"


def items_by_lookup_keys(conn: sqlite3.Connection, language: str, kind: ItemKind, keys: list[str]) -> list[Item]:
    """Main-deck items spelled like any of `keys`."""
    if not keys:
        return []
    placeholders = ",".join("?" * len(keys))
    # driven from the key index: matching items to a long key list the other way round probes it per item
    rows = conn.execute(
        f"SELECT items.* FROM items WHERE items.id IN (SELECT item_id FROM item_keys WHERE key IN ({placeholders})) "
        f"AND items.deleted = 0 AND {IN_MAIN_DECK} AND items.language = ? AND items.kind = ?",
        [*keys, language, kind],
    )
    return [_from_row(r) for r in rows]


def items_of_kind(conn: sqlite3.Connection, language: str, kind: ItemKind) -> list[Item]:
    """Main-deck items of `kind` in `language`."""
    rows = conn.execute(
        f"SELECT * FROM items WHERE deleted = 0 AND {IN_MAIN_DECK} AND language = ? AND kind = ? ORDER BY lookup_key",
        (language, kind),
    )
    return [_from_row(r) for r in rows]


def forms_of_lexemes(conn: sqlite3.Connection, lexeme_ids: list[str], main_only: bool = False) -> list[Item]:
    if not lexeme_ids:
        return []
    placeholders = ",".join("?" * len(lexeme_ids))
    main = f" AND {IN_MAIN_DECK}" if main_only else ""
    rows = conn.execute(
        f"SELECT * FROM items WHERE deleted = 0{main} AND kind = 'form' AND lexeme_id IN ({placeholders})", lexeme_ids
    )
    return [_from_row(r) for r in rows]


def upsert_item(conn: sqlite3.Connection, item: Item) -> None:
    conn.execute(
        "INSERT INTO items (id, deck_id, kind, language, data, lookup_key, lexeme_id, tags, created_at, updated_at, "
        "deleted, seq) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT (id) DO UPDATE SET "
        "deck_id = excluded.deck_id, kind = excluded.kind, language = excluded.language, data = excluded.data, "
        "lookup_key = excluded.lookup_key, lexeme_id = excluded.lexeme_id, tags = excluded.tags, "
        "updated_at = excluded.updated_at, deleted = excluded.deleted, seq = excluded.seq",
        (
            item.id,
            item.deck_id,
            item.kind,
            item.language,
            encode_item_data(item.data),
            item.lookup_key,
            item.lexeme_id,
            json.dumps(item.tags, ensure_ascii=False),
            item.created_at,
            item.updated_at,
            int(item.deleted),
            item.seq,
        ),
    )
    conn.execute("DELETE FROM item_keys WHERE item_id = ?", (item.id,))
    if not item.deleted:
        conn.executemany(
            "INSERT INTO item_keys (item_id, key) VALUES (?, ?)", [(item.id, k) for k in lookup_keys(item.data)]
        )


def items_in_deck(conn: sqlite3.Connection, deck_id: str) -> list[Item]:
    return [_from_row(r) for r in conn.execute("SELECT * FROM items WHERE deleted = 0 AND deck_id = ?", (deck_id,))]


def main_twin(conn: sqlite3.Connection, item: Item) -> Item | None:
    """The main-deck item a review-set item corresponds to: the copy "add to main deck" made, or else a live main-deck
    item of the same kind and language sharing one of its spellings."""
    row = conn.execute(
        f"SELECT items.* FROM item_copies JOIN items ON items.id = item_copies.item_id "
        f"WHERE item_copies.source_item_id = ? AND items.deleted = 0 AND {IN_MAIN_DECK}",
        (item.id,),
    ).fetchone()
    if row is None and item.language is not None:
        row = conn.execute(
            f"SELECT items.* FROM item_keys AS mine JOIN item_keys AS theirs ON theirs.key = mine.key "
            f"JOIN items ON items.id = theirs.item_id WHERE mine.item_id = ? AND items.deleted = 0 AND {IN_MAIN_DECK} "
            "AND items.kind = ? AND items.language = ? ORDER BY items.created_at LIMIT 1",
            (item.id, item.kind, item.language),
        ).fetchone()
    return None if row is None else _from_row(row)


def ephemeral_items_sharing_keys(conn: sqlite3.Connection, item: Item) -> list[str]:
    """Review-set items spelled like `item` (same kind and language), whose main-deck status `item` may change."""
    rows = conn.execute(
        "SELECT DISTINCT items.id FROM item_keys AS mine JOIN item_keys AS theirs ON theirs.key = mine.key "
        "JOIN items ON items.id = theirs.item_id JOIN decks ON decks.id = items.deck_id "
        "WHERE mine.item_id = ? AND items.deleted = 0 AND decks.ephemeral = 1 AND items.kind = ? "
        "AND items.language IS ?",
        (item.id, item.kind, item.language),
    )
    return [r["id"] for r in rows]


def record_copy(conn: sqlite3.Connection, source_item_id: str, item_id: str) -> None:
    conn.execute(
        "INSERT INTO item_copies (source_item_id, item_id) VALUES (?, ?) "
        "ON CONFLICT (source_item_id) DO UPDATE SET item_id = excluded.item_id",
        (source_item_id, item_id),
    )


def copies_of(conn: sqlite3.Connection, item_id: str) -> list[str]:
    """The review-set items that `item_id` was copied from."""
    return [r[0] for r in conn.execute("SELECT source_item_id FROM item_copies WHERE item_id = ?", (item_id,))]
