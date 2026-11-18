import sqlite3

import attr

from srs.core.cards import live_templates_of
from srs.core.cards import rerender_item_cards
from srs.core.cards import set_item_cards
from srs.core.cards import tombstone_item_cards
from srs.core.cards import touch_item_cards
from srs.domain.errors import InvalidRequest
from srs.domain.ids import new_id
from srs.domain.item_data import FactData
from srs.domain.item_data import FormData
from srs.domain.item_data import ItemData
from srs.domain.item_data import LexemeData
from srs.domain.item_data import PhraseData
from srs.domain.item_input import ItemInput
from srs.domain.kinds import LANGUAGE_REQUIRED
from srs.domain.kinds import SKILLS_BY_KIND
from srs.domain.kinds import ItemKind
from srs.domain.normalize import lookup_key
from srs.repo.decks import get_deck
from srs.repo.items import Item
from srs.repo.items import copies_of
from srs.repo.items import ephemeral_items_sharing_keys
from srs.repo.items import find_item
from srs.repo.items import forms_of_lexemes
from srs.repo.items import get_item
from srs.repo.items import upsert_item
from srs.repo.settings import load_settings
from srs.repo.templates import Template
from srs.repo.templates import get_template
from srs.repo.templates import list_templates


def _require_text(name: str, value: str) -> None:
    if not value.strip():
        raise InvalidRequest(f"`{name}` must not be empty")


def _require_lexeme(conn: sqlite3.Connection, lexeme_id: str) -> Item:
    lexeme = find_item(conn, lexeme_id)
    if lexeme is None or lexeme.deleted or lexeme.kind != ItemKind.LEXEME:
        raise InvalidRequest(f"{lexeme_id} is not a lexeme")
    return lexeme


@attr.s(auto_attribs=True, frozen=True)
class _Derived:
    language: str | None
    lookup_key: str | None
    lexeme_id: str | None


def _validate(conn: sqlite3.Connection, kind: ItemKind, language: str | None, data: ItemData) -> _Derived:
    if kind in LANGUAGE_REQUIRED and not language:
        raise InvalidRequest(f"items of kind {kind} need a `language`")
    match data:
        case LexemeData():
            _require_text("lemma", data.lemma)
            _require_text("gloss", data.gloss)
            return _Derived(language=language, lookup_key=lookup_key(data.lemma), lexeme_id=None)
        case FormData():
            _require_text("form", data.form)
            lexeme = _require_lexeme(conn, data.lexeme_id)
            if language is not None and language != lexeme.language:
                raise InvalidRequest(f"form language {language} doesn't match its lexeme's ({lexeme.language})")
            return _Derived(language=lexeme.language, lookup_key=lookup_key(data.form), lexeme_id=lexeme.id)
        case PhraseData():
            _require_text("text", data.text)
            _require_text("translation", data.translation)
            for lexeme_id in data.lexeme_ids:
                _require_lexeme(conn, lexeme_id)
            return _Derived(language=language, lookup_key=lookup_key(data.text), lexeme_id=None)
        case FactData():
            _require_text("front", data.front)
            _require_text("back", data.back)
            return _Derived(language=language, lookup_key=None, lexeme_id=None)


def _check_main_deck_refs(conn: sqlite3.Connection, data: ItemData) -> None:
    """Main-deck items can't build on review-set lexemes: the knowledge base would then report words it doesn't
    contain, and throwing the review set away would orphan them."""
    refs = [data.lexeme_id] if isinstance(data, FormData) else data.lexeme_ids if isinstance(data, PhraseData) else []
    for lexeme_id in refs:
        if get_deck(conn, get_item(conn, lexeme_id).deck_id).ephemeral:
            raise InvalidRequest(f"{lexeme_id} is in a review set; add it to a main deck first")


def _touch_review_set_twins(conn: sqlite3.Connection, item: Item, seq: int) -> None:
    """A main-deck item appearing, changing or going away can change which review-set items show as "in a main
    deck"; resend their cards so clients pick that up."""
    if get_deck(conn, item.deck_id).ephemeral:
        return
    for item_id in set(ephemeral_items_sharing_keys(conn, item)) | set(copies_of(conn, item.id)):
        touch_item_cards(conn, item_id, seq)


def _choose_templates(conn: sqlite3.Connection, kind: ItemKind, template_ids: list[str] | None) -> list[Template]:
    if template_ids is None:
        return [t for t in list_templates(conn) if t.kind == kind and t.default_enabled]
    templates = [get_template(conn, tid) for tid in template_ids]
    for t in templates:
        if t.kind != kind:
            raise InvalidRequest(f"template {t.id} is for {t.kind} items, not {kind}")
        if t.skill not in SKILLS_BY_KIND[kind]:
            raise InvalidRequest(f"template {t.id} has skill {t.skill}, which {kind} items don't support")
    return templates


def save_item(conn: sqlite3.Connection, inp: ItemInput, seq: int, now: int) -> Item:
    """Create or update an item and bring its cards in line. Updates can't change an item's kind."""
    data = inp.data()
    deck = get_deck(conn, inp.deck_id)
    derived = _validate(conn, inp.kind, inp.language, data)
    if not deck.ephemeral:
        _check_main_deck_refs(conn, data)
    existing = None if inp.id is None else find_item(conn, inp.id)
    if existing is not None and not existing.deleted:
        _touch_review_set_twins(conn, existing, seq)  # under its old spellings
    if existing is not None and existing.kind != inp.kind:
        raise InvalidRequest(f"item {existing.id} is a {existing.kind}; kind can't change")
    item = Item(
        id=inp.id or new_id(),
        deck_id=inp.deck_id,
        kind=inp.kind,
        language=derived.language,
        data=data,
        lookup_key=derived.lookup_key,
        lexeme_id=derived.lexeme_id,
        tags=inp.tags,
        created_at=(inp.created_at or now) if existing is None else existing.created_at,
        updated_at=now,
        deleted=False,
        seq=seq,
    )
    upsert_item(conn, item)
    settings = load_settings(conn)
    if existing is None or existing.deleted or inp.template_ids is not None:
        set_item_cards(conn, item, _choose_templates(conn, item.kind, inp.template_ids), settings, seq)
    else:
        set_item_cards(conn, item, live_templates_of(conn, item), settings, seq)
    if item.kind == ItemKind.LEXEME:
        for form in forms_of_lexemes(conn, [item.id]):
            if form.language != item.language:
                upsert_item(conn, attr.evolve(form, language=item.language, seq=seq))
            rerender_item_cards(conn, form, seq)
    _touch_review_set_twins(conn, item, seq)
    return item


def delete_item(conn: sqlite3.Connection, item_id: str, seq: int, now: int) -> None:
    item = get_item(conn, item_id)
    if item.kind == ItemKind.LEXEME and forms_of_lexemes(conn, [item.id]):
        raise InvalidRequest(f"lexeme {item_id} still has forms; delete those first")
    _touch_review_set_twins(conn, item, seq)
    upsert_item(conn, attr.evolve(item, deleted=True, updated_at=now, seq=seq))
    tombstone_item_cards(conn, item_id, seq)
