"""Review sets: decks for cramming (say, the words of one TV episode) that stay out of the knowledge base until you
pick individual items to add to a main deck."""

import sqlite3

import attr

from srs.core.cards import replay_card
from srs.core.cards import touch_item_cards
from srs.core.items import save_item
from srs.domain.errors import InvalidRequest
from srs.domain.ids import new_id
from srs.domain.item_data import FactData
from srs.domain.item_data import FormData
from srs.domain.item_data import LexemeData
from srs.domain.item_data import PhraseData
from srs.domain.item_input import ItemInput
from srs.repo.cards import cards_for_items
from srs.repo.decks import Deck
from srs.repo.decks import get_deck
from srs.repo.decks import largest_main_deck
from srs.repo.decks import list_decks
from srs.repo.items import Item
from srs.repo.items import get_item
from srs.repo.items import main_twin
from srs.repo.items import record_copy
from srs.repo.reviews import insert_review
from srs.repo.reviews import reviews_for_card
from srs.repo.settings import load_settings
from srs.repo.templates import list_templates


@attr.s(auto_attribs=True, frozen=True)
class PromoteResult:
    item: Item
    # False when the item was already in a main deck (by an earlier promote, or spelled the same)
    created: bool


def _target_deck(conn: sqlite3.Connection, review_set: Deck, item: Item, deck_id: str | None) -> Deck:
    chosen = deck_id or review_set.promote_to
    if chosen is not None:
        deck = get_deck(conn, chosen)
        if deck.ephemeral:
            raise InvalidRequest(f"{deck.name} is a review set, not a main deck")
        return deck
    largest = largest_main_deck(conn, item.language)
    if largest is not None:
        return get_deck(conn, largest)
    main = [d for d in list_decks(conn) if not d.ephemeral]
    if not main:
        raise InvalidRequest("there's no main deck to add it to")
    return main[0]


def _item_input(item: Item, deck_id: str, template_ids: list[str]) -> ItemInput:
    data = item.data
    return ItemInput(
        deck_id=deck_id,
        kind=item.kind,
        language=item.language,
        tags=item.tags,
        lexeme=data if isinstance(data, LexemeData) else None,
        form=data if isinstance(data, FormData) else None,
        phrase=data if isinstance(data, PhraseData) else None,
        fact=data if isinstance(data, FactData) else None,
        id=new_id(),
        template_ids=template_ids,
        # keeps new-card order, and lets the copied reviews replay from the start
        created_at=item.created_at,
    )


def promote_item(conn: sqlite3.Connection, item_id: str, deck_id: str | None, seq: int, now: int) -> PromoteResult:
    """Copy a review-set item into a main deck. Cards it shares with the review-set item bring their review history
    along (it's real practice, and a card with none waits behind the daily new-card limit). The review-set item stays, and
    from then on the two are scheduled independently. Promoting something already in a main deck is a no-op."""
    item = get_item(conn, item_id)
    review_set = get_deck(conn, item.deck_id)
    if not review_set.ephemeral:
        raise InvalidRequest(f"{item_id} is already in a main deck")
    twin = main_twin(conn, item)
    if twin is not None:
        return PromoteResult(item=twin, created=False)

    source_cards = [c for c in cards_for_items(conn, [item.id]) if not c.deleted]
    target = _target_deck(conn, review_set, item, deck_id)
    # the kind's usual cards (a review set may only practise some, eg recognition before watching a show), plus any
    # others the review-set item had
    template_ids = [t.id for t in list_templates(conn) if t.kind == item.kind and t.default_enabled]
    template_ids += [c.template_id for c in source_cards if c.template_id not in template_ids]
    copy = save_item(conn, _item_input(item, target.id, template_ids), seq, now)
    record_copy(conn, item.id, copy.id)

    settings = load_settings(conn)
    copied_by_template = {c.template_id: c for c in cards_for_items(conn, [copy.id])}
    for source in source_cards:
        dest = copied_by_template[source.template_id]
        for r in reviews_for_card(conn, source.id):
            insert_review(conn, attr.evolve(r, id=f"{r.id}@{dest.id}", card_id=dest.id, source="review-set"), now)
        replay_card(conn, dest.id, settings, seq)
    touch_item_cards(conn, item.id, seq)  # so clients see it's in a main deck now
    return PromoteResult(item=copy, created=True)
