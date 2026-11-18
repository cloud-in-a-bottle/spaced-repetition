"""Read side of the offline dictionaries (see build.py), plus installing them in the background."""

import json
import sqlite3
import threading
from pathlib import Path

import attr
from loguru import logger

from srs.dictionary.build import KAIKKI_LANGUAGES
from srs.dictionary.build import build_dictionary
from srs.domain.normalize import lookup_key

# wiktextract part-of-speech names -> ours (srs.domain.kinds.PartOfSpeech)
POS = {
    "noun": "noun",
    "verb": "verb",
    "adj": "adjective",
    "adv": "adverb",
    "prep": "preposition",
    "pron": "pronoun",
    "conj": "conjunction",
    "intj": "interjection",
    "num": "numeral",
    "det": "determiner",
    "article": "determiner",
    "particle": "particle",
    "name": "proper_noun",
}


@attr.s(auto_attribs=True, frozen=True)
class FormOf:
    lemma: str
    # eg "third-person singular preterite indicative of zarpar"
    description: str


@attr.s(auto_attribs=True, frozen=True)
class DictEntry:
    word: str
    # ours where it maps (see POS), else wiktextract's own name
    pos: str
    gender: str | None
    senses: list[str]
    form_of: list[FormOf]


class Dictionary:
    def __init__(self, path: Path) -> None:
        self._conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, check_same_thread=False)
        self._lock = threading.Lock()

    def entries(self, word: str) -> list[DictEntry]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT word, pos, gender, senses, form_of FROM entries WHERE key = ?", (lookup_key(word),)
            ).fetchall()
        return [
            DictEntry(
                word=w,
                pos=POS.get(pos, pos),
                gender=gender,
                senses=json.loads(senses),
                form_of=[FormOf(lemma=f["lemma"], description=f["desc"]) for f in json.loads(form_of)],
            )
            for w, pos, gender, senses, form_of in rows
        ]

    def lemmas(self, word: str) -> set[str]:
        """Dictionary forms a word could be: the lemmas it's an inflection of, plus itself if it's a headword."""
        result = set()
        for e in self.entries(word):
            if e.senses and e.pos != "proper_noun":
                result.add(lookup_key(e.word))
            result.update(lookup_key(f.lemma) for f in e.form_of)
        return result

    def is_only_a_name(self, word: str) -> bool:
        entries = self.entries(word)
        return bool(entries) and all(e.pos == "proper_noun" for e in entries)

    def close(self) -> None:
        self._conn.close()


@attr.s(auto_attribs=True)
class InstallStatus:
    # missing | installing | installed | failed
    state: str
    entries: int = 0
    error: str | None = None


class Dictionaries:
    """The installed dictionaries under `data_dir`, opened lazily, and installs running in background threads."""

    def __init__(self, data_dir: Path) -> None:
        self._dir = data_dir / "dictionaries"
        self._open: dict[str, Dictionary] = {}
        self._installing: dict[str, InstallStatus] = {}
        self._lock = threading.Lock()

    def path(self, language: str) -> Path:
        return self._dir / f"{language}.sqlite"

    def get(self, language: str) -> Dictionary | None:
        with self._lock:
            if language not in self._open and self.path(language).exists():
                self._open[language] = Dictionary(self.path(language))
            return self._open.get(language)

    def status(self, language: str) -> InstallStatus:
        with self._lock:
            if language in self._installing:
                return attr.evolve(self._installing[language])
        return InstallStatus(state="installed" if self.path(language).exists() else "missing")

    def available(self) -> list[str]:
        return sorted(KAIKKI_LANGUAGES)

    def install(self, language: str, source: str | None = None) -> InstallStatus:
        """Download and build in the background (a few minutes for Spanish); replaces any installed copy."""
        if language not in KAIKKI_LANGUAGES:
            raise ValueError(f"no dictionary source for {language!r}")
        with self._lock:
            current = self._installing.get(language)
            if current is not None and current.state == "installing":
                return attr.evolve(current)
            status = InstallStatus(state="installing")
            self._installing[language] = status

        def progress(n: int) -> None:
            status.entries = n

        def run() -> None:
            try:
                n = build_dictionary(language, self.path(language), source, progress)
                with self._lock:
                    old = self._open.pop(language, None)
                    if old is not None:
                        old.close()
                    status.state, status.entries = "installed", n
                logger.info(f"installed {language} dictionary: {n} entries")
            except Exception as e:
                logger.exception(f"installing {language} dictionary failed")
                status.state, status.error = "failed", str(e)

        threading.Thread(target=run, name=f"dictionary-{language}", daemon=True).start()
        return attr.evolve(status)
