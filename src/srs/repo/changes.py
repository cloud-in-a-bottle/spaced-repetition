import sqlite3


def next_seq(conn: sqlite3.Connection) -> int:
    """Bump the global change counter. Call inside a transaction; every row written in it can share the value."""
    row = conn.execute("UPDATE change_counter SET value = value + 1 WHERE id = 1 RETURNING value").fetchone()
    return int(row[0])


def current_seq(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT value FROM change_counter WHERE id = 1").fetchone()[0])
