"""Builds an offline dictionary for one language from Wiktionary, as extracted by kaikki.org (wiktextract): every
headword with its English glosses, plus "form of" links that map inflections to their lemma ("zarpó" -> zarpar).
That's what lets the reader treat "zarpó" as a form of zarpar you may already know."""

import gzip
import json
import os
import sqlite3
import urllib.request
from collections.abc import Callable
from collections.abc import Iterator
from pathlib import Path
from typing import IO

from srs.domain.normalize import lookup_key

# kaikki.org names its per-language dumps by English language name.
KAIKKI_LANGUAGES = {
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "it": "Italian",
    "pt": "Portuguese",
}
SOURCE_URL = "https://kaikki.org/dictionary/{name}/kaikki.org-dictionary-{name}.jsonl.gz"
SCHEMA = """
CREATE TABLE entries (
    key TEXT NOT NULL,
    word TEXT NOT NULL,
    pos TEXT NOT NULL,
    gender TEXT,
    senses TEXT NOT NULL,
    form_of TEXT NOT NULL
);
CREATE TABLE meta (k TEXT PRIMARY KEY, v TEXT NOT NULL);
"""
MAX_SENSES = 8


def source_url(language: str) -> str:
    return SOURCE_URL.format(name=KAIKKI_LANGUAGES[language])


def _gender(senses: list[dict]) -> str | None:  # type: ignore[type-arg]
    for s in senses:
        tags = set(s.get("tags", []))
        if {"feminine", "masculine"} <= tags:
            return "common"
        if "feminine" in tags:
            return "feminine"
        if "masculine" in tags:
            return "masculine"
    return None


def _lemma(form_of_word: str) -> str:
    # clitic forms come through as eg "decir combined with indirect object me and direct object lo"
    return form_of_word.split(" combined with ")[0].strip()


def entry_row(d: dict) -> tuple[str, str, str, str | None, str, str] | None:  # type: ignore[type-arg]
    word = d.get("word", "")
    if not word or " " in word:  # the reader looks up single words only
        return None
    senses: list[str] = []
    form_of: list[dict[str, str]] = []
    for s in d.get("senses", []):
        glosses = s.get("raw_glosses") or s.get("glosses") or []
        if not glosses:
            continue
        if s.get("form_of"):
            form_of.append({"lemma": _lemma(s["form_of"][0]["word"]), "desc": " ".join(s.get("glosses", []))})
        elif len(senses) < MAX_SENSES:
            senses.append("; ".join(glosses))
    if not senses and not form_of:
        return None
    return (
        lookup_key(word),
        word,
        d.get("pos", ""),
        _gender(d.get("senses", [])),
        json.dumps(senses, ensure_ascii=False),
        json.dumps(form_of[:12], ensure_ascii=False),
    )


def _lines(source: str | Path) -> Iterator[str]:
    stream: IO[bytes]
    if str(source).startswith(("http://", "https://")):
        stream = urllib.request.urlopen(str(source), timeout=60)  # noqa: S310 - fixed kaikki.org URL
    else:
        stream = open(source, "rb")  # noqa: SIM115
    with stream, gzip.open(stream, "rt", encoding="utf-8") as text:
        yield from text


def build_dictionary(
    language: str, dest: Path, source: str | Path | None = None, progress: Callable[[int], None] | None = None
) -> int:
    """Stream the dump (from kaikki.org unless `source` is given) into a fresh sqlite file at `dest`, replacing it
    atomically when done. Returns the number of entries."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".building")
    tmp.unlink(missing_ok=True)
    db = sqlite3.connect(tmp)
    db.executescript(SCHEMA)
    count, batch = 0, []
    for line in _lines(source or source_url(language)):
        row = entry_row(json.loads(line))
        if row is None:
            continue
        batch.append(row)
        count += 1
        if len(batch) >= 5000:
            db.executemany("INSERT INTO entries VALUES (?, ?, ?, ?, ?, ?)", batch)
            batch = []
            if progress:
                progress(count)
    db.executemany("INSERT INTO entries VALUES (?, ?, ?, ?, ?, ?)", batch)
    db.execute("CREATE INDEX entries_key ON entries (key)")
    db.executemany(
        "INSERT INTO meta VALUES (?, ?)",
        [("language", language), ("source", str(source or source_url(language))), ("entries", str(count))],
    )
    db.commit()
    db.execute("VACUUM")
    db.close()
    os.replace(tmp, dest)
    return count
