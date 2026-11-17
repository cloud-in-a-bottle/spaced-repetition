import enum

import attr


class CardState(enum.StrEnum):
    NEW = "new"
    LEARNING = "learning"
    REVIEW = "review"
    RELEARNING = "relearning"


class Rating(enum.IntEnum):
    AGAIN = 1
    HARD = 2
    GOOD = 3
    EASY = 4


@attr.s(auto_attribs=True, frozen=True)
class Review:
    id: str
    card_id: str
    rating: Rating
    reviewed_at: int
    duration_ms: int | None
    source: str


@attr.s(auto_attribs=True, frozen=True)
class Schedule:
    state: CardState
    step: int | None
    stability: float | None
    difficulty: float | None
    due: int
    last_review: int | None
    reps: int
    lapses: int
