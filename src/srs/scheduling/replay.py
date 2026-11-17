from collections.abc import Sequence
from datetime import UTC
from datetime import datetime
from datetime import timedelta

import fsrs

from srs.domain.schedule import CardState
from srs.domain.schedule import Rating
from srs.domain.schedule import Review
from srs.domain.schedule import Schedule
from srs.domain.settings import Settings
from srs.scheduling.fuzz import fuzzed_interval_days

_STATE_FROM_FSRS = {
    fsrs.State.Learning: CardState.LEARNING,
    fsrs.State.Review: CardState.REVIEW,
    fsrs.State.Relearning: CardState.RELEARNING,
}


def make_scheduler(settings: Settings) -> fsrs.Scheduler:
    return fsrs.Scheduler(
        parameters=settings.fsrs_parameters,
        desired_retention=settings.desired_retention,
        learning_steps=tuple(timedelta(minutes=m) for m in settings.learning_steps_minutes),
        relearning_steps=tuple(timedelta(minutes=m) for m in settings.relearning_steps_minutes),
        maximum_interval=settings.maximum_interval_days,
        enable_fuzzing=False,
    )


def to_datetime(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, tz=UTC)


def to_ms(dt: datetime) -> int:
    return round(dt.timestamp() * 1000)


def sort_reviews(reviews: Sequence[Review]) -> list[Review]:
    return sorted(reviews, key=lambda r: (r.reviewed_at, r.id))


def replay(created_at: int, reviews: Sequence[Review], settings: Settings) -> Schedule:
    """The card's schedule is a pure function of its reviews, applied in time order (ties broken by id).

    This is what makes offline sync conflict-free: devices only ever add reviews, and any device holding the same set
    of reviews computes the same schedule.
    """
    scheduler = make_scheduler(settings)
    card = fsrs.Card(due=to_datetime(created_at))
    reps = 0
    lapses = 0
    for review in sort_reviews(reviews):
        if card.state == fsrs.State.Review and review.rating == Rating.AGAIN:
            lapses += 1
        reviewed_at = to_datetime(review.reviewed_at)
        card, _ = scheduler.review_card(card, fsrs.Rating(int(review.rating)), review_datetime=reviewed_at)
        if card.state == fsrs.State.Review:
            interval = (card.due - reviewed_at).days
            fuzzed = fuzzed_interval_days(interval, settings.maximum_interval_days, review.id)
            card.due = reviewed_at + timedelta(days=fuzzed)
        reps += 1
    return Schedule(
        state=CardState.NEW if reps == 0 else _STATE_FROM_FSRS[card.state],
        step=card.step,
        stability=card.stability,
        difficulty=card.difficulty,
        due=to_ms(card.due),
        last_review=None if card.last_review is None else to_ms(card.last_review),
        reps=reps,
        lapses=lapses,
    )


def retrievability(schedule: Schedule, now: int, settings: Settings) -> float:
    if schedule.last_review is None or schedule.stability is None:
        return 0.0
    card = fsrs.Card(
        state=fsrs.State.Review,
        stability=schedule.stability,
        difficulty=schedule.difficulty,
        last_review=to_datetime(schedule.last_review),
    )
    return float(make_scheduler(settings).get_card_retrievability(card, to_datetime(now)))
