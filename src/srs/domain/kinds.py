import enum


class ItemKind(enum.StrEnum):
    LEXEME = "lexeme"
    FORM = "form"
    PHRASE = "phrase"
    FACT = "fact"


class Skill(enum.StrEnum):
    """What a card asks you to do with its item. A template declares exactly one skill."""

    RECOGNIZE = "recognize"
    PRODUCE = "produce"
    RECALL = "recall"


SKILLS_BY_KIND: dict[ItemKind, tuple[Skill, ...]] = {
    ItemKind.LEXEME: (Skill.RECOGNIZE, Skill.PRODUCE),
    ItemKind.FORM: (Skill.RECOGNIZE, Skill.PRODUCE),
    ItemKind.PHRASE: (Skill.RECOGNIZE, Skill.PRODUCE),
    ItemKind.FACT: (Skill.RECALL,),
}

LANGUAGE_REQUIRED: frozenset[ItemKind] = frozenset({ItemKind.LEXEME, ItemKind.PHRASE})


class PartOfSpeech(enum.StrEnum):
    NOUN = "noun"
    PROPER_NOUN = "proper_noun"
    VERB = "verb"
    AUXILIARY = "auxiliary"
    ADJECTIVE = "adjective"
    ADVERB = "adverb"
    PRONOUN = "pronoun"
    DETERMINER = "determiner"
    PREPOSITION = "preposition"
    CONJUNCTION = "conjunction"
    NUMERAL = "numeral"
    PARTICLE = "particle"
    INTERJECTION = "interjection"
    OTHER = "other"
