-- Undo: a review id here is left out of scheduling. Like reviews, voids only ever get added (a two-phase set), so
-- devices merge them without conflicts; a void may arrive before the review it cancels.
CREATE TABLE voided_reviews (
    review_id TEXT PRIMARY KEY,
    received_at INTEGER NOT NULL
);
