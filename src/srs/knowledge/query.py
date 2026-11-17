import sqlite3
from collections import defaultdict

from srs.domain.item_data import FormData
from srs.domain.item_data import LexemeData
from srs.domain.item_keys import lookup_keys
from srs.domain.kinds import ItemKind
from srs.domain.kinds import Skill
from srs.domain.normalize import lookup_key
from srs.domain.schedule import CardState
from srs.domain.settings import Settings
from srs.knowledge.models import FormKnowledge
from srs.knowledge.models import KnowledgeStatus
from srs.knowledge.models import LexemeKnowledge
from srs.knowledge.models import SkillKnowledge
from srs.knowledge.models import WordLookup
from srs.knowledge.models import WordMatch
from srs.repo.cards import Card
from srs.repo.cards import cards_for_items
from srs.repo.items import Item
from srs.repo.items import forms_of_lexemes
from srs.repo.items import get_item
from srs.repo.items import items_by_lookup_keys
from srs.repo.items import items_of_kind
from srs.repo.settings import load_settings
from srs.repo.templates import list_templates
from srs.scheduling.replay import retrievability


def _skill_knowledge(card: Card, skill_by_template: dict[str, Skill], settings: Settings, now: int) -> SkillKnowledge:
    s = card.schedule
    return SkillKnowledge(
        skill=skill_by_template[card.template_id],
        template_id=card.template_id,
        state=s.state,
        retrievability=retrievability(s, now, settings),
        stability_days=s.stability,
        difficulty=s.difficulty,
        reps=s.reps,
        lapses=s.lapses,
        last_review=s.last_review,
        due=s.due,
        suspended=card.suspended,
    )


def _status(skills: list[SkillKnowledge]) -> KnowledgeStatus:
    if any(k.state == CardState.REVIEW for k in skills):
        return KnowledgeStatus.KNOWN
    if any(k.reps > 0 for k in skills):
        return KnowledgeStatus.LEARNING
    return KnowledgeStatus.NEW


def _lexeme_knowledge(conn: sqlite3.Connection, lexemes: list[Item], now: int) -> dict[str, LexemeKnowledge]:
    """Knowledge for many lexemes at once, with a fixed number of queries regardless of how many there are."""
    settings = load_settings(conn)
    skill_by_template = {t.id: t.skill for t in list_templates(conn)}
    forms = forms_of_lexemes(conn, [lx.id for lx in lexemes])
    cards_by_item: dict[str, list[Card]] = defaultdict(list)
    for card in cards_for_items(conn, [lx.id for lx in lexemes] + [f.id for f in forms]):
        if not card.deleted and card.template_id in skill_by_template:
            cards_by_item[card.item_id].append(card)
    forms_by_lexeme: dict[str, list[Item]] = defaultdict(list)
    for form in forms:
        assert form.lexeme_id is not None
        forms_by_lexeme[form.lexeme_id].append(form)

    def skills_of(item_id: str) -> list[SkillKnowledge]:
        return [_skill_knowledge(c, skill_by_template, settings, now) for c in cards_by_item[item_id]]

    result = {}
    for lx in lexemes:
        assert isinstance(lx.data, LexemeData) and lx.language is not None
        own = skills_of(lx.id)
        form_knowledge = []
        for form in forms_by_lexeme[lx.id]:
            assert isinstance(form.data, FormData)
            form_knowledge.append(
                FormKnowledge(
                    item_id=form.id, form=form.data.form, features=form.data.features, skills=skills_of(form.id)
                )
            )
        all_skills = own + [k for f in form_knowledge for k in f.skills]
        result[lx.id] = LexemeKnowledge(
            item_id=lx.id,
            language=lx.language,
            lemma=lx.data.lemma,
            pos=lx.data.pos,
            gloss=lx.data.gloss,
            features=lx.data.features,
            tags=lx.tags,
            status=_status(all_skills),
            recall_probability=max((k.retrievability for k in own), default=0.0),
            skills=own,
            forms=form_knowledge,
        )
    return result


def lookup_words(conn: sqlite3.Connection, language: str, words: list[str], now: int) -> list[WordLookup]:
    """Match each word against lexeme lemmas and inflected forms in `language`. A word can match several lexemes
    (homographs, or a form shared by two verbs); a word with no matches is one the user isn't studying."""
    keys = sorted({lookup_key(w) for w in words})
    lexemes = {lx.id: lx for lx in items_by_lookup_keys(conn, language, ItemKind.LEXEME, keys)}
    forms = items_by_lookup_keys(conn, language, ItemKind.FORM, keys)
    for form in forms:
        assert form.lexeme_id is not None
        if form.lexeme_id not in lexemes:
            lexemes[form.lexeme_id] = get_item(conn, form.lexeme_id)
    knowledge = _lexeme_knowledge(conn, list(lexemes.values()), now)

    matches_by_key: dict[str, list[WordMatch]] = defaultdict(list)
    wanted = set(keys)
    for lx in lexemes.values():
        for key in wanted.intersection(lookup_keys(lx.data)):
            matches_by_key[key].append(WordMatch(matched_form_id=None, lexeme=knowledge[lx.id]))
    for form in forms:
        assert form.lexeme_id is not None
        for key in wanted.intersection(lookup_keys(form.data)):
            matches_by_key[key].append(WordMatch(matched_form_id=form.id, lexeme=knowledge[form.lexeme_id]))
    return [WordLookup(word=w, matches=matches_by_key[lookup_key(w)]) for w in words]


def list_lexemes(
    conn: sqlite3.Connection, language: str, status: KnowledgeStatus | None, now: int
) -> list[LexemeKnowledge]:
    knowledge = _lexeme_knowledge(conn, items_of_kind(conn, language, ItemKind.LEXEME), now)
    return [k for k in knowledge.values() if status is None or k.status == status]
