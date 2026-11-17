import attr

from srs.domain.kinds import PartOfSpeech


@attr.s(auto_attribs=True, frozen=True)
class LexemeData:
    """A dictionary word. `lemma` is its root / citation form, eg "hablar"."""

    lemma: str
    pos: PartOfSpeech
    gloss: str
    # Free-form grammatical properties of the word itself, eg {"gender": "feminine"}.
    features: dict[str, str] = attr.Factory(dict)
    notes: str = ""
    # other accepted spellings; knowledge lookups match these too
    alternatives: list[str] = attr.Factory(list)


@attr.s(auto_attribs=True, frozen=True)
class FormData:
    """One inflected form of a lexeme, eg "hablo" = hablar + {"tense": "present", "person": "1st", ...}."""

    lexeme_id: str
    form: str
    features: dict[str, str]
    gloss: str = ""
    notes: str = ""
    # other correct forms for the same features, eg the -se subjunctive "hablase" alongside "hablara"
    alternatives: list[str] = attr.Factory(list)


@attr.s(auto_attribs=True, frozen=True)
class PhraseData:
    text: str
    translation: str
    notes: str = ""
    # Lexemes this phrase exercises, so practising the phrase can inform what words you know.
    lexeme_ids: list[str] = attr.Factory(list)


@attr.s(auto_attribs=True, frozen=True)
class FactData:
    """Anything that isn't language material: a plain prompt and answer."""

    front: str
    back: str
    notes: str = ""


ItemData = LexemeData | FormData | PhraseData | FactData
