import attr
from litestar import get

from srs.domain.kinds import LANGUAGE_REQUIRED
from srs.domain.kinds import SKILLS_BY_KIND
from srs.domain.kinds import ItemKind
from srs.domain.kinds import PartOfSpeech
from srs.domain.kinds import Skill


@attr.s(auto_attribs=True, frozen=True)
class KindInfo:
    kind: ItemKind
    skills: list[Skill]
    language_required: bool


@attr.s(auto_attribs=True, frozen=True)
class SchemaInfo:
    kinds: list[KindInfo]
    parts_of_speech: list[PartOfSpeech]


@get("/schema", sync_to_thread=False)
def schema_show() -> SchemaInfo:
    """The item taxonomy, for building forms in the UI."""
    return SchemaInfo(
        kinds=[
            KindInfo(kind=k, skills=list(SKILLS_BY_KIND[k]), language_required=k in LANGUAGE_REQUIRED)
            for k in ItemKind
        ],
        parts_of_speech=list(PartOfSpeech),
    )
