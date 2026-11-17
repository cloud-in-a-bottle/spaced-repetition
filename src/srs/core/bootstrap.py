import sqlite3

from srs.core.decks import create_deck
from srs.domain.settings import Settings
from srs.render.default_templates import BASE_CSS
from srs.render.default_templates import DEFAULT_TEMPLATES
from srs.repo.changes import next_seq
from srs.repo.decks import list_decks
from srs.repo.settings import save_settings
from srs.repo.settings import settings_seq
from srs.repo.templates import Template
from srs.repo.templates import count_templates
from srs.repo.templates import upsert_template


def bootstrap(conn: sqlite3.Connection, now: int) -> None:
    """First-run setup: default templates, settings and a deck. Only ever adds; never overwrites the user's edits."""
    seq = next_seq(conn)
    if count_templates(conn) == 0:
        for t in DEFAULT_TEMPLATES:
            upsert_template(
                conn,
                Template(
                    id=t.id,
                    name=t.name,
                    kind=t.kind,
                    skill=t.skill,
                    front=t.front,
                    back=t.back,
                    css=BASE_CSS,
                    default_enabled=t.default_enabled,
                    deleted=False,
                    seq=seq,
                ),
            )
    if settings_seq(conn) == 0:
        save_settings(conn, Settings(), seq)
    if not list_decks(conn):
        create_deck(conn, "Default", seq, now)
