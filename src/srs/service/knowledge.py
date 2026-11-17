import attr
from litestar import get
from litestar import post
from litestar.params import FromQuery
from litestar.params import JSONBody

from srs.api.deps import Db
from srs.domain.clock import now_ms
from srs.domain.errors import InvalidRequest
from srs.knowledge.models import KnowledgeStatus
from srs.knowledge.models import LexemeKnowledge
from srs.knowledge.models import WordLookup
from srs.knowledge.query import list_lexemes
from srs.knowledge.query import lookup_words
from srs.service.permissions import KNOWLEDGE_READ
from srs.service.permissions import require_grant

_MAX_WORDS = 5000


@attr.s(auto_attribs=True, frozen=True)
class LookupRequest:
    language: str
    words: list[str]


@attr.s(auto_attribs=True, frozen=True)
class LookupResponse:
    results: list[WordLookup]


@attr.s(auto_attribs=True, frozen=True)
class LexemeList:
    lexemes: list[LexemeKnowledge]


@post("/v1/lexemes/lookup", sync_to_thread=True, guards=[require_grant(KNOWLEDGE_READ)], status_code=200)
def lexemes_lookup(db: Db, data: JSONBody[LookupRequest]) -> LookupResponse:
    """For each word (lemma or inflected form), which lexemes it is and how well the user knows them."""
    if len(data.words) > _MAX_WORDS:
        raise InvalidRequest(f"at most {_MAX_WORDS} words per request")
    with db.transaction() as conn:
        return LookupResponse(results=lookup_words(conn, data.language, data.words, now_ms()))


@get("/v1/lexemes", sync_to_thread=True, guards=[require_grant(KNOWLEDGE_READ)])
def lexemes_index(db: Db, language: FromQuery[str], status: FromQuery[KnowledgeStatus | None] = None) -> LexemeList:
    """Every lexeme the user has in `language`, optionally only those with the given status."""
    with db.transaction() as conn:
        return LexemeList(lexemes=list_lexemes(conn, language, status, now_ms()))
