import sqlite3

import attr

from srs.domain.ids import new_id
from srs.domain.settings import Settings
from srs.render.context import render_context
from srs.render.engine import render_card
from srs.repo.cards import Card
from srs.repo.cards import cards_for_items
from srs.repo.cards import get_card
from srs.repo.cards import upsert_card
from srs.repo.items import Item
from srs.repo.items import get_item
from srs.repo.reviews import reviews_for_card
from srs.repo.templates import Template
from srs.repo.templates import get_template
from srs.scheduling.replay import replay


def _lexeme_for(conn: sqlite3.Connection, item: Item) -> Item | None:
    return None if item.lexeme_id is None else get_item(conn, item.lexeme_id)


def set_item_cards(
    conn: sqlite3.Connection, item: Item, templates: list[Template], settings: Settings, seq: int, now: int
) -> None:
    """Make the item's live cards exactly those for `templates`, (re)rendering each one.

    Cards for other templates are tombstoned rather than removed, so re-enabling a template brings back its history.
    """
    wanted = {t.id: t for t in templates}
    existing = {c.template_id: c for c in cards_for_items(conn, [item.id])}
    lexeme = _lexeme_for(conn, item)
    context = render_context(item, lexeme)
    for template_id, old in existing.items():
        if template_id not in wanted and not old.deleted:
            upsert_card(conn, attr.evolve(old, deleted=True, seq=seq))
    for template in templates:
        rendered = render_card(template, context)
        card = existing.get(template.id)
        if card is None:
            card = Card(
                id=new_id(),
                item_id=item.id,
                template_id=template.id,
                created_at=now,
                suspended=False,
                deleted=False,
                front_html="",
                back_html="",
                schedule=replay(now, [], settings),
                seq=seq,
            )
        upsert_card(
            conn,
            attr.evolve(card, deleted=False, front_html=rendered.front_html, back_html=rendered.back_html, seq=seq),
        )


def live_templates_of(conn: sqlite3.Connection, item: Item) -> list[Template]:
    return [get_template(conn, c.template_id) for c in cards_for_items(conn, [item.id]) if not c.deleted]


def rerender_item_cards(conn: sqlite3.Connection, item: Item, seq: int) -> None:
    context = render_context(item, _lexeme_for(conn, item))
    for card in cards_for_items(conn, [item.id]):
        if card.deleted:
            continue
        rendered = render_card(get_template(conn, card.template_id), context)
        upsert_card(conn, attr.evolve(card, front_html=rendered.front_html, back_html=rendered.back_html, seq=seq))


def tombstone_item_cards(conn: sqlite3.Connection, item_id: str, seq: int) -> None:
    for card in cards_for_items(conn, [item_id]):
        if not card.deleted:
            upsert_card(conn, attr.evolve(card, deleted=True, seq=seq))


def touch_item_cards(conn: sqlite3.Connection, item_id: str, seq: int) -> None:
    """Re-send the item's cards to clients, eg because the item moved deck (clients file cards under decks)."""
    for card in cards_for_items(conn, [item_id]):
        upsert_card(conn, attr.evolve(card, seq=seq))


def replay_card(conn: sqlite3.Connection, card_id: str, settings: Settings, seq: int) -> None:
    card = get_card(conn, card_id)
    schedule = replay(card.created_at, reviews_for_card(conn, card_id), settings)
    upsert_card(conn, attr.evolve(card, schedule=schedule, seq=seq))
