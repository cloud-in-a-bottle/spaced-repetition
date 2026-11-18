import attr
from litestar import post
from litestar.params import JSONBody

from srs.api.deps import Db
from srs.api.views import SyncCardView
from srs.api.views import sync_card_view
from srs.core.sync import changes_since
from srs.core.sync import record_reviews
from srs.core.sync import record_voids
from srs.domain.clock import now_ms
from srs.domain.errors import InvalidRequest
from srs.domain.schedule import Rating
from srs.domain.schedule import Review
from srs.domain.settings import Settings
from srs.repo.changes import next_seq
from srs.repo.decks import Deck

_MAX_CLOCK_SKEW_MS = 24 * 3600 * 1000


@attr.s(auto_attribs=True, frozen=True)
class ReviewInput:
    id: str
    card_id: str
    rating: int
    reviewed_at: int
    duration_ms: int | None = None


@attr.s(auto_attribs=True, frozen=True)
class SyncRequest:
    cursor: int
    reviews: list[ReviewInput] = attr.Factory(list)
    # ids of reviews to undo
    voids: list[str] = attr.Factory(list)


@attr.s(auto_attribs=True, frozen=True)
class SyncResponse:
    cursor: int
    # only sent when changed since `cursor`
    settings: Settings | None
    decks: list[Deck]
    cards: list[SyncCardView]


def to_review(r: ReviewInput, source: str, now: int) -> Review:
    if r.rating not in (1, 2, 3, 4):
        raise InvalidRequest(f"review {r.id}: rating must be 1-4")
    if r.reviewed_at > now + _MAX_CLOCK_SKEW_MS:
        raise InvalidRequest(f"review {r.id} is dated in the future")
    return Review(
        id=r.id,
        card_id=r.card_id,
        rating=Rating(r.rating),
        reviewed_at=r.reviewed_at,
        duration_ms=r.duration_ms,
        source=source,
    )


@post("/sync", sync_to_thread=True)
def sync(db: Db, data: JSONBody[SyncRequest]) -> SyncResponse:
    """Push the client's queued reviews, pull everything that changed since its cursor."""
    now = now_ms()
    reviews = [to_review(r, "app", now) for r in data.reviews]
    with db.transaction() as conn:
        if reviews:
            record_reviews(conn, reviews, next_seq(conn), now)
        if data.voids:
            record_voids(conn, data.voids, next_seq(conn), now)
        changes = changes_since(conn, data.cursor)
    return SyncResponse(
        cursor=changes.cursor,
        settings=changes.settings,
        decks=changes.decks,
        cards=[sync_card_view(c) for c in changes.cards],
    )
