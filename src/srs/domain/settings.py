import attr
from fsrs.scheduler import DEFAULT_PARAMETERS


@attr.s(auto_attribs=True, frozen=True)
class Settings:
    desired_retention: float = 0.9
    learning_steps_minutes: list[float] = attr.Factory(lambda: [1.0, 10.0])
    relearning_steps_minutes: list[float] = attr.Factory(lambda: [10.0])
    maximum_interval_days: int = 36500
    new_cards_per_day: int = 20
    # local hour at which a new study day starts (like anki's "next day starts at")
    day_starts_at_hour: int = 4
    fsrs_parameters: list[float] = attr.Factory(lambda: list(DEFAULT_PARAMETERS))
