"""Convert an anki backup into an srs import bundle, plus a record of every decision for review.

    uv run python -m tools.anki_import.main <backup.colpkg> <out_dir>

Writes <out_dir>/bundle.json (POST to /api/import), settings.json (PUT to /api/settings), REPORT.md and items.csv.
"""

import json
import sys
from collections import Counter
from pathlib import Path

from tools.anki_import.anki_reader import read_colpkg
from tools.anki_import.builder import Builder
from tools.anki_import.facts import import_ham
from tools.anki_import.facts import import_ipa
from tools.anki_import.mandarin import import_hsk
from tools.anki_import.overrides import load_overrides
from tools.anki_import.report import write_items_csv
from tools.anki_import.report import write_report
from tools.anki_import.reviews import build_reviews
from tools.anki_import.spanish_conjugation import KOFI_NOTETYPE
from tools.anki_import.spanish_conjugation import ensure_verb_lexemes
from tools.anki_import.spanish_conjugation import import_conjugated_verbs
from tools.anki_import.spanish_conjugation import import_kofi
from tools.anki_import.spanish_vocab import import_spanish_vocab
from tools.anki_import.spanish_vocab import is_spanish_vocab

SKIP_DECK_PREFIXES = ("Korean", "Chinese Pinyin")


def convert(colpkg: Path, out_dir: Path) -> None:
    ov = load_overrides()
    col = read_colpkg(colpkg)
    b = Builder()
    kofi_notes = []
    verbs_needed: set[str] = set()
    anchor = None
    for note in col.notes:
        if not note.cards:
            continue
        decks = {c.deck for c in note.cards}
        if all(d.startswith(SKIP_DECK_PREFIXES) for d in decks):
            continue
        if note.notetype == KOFI_NOTETYPE:
            kofi_notes.append(note)
        elif is_spanish_vocab(note):
            import_spanish_vocab(note, b, ov)
            anchor = anchor or note
        elif "Spanish::conjugated verbs" in decks:
            infinitive = import_conjugated_verbs(note, b, ov)
            if infinitive:
                verbs_needed.add(infinitive)
        elif note.notetype == "HSK":
            import_hsk(note, b, ov)
        elif note.notetype == "Amateur Radio Pool Question":
            import_ham(note, b)
        elif any(d.startswith("English IPA") for d in decks):
            import_ipa(note, b)
        else:
            b.skip(f"no rule for notetype {note.notetype!r} in {sorted(decks)}", note)
    verbs_needed |= import_kofi(kofi_notes, b, ov)
    assert anchor is not None
    ensure_verb_lexemes(verbs_needed, b, ov, anchor)

    reviews, stats = build_reviews(col.reviews, b)
    suspended = set(b.suspended_cards())
    bundle = {
        "decks": [{"id": deck_id, "name": name} for name, deck_id in b.decks.items()],
        "items": [
            {
                "id": item.id,
                "deck_id": item.deck,
                "kind": item.kind,
                "language": item.language,
                "tags": item.tags,
                item.kind: item.data,
                "template_ids": item.templates,
                "created_at": item.created_at,
            }
            for item in b.items.values()
        ],
        "reviews": reviews,
        "suspended": [{"item_id": i, "template_id": t} for i, t in sorted(suspended)],
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "bundle.json").write_text(json.dumps(bundle, ensure_ascii=False))
    (out_dir / "settings.json").write_text(json.dumps(ov.settings, indent=2))
    review_counts = Counter(str(r["item_id"]) for r in reviews)
    write_items_csv(b, review_counts, suspended, out_dir / "items.csv")
    write_report(b, stats, suspended, out_dir / "REPORT.md", colpkg.name)
    print(f"{len(b.items)} items, {len(reviews)} reviews, {len(suspended)} suspended cards, {len(b.skipped)} skipped")


if __name__ == "__main__":
    convert(Path(sys.argv[1]), Path(sys.argv[2]))
