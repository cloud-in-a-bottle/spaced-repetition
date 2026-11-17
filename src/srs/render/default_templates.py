import attr

from srs.domain.kinds import ItemKind
from srs.domain.kinds import Skill

BASE_CSS = """
.card { font-family: system-ui, sans-serif; text-align: center; font-size: 1.4rem; line-height: 1.5; }
.term { font-size: 2.2rem; font-weight: 600; }
.hint { color: #888; font-size: 1rem; }
.answer { margin-top: 0.5rem; }
.notes { color: #888; font-size: 1rem; margin-top: 1rem; white-space: pre-wrap; }
hr { border: none; border-top: 1px solid #8884; margin: 1rem 0; }
"""


@attr.s(auto_attribs=True, frozen=True)
class DefaultTemplate:
    id: str
    name: str
    kind: ItemKind
    skill: Skill
    front: str
    back: str
    default_enabled: bool


_NOTES = '{% if notes %}<div class="notes">{{ notes }}</div>{% endif %}'

DEFAULT_TEMPLATES: tuple[DefaultTemplate, ...] = (
    DefaultTemplate(
        id="lexeme-recognize",
        name="Word → meaning",
        kind=ItemKind.LEXEME,
        skill=Skill.RECOGNIZE,
        front='<div class="term" lang="{{ language }}">{{ lemma }}</div><div class="hint">{{ pos }}</div>',
        back='{{ front_side }}<hr><div class="answer">{{ gloss }}</div>'
        '{% if features %}<div class="hint">{{ features|features }}</div>{% endif %}' + _NOTES,
        default_enabled=True,
    ),
    DefaultTemplate(
        id="lexeme-produce",
        name="Meaning → word",
        kind=ItemKind.LEXEME,
        skill=Skill.PRODUCE,
        front='<div class="answer">{{ gloss }}</div><div class="hint">{{ pos }}</div>',
        back='{{ front_side }}<hr><div class="term" lang="{{ language }}">{{ lemma }}</div>'
        '{% if features %}<div class="hint">{{ features|features }}</div>{% endif %}' + _NOTES,
        default_enabled=True,
    ),
    DefaultTemplate(
        id="form-produce",
        name="Conjugate / inflect",
        kind=ItemKind.FORM,
        skill=Skill.PRODUCE,
        front='<div class="term" lang="{{ language }}">{{ lexeme.lemma }}</div>'
        '<div class="hint">{{ features|features }}</div>',
        back='{{ front_side }}<hr><div class="term" lang="{{ language }}">{{ form }}</div>'
        '{% if gloss %}<div class="answer">{{ gloss }}</div>{% endif %}' + _NOTES,
        default_enabled=True,
    ),
    DefaultTemplate(
        id="form-recognize",
        name="Identify form",
        kind=ItemKind.FORM,
        skill=Skill.RECOGNIZE,
        front='<div class="term" lang="{{ language }}">{{ form }}</div>',
        back='{{ front_side }}<hr><div class="answer">{{ lexeme.lemma }} — {{ lexeme.gloss }}</div>'
        '<div class="hint">{{ features|features }}</div>' + _NOTES,
        default_enabled=False,
    ),
    DefaultTemplate(
        id="phrase-recognize",
        name="Phrase → translation",
        kind=ItemKind.PHRASE,
        skill=Skill.RECOGNIZE,
        front='<div lang="{{ language }}">{{ text }}</div>',
        back='{{ front_side }}<hr><div class="answer">{{ translation }}</div>' + _NOTES,
        default_enabled=True,
    ),
    DefaultTemplate(
        id="phrase-produce",
        name="Translation → phrase",
        kind=ItemKind.PHRASE,
        skill=Skill.PRODUCE,
        front='<div class="answer">{{ translation }}</div>',
        back='{{ front_side }}<hr><div lang="{{ language }}">{{ text }}</div>' + _NOTES,
        default_enabled=False,
    ),
    DefaultTemplate(
        id="fact-recall",
        name="Front → back",
        kind=ItemKind.FACT,
        skill=Skill.RECALL,
        front="<div>{{ front }}</div>",
        back='{{ front_side }}<hr><div class="answer">{{ back }}</div>' + _NOTES,
        default_enabled=True,
    ),
)
