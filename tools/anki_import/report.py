import csv
from collections import Counter
from collections import defaultdict
from pathlib import Path

from tools.anki_import.builder import Builder
from tools.anki_import.builder import ItemDraft
from tools.anki_import.reviews import ReviewStats

_RULES = """\
## What the import does

- **Spanish vocab** (decks 1-5, plus one Spanish note filed under Mandarin "Mine") → `lexeme` items in deck
  *Spanish*.
  - Which side is Spanish is decided per note by word frequencies (wordfreq) + accents; early cards were written
    English-first. The anki card that showed Spanish first becomes the **recognize** card, the other **produce**,
    so review history lands on the right skill.
  - Part of speech comes from the deck (Nouns / Verbs / Prepositions) or, for Adjectives-and-Adverbs and Other,
    from `overrides.toml` (`[spanish.terms]`), which I filled in word by word.
  - Nouns: the article is split off into `features.article` / `features.gender` (and `number=plural` for los/las);
    the lemma is the bare noun. The default templates show the article with the lemma.
  - Spelling: missing accents and typos fixed per `[spanish.spelling]` / `[spanish.term_fixes]` (listed below).
  - Multi-word entries that aren't nouns/verbs are tagged `expression` (or `construction` for patterns like
    "más … que").
  - Notes with the same lemma + part of speech are merged into one item; their histories are combined and
    differing glosses joined with "; ".
- **KOFI Ultimate Conjugation** → `form` items in deck *Spanish conjugation*, linked to the verb lexeme.
  Features (mood, tense, person, number, polarity, pronoun for tú-vs-vos) come from the deck's tags; the answer is
  the form, and "a | b" answers keep b as an alternative spelling. Cards become **produce** (conjugate). KOFI's
  "El verbo en él debe es …" cards become the **recognize** card of the matching form. The deck's per-form notes
  are kept in `notes`; its context sentences are not (the features say the same thing). Only the
  irregular_form / regular_form / regular_spelling_change tags are kept.
- **conjugated verbs** (hand-made) → single forms ("saber present yo" → sé) become forms; whole paradigms
  ("ser, present tense") become facts.
- **HSK** → `lexeme` items (language `zh`) in deck *Mandarin*: lemma = simplified, traditional as an alternative
  spelling, pinyin + HSK level as features, the example sentence in notes. HSK's part-of-speech labels are mapped
  per `[mandarin.pos]`; the original label stays as `features.pos_detail`. Only a recognize card (the deck had
  only that one).
- **Amateur Radio** → `fact` items, one deck per question pool; the question id goes in notes.
- **English IPA** → `fact` items. The backup has no media, so the symbol images and audio are gone; cards that
  relied on them are flagged.
- **Skipped**: Korean and Chinese Pinyin decks (as asked); anything listed under "Skipped" below.
- **Scheduling**: review history comes across from the anki review log and FSRS replays it, using the FSRS
  parameters from your anki preset. Due dates therefore come from FSRS replay, not anki's stored due dates.
  Manual reschedules are dropped, and a "forget" drops the history before it. A card is suspended only if every
  anki card merged into it was suspended.
"""


def _summary(item: ItemDraft) -> tuple[str, str, str]:
    d = item.data
    if item.kind == "lexeme":
        return str(d["lemma"]), str(d["pos"]), str(d["gloss"])
    if item.kind == "form":
        return str(d["form"]), "", " · ".join(str(v) for v in d["features"].values())  # type: ignore[union-attr]
    return str(d["front"]).replace("\n", " ")[:120], "", str(d["back"]).replace("\n", " ")[:120]


def write_items_csv(b: Builder, review_counts: Counter[str], suspended: set[tuple[str, str]], path: Path) -> None:
    deck_names = {v: k for k, v in b.decks.items()}
    with path.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(
            [
                "item_id",
                "deck",
                "kind",
                "language",
                "text",
                "pos",
                "meaning",
                "features",
                "alternatives",
                "tags",
                "cards",
                "suspended",
                "reviews",
                "anki_note_ids",
                "original",
                "flags",
            ]
        )
        for item in sorted(b.items.values(), key=lambda i: (i.deck, i.kind, i.id)):
            text, pos, meaning = _summary(item)
            features = item.data.get("features", {})
            w.writerow(
                [
                    item.id,
                    deck_names[item.deck],
                    item.kind,
                    item.language or "",
                    text,
                    pos,
                    meaning,
                    "; ".join(f"{k}={v}" for k, v in features.items()) if isinstance(features, dict) else "",
                    ", ".join(item.data.get("alternatives", [])),  # type: ignore[arg-type]
                    ", ".join(item.tags),
                    ", ".join(item.templates),
                    ", ".join(t for t in item.templates if (item.id, t) in suspended),
                    review_counts[item.id],
                    " ".join(str(n) for n in item.anki_note_ids),
                    " | ".join(item.original),
                    " | ".join(item.flags),
                ]
            )


def write_report(b: Builder, stats: ReviewStats, suspended: set[tuple[str, str]], path: Path, source: str) -> None:
    lines = [f"# Anki import record\n\nSource: `{source}`\n", _RULES, "## Result\n"]
    by_deck: dict[str, Counter[str]] = defaultdict(Counter)
    deck_names = {v: k for k, v in b.decks.items()}
    for item in b.items.values():
        by_deck[deck_names[item.deck]][item.kind] += 1
    lines.append("| deck | items | cards | suspended |\n|---|---|---|---|")
    for deck in sorted(by_deck):
        items = [i for i in b.items.values() if deck_names[i.deck] == deck]
        cards = sum(len(i.templates) for i in items)
        susp = sum(1 for i in items for t in i.templates if (i.id, t) in suspended)
        kinds = ", ".join(f"{n} {k}" for k, n in sorted(by_deck[deck].items()))
        lines.append(f"| {deck} | {kinds} | {cards} | {susp} |")
    lines.append(
        f"\nReviews imported: **{stats.imported}** (dropped {stats.dropped_manual} manual/reschedule entries and "
        f"{stats.dropped_before_reset} entries before a 'forget').\n"
    )
    flagged = [i for i in b.items.values() if any(not f.startswith("merged duplicate") for f in i.flags)]
    lines.append(f"## Needs a look ({len(flagged)} items)\n")
    for item in sorted(flagged, key=lambda i: i.id):
        text, _, meaning = _summary(item)
        why = "; ".join(f for f in item.flags if not f.startswith("merged duplicate"))
        lines.append(f"- `{item.id}` {text} — {meaning}: {why}")
    sections: dict[str, list[str]] = defaultdict(list)
    for entry in b.log:
        ids = f" (note {', '.join(map(str, entry.note_ids))})" if entry.note_ids else ""
        sections[entry.section].append(f"- {entry.message}{ids}")
    titles = {
        "spelling": "Spelling fixes",
        "gender": "Gender corrections",
        "merges": "Merged duplicates",
        "conjugation": "Conjugation decisions",
        "dropped": "Dropped cards",
    }
    for key, title in titles.items():
        if sections.get(key):
            lines.append(f"\n## {title} ({len(sections[key])})\n")
            lines.extend(sections[key])
    lines.append(f"\n## Skipped ({len(b.skipped)})\n")
    lines.extend(f"- {e.message} (note {', '.join(map(str, e.note_ids))})" for e in b.skipped)
    path.write_text("\n".join(lines) + "\n")
