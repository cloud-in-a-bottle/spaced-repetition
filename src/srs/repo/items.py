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


def items_by_lookup_keys(conn: sqlite3.Connection, language: str, kind: ItemKind, keys: list[str]) -> list[Item]:
    if not keys:
        return []
    placeholders = ",".join("?" * len(keys))
    rows = conn.execute(
        "SELECT DISTINCT items.* FROM items JOIN item_keys ON item_keys.item_id = items.id "
        f"WHERE items.deleted = 0 AND items.language = ? AND items.kind = ? AND item_keys.key IN ({placeholders})",
        [language, kind, *keys],
    )
    return [_from_row(r) for r in rows]


def items_of_kind(conn: sqlite3.Connection, language: str, kind: ItemKind) -> list[Item]:
    rows = conn.execute(
        "SELECT * FROM items WHERE deleted = 0 AND language = ? AND kind = ? ORDER BY lookup_key", (language, kind)
    )
    return [_from_row(r) for r in rows]


def forms_of_lexemes(conn: sqlite3.Connection, lexeme_ids: list[str]) -> list[Item]:
    if not lexeme_ids:
        return []
    placeholders = ",".join("?" * len(lexeme_ids))
    rows = conn.execute(
        f"SELECT * FROM items WHERE deleted = 0 AND kind = 'form' AND lexeme_id IN ({placeholders})", lexeme_ids
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
