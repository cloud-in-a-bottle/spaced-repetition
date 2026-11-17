from litestar.testing import TestClient

from srs.domain.clock import now_ms
from tests.unit.helpers import DAY_MS
from tests.unit.helpers import sync


def _bundle() -> dict:  # type: ignore[type-arg]
    t0 = now_ms() - 20 * DAY_MS
    return {
        "decks": [{"id": "spanish", "name": "Spanish"}],
        "items": [
            # forms come first here on purpose: the import orders lexemes ahead of them
            {
                "id": "hablo",
                "deck_id": "spanish",
                "kind": "form",
                "form": {"lexeme_id": "hablar", "form": "hablo", "features": {"person": "1st"}},
            },
            {
                "id": "hablar",
                "deck_id": "spanish",
                "kind": "lexeme",
                "language": "es",
                "lexeme": {"lemma": "hablar", "pos": "verb", "gloss": "to speak"},
            },
        ],
        "reviews": [
            {"id": "anki-1", "item_id": "hablar", "template_id": "lexeme-recognize", "rating": 3, "reviewed_at": t0},
            {
                "id": "anki-2",
                "item_id": "hablar",
                "template_id": "lexeme-recognize",
                "rating": 3,
                "reviewed_at": t0 + 3 * DAY_MS,
            },
        ],
    }


def test_import_is_idempotent(client: TestClient) -> None:  # type: ignore[type-arg]
    r = client.post("/api/import", json=_bundle())
    assert r.status_code == 201, r.text
    assert r.json() == {"decks": 1, "items": 2, "new_reviews": 2}
    r = client.post("/api/import", json=_bundle())
    assert r.json()["new_reviews"] == 0
    cards = sync(client)["cards"]
    assert len(cards) == 3
    recognize = next(c for c in cards if c["item_id"] == "hablar" and c["template_id"] == "lexeme-recognize")
    assert recognize["reps"] == 2 and recognize["state"] == "review"


def test_import_review_for_missing_card(client: TestClient) -> None:  # type: ignore[type-arg]
    bundle = _bundle()
    bundle["reviews"][0]["template_id"] = "form-recognize"
    assert client.post("/api/import", json=bundle).status_code == 400
    # the whole import is one transaction
    assert sync(client)["cards"] == []


def test_import_suspends_and_keeps_created_at(client: TestClient) -> None:  # type: ignore[type-arg]
    bundle = _bundle()
    bundle["items"][1]["created_at"] = 1_500_000_000_000
    bundle["suspended"] = [{"item_id": "hablar", "template_id": "lexeme-produce"}]
    assert client.post("/api/import", json=bundle).status_code == 201
    cards = {(c["item_id"], c["template_id"]): c for c in sync(client)["cards"]}
    assert cards[("hablar", "lexeme-produce")]["suspended"]
    assert not cards[("hablar", "lexeme-recognize")]["suspended"]
    assert cards[("hablar", "lexeme-produce")]["created_at"] == 1_500_000_000_000
    # re-importing without the suspension lifts it
    bundle["suspended"] = []
    client.post("/api/import", json=bundle)
    produce = next(c for c in sync(client)["cards"] if c["template_id"] == "lexeme-produce")
    assert not produce["suspended"]
