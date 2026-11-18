import sqlite3

from srs.domain.schedule import Rating
from srs.domain.schedule import Review


def _from_row(row: sqlite3.Row) -> Review:
    return Review(
        id=row["id"],
        card_id=row["card_id"],
        rating=Rating(row["rating"]),
        reviewed_at=row["reviewed_at"],
        duration_ms=row["duration_ms"],
        source=row["source"],
    )


def insert_review(conn: sqlite3.Connection, review: Review, received_at: int) -> bool:
    """Idempotent: returns False if a review with this id was already recorded."""
    cursor = conn.execute(
        "INSERT INTO reviews (id, card_id, rating, reviewed_at, duration_ms, source, received_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT (id) DO NOTHING",
        (
            review.id,
            review.card_id,
            int(review.rating),
            review.reviewed_at,
            review.duration_ms,
            review.source,
            received_at,
        ),
    )
    return cursor.rowcount == 1


def reviews_for_card(conn: sqlite3.Connection, card_id: str) -> list[Review]:
    """The card's reviews that count: undone (voided) ones are left out."""
    rows = conn.execute(
        "SELECT * FROM reviews WHERE card_id = ? AND id NOT IN (SELECT review_id FROM voided_reviews) "
        "ORDER BY reviewed_at, id",
        (card_id,),
    )
    return [_from_row(r) for r in rows]


def find_review(conn: sqlite3.Connection, review_id: str) -> Review | None:
    row = conn.execute("SELECT * FROM reviews WHERE id = ?", (review_id,)).fetchone()
    return None if row is None else _from_row(row)


def insert_void(conn: sqlite3.Connection, review_id: str, received_at: int) -> bool:
    """Idempotent: returns False if this review was already voided."""
    cursor = conn.execute(
        "INSERT INTO voided_reviews (review_id, received_at) VALUES (?, ?) ON CONFLICT (review_id) DO NOTHING",
        (review_id, received_at),
    )
    return cursor.rowcount == 1
