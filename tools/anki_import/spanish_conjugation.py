"""The 'Ultimate Spanish Conjugation' (KOFI) deck and the small hand-made 'conjugated verbs' deck -> form items."""

import re

import attr

from tools.anki_import.anki_reader import AnkiNote
from tools.anki_import.builder import Builder
from tools.anki_import.builder import JsonDict
from tools.anki_import.builder import slug
from tools.anki_import.overrides import Overrides
from tools.anki_import.text import clean
from tools.anki_import.text import one_line

DECK = "Spanish conjugation"
KOFI_NOTETYPE = "Ultimate Spanish Conjugation [Ankiweb]"

# KOFI tense tag -> features (and a short key for ids)
_TENSES: dict[str, tuple[str, dict[str, str]]] = {
    "presente": ("pres", {"mood": "indicative", "tense": "present"}),
    "imperfecto": ("impf", {"mood": "indicative", "tense": "imperfect"}),
    "indefinido": ("pret", {"mood": "indicative", "tense": "preterite"}),
    "futuro": ("fut", {"mood": "indicative", "tense": "future"}),
    "condicional": ("cond", {"mood": "conditional"}),
    "subjuntivo_presente": ("subj-pres", {"mood": "subjunctive", "tense": "present"}),
    "subjuntivo_pasado": ("subj-impf", {"mood": "subjunctive", "tense": "imperfect"}),
    "subjuntivo_futuro": ("subj-fut", {"mood": "subjunctive", "tense": "future"}),
    "imperativo": ("imp", {"mood": "imperative"}),
    "gerundio": ("ger", {"verb_form": "gerund"}),
    "participio": ("part", {"verb_form": "participle"}),
}
_PERSONS: dict[str, tuple[str, dict[str, str]]] = {
    "yo": ("1s", {"person": "1st", "number": "singular"}),
    "tú_vos": ("2s", {"person": "2nd", "number": "singular"}),
    "él_ella_usted": ("3s", {"person": "3rd", "number": "singular"}),
    "nosotros": ("1p", {"person": "1st", "number": "plural"}),
    "vosotros": ("2p", {"person": "2nd", "number": "plural"}),
    "ellos_ellas_ustedes": ("3p", {"person": "3rd", "number": "plural"}),
}
# pronoun shown in KOFI's "El verbo en <pronoun> <form>" cards
_PRONOUN_PERSON = {
    "yo": "yo",
    "tú": "tú_vos",
    "vos": "tú_vos",
    "él": "él_ella_usted",
    "ella": "él_ella_usted",
    "usted": "él_ella_usted",
    "nosotros": "nosotros",
    "vosotros": "vosotros",
    "ellos": "ellos_ellas_ustedes",
    "ellas": "ellos_ellas_ustedes",
    "ustedes": "ellos_ellas_ustedes",
}
_KEEP_TAGS = {"irregular_form", "regular_form", "regular_spelling_change"}
_INFINITIVE_TAG = re.compile(r"^[a-záéíóúñü]*(ar|er|ir|ír)(se)?$")
_CLOZE = re.compile(r"\{\{c1::(.*?)\}\}", re.DOTALL)
_HILITE = re.compile(r'<span class="cloze_hilite">(.*?)</span>')
_CLITIC = re.compile(r"^(me|te|se|nos|os) (.+)$")


def lexeme_id(infinitive: str) -> str:
    return f"es-verb-{slug(infinitive)}"


@attr.s(auto_attribs=True, frozen=True)
class _Parsed:
    infinitive: str
    key: str
    features: dict[str, str]
    forms: list[str]


def _infinitive(note: AnkiNote) -> str | None:
    candidates = [t for t in note.tags if _INFINITIVE_TAG.match(t)]
    return candidates[0] if len(candidates) == 1 else None


def _person(tags: set[str]) -> tuple[str, dict[str, str]] | None:
    persons = [p for p in _PERSONS if p in tags]
    if not persons:
        return None
    key, features = _PERSONS[persons[0]]
    features = dict(features)
    # tú and vos have separate cards where their forms differ (some presents and imperatives)
    if "vos" in tags:
        return key + "-vos", {**features, "pronoun": "vos"}
    if "tú" in tags:
        return key + "-tu", {**features, "pronoun": "tú"}
    return key, features


def _parse_kofi(note: AnkiNote) -> _Parsed | str:
    tags = set(note.tags)
    infinitive = _infinitive(note)
    if infinitive is None:
        return f"no single infinitive tag in {sorted(tags)}"
    tense = next((t for t in _TENSES if t in tags), None)
    if tense is None:
        return "no tense tag"
    tense_key, features = _TENSES[tense]
    features = dict(features)
    key = tense_key
    if "negative_imperativo" in tags:
        features["polarity"] = "negative"
        key += "-neg"
    if tense not in ("gerundio", "participio"):
        person = _person(tags)
        if person is not None:
            key += "-" + person[0]
            features.update(person[1])
        else:
            # impersonal "hay"
            key += "-impers"
            features.update({"person": "3rd", "number": "singular", "usage": "impersonal"})
    m = _CLOZE.search(note.fields["Prompt"])
    if m is None:
        return "no cloze"
    answer = clean(m.group(1).split("::")[0])
    forms = [f.strip() for f in answer.split("|") if f.strip()]
    return _Parsed(infinitive=infinitive, key=key, features=features, forms=forms)


def _form_data(parsed: _Parsed, note: AnkiNote) -> JsonDict:
    alternatives = parsed.forms[1:]
    m = _CLITIC.match(parsed.forms[0])
    if m:
        # reflexive "me endeudo": also findable as plain "endeudo"
        alternatives.append(m.group(2))
    return {
        "lexeme_id": lexeme_id(parsed.infinitive),
        "form": parsed.forms[0],
        "features": parsed.features,
        "gloss": "",
        "notes": clean(note.fields.get("Notes", "")),
        "alternatives": list(dict.fromkeys(alternatives)),
    }


def import_kofi(notes: list[AnkiNote], b: Builder, ov: Overrides) -> set[str]:
    """Returns the infinitives used, so lexemes can be ensured for them."""
    infinitives: set[str] = set()
    infinitive_cards: list[AnkiNote] = []
    for note in notes:
        if "orientation" in note.tags:
            b.skip("KOFI orientation card (deck instructions, not content)", note)
            continue
        if "infinitivo" in note.tags:
            infinitive_cards.append(note)
            continue
        parsed = _parse_kofi(note)
        if isinstance(parsed, str):
            b.skip(f"KOFI card not understood: {parsed}: {one_line(note.fields['Prompt'])[:80]!r}", note)
            continue
        infinitives.add(parsed.infinitive)
        b.add(
            item_id=f"es-form-{slug(parsed.infinitive)}-{parsed.key}",
            deck=DECK,
            kind="form",
            language=None,
            data=_form_data(parsed, note),
            source=note,
            cards=[(c, "form-produce") for c in note.cards],
            tags=sorted(_KEEP_TAGS & set(note.tags)),
            original=one_line(note.fields["Prompt"]),
        )
    for note in infinitive_cards:
        _import_infinitive_card(note, b)
    return infinitives


def _import_infinitive_card(note: AnkiNote, b: Builder) -> None:
    """KOFI's "El verbo en <él debe> es {{deber}}" cards ask for the infinitive of a shown form: that's the
    recognize skill of the form, so they become a form-recognize card on the matching form item."""
    infinitive = _infinitive(note)
    hilite = _HILITE.search(note.fields["Prompt"])
    if infinitive is None or hilite is None:
        b.skip("KOFI infinitive card not understood", note)
        return
    pronoun, _, form = one_line(hilite.group(1)).partition(" ")
    person_tag = _PRONOUN_PERSON.get(pronoun)
    matches = [
        item
        for item in b.items.values()
        if item.kind == "form"
        and item.data["lexeme_id"] == lexeme_id(infinitive)
        and set(form.split(" | ")) & {item.data["form"], *item.data["alternatives"]}  # type: ignore[misc]
        and (person_tag is None or item.data["features"] == {**item.data["features"], **_PERSONS[person_tag][1]})  # type: ignore[dict-item]
    ]
    # prefer the present indicative when the same spelling is several forms
    matches.sort(key=lambda i: (i.data["features"].get("tense") != "present", i.id))  # type: ignore[union-attr]
    if not matches:
        b.skip(f"KOFI infinitive card: no form item for {pronoun} {form} ({infinitive})", note)
        return
    item = matches[0]
    b.add(
        item_id=item.id,
        deck=DECK,
        kind="form",
        language=None,
        data=dict(item.data),
        source=note,
        cards=[(c, "form-recognize") for c in note.cards],
        original=one_line(note.fields["Prompt"]),
        log_merge=False,
    )
    b.note("conjugation", f"'{pronoun} {form} → {infinitive}' became the form-recognize card of {item.id}", note)


# --- the hand-made "conjugated verbs" deck: "saber present yo" -> "sé", or whole paradigms


_SINGLE = re.compile(r"^(\w+),? (present|preterite) (yo|tú)$")
_PARADIGM = re.compile(r"^(\w+), (present|preterite) tense$")
_SIMPLE_TENSES = {
    "present": ("pres", {"mood": "indicative", "tense": "present"}),
    "preterite": ("pret", {"mood": "indicative", "tense": "preterite"}),
}


def import_conjugated_verbs(note: AnkiNote, b: Builder, ov: Overrides) -> str | None:
    """Returns the verb's infinitive, or None if the note was turned into a fact / skipped."""
    front, back = one_line(note.fields["Front"]), one_line(note.fields["Back"])
    special = ov.conjugated_notes.get(front)
    if special is not None:
        if "vocab" in special:
            from tools.anki_import.spanish_vocab import import_spanish_vocab  # noqa: PLC0415

            import_spanish_vocab(note, b, ov, pos_hint=str(special["vocab"]))
            b.note("conjugation", f"'{front}' is vocabulary, not a conjugation; filed as a {special['vocab']}", note)
            return None
        infinitive = str(special["lexeme"])
        b.add(
            item_id=f"es-form-{slug(infinitive)}-{special['key']}",
            deck=DECK,
            kind="form",
            language=None,
            data={
                "lexeme_id": lexeme_id(infinitive),
                "form": front,
                "features": special["features"],
                "gloss": "",
                "notes": "",
                "alternatives": [],
            },
            source=note,
            # here the front is the form: ord 0 asks form -> what it is (recognize)
            cards=[(c, "form-recognize" if c.ord == 0 else "form-produce") for c in note.cards],
            original=f"{front} → {back}",
        )
        return infinitive
    single = _SINGLE.match(front)
    if single:
        infinitive, tense, pronoun = single.groups()
        tense_key, features = _SIMPLE_TENSES[tense]
        person_key, person_features = _PERSONS["yo" if pronoun == "yo" else "tú_vos"]
        if pronoun == "tú":
            person_key, person_features = person_key + "-tu", {**person_features, "pronoun": "tú"}
        data: JsonDict = {
            "lexeme_id": lexeme_id(infinitive),
            "form": back,
            "features": {**features, **person_features},
            "gloss": "",
            "notes": "",
            "alternatives": [],
        }
        # ord 0 asks "saber present yo" -> "sé" (produce), ord 1 the reverse (recognize)
        b.add(
            item_id=f"es-form-{slug(infinitive)}-{tense_key}-{person_key}",
            deck=DECK,
            kind="form",
            language=None,
            data=data,
            source=note,
            cards=[(c, "form-produce" if c.ord == 0 else "form-recognize") for c in note.cards],
            original=f"{front} → {back}",
        )
        return infinitive
    if _PARADIGM.match(front):
        b.add(
            item_id=f"anki-{note.id}",
            deck=DECK,
            kind="fact",
            language="es",
            data={"front": front, "back": back, "notes": ""},
            source=note,
            # a fact only has one card; the reverse direction (whole paradigm -> name) is dropped
            cards=[(c, "fact-recall") for c in note.cards if c.ord == 0],
            tags=["conjugation-table"],
            original=f"{front} → {back}",
        )
        b.note("conjugation", f"full paradigm '{front}' kept as a fact (it tests the whole table, not one form)", note)
        if any(c.ord == 1 for c in note.cards):
            b.note("dropped", f"reverse card of paradigm '{front}' dropped (facts have one direction)", note)
        return None
    b.skip(f"conjugated-verbs note not understood: {front!r} → {back!r}", note)
    return None


def ensure_verb_lexemes(infinitives: set[str], b: Builder, ov: Overrides, anchor: AnkiNote) -> None:
    """Forms need their lexeme. Verbs not in the vocab decks get one with no cards, glossed from overrides."""
    for infinitive in sorted(infinitives):
        if lexeme_id(infinitive) in b.items:
            continue
        gloss = ov.conjugation_only_verbs.get(infinitive)
        if gloss is None:
            raise ValueError(f"no gloss for conjugation-only verb {infinitive!r}; add it to overrides.toml")
        draft = b.add(
            item_id=lexeme_id(infinitive),
            deck="Spanish",
            kind="lexeme",
            language="es",
            data={"lemma": infinitive, "pos": "verb", "gloss": gloss, "features": {}, "notes": "", "alternatives": []},
            source=anchor,
            cards=[],
            tags=["conjugation-only"],
            flags=["created for its conjugations; gloss written by the importer"],
        )
        draft.anki_note_ids.clear()
        b.note("conjugation", f"created verb lexeme '{infinitive}' ({gloss}) with no cards, for its forms")
