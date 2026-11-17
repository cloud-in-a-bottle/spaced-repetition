import attr
from litestar import delete
from litestar import get
from litestar import post
from litestar import put
from litestar.params import FromPath
from litestar.params import FromQuery
from litestar.params import JSONBody

from srs.api.deps import Db
from srs.api.views import ItemView
from srs.api.views import item_view
from srs.core.items import delete_item
from srs.core.items import save_item
from srs.domain.clock import now_ms
from srs.domain.errors import InvalidRequest
from srs.domain.item_input import ItemInput
from srs.domain.kinds import ItemKind
from srs.repo.cards import cards_for_items
from srs.repo.cards import get_card
from srs.repo.cards import upsert_card
from srs.repo.changes import next_seq
from srs.repo.items import get_item
from srs.repo.items import list_items


@get("/items", sync_to_thread=True)
def items_index(
    db: Db,
    deck_id: FromQuery[str | None] = None,
    kind: FromQuery[ItemKind | None] = None,
    q: FromQuery[str | None] = None,
) -> list[ItemView]:
    with db.transaction() as conn:
        items = list_items(conn, deck_id, kind, q)
        cards = cards_for_items(conn, [i.id for i in items])
    return [item_view(i, [c for c in cards if c.item_id == i.id]) for i in items]


@get("/items/{item_id:str}", sync_to_thread=True)
def item_show(db: Db, item_id: FromPath[str]) -> ItemView:
    with db.transaction() as conn:
        item = get_item(conn, item_id)
        return item_view(item, cards_for_items(conn, [item.id]))


@post("/items", sync_to_thread=True)
def item_create(db: Db, data: JSONBody[ItemInput]) -> ItemView:
    if data.id is not None:
        raise InvalidRequest("use PUT /api/items/{id} to save an item with a chosen id")
    with db.transaction() as conn:
        item = save_item(conn, data, next_seq(conn), now_ms())
        return item_view(item, cards_for_items(conn, [item.id]))


@put("/items/{item_id:str}", sync_to_thread=True)
def item_save(db: Db, item_id: FromPath[str], data: JSONBody[ItemInput]) -> ItemView:
    """Create-or-replace under a client-chosen id."""
    with db.transaction() as conn:
        item = save_item(conn, attr.evolve(data, id=item_id), next_seq(conn), now_ms())
        return item_view(item, cards_for_items(conn, [item.id]))


@delete("/items/{item_id:str}", sync_to_thread=True)
def item_delete(db: Db, item_id: FromPath[str]) -> None:
    with db.transaction() as conn:
        delete_item(conn, item_id, next_seq(conn), now_ms())


@attr.s(auto_attribs=True, frozen=True)
class SuspendInput:
    suspended: bool


@put("/cards/{card_id:str}/suspended", sync_to_thread=True)
def card_suspend(db: Db, card_id: FromPath[str], data: JSONBody[SuspendInput]) -> None:
    with db.transaction() as conn:
        card = get_card(conn, card_id)
        upsert_card(conn, attr.evolve(card, suspended=data.suspended, seq=next_seq(conn)))
