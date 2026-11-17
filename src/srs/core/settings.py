import sqlite3

from srs.core.cards import replay_card
from srs.domain.errors import InvalidRequest
from srs.domain.settings import Settings
from srs.repo.cards import all_card_ids
from srs.repo.settings import save_settings


def update_settings(conn: sqlite3.Connection, settings: Settings, seq: int) -> None:
    """Scheduling settings feed into replay, so every card is replayed under the new ones."""
    if not 0.5 <= settings.desired_retention < 1.0:
        raise InvalidRequest("desired_retention must be in [0.5, 1)")
    if len(settings.fsrs_parameters) != 21:
        raise InvalidRequest("fsrs_parameters must have 21 values (FSRS-6)")
    if not 0 <= settings.day_starts_at_hour < 24:
        raise InvalidRequest("day_starts_at_hour must be in [0, 24)")
    save_settings(conn, settings, seq)
    for card_id in all_card_ids(conn):
        replay_card(conn, card_id, settings, seq)
