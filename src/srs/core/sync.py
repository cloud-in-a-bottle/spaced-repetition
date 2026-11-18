import sqlite3

import attr

from srs.core.cards import replay_card
from srs.domain.errors import InvalidRequest
from srs.domain.schedule import Review
from srs.domain.settings import Settings
from srs.repo.cards import Card
from srs.repo.cards import card_from_row
from srs.repo.changes import current_seq
from srs.repo.decks import Deck
from srs.repo.decks import decks_changed_since
from srs.repo.items import get_item
from srs.repo.items import main_twin
from srs.repo.reviews import find_review
from srs.repo.reviews import insert_review
from srs.repo.settings import load_settings
from srs.repo.settings import settings_seq


def record_reviews(conn: sqlite3.Connection, reviews: list[Review], seq: int, now: int) -> int:
    """Add reviews to the log (ignoring ones already recorded) and replay the cards they touch. Returns how many were
    new. Re-sending a review is harmless, which is what lets clients retry a sync that failed halfway."""
    touched: set[str] = set()
    inserted = 0
    for review in reviews:
        existing = find_review(conn, review.id)
        if existing is not None:
            if existing.card_id != review.card_id:
                raise InvalidRequest(f"review {review.id} was already recorded for a different card")
            continue
        if conn.execute("SELECT 1 FROM cards WHERE id = ?", (review.card_id,)).fetchone() is None:
            raise InvalidRequest(f"review {review.id} is for unknown card {review.card_id}")
        insert_review(conn, review, received_at=now)
        inserted += 1
        touched.add(review.card_id)
    settings = load_settings(conn)
    for card_id in sorted(touched):
        replay_card(conn, card_id, settings, seq)
    return inserted


@attr.s(auto_attribs=True, frozen=True)
class SyncCard:
    """A card as the client stores it: rendered html plus enough item info to file it and schedule it offline."""

    card: Card
    deck_id: str
    item_kind: str
    skill: str
    template_name: str
    # the item's part of speech; a form takes its lexeme's. None for phrases and facts.
    pos: str | None
    # for review-set cards: the main deck holding this item (see main_twin), if any
    main_deck_id: str | None


@attr.s(auto_attribs=True, frozen=True)
class Changes:
    cursor: int
    settings: Settings | None
    decks: list[Deck]
    cards: list[SyncCard]


def _main_deck_of(conn: sqlite3.Connection, item_id: str, cache: dict[str, str | None]) -> str | None:
    if item_id not in cache:
        twin = main_twin(conn, get_item(conn, item_id))
        cache[item_id] = None if twin is None else twin.deck_id
    return cache[item_id]


def changes_since(conn: sqlite3.Connection, cursor: int) -> Changes:
    rows = conn.execute(
        "SELECT cards.*, items.deck_id AS item_deck_id, items.kind AS item_kind, templates.skill AS template_skill, "
        "templates.name AS template_name, decks.ephemeral AS item_ephemeral, "
        "COALESCE(json_extract(items.data, '$.pos'), json_extract(lexemes.data, '$.pos')) AS item_pos "
        "FROM cards JOIN items ON items.id = cards.item_id "
        "LEFT JOIN items AS lexemes ON lexemes.id = items.lexeme_id "
        "JOIN templates ON templates.id = cards.template_id "
        "JOIN decks ON decks.id = items.deck_id "
        "WHERE cards.seq > ? ORDER BY cards.seq",
        (cursor,),
    ).fetchall()
    twins: dict[str, str | None] = {}
    cards = [
        SyncCard(
            card=card_from_row(r),
            deck_id=r["item_deck_id"],
            item_kind=r["item_kind"],
            skill=r["template_skill"],
            template_name=r["template_name"],
            pos=r["item_pos"],
            main_deck_id=_main_deck_of(conn, r["item_id"], twins) if r["item_ephemeral"] else None,
        )
        for r in rows
    ]
    return Changes(
        cursor=current_seq(conn),
        settings=load_settings(conn) if settings_seq(conn) > cursor or cursor == 0 else None,
        decks=decks_changed_since(conn, cursor),
        cards=cards,
    )
