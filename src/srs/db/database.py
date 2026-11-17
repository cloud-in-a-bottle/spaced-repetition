import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from srs.db.connection import connect
from srs.db.migrate import migrate


class Database:
    """One shared connection, serialized by a lock. Plenty for a single-user app, and it keeps transactions simple."""

    def __init__(self, path: Path) -> None:
        self._conn = connect(path)
        self._lock = threading.Lock()
        migrate(self._conn)

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                yield self._conn
            except BaseException:
                self._conn.execute("ROLLBACK")
                raise
            self._conn.execute("COMMIT")

    def close(self) -> None:
        self._conn.close()
