import sqlite3

import attr

from srs.core.decks import create_deck
from srs.core.decks import rename_deck
from srs.core.items import save_item
from srs.core.sync import record_reviews
from srs.domain.errors import InvalidRequest
from srs.domain.errors import NotFound
from srs.domain.item_input import ItemInput
from srs.domain.kinds import ItemKind
from srs.domain.schedule import Rating
from srs.domain.schedule import Review
from srs.repo.cards import cards_for_items
from srs.repo.cards import upsert_card
from srs.repo.decks import find_deck_by_name
from srs.repo.decks import get_deck


@attr.s(auto_attribs=True, frozen=True)
class ImportDeck:
    id: str
    name: str


@attr.s(auto_attribs=True, frozen=True)
class ImportReview:
    """Past reviews are addressed by (item, template), since card ids are assigned by the server."""

    id: str
    item_id: str
    template_id: str
    rating: int
    reviewed_at: int
    duration_ms: int | None = None


@attr.s(auto_attribs=True, frozen=True)
class ImportCardRef:
    item_id: str
    template_id: str


@attr.s(auto_attribs=True, frozen=True)
class ImportBundle:
    """Everything needed to bring a collection over from elsewhere (eg a converted anki deck).

    Every entity carries its own id, so importing the same bundle twice updates in place rather than duplicating.
    Items must have ids. Lexemes are saved before forms and phrases, so those can refer to lexemes in the same bundle.
    """

    decks: list[ImportDeck] = attr.Factory(list)
    items: list[ItemInput] = attr.Factory(list)
    reviews: list[ImportReview] = attr.Factory(list)
    # cards of the bundle's items to suspend; the bundle's other cards are unsuspended
    suspended: list[ImportCardRef] = attr.Factory(list)


@attr.s(auto_attribs=True, frozen=True)
class ImportResult:
    decks: int
    items: int
    new_reviews: int


_KIND_ORDER = {ItemKind.LEXEME: 0, ItemKind.FACT: 1, ItemKind.FORM: 2, ItemKind.PHRASE: 3}


def _upsert_deck(conn: sqlite3.Connection, deck: ImportDeck, seq: int, now: int) -> None:
    try:
        existing = get_deck(conn, deck.id)
    except NotFound:
        same_name = find_deck_by_name(conn, deck.name)
        if same_name is not None:
            raise InvalidRequest(f"deck {deck.name!r} already exists with id {same_name.id}") from None
        create_deck(conn, deck.name, seq, now, deck_id=deck.id)
        return
    if existing.name != deck.name:
        rename_deck(conn, deck.id, deck.name, seq)


def import_bundle(conn: sqlite3.Connection, bundle: ImportBundle, seq: int, now: int) -> ImportResult:
    for deck in bundle.decks:
        _upsert_deck(conn, deck, seq, now)
    for inp in sorted(bundle.items, key=lambda i: _KIND_ORDER[i.kind]):
        if inp.id is None:
            raise InvalidRequest("imported items need an `id`")
        save_item(conn, inp, seq, now)

    cards = {(c.item_id, c.template_id): c for c in cards_for_items(conn, [i.id for i in bundle.items if i.id])}
    to_suspend = {(s.item_id, s.template_id) for s in bundle.suspended}
    missing = to_suspend - cards.keys()
    if missing:
        raise InvalidRequest(f"can't suspend cards that don't exist: {sorted(missing)[:5]}")
    for key, card in cards.items():
        if not card.deleted and card.suspended != (key in to_suspend):
            upsert_card(conn, attr.evolve(card, suspended=key in to_suspend, seq=seq))
    card_ids = {key: c.id for key, c in cards.items()}
    reviews = []
    for r in bundle.reviews:
        card_id = card_ids.get((r.item_id, r.template_id))
        if card_id is None:
            raise InvalidRequest(f"review {r.id}: item {r.item_id} has no card for template {r.template_id}")
        if r.rating not in (1, 2, 3, 4):
            raise InvalidRequest(f"review {r.id}: rating must be 1-4")
        reviews.append(
            Review(
                id=r.id,
                card_id=card_id,
                rating=Rating(r.rating),
                reviewed_at=r.reviewed_at,
                duration_ms=r.duration_ms,
                source="import",
            )
        )
    new_reviews = record_reviews(conn, reviews, seq, now)
    return ImportResult(decks=len(bundle.decks), items=len(bundle.items), new_reviews=new_reviews)
