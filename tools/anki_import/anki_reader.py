"""Reads an anki .colpkg backup (the zstd 'collection.anki21b' format, anki >= 2.1.50) straight from its sqlite."""

import sqlite3
import tempfile
import zipfile
from pathlib import Path

import attr
import zstandard


@attr.s(auto_attribs=True, frozen=True)
class AnkiCard:
    id: int
    ord: int
    deck: str
    # anki queue: -3/-2 buried, -1 suspended, 0 new, 1/3 learning, 2 review
    queue: int


@attr.s(auto_attribs=True, frozen=True)
class AnkiNote:
    id: int
    notetype: str
    fields: dict[str, str]
    tags: list[str]
    cards: list[AnkiCard]


@attr.s(auto_attribs=True, frozen=True)
class AnkiReview:
    id: int  # ms timestamp of the review
    card_id: int
    ease: int  # 1-4 (0 for manual reschedules)
    type: int  # 0 learn, 1 review, 2 relearn, 3 filtered, 4 manual
    time_ms: int


@attr.s(auto_attribs=True, frozen=True)
class AnkiCollection:
    notes: list[AnkiNote]
    reviews: list[AnkiReview]


def _decompress_collection(colpkg: Path, out_dir: Path) -> Path:
    with zipfile.ZipFile(colpkg) as z:
        names = z.namelist()
        if "collection.anki21b" not in names:
            raise ValueError(f"{colpkg} isn't a new-format backup (no collection.anki21b); entries: {names}")
        raw = z.read("collection.anki21b")
    db_path = out_dir / "collection.sqlite"
    with zstandard.ZstdDecompressor().stream_reader(raw) as reader:
        db_path.write_bytes(reader.read())
    return db_path


def read_colpkg(colpkg: Path) -> AnkiCollection:
    with tempfile.TemporaryDirectory() as tmp:
        db_path = _decompress_collection(colpkg, Path(tmp))
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.create_collation("unicase", lambda a, b: (a.casefold() > b.casefold()) - (a.casefold() < b.casefold()))
        deck_names = {r["id"]: r["name"].replace("\x1f", "::") for r in conn.execute("SELECT id, name FROM decks")}
        notetype_names = {r["id"]: r["name"] for r in conn.execute("SELECT id, name FROM notetypes")}
        field_names: dict[int, list[str]] = {}
        for r in conn.execute("SELECT ntid, ord, name FROM fields ORDER BY ntid, ord"):
            field_names.setdefault(r["ntid"], []).append(r["name"])
        cards_by_note: dict[int, list[AnkiCard]] = {}
        for r in conn.execute("SELECT id, nid, ord, did, queue FROM cards ORDER BY nid, ord"):
            cards_by_note.setdefault(r["nid"], []).append(
                AnkiCard(id=r["id"], ord=r["ord"], deck=deck_names[r["did"]], queue=r["queue"])
            )
        notes = []
        for r in conn.execute("SELECT id, mid, flds, tags FROM notes ORDER BY id"):
            names = field_names[r["mid"]]
            values = r["flds"].split("\x1f")
            notes.append(
                AnkiNote(
                    id=r["id"],
                    notetype=notetype_names[r["mid"]],
                    fields=dict(zip(names, values, strict=True)),
                    tags=r["tags"].split(),
                    cards=cards_by_note.get(r["id"], []),
                )
            )
        reviews = [
            AnkiReview(id=r["id"], card_id=r["cid"], ease=r["ease"], type=r["type"], time_ms=r["time"])
            for r in conn.execute("SELECT id, cid, ease, type, time FROM revlog ORDER BY id")
        ]
        conn.close()
    return AnkiCollection(notes=notes, reviews=reviews)
