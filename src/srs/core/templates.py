import sqlite3

import attr

from srs.core.cards import rerender_item_cards
from srs.domain.errors import InvalidRequest
from srs.domain.kinds import SKILLS_BY_KIND
from srs.domain.kinds import ItemKind
from srs.domain.kinds import Skill
from srs.repo.cards import cards_for_template
from srs.repo.items import get_item
from srs.repo.templates import Template
from srs.repo.templates import get_template
from srs.repo.templates import upsert_template


@attr.s(auto_attribs=True, frozen=True)
class TemplateInput:
    id: str
    name: str
    kind: ItemKind
    skill: Skill
    front: str
    back: str
    css: str
    default_enabled: bool


def save_template(conn: sqlite3.Connection, inp: TemplateInput, seq: int) -> Template:
    """Create or update a template, then re-render every card that uses it."""
    if inp.skill not in SKILLS_BY_KIND[inp.kind]:
        raise InvalidRequest(f"{inp.kind} items don't support skill {inp.skill}")
    existing = conn.execute("SELECT kind FROM templates WHERE id = ?", (inp.id,)).fetchone()
    if existing is not None and existing["kind"] != inp.kind:
        raise InvalidRequest("a template's kind can't change")
    template = Template(
        id=inp.id,
        name=inp.name,
        kind=inp.kind,
        skill=inp.skill,
        front=inp.front,
        back=inp.back,
        css=inp.css,
        default_enabled=inp.default_enabled,
        deleted=False,
        seq=seq,
    )
    upsert_template(conn, template)
    for item_id in {c.item_id for c in cards_for_template(conn, inp.id) if not c.deleted}:
        rerender_item_cards(conn, get_item(conn, item_id), seq)
    return get_template(conn, inp.id)
