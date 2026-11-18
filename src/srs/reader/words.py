"""What the reader knows about each word: its status (from the deck, the owner's marks and the review sets, with the
dictionary mapping inflections to lemmas) and the details shown when you click it."""

import json
import re
import sqlite3
from collections import defaultdict

import attr

from srs.dictionary.store import DictEntry
from srs.dictionary.store import Dictionary
from srs.domain.kinds import PartOfSpeech
from srs.domain.normalize import lookup_key
from srs.domain.schedule import CardState
from srs.knowledge.models import LexemeKnowledge
from srs.knowledge.query import lookup_words
from srs.reader.conjugation import english_form
from srs.reader.text_formats import Token

# A deck word counts as known for reading if FSRS puts the chance of recalling it at least this high.
KNOWN_RECALL = 0.8


class Status:
    KNOWN = "known"  # in a main deck and recalled well: no highlight
    LEARNING = "learning"  # in a main deck but weak, never studied, or suspended
    NEW = "new"  # not in any deck: highlighted
    IGNORED = "ignored"  # marked by the owner as not worth learning (names, foreign words)
    NAME = "name"  # looks like a proper noun: no highlight


def reading_status(lx: LexemeKnowledge) -> str:
    """Recognition is what matters for reading, so the best recall over the word's cards decides; words learned only
    through their conjugations count by those."""
    studied = [s for s in lx.skills if s.reps > 0] or [s for f in lx.forms for s in f.skills if s.reps > 0]
    if not studied:
        return Status.LEARNING
    best = max(s.retrievability for s in studied)
    in_review = any(s.state == CardState.REVIEW for s in studied)
    return Status.KNOWN if in_review and best >= KNOWN_RECALL else Status.LEARNING


def marks(conn: sqlite3.Connection, language: str, keys: list[str]) -> dict[str, str]:
    result = {}
    for i in range(0, len(keys), 500):
        chunk = keys[i : i + 500]
        rows = conn.execute(
            f"SELECT key, status FROM word_marks WHERE language = ? AND key IN ({','.join('?' * len(chunk))})",
            [language, *chunk],
        )
        result.update({r["key"]: r["status"] for r in rows})
    return result


def roots_of(dictionary: Dictionary | None, word: str) -> list[str]:
    """Where a "known" mark for `word` goes: its root forms per the dictionary (itself first if it's a headword
    too), so knowing "abandona" covers abandonar and all its forms, like deck cards do. Words the dictionary
    doesn't know are their own root."""
    key = lookup_key(word)
    lemmas = dictionary.lemmas(key) if dictionary is not None else set()
    return sorted(lemmas, key=lambda k: (k != key, k)) or [key]


def default_roots(dictionary: Dictionary | None, word: str) -> list[str]:
    """The roots "known" goes on when nobody picks: a word that's a headword itself is its own root ("para", not
    parar and parir; "abierto", not abrir), and only a pure inflection spreads to what it inflects ("zarpó" ->
    zarpar, "fuese" -> ir and ser)."""
    roots = roots_of(dictionary, word)
    return roots[:1] if roots[0] == lookup_key(word) else roots


def mark_words(
    conn: sqlite3.Connection,
    dictionary: Dictionary | None,
    language: str,
    words: list[str],
    status: str | None,
    now: int,
    roots: list[str] | None = None,
) -> None:
    """`known` marks the words' roots (see default_roots, unless `roots` picks); `ignored` marks the exact
    spellings (names, foreign words); None clears both the spellings and all their roots."""
    exact = sorted({lookup_key(w) for w in words})
    if status == "ignored":
        set_marks(conn, language, exact, status, now)
    elif status == "known":
        targets = {lookup_key(r) for r in roots} if roots else {r for w in words for r in default_roots(dictionary, w)}
        set_marks(conn, language, sorted(targets), status, now)
    else:
        set_marks(conn, language, sorted({*exact, *(r for w in words for r in roots_of(dictionary, w))}), None, now)


def set_marks(conn: sqlite3.Connection, language: str, keys: list[str], status: str | None, now: int) -> None:
    """Low level: set or clear marks on exactly these keys."""
    keys = sorted({lookup_key(k) for k in keys})
    if status is None:
        conn.executemany("DELETE FROM word_marks WHERE language = ? AND key = ?", [(language, k) for k in keys])
        return
    conn.executemany(
        "INSERT INTO word_marks (language, key, status, updated_at) VALUES (?, ?, ?, ?) "
        "ON CONFLICT (language, key) DO UPDATE SET status = excluded.status, updated_at = excluded.updated_at",
        [(language, k, status, now) for k in keys],
    )


def _review_set_items(conn: sqlite3.Connection, language: str, keys: list[str]) -> dict[str, list[sqlite3.Row]]:
    """Review-set lexemes (directly, or via a form) spelled like each key."""
    result: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for i in range(0, len(keys), 500):
        chunk = keys[i : i + 500]
        rows = conn.execute(
            "SELECT item_keys.key AS key, coalesce(lexemes.id, items.id) AS item_id, "
            "coalesce(lexemes.data, items.data) AS data, items.deck_id AS deck_id "
            "FROM item_keys JOIN items ON items.id = item_keys.item_id JOIN decks ON decks.id = items.deck_id "
            "LEFT JOIN items AS lexemes ON lexemes.id = items.lexeme_id "
            "WHERE decks.ephemeral = 1 AND items.deleted = 0 AND items.language = ? AND items.kind IN ('lexeme', 'form') "
            f"AND item_keys.key IN ({','.join('?' * len(chunk))})",
            [language, *chunk],
        )
        for r in rows:
            result[r["key"]].append(r)
    return result


@attr.s(auto_attribs=True, frozen=True)
class WordContext:
    """Everything the deck, marks and review sets say about a set of words, gathered in a few queries."""

    candidates: dict[str, set[str]]  # word key -> itself plus dictionary lemmas
    deck: dict[str, list[LexemeKnowledge]]  # candidate key -> main-deck lexemes matching it
    matched_by_form: dict[str, set[str]]  # candidate key -> lexeme ids it matched as an inflected form
    marks: dict[str, str]
    review_sets: dict[str, list[sqlite3.Row]]


def gather(
    conn: sqlite3.Connection, dictionary: Dictionary | None, language: str, keys: list[str], now: int
) -> WordContext:
    candidates = {k: {k} | (dictionary.lemmas(k) if dictionary else set()) for k in keys}
    everything = sorted(set().union(*candidates.values())) if candidates else []
    deck: dict[str, list[LexemeKnowledge]] = {}
    by_form: dict[str, set[str]] = {}
    for i in range(0, len(everything), 4000):
        for wl in lookup_words(conn, language, everything[i : i + 4000], now):
            deck[wl.word] = [m.lexeme for m in wl.matches]
            by_form[wl.word] = {m.lexeme.item_id for m in wl.matches if m.matched_form_ids and not m.matched_lemma}
    return WordContext(
        candidates=candidates,
        deck=deck,
        matched_by_form=by_form,
        marks=marks(conn, language, everything),
        review_sets=_review_set_items(conn, language, everything),
    )


def known_root(ctx: WordContext, key: str) -> str | None:
    """The root a word is marked known through, if any."""
    return next((c for c in sorted(ctx.candidates[key]) if c != key and ctx.marks.get(c) == Status.KNOWN), None)


def status_of(ctx: WordContext, key: str) -> str:
    lexemes = [lx for c in ctx.candidates[key] for lx in ctx.deck.get(c, [])]
    statuses = {reading_status(lx) for lx in lexemes}
    if Status.KNOWN in statuses:
        return Status.KNOWN
    if statuses:
        return Status.LEARNING
    if key in ctx.marks:  # this spelling: known or ignored
        return ctx.marks[key]
    if known_root(ctx, key) is not None:
        return Status.KNOWN
    # review sets are throwaway cramming decks, not knowledge: a word only in one is still new (the word panel
    # lists the review set)
    return Status.NEW


def word_statuses(
    conn: sqlite3.Connection,
    dictionary: Dictionary | None,
    language: str,
    tokens: list[Token],
    now: int,
) -> dict[str, str]:
    """Status per distinct word in `tokens`. A word in no deck that's always capitalized is taken for a name when the
    dictionary has no common word spelled that way, or when it's capitalized mid-sentence too (so "Vega" in "Lope de
    Vega" counts, but a capitalized sentence-initial word doesn't)."""
    capitalized: dict[str, bool] = {}
    mid_sentence: dict[str, bool] = {}
    sentence_start = True
    for t in tokens:
        if t.key is None:
            if any(ch in t.text for ch in ".!?¿¡…-\n") or not t.text.strip():
                sentence_start = sentence_start or any(ch in t.text for ch in ".!?¿¡…-\n")
            continue
        if len(t.text) > 1 and t.text.isupper():  # SHOUTING or a speaker label: says nothing about names
            capitalized.setdefault(t.key, True)
            mid_sentence.setdefault(t.key, False)
            sentence_start = False
            continue
        cap = t.text[:1].isupper()
        capitalized[t.key] = capitalized.get(t.key, True) and cap
        mid_sentence[t.key] = mid_sentence.get(t.key, False) or (cap and not sentence_start)
        sentence_start = False
    keys = sorted(capitalized)
    ctx = gather(conn, dictionary, language, keys, now)
    result = {}
    for key in keys:
        status = status_of(ctx, key)
        if status == Status.NEW and capitalized[key]:
            # always capitalized, and either not a common word or capitalized mid-sentence too ("Lope de Vega")
            common = dictionary.lemmas(key) if dictionary is not None else {key}
            looks_like_name = not common or mid_sentence[key]
            if looks_like_name:
                status = Status.NAME
        result[key] = status
    return result


@attr.s(auto_attribs=True, frozen=True)
class DeckMatch:
    item_id: str
    deck_id: str | None
    lemma: str
    pos: str
    gloss: str
    # a reading status (see Status), or "review_set" for review-set entries
    status: str
    recall: float
    # how the clicked word reached it: "word" (its lemma or one of its forms) or "dictionary" (via the lemma
    # the dictionary says it's an inflection of)
    via: str


@attr.s(auto_attribs=True, frozen=True)
class Suggestion:
    """A prefilled lexeme for "add to deck"."""

    lemma: str
    pos: str
    gloss: str
    gender: str | None


@attr.s(auto_attribs=True, frozen=True)
class WordDetails:
    word: str
    key: str
    status: str
    # `known` / `ignored` for this spelling, or `known` through a root (see `mark_root`)
    mark: str | None
    mark_root: str | None
    # where "I know this" would put the mark (see roots_of); several for words like "casas" (casa / casar)
    roots: list[str]
    deck: list[DeckMatch]
    review_sets: list[DeckMatch]
    dictionary: list[DictEntry]
    # entries for the lemmas `dictionary` says the word is an inflection of
    lemma_entries: list[DictEntry]
    suggestion: Suggestion | None


def _with_english(entry: DictEntry, lemma_entries: list[DictEntry]) -> DictEntry:
    """Fill in English renderings of verb forms ("I renounced"), from the lemma's English sense."""
    if entry.pos != "verb" or not entry.form_of:
        return entry
    senses_of: dict[str, list[str]] = {}
    for le in lemma_entries:
        if le.pos == "verb":
            senses_of.setdefault(lookup_key(le.word), le.senses)
    forms = [
        attr.evolve(f, english=english_form(f.description, senses_of.get(lookup_key(f.lemma), [])))
        for f in entry.form_of
    ]
    return attr.evolve(entry, form_of=forms)


def _first_gloss(senses: list[str]) -> str:
    gloss = re.sub(r"^\([^)]*\)\s*", "", senses[0]) if senses else ""
    return gloss[:120]


def _suggest(word: str, entries: list[DictEntry], lemma_entries: list[DictEntry]) -> Suggestion | None:
    allowed = {p.value for p in PartOfSpeech}
    # the word's own headword first ("silencio" the noun, not a form of silenciar), else its lemma's
    for e in [*entries, *lemma_entries]:
        if e.senses and e.pos in allowed and e.pos != PartOfSpeech.PROPER_NOUN:
            return Suggestion(lemma=e.word, pos=e.pos, gloss=_first_gloss(e.senses), gender=e.gender)
    return Suggestion(lemma=word.lower(), pos=PartOfSpeech.OTHER.value, gloss="", gender=None) if word else None


def word_details(
    conn: sqlite3.Connection, dictionary: Dictionary | None, language: str, word: str, now: int
) -> WordDetails:
    return word_details_many(conn, dictionary, language, [word], now)[lookup_key(word)]


def word_details_many(
    conn: sqlite3.Connection, dictionary: Dictionary | None, language: str, words: list[str], now: int
) -> dict[str, WordDetails]:
    """Details for many words at once (eg every word of a text, for reading offline), keyed by lookup key, with
    the deck and mark lookups batched."""
    by_key = {lookup_key(w): w for w in words}
    ctx = gather(conn, dictionary, language, sorted(by_key), now)
    lexeme_ids = sorted({lx.item_id for lxs in ctx.deck.values() for lx in lxs})
    deck_ids: dict[str, str] = {}
    for i in range(0, len(lexeme_ids), 500):
        chunk = lexeme_ids[i : i + 500]
        rows = conn.execute(f"SELECT id, deck_id FROM items WHERE id IN ({','.join('?' * len(chunk))})", chunk)
        deck_ids.update({r["id"]: r["deck_id"] for r in rows})
    return {key: _details(ctx, dictionary, deck_ids, key, word) for key, word in by_key.items()}


def _details(
    ctx: WordContext, dictionary: Dictionary | None, deck_ids: dict[str, str], key: str, word: str
) -> WordDetails:
    deck, seen = [], set()
    for c in sorted(ctx.candidates[key], key=lambda c: c != key):  # the word itself first
        for lx in ctx.deck.get(c, []):
            if lx.item_id in seen:
                continue
            seen.add(lx.item_id)
            deck.append(
                DeckMatch(
                    item_id=lx.item_id,
                    deck_id=deck_ids.get(lx.item_id),
                    lemma=lx.lemma,
                    pos=str(lx.pos),
                    gloss=lx.gloss,
                    status=reading_status(lx),
                    recall=round(max([s.retrievability for s in lx.skills] or [lx.recall_probability]), 3),
                    via="word" if c == key else "dictionary",
                )
            )
    review_sets, seen = [], set()
    for c in ctx.candidates[key]:
        for r in ctx.review_sets.get(c, []):
            if r["item_id"] in seen:
                continue
            seen.add(r["item_id"])
            data = json.loads(r["data"])
            review_sets.append(
                DeckMatch(
                    item_id=r["item_id"],
                    deck_id=r["deck_id"],
                    lemma=data.get("lemma", ""),
                    pos=data.get("pos", ""),
                    gloss=data.get("gloss", ""),
                    status="review_set",
                    recall=0.0,
                    via="word" if c == key else "dictionary",
                )
            )
    entries = dictionary.entries(word) if dictionary else []
    lemma_words = sorted({f.lemma for e in entries for f in e.form_of})
    lemma_entries = [le for lw in lemma_words for le in (dictionary.entries(lw) if dictionary else []) if le.senses]
    entries = [_with_english(e, lemma_entries) for e in entries]
    return WordDetails(
        word=word,
        key=key,
        status=status_of(ctx, key),
        mark=ctx.marks.get(key) or ("known" if known_root(ctx, key) else None),
        mark_root=None if key in ctx.marks else known_root(ctx, key),
        roots=roots_of(dictionary, word),
        deck=deck,
        review_sets=review_sets,
        dictionary=entries,
        lemma_entries=lemma_entries,
        suggestion=_suggest(word, entries, lemma_entries),
    )
