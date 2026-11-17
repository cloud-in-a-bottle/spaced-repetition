import attr
from litestar import delete
from litestar import get
from litestar import post
from litestar import put
from litestar.params import FromPath
from litestar.params import JSONBody

from srs.api.deps import Db
from srs.core.decks import create_deck
from srs.core.decks import delete_deck
from srs.core.decks import rename_deck
from srs.domain.clock import now_ms
from srs.repo.changes import next_seq
from srs.repo.decks import Deck
from srs.repo.decks import list_decks


@attr.s(auto_attribs=True, frozen=True)
class DeckInput:
    name: str


@get("/decks", sync_to_thread=True)
def decks_index(db: Db) -> list[Deck]:
    with db.transaction() as conn:
        return list_decks(conn)


@post("/decks", sync_to_thread=True)
def deck_create(db: Db, data: JSONBody[DeckInput]) -> Deck:
    with db.transaction() as conn:
        return create_deck(conn, data.name, next_seq(conn), now_ms())


@put("/decks/{deck_id:str}", sync_to_thread=True)
def deck_rename(db: Db, deck_id: FromPath[str], data: JSONBody[DeckInput]) -> Deck:
    with db.transaction() as conn:
        return rename_deck(conn, deck_id, data.name, next_seq(conn))


@delete("/decks/{deck_id:str}", sync_to_thread=True)
def deck_delete(db: Db, deck_id: FromPath[str]) -> None:
    with db.transaction() as conn:
        delete_deck(conn, deck_id, next_seq(conn))
