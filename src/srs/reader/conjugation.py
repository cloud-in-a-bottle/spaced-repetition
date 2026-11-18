"""Verb help for the reader: whether a verb is regular, and what an inflected form means in English, from
Wiktionary's descriptions ("first-person singular preterite indicative of renunciar" -> "I renounced")."""

import re
import unicodedata

import attr
from lemminflect import getInflection

_PERSONS = {"first": 1, "second": 2, "third": 3}
_SUBJECTS = {
    (1, "singular"): "I",
    (2, "singular"): "you",
    (3, "singular"): "he/she/it",
    (1, "plural"): "we",
    (2, "plural"): "you all",
    (3, "plural"): "they",
}


@attr.s(auto_attribs=True, frozen=True)
class FormDescription:
    persons: list[int]
    number: str | None  # singular / plural
    tenses: list[str]  # present / preterite / imperfect / future (a few forms are present-or-preterite)
    mood: str | None  # indicative / subjunctive / imperative / conditional / gerund / participle / infinitive
    voseo: bool = False
    negative: bool = False


def parse_description(desc: str) -> FormDescription | None:
    """The grammatical part of a Wiktionary form description, or None if it isn't a verb form we can read."""
    text = desc.split(":", 1)[1] if desc.startswith("inflection of") and ":" in desc else desc.split(" of ", 1)[0]
    text = text.lower()
    words = set(re.split(r"[\s/,-]+", text))
    if "gerund" in words:
        return FormDescription([], None, [], "gerund")
    if "participle" in words:
        return FormDescription([], None, [], "participle")
    if "infinitive" in words:
        return FormDescription([], None, [], "infinitive")
    persons = sorted({_PERSONS[w] for w in words if w in _PERSONS})
    number = "plural" if "plural" in words and "singular" not in words else "singular" if "singular" in words else None
    tenses = [t for t in ("present", "preterite", "imperfect", "future") if t in words]
    if "conditional" in words:
        mood = "conditional"
    elif "imperative" in words:
        mood = "imperative"
    elif "subjunctive" in words:
        mood = "subjunctive"
    elif "indicative" in words:
        mood = "indicative"
    else:
        return None
    if not persons or number is None:
        return None
    return FormDescription(persons, number, tenses, mood, voseo="voseo" in words, negative="negative" in words)


def english_verb(senses: list[str]) -> str | None:
    """The plain English verb from a Spanish verb's first sense: "(transitive) to renounce, to give up" ->
    "renounce"."""
    for sense in senses[:3]:
        clean = re.sub(r"\([^)]*\)", "", sense).strip()
        for chunk in re.split(r"[;,]", clean):
            chunk = chunk.strip()
            if chunk.startswith("to ") and len(chunk) > 3:
                return chunk[3:].strip()
    return None


def _inflect(verb: str, tag: str) -> str:
    """Inflect the first word of a verb phrase ("give up" -> "gave up")."""
    head, _, rest = verb.partition(" ")
    forms = getInflection(head, tag=tag)
    inflected = forms[0] if forms else head
    return f"{inflected} {rest}".strip()


def _be(subject_person: int, number: str, past: bool) -> str:
    if past:
        return "was" if number == "singular" and subject_person in (1, 3) else "were"
    if number == "singular":
        return {1: "am", 2: "are", 3: "is"}[subject_person]
    return "are"


def _finite(verb: str, person: int, number: str, tense: str, mood: str) -> str:
    """The English verb (without subject) for one person."""
    is_be = verb == "be" or verb.startswith("be ")
    rest = verb[3:] if verb.startswith("be ") else ""
    third_singular = person == 3 and number == "singular"
    if mood == "conditional":
        return f"would {verb}"
    if mood == "subjunctive":
        if tense == "imperfect":
            return ("were " + rest).strip() if is_be else _inflect(verb, "VBD")
        return verb  # "(that) he renounce"
    if tense == "preterite":
        return (_be(person, number, True) + " " + rest).strip() if is_be else _inflect(verb, "VBD")
    if tense == "imperfect":
        return (_be(person, number, True) + " " + rest).strip() if is_be else f"used to {verb}"
    if tense == "future":
        return f"will {verb}"
    if is_be:
        return (_be(person, number, False) + " " + rest).strip()
    return _inflect(verb, "VBZ") if third_singular else verb


def english_form(desc: str, senses: list[str]) -> str | None:
    """A rough English rendering of an inflected form, eg "I renounced", "(that) they renounce", "renounce! (tú)",
    "tell! (tú) (+ me, lo)". None when the description or the verb's English can't be read."""
    form = parse_description(desc)
    verb = english_verb(senses)
    if form is None or verb is None:
        return None
    rendered = _english(form, verb)
    clitics = _clitics(desc)
    return f"{rendered} (+ {clitics})" if clitics else rendered


def _clitics(desc: str) -> str | None:
    """Attached pronouns: "... of decir combined with indirect object me and direct object lo" -> "me, lo"."""
    if " combined with " not in desc:
        return None
    tail = desc.split(" combined with ", 1)[1]
    pronouns = re.sub(r"\b(indirect|direct|object|reflexive|pronoun)\b", "", tail).replace(" and ", ",")
    return ", ".join(p.strip() for p in pronouns.split(",") if p.strip())


def _english(form: FormDescription, verb: str) -> str:
    if form.mood == "gerund":
        return _inflect(verb, "VBG")
    if form.mood == "participle":
        return _inflect(verb, "VBN")
    if form.mood == "infinitive":
        return f"to {verb}"
    assert form.number is not None
    if form.mood == "imperative":
        if form.persons == [1]:
            command = f"let's {verb}"
        else:
            command = f"don't {verb}" if form.negative else verb
        who = {
            (2, "singular"): "vos" if form.voseo else "tú",
            (2, "plural"): "vosotros",
            (3, "singular"): "usted",
            (3, "plural"): "ustedes",
        }.get((form.persons[0], form.number))
        return f"{command}!" + (f" ({who})" if who else "")
    renderings = []
    for tense in form.tenses or ["present"]:
        for person in form.persons:
            subject = _SUBJECTS[(person, form.number)]
            if form.voseo and person == 2:
                subject = "you (vos)"
            verb_form = _finite(verb, person, form.number, tense, form.mood or "indicative")
            prefix = "(that) " if form.mood == "subjunctive" and tense != "imperfect" else ""
            prefix = "(if) " if form.mood == "subjunctive" and tense == "imperfect" else prefix
            renderings.append(f"{prefix}{subject} {verb_form}")
    return " / ".join(dict.fromkeys(renderings))


@attr.s(auto_attribs=True, frozen=True)
class VerbClass:
    # regular / stem-changing / irregular
    label: str
    # sound or spelling alternations from Wiktionary's conjugation table, eg ["e→ie"], ["c→qu (spelling)"]
    notes: list[str]


def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def verb_class(irregular: bool, alternations: list[str]) -> VerbClass:
    """Classify from Wiktionary's conjugation tags: "irregular" in the table, plus alternation classes. Vowel changes
    in the stem (e-ie, o-ue, e-i) and c-zc make a verb stem-changing; consonant swaps that only keep the sound
    (c-qu, g-j, z-c, g-gu) and accent shifts (i-í) are spelling changes of a regular verb."""
    notes, stem_change = [], False
    for alt in alternations:
        parts = alt.split("-")
        arrow = "→".join(parts)
        if len({_strip_accents(p) for p in parts}) == 1:
            notes.append(f"{arrow} (accent)")
        elif all(set(_strip_accents(p)) <= set("aeiou") for p in parts) or alt == "c-zc":
            notes.append(arrow)
            stem_change = True
        else:
            notes.append(f"{arrow} (spelling)")
    label = "irregular" if irregular else "stem-changing" if stem_change else "regular"
    return VerbClass(label=label, notes=notes)
