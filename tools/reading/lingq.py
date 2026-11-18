"""Reading LingQ's vocabulary export (CSV: term, phrase, tags..., meanings...)."""

import csv
from pathlib import Path


def read_terms(path: Path) -> tuple[list[str], list[str]]:
    """(single words, multi-word phrases) from a LingQ CSV export. The export has no status column, so export the
    known LingQs (or whatever subset you mean) on their own."""
    with path.open(encoding="utf-8-sig", newline="") as f:
        terms = [row["term"].strip() for row in csv.DictReader(f) if row.get("term", "").strip()]
    words = sorted({t for t in terms if " " not in t})
    phrases = sorted({t for t in terms if " " in t})
    return words, phrases
