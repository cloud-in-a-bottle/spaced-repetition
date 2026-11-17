"""Accumulates the import bundle: decks, items (merging duplicates), the anki card -> new card mapping, and a log of
every decision for REPORT.md."""

import re
from collections import defaultdict

import attr

from tools.anki_import.anki_reader import AnkiCard
from tools.anki_import.anki_reader import AnkiNote

JsonDict = dict[str, object]


@attr.s(auto_attribs=True)
class ItemDraft:
    id: str
    deck: str
    kind: str
    language: str | None
    data: JsonDict
    tags: list[str]
    created_at: int
    templates: list[str]
    anki_note_ids: list[int]
    # anki card id -> template it became
    anki_cards: dict[int, str] = attr.Factory(dict)
    suspended_by_card: dict[int, bool] = attr.Factory(dict)
    original: list[str] = attr.Factory(list)
    flags: list[str] = attr.Factory(list)


@attr.s(auto_attribs=True, frozen=True)
class LogEntry:
    section: str
    message: str
    note_ids: tuple[int, ...]


def slug(text: str) -> str:
    return re.sub(r"[^\w]+", "-", text.strip().casefold()).strip("-")


class Builder:
    def __init__(self) -> None:
        self.decks: dict[str, str] = {}
        self.items: dict[str, ItemDraft] = {}
        self.log: list[LogEntry] = []
        self.skipped: list[LogEntry] = []

    def note(self, section: str, message: str, *notes: AnkiNote) -> None:
        self.log.append(LogEntry(section, message, tuple(n.id for n in notes)))

    def skip(self, reason: str, *notes: AnkiNote) -> None:
        self.skipped.append(LogEntry("skipped", reason, tuple(n.id for n in notes)))

    def deck(self, name: str) -> str:
        return self.decks.setdefault(name, slug(name))

    def add(
        self,
        *,
        item_id: str,
        deck: str,
        kind: str,
        language: str | None,
        data: JsonDict,
        source: AnkiNote,
        cards: list[tuple[AnkiCard, str]],
        tags: list[str] | None = None,
        original: str = "",
        flags: list[str] | None = None,
        extra_templates: list[str] | None = None,
        log_merge: bool = True,
    ) -> ItemDraft:
        """Add an item, or merge into the existing item with this id: cards and history combine, and for lexemes
        differing glosses are joined."""
        existing = self.items.get(item_id)
        if existing is None:
            existing = ItemDraft(
                id=item_id,
                deck=self.deck(deck),
                kind=kind,
                language=language,
                data=data,
                tags=list(tags or []),
                created_at=source.id,
                templates=[],
                anki_note_ids=[],
            )
            self.items[item_id] = existing
        else:
            self._merge_data(existing, data, source, log_merge)
        if source.id not in existing.anki_note_ids:
            existing.anki_note_ids.append(source.id)
        for t in tags or []:
            if t not in existing.tags:
                existing.tags.append(t)
        for card, template in cards:
            existing.anki_cards[card.id] = template
            existing.suspended_by_card[card.id] = card.queue == -1
            if template not in existing.templates:
                existing.templates.append(template)
        for template in extra_templates or []:
            if template not in existing.templates:
                existing.templates.append(template)
        if original:
            existing.original.append(original)
        existing.flags.extend(flags or [])
        return existing

    def _merge_data(self, existing: ItemDraft, data: JsonDict, source: AnkiNote, log_merge: bool) -> None:
        for key in ("gloss", "translation", "back"):
            old, new = existing.data.get(key), data.get(key)
            if isinstance(old, str) and isinstance(new, str) and new and new.casefold() not in old.casefold():
                existing.data[key] = f"{old}; {new}"
        for key in ("alternatives",):
            old_alts, new_alts = existing.data.get(key), data.get(key)
            if isinstance(old_alts, list) and isinstance(new_alts, list):
                existing.data[key] = list(dict.fromkeys([*old_alts, *new_alts]))
        for key in ("notes",):
            old, new = existing.data.get(key), data.get(key)
            if isinstance(old, str) and isinstance(new, str) and new and new not in old:
                existing.data[key] = f"{old}\n{new}".strip()
        if not log_merge:
            return
        existing.flags.append(f"merged duplicate anki note {source.id}")
        self.note("merges", f"{existing.id}: merged note {source.id} into note(s) {existing.anki_note_ids}", source)

    def suspended_cards(self) -> list[tuple[str, str]]:
        """(item, template) pairs to suspend: those where every anki card that became that card was suspended."""
        out = []
        for item in self.items.values():
            by_template: dict[str, list[bool]] = defaultdict(list)
            for card_id, template in item.anki_cards.items():
                by_template[template].append(item.suspended_by_card[card_id])
            out.extend((item.id, t) for t, flags in by_template.items() if flags and all(flags))
        return sorted(out)
