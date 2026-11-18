"""Review sets: throwaway study decks (see the app's README), eg the words to know before an episode."""

import re
import unicodedata
from typing import Any

from tools.reading.client import SrsClient


def slug(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def review_set_bundle(
    deck_id: str,
    name: str,
    words: list[dict[str, Any]],
    language: str = "es",
    promote_to: str | None = None,
    tags: list[str] | None = None,
    templates: list[str] | None = None,
    created_at: int = 1_795_000_000_000,
) -> dict[str, Any]:
    """An import bundle for a review set. `words`, in study order: [{"lemma", "pos", "gloss", "gender"?, "notes"?}].
    Recognition cards only by default (that's what reading and watching need); "add to main deck" gives a word
    the usual cards later."""
    items = []
    for rank, w in enumerate(words):
        features = {}
        if w.get("pos") == "noun" and w.get("gender") in ("masculine", "feminine"):
            features = {
                "gender": w["gender"],
                "article": w.get("article") or ("la" if w["gender"] == "feminine" else "el"),
            }
        items.append(
            {
                "id": f"{deck_id}-{slug(w['lemma'])}-{w['pos']}",
                "deck_id": deck_id,
                "kind": "lexeme",
                "language": language,
                "tags": tags or [],
                "lexeme": {
                    "lemma": w["lemma"],
                    "pos": w["pos"],
                    "gloss": w["gloss"],
                    "features": features,
                    "notes": w.get("notes", ""),
                },
                "template_ids": templates or ["lexeme-recognize"],
                "created_at": created_at + rank,  # new cards come up in this order
            }
        )
    deck = {"id": deck_id, "name": name, "ephemeral": True, "promote_to": promote_to}
    return {"decks": [deck], "items": items}


def import_bundle(client: SrsClient, bundle: dict[str, Any]) -> Any:
    return client.post("/import", bundle)
