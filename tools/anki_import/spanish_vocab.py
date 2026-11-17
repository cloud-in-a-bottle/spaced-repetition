import re

from wordfreq import zipf_frequency

from tools.anki_import.anki_reader import AnkiNote
from tools.anki_import.builder import Builder
from tools.anki_import.builder import JsonDict
from tools.anki_import.builder import slug
from tools.anki_import.overrides import Overrides
from tools.anki_import.text import one_line

DECK = "Spanish"
POS_BY_DECK = {"Spanish::1: Nouns": "noun", "Spanish::2: Verbs": "verb", "Spanish::5: prepositions": "preposition"}
_ARTICLE = re.compile(r"^(el/la|la/el|el|la|los|las)\s+(.+)$")
_TRAILING_NOTE = re.compile(r"^(.*?)\s*[\(\[]([^\)\]]*)[\)\]]\s*$")
_WORD = re.compile(r"[a-záéíóúñü]+")


def is_spanish_vocab(note: AnkiNote) -> bool:
    decks = {c.deck for c in note.cards}
    if any(d.startswith("Spanish::") for d in decks):
        return not any("KOFI" in d or "conjugated verbs" in d for d in decks)
    # one Spanish note filed under the personal Mandarin subdeck
    return note.notetype.startswith("Basic") and "Mandarin: Vocabulary::Mine" in decks


def _spanishness(text: str) -> float:
    words = _WORD.findall(text.lower())
    if not words:
        return 0.0
    es = sum(zipf_frequency(w, "es") for w in words) / len(words)
    en = sum(zipf_frequency(w, "en") for w in words) / len(words)
    return es - en + (2.0 if re.search(r"[áéíóúñü¿¡]", text.lower()) else 0.0)


def _fix_spelling(text: str, ov: Overrides) -> tuple[str, list[str]]:
    changes = []

    def repl(m: re.Match[str]) -> str:
        word = m.group(0)
        fixed = ov.spelling.get(word)
        if fixed is None:
            return word
        changes.append(f"{word} → {fixed}")
        return fixed

    return _WORD.sub(repl, text), changes


def _templates_for(note: AnkiNote, spanish_front: bool) -> list[tuple[int, str]]:
    # "Basic (and reversed card)": ord 0 asks Front -> Back, ord 1 asks Back -> Front
    forward = "lexeme-recognize" if spanish_front else "lexeme-produce"
    backward = "lexeme-produce" if spanish_front else "lexeme-recognize"
    return [(c.id, forward if c.ord == 0 else backward) for c in note.cards]


def import_spanish_vocab(note: AnkiNote, b: Builder, ov: Overrides, pos_hint: str | None = None) -> None:
    front, back = one_line(note.fields["Front"]), one_line(note.fields["Back"])
    diff = _spanishness(front) - _spanishness(back)
    spanish_front = diff > -1.0
    es, en = (front, back) if spanish_front else (back, front)
    flags = []
    if abs(diff) < 1.5:
        flags.append(f"guessed which side is Spanish (score {diff:+.1f}): {es!r}")
    if not es or not en:
        b.skip(f"empty side: {front!r} / {back!r}", note)
        return

    as_written = es
    if es in ov.term_fixes:
        es = ov.term_fixes[es]
        b.note("spelling", f"{as_written!r} → {es!r} (in context)", note)

    deck = next(iter(c.deck for c in note.cards))
    override = ov.terms.get(as_written)
    pos = override.pos if override else (pos_hint or POS_BY_DECK.get(deck))
    if pos is None:
        pos = "other"
        flags.append("no part of speech decided; filed as 'other'")
    notes: list[str] = []
    features: dict[str, str] = {}
    alternatives: list[str] = list(override.alternatives) if override else []
    tags = list(override.tags) if override else []
    if override and override.note:
        notes.append(override.note)
    if override and override.gender:
        features["gender"] = override.gender

    lemma = es
    if override and override.lemma:
        lemma = override.lemma
    else:
        m = _TRAILING_NOTE.match(lemma)
        if m and m.group(1):
            lemma, extra = m.group(1), m.group(2)
            notes.append(f"({extra})")
        if pos == "noun":
            m = _ARTICLE.match(lemma)
            if m:
                article, lemma = m.group(1), m.group(2)
                features.update(_noun_features(article, lemma, ov, b, note))
            elif "gender" not in features:
                flags.append("noun without article; gender unknown")
    if not (override and override.lemma):
        lemma = lemma.lower()
    lemma, changes = _fix_spelling(lemma, ov)
    for change in changes:
        b.note("spelling", f"{as_written!r}: {change}", note)
    if " " in lemma and pos not in ("noun", "verb") and "construction" not in tags and "expression" not in tags:
        tags.append("expression")

    data: JsonDict = {
        "lemma": lemma,
        "pos": pos,
        "gloss": en,
        "features": features,
        "notes": "\n".join(notes),
        "alternatives": alternatives,
    }
    cards = [(c, t) for c in note.cards for cid, t in _templates_for(note, spanish_front) if cid == c.id]
    b.add(
        item_id=f"es-{pos}-{slug(lemma)}",
        deck=DECK,
        kind="lexeme",
        language="es",
        data=data,
        source=note,
        cards=cards,
        tags=tags,
        original=f"{front} → {back}",
        flags=flags,
    )


def _noun_features(article: str, lemma: str, ov: Overrides, b: Builder, note: AnkiNote) -> dict[str, str]:
    if article in ("el/la", "la/el"):
        return {"gender": "masculine/feminine", "article": "el/la"}
    gender = "masculine" if article in ("el", "los") else "feminine"
    if article == "el" and lemma in ov.feminine_with_el:
        gender = "feminine"
        b.note("gender", f"'el {lemma}' is feminine (el before stressed a-)", note)
    features = {"gender": gender, "article": article}
    if article in ("los", "las"):
        features["number"] = "plural"
    return features
