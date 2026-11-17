import enum

import attr

from srs.domain.kinds import PartOfSpeech
from srs.domain.kinds import Skill
from srs.domain.schedule import CardState


class KnowledgeStatus(enum.StrEnum):
    # has cards, none reviewed yet
    NEW = "new"
    # reviewed, but no card has graduated to long-term review
    LEARNING = "learning"
    # at least one card (of the lexeme or any of its forms) is in long-term review
    KNOWN = "known"


@attr.s(auto_attribs=True, frozen=True)
class SkillKnowledge:
    skill: Skill
    template_id: str
    state: CardState
    # probability of recalling this right now, per FSRS; 0 if never reviewed
    retrievability: float
    stability_days: float | None
    difficulty: float | None
    reps: int
    lapses: int
    last_review: int | None
    due: int
    suspended: bool


@attr.s(auto_attribs=True, frozen=True)
class FormKnowledge:
    item_id: str
    form: str
    features: dict[str, str]
    skills: list[SkillKnowledge]


@attr.s(auto_attribs=True, frozen=True)
class LexemeKnowledge:
    item_id: str
    language: str
    lemma: str
    pos: PartOfSpeech
    gloss: str
    features: dict[str, str]
    tags: list[str]
    status: KnowledgeStatus
    # highest retrievability over the lexeme's own cards (not its forms'); 0 if none reviewed
    recall_probability: float
    skills: list[SkillKnowledge]
    forms: list[FormKnowledge]


@attr.s(auto_attribs=True, frozen=True)
class WordMatch:
    # set when the word matched one of the lexeme's forms rather than its lemma
    matched_form_id: str | None
    lexeme: LexemeKnowledge


@attr.s(auto_attribs=True, frozen=True)
class WordLookup:
    word: str
    matches: list[WordMatch]
