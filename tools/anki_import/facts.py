import re

from tools.anki_import.anki_reader import AnkiNote
from tools.anki_import.builder import Builder
from tools.anki_import.text import clean
from tools.anki_import.text import one_line

_HAM_DECKS = {
    "Amateur Radio::Ham Technician 2022-26": ("Ham Technician", "technician-2022-26"),
    "Amateur Radio::Ham General 2023-27": ("Ham General", "general-2023-27"),
    "Amateur Radio::Ham Extra 2020-24": ("Ham Extra", "extra-2020-24"),
}
IPA_DECK = "English IPA"
_IMG = re.compile(r"<img[^>]*>", re.IGNORECASE)


def import_ham(note: AnkiNote, b: Builder) -> None:
    deck, pool = _HAM_DECKS[note.cards[0].deck]
    f = note.fields
    b.add(
        item_id=f"anki-{note.id}",
        deck=deck,
        kind="fact",
        language=None,
        data={
            "front": f"{clean(f['question'])}\n\n{clean(f['choices'])}",
            "back": f"({one_line(f['answer_letter'])}) {clean(f['answer_text'])}",
            "notes": one_line(f["head"]),
        },
        source=note,
        cards=[(c, "fact-recall") for c in note.cards],
        tags=["ham-radio", pool],
    )


def _had_media(raw: str) -> bool:
    return bool(_IMG.search(raw)) or "[sound:" in raw


def import_ipa(note: AnkiNote, b: Builder) -> None:
    f = note.fields
    if note.notetype == "Full Model":
        # these keep the symbol as text too, so they read fine without the (missing) symbol images and audio
        flags: list[str] = []
        symbol = one_line(f["IPA Symbol (Text)"])
        if not symbol:
            b.skip("IPA note with no text symbol (image only, and media is missing)", note)
            return
        examples, notes = clean(f["Examples"]), clean(f["Notes"])
        b.add(
            item_id=f"anki-{note.id}",
            deck=IPA_DECK,
            kind="fact",
            language="en",
            data={"front": f"IPA symbol: /{symbol}/", "back": examples, "notes": notes},
            source=note,
            cards=[(c, "fact-recall") for c in note.cards if c.ord == 0],
            tags=["ipa"],
            flags=flags,
        )
        reverse = [c for c in note.cards if c.ord == 1]
        if reverse:
            b.add(
                item_id=f"anki-{note.id}-reverse",
                deck=IPA_DECK,
                kind="fact",
                language="en",
                data={"front": f"Which IPA symbol?\n\n{examples}", "back": f"/{symbol}/", "notes": notes},
                source=note,
                cards=[(c, "fact-recall") for c in reverse],
                tags=["ipa"],
                flags=flags,
            )
        return
    back = clean(f["Back"])
    flags = (
        ["its image is missing from the backup; check the text still answers the card"]
        if _had_media(f["Back"])
        else []
    )
    b.add(
        item_id=f"anki-{note.id}",
        deck=IPA_DECK,
        kind="fact",
        language="en",
        data={"front": clean(f["Front"]), "back": back, "notes": clean(f.get("Notes", ""))},
        source=note,
        cards=[(c, "fact-recall") for c in note.cards],
        tags=["ipa"],
        flags=flags,
    )
