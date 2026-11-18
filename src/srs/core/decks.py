import sqlite3

import attr

from srs.core.items import delete_item
from srs.domain.errors import InvalidRequest
from srs.domain.ids import new_id
from srs.domain.kinds import ItemKind
from srs.repo.decks import Deck
from srs.repo.decks import find_deck_by_name
from srs.repo.decks import get_deck
from srs.repo.decks import insert_deck
from srs.repo.decks import list_decks
from srs.repo.decks import update_deck
from srs.repo.items import items_in_deck


def _check_promote_to(conn: sqlite3.Connection, ephemeral: bool, promote_to: str | None) -> None:
    if promote_to is None:
        return
    if not ephemeral:
        raise InvalidRequest("only review sets have a `promote_to` deck")
    if get_deck(conn, promote_to).ephemeral:
        raise InvalidRequest("`promote_to` must be a main deck, not a review set")


def create_deck(
    conn: sqlite3.Connection,
    name: str,
    seq: int,
    now: int,
    deck_id: str | None = None,
    ephemeral: bool = False,
    promote_to: str | None = None,
) -> Deck:
    name = name.strip()
    if not name:
        raise InvalidRequest("deck name must not be empty")
    if find_deck_by_name(conn, name) is not None:
        raise InvalidRequest(f"a deck named {name!r} already exists")
    _check_promote_to(conn, ephemeral, promote_to)
    deck = Deck(
        id=deck_id or new_id(),
        name=name,
        created_at=now,
        deleted=False,
        seq=seq,
        ephemeral=ephemeral,
        promote_to=promote_to,
    )
    insert_deck(conn, deck)
    return deck


def update_deck_settings(conn: sqlite3.Connection, deck_id: str, name: str, promote_to: str | None, seq: int) -> Deck:
    """Rename a deck and (for a review set) change where its items get promoted. Whether a deck is a review set is
    fixed at creation: flipping it would silently add or remove its items from the knowledge base."""
    deck = get_deck(conn, deck_id)
    name = name.strip()
    other = find_deck_by_name(conn, name)
    if not name or (other is not None and other.id != deck_id):
        raise InvalidRequest(f"invalid or duplicate deck name {name!r}")
    _check_promote_to(conn, deck.ephemeral, promote_to)
    deck = attr.evolve(deck, name=name, promote_to=promote_to, seq=seq)
    update_deck(conn, deck)
    return deck


def delete_deck(conn: sqlite3.Connection, deck_id: str, seq: int, now: int) -> None:
    """Main decks must be emptied first. A review set is meant to be thrown away, so its items go with it (copies
    already added to a main deck stay)."""
    deck = get_deck(conn, deck_id)
    if deck.ephemeral:
        items = items_in_deck(conn, deck_id)
        for item in sorted(items, key=lambda i: i.kind != ItemKind.FORM):  # forms before their lexemes
            delete_item(conn, item.id, seq, now)
    elif conn.execute("SELECT 1 FROM items WHERE deck_id = ? AND deleted = 0", (deck_id,)).fetchone():
        raise InvalidRequest("deck isn't empty; move or delete its items first")
    for d in list_decks(conn):
        if d.promote_to == deck_id:
            update_deck(conn, attr.evolve(d, promote_to=None, seq=seq))
    update_deck(conn, attr.evolve(get_deck(conn, deck_id), deleted=True, seq=seq))
