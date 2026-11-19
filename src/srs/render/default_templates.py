import attr

from srs.domain.kinds import ItemKind
from srs.domain.kinds import Skill

BASE_CSS = """
.card { font-family: system-ui, sans-serif; text-align: center; font-size: 1.4rem; line-height: 1.5; }
.term { font-size: 2.2rem; font-weight: 600; }
.hint { color: #888; font-size: 1rem; }
.answer { margin-top: 0.5rem; }
.notes { color: #888; font-size: 1rem; margin-top: 1rem; white-space: pre-wrap; }
.prewrap { white-space: pre-wrap; text-align: left; }
hr { border: none; border-top: 1px solid #8884; margin: 1rem 0; }
.prompt { font-size: 1.3rem; line-height: 1.7; }
.cloze { color: rgb(210, 142, 2); font-weight: 600; }
.aside { color: #888; }
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
# eg "la casa": shows the article for languages where it carries the gender
_LEMMA = "{% if features.get('article') %}{{ features.article }} {% endif %}{{ lemma }}"
_ALTERNATIVES = '{% if alternatives %}<div class="hint">also: {{ alternatives|join(", ") }}</div>{% endif %}'

FORM_PRODUCE_FRONT = (
    '{% if prompt %}<div class="prompt" lang="{{ language }}">{{ prompt|cloze("…" ~ lexeme.lemma ~ "…") }}</div>'
    '{% else %}<div class="term" lang="{{ language }}">{{ lexeme.lemma }}</div>'
    '<div class="hint">{{ features|features }}</div>{% endif %}'
)
FORM_PRODUCE_BACK = (
    '{% if prompt %}<div class="prompt" lang="{{ language }}">{{ prompt|cloze(form, "cloze answer") }}</div>'
    '<div class="hint">{{ features|features }}</div>'
    '{% else %}{{ front_side }}<hr><div class="term" lang="{{ language }}">{{ form }}</div>{% endif %}'
    + _ALTERNATIVES
    + '{% if gloss %}<div class="answer">{{ gloss }}</div>{% endif %}'
    + _NOTES
)

DEFAULT_TEMPLATES: tuple[DefaultTemplate, ...] = (
    DefaultTemplate(
        id="lexeme-recognize",
        name="Word → meaning",
        kind=ItemKind.LEXEME,
        skill=Skill.RECOGNIZE,
        front='<div class="term" lang="{{ language }}">' + _LEMMA + '</div><div class="hint">{{ pos }}</div>',
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
        back='{{ front_side }}<hr><div class="term" lang="{{ language }}">'
        + _LEMMA
        + "</div>"
        + _ALTERNATIVES
        + '{% if features %}<div class="hint">{{ features|features }}</div>{% endif %}'
        + _NOTES,
        default_enabled=True,
    ),
    DefaultTemplate(
        id="form-produce",
        name="Conjugate / inflect",
        kind=ItemKind.FORM,
        skill=Skill.PRODUCE,
        # with a sentence prompt (eg imported from anki's KOFI deck) the card is a cloze; otherwise lemma + features
        front=FORM_PRODUCE_FRONT,
        back=FORM_PRODUCE_BACK,
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
        front='<div class="prewrap">{{ front }}</div>',
        back='{{ front_side }}<hr><div class="answer prewrap">{{ back }}</div>' + _NOTES,
        default_enabled=True,
    ),
)
