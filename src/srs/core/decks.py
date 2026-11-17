import sqlite3

import attr

from srs.domain.errors import InvalidRequest
from srs.domain.ids import new_id
from srs.repo.decks import Deck
from srs.repo.decks import find_deck_by_name
from srs.repo.decks import get_deck
from srs.repo.decks import insert_deck
from srs.repo.decks import update_deck


def create_deck(conn: sqlite3.Connection, name: str, seq: int, now: int, deck_id: str | None = None) -> Deck:
    name = name.strip()
    if not name:
        raise InvalidRequest("deck name must not be empty")
    if find_deck_by_name(conn, name) is not None:
        raise InvalidRequest(f"a deck named {name!r} already exists")
    deck = Deck(id=deck_id or new_id(), name=name, created_at=now, deleted=False, seq=seq)
    insert_deck(conn, deck)
    return deck


def rename_deck(conn: sqlite3.Connection, deck_id: str, name: str, seq: int) -> Deck:
    deck = get_deck(conn, deck_id)
    name = name.strip()
    other = find_deck_by_name(conn, name)
    if not name or (other is not None and other.id != deck_id):
        raise InvalidRequest(f"invalid or duplicate deck name {name!r}")
    deck = attr.evolve(deck, name=name, seq=seq)
    update_deck(conn, deck)
    return deck


def delete_deck(conn: sqlite3.Connection, deck_id: str, seq: int) -> None:
    deck = get_deck(conn, deck_id)
    if conn.execute("SELECT 1 FROM items WHERE deck_id = ? AND deleted = 0", (deck_id,)).fetchone():
        raise InvalidRequest("deck isn't empty; move or delete its items first")
    update_deck(conn, attr.evolve(deck, deleted=True, seq=seq))
