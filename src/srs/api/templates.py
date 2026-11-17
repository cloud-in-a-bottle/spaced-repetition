import attr
from litestar import get
from litestar import put
from litestar.params import FromPath
from litestar.params import JSONBody

from srs.api.deps import Db
from srs.core.templates import TemplateInput
from srs.core.templates import save_template
from srs.domain.kinds import ItemKind
from srs.domain.kinds import Skill
from srs.repo.changes import next_seq
from srs.repo.templates import Template
from srs.repo.templates import list_templates


@attr.s(auto_attribs=True, frozen=True)
class TemplateBody:
    name: str
    kind: ItemKind
    skill: Skill
    front: str
    back: str
    css: str
    default_enabled: bool


@get("/templates", sync_to_thread=True)
def templates_index(db: Db) -> list[Template]:
    with db.transaction() as conn:
        return list_templates(conn)


@put("/templates/{template_id:str}", sync_to_thread=True)
def template_save(db: Db, template_id: FromPath[str], data: JSONBody[TemplateBody]) -> Template:
    with db.transaction() as conn:
        return save_template(conn, TemplateInput(id=template_id, **attr.asdict(data)), next_seq(conn))
