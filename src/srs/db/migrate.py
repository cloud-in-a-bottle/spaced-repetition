import sqlite3
from importlib import resources

from loguru import logger


def _migration_files() -> list[tuple[int, str]]:
    files = []
    for entry in resources.files("srs.db.migrations").iterdir():
        if entry.name.endswith(".sql"):
            version = int(entry.name.split("_", 1)[0])
            files.append((version, entry.read_text()))
    return sorted(files)


def migrate(conn: sqlite3.Connection) -> None:
    """Apply each `migrations/NNNN_*.sql` newer than the db's `user_version`, each in its own transaction."""
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    for version, sql in _migration_files():
        if version <= current:
            continue
        logger.info(f"applying migration {version}")
        conn.executescript(f"BEGIN;\n{sql}\nPRAGMA user_version = {version};\nCOMMIT;")
