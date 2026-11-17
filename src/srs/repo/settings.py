import json
import sqlite3

import attr

from srs.domain.settings import Settings


def load_settings(conn: sqlite3.Connection) -> Settings:
    row = conn.execute("SELECT json FROM settings WHERE id = 1").fetchone()
    if row is None:
        return Settings()
    return Settings(**json.loads(row["json"]))


def save_settings(conn: sqlite3.Connection, settings: Settings, seq: int) -> None:
    conn.execute(
        "INSERT INTO settings (id, json, seq) VALUES (1, ?, ?) ON CONFLICT (id) DO UPDATE SET json = excluded.json, "
        "seq = excluded.seq",
        (json.dumps(attr.asdict(settings)), seq),
    )


def settings_seq(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT seq FROM settings WHERE id = 1").fetchone()
    return 0 if row is None else int(row["seq"])
