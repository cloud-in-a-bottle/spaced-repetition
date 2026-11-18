import json

from litestar.testing import TestClient

from srs.domain.clock import now_ms
from tests.unit.helpers import add_form
from tests.unit.helpers import add_lexeme
from tests.unit.helpers import sync

KNOWLEDGE = {"X-OpenHost-Consumer-Id": "a", "X-OpenHost-Permissions": json.dumps([{"grant": "knowledge:read"}])}


def _review_set(client: TestClient, name: str = "Episode 2", promote_to: str | None = None) -> str:  # type: ignore[type-arg]
    r = client.post("/api/decks", json={"name": name, "ephemeral": True, "promote_to": promote_to})
    assert r.status_code == 201, r.text
    return str(r.json()["id"])


def _known_lemmas(client: TestClient, words: list[str]) -> dict[str, list[str]]:  # type: ignore[type-arg]
    r = client.post("/service/v1/lexemes/lookup", json={"language": "es", "words": words}, headers=KNOWLEDGE)
    assert r.status_code == 200, r.text
    return {w["word"]: [m["lexeme"]["lemma"] for m in w["matches"]] for w in r.json()["results"]}


def _cards_of(client: TestClient, item_id: str, cursor: int = 0) -> list[dict]:  # type: ignore[type-arg]
    return [c for c in sync(client, cursor)["cards"] if c["item_id"] == item_id]


def test_review_set_items_stay_out_of_knowledge_until_promoted(client: TestClient, deck_id: str) -> None:  # type: ignore[type-arg]
    rs = _review_set(client, promote_to=deck_id)
    lx = add_lexeme(client, rs, "zarpar", "to set sail")
    assert _known_lemmas(client, ["zarpar"]) == {"zarpar": []}
    assert client.get("/service/v1/lexemes", params={"language": "es"}, headers=KNOWLEDGE).json()["lexemes"] == []

    r = client.post(f"/api/items/{lx['id']}/promote", json={})
    assert r.status_code == 201, r.text
    assert r.json()["created"] is True and r.json()["item"]["deck_id"] == deck_id
    assert _known_lemmas(client, ["zarpar"]) == {"zarpar": ["zarpar"]}
    # the review-set copy stays, and now shows where it went
    assert {c["main_deck_id"] for c in _cards_of(client, lx["id"])} == {deck_id}


def test_promote_carries_reviews_over(client: TestClient, deck_id: str) -> None:  # type: ignore[type-arg]
    rs = _review_set(client)
    lx = add_lexeme(client, rs, "galeón", "galleon", pos="noun")
    card = next(c for c in _cards_of(client, lx["id"]) if c["template_id"] == "lexeme-recognize")
    t = now_ms() - 60_000
    sync(client, 0, [{"id": "r1", "card_id": card["id"], "rating": 3, "reviewed_at": t, "duration_ms": 900}])

    copy = client.post(f"/api/items/{lx['id']}/promote", json={}).json()["item"]
    assert copy["deck_id"] == deck_id  # no promote_to: the main deck with most items in the language (the only one)
    copied = {c["template_id"]: c for c in _cards_of(client, copy["id"])}
    assert copied["lexeme-recognize"]["reps"] == 1 and copied["lexeme-recognize"]["state"] != "new"
    assert copied["lexeme-produce"]["reps"] == 0

    # later reviews of the review-set card don't touch the main copy
    sync(client, 0, [{"id": "r2", "card_id": card["id"], "rating": 1, "reviewed_at": t + 1000, "duration_ms": 1}])
    assert {c["template_id"]: c for c in _cards_of(client, copy["id"])}["lexeme-recognize"]["reps"] == 1


def test_promote_is_a_noop_when_already_in_a_main_deck(client: TestClient, deck_id: str) -> None:  # type: ignore[type-arg]
    main = add_lexeme(client, deck_id, "soldado", "soldier", pos="noun")
    rs = _review_set(client)
    lx = add_lexeme(client, rs, "soldado", "soldier", pos="noun")
    assert {c["main_deck_id"] for c in _cards_of(client, lx["id"])} == {deck_id}
    r = client.post(f"/api/items/{lx['id']}/promote", json={}).json()
    assert r == {"created": False, "item": r["item"]} and r["item"]["id"] == main["id"]


def test_main_deck_status_follows_main_deck_changes(client: TestClient, deck_id: str) -> None:  # type: ignore[type-arg]
    rs = _review_set(client)
    lx = add_lexeme(client, rs, "taberna", "tavern", pos="noun")
    assert {c["main_deck_id"] for c in _cards_of(client, lx["id"])} == {None}

    cursor = sync(client)["cursor"]
    main = add_lexeme(client, deck_id, "taberna", "tavern", pos="noun")
    assert {c["main_deck_id"] for c in _cards_of(client, lx["id"], cursor)} == {deck_id}

    cursor = sync(client)["cursor"]
    assert client.delete(f"/api/items/{main['id']}").status_code == 204
    assert {c["main_deck_id"] for c in _cards_of(client, lx["id"], cursor)} == {None}


def test_deleting_a_review_set_keeps_promoted_copies(client: TestClient, deck_id: str) -> None:  # type: ignore[type-arg]
    rs = _review_set(client)
    kept = add_lexeme(client, rs, "zarpar", "to set sail")
    add_form(client, rs, kept["id"], "zarpó", {"person": "3rd"})
    add_lexeme(client, rs, "navío", "ship", pos="noun")
    client.post(f"/api/items/{kept['id']}/promote", json={})

    assert client.delete(f"/api/decks/{rs}").status_code == 204
    assert [d["id"] for d in client.get("/api/decks").json()] == [deck_id]
    assert _known_lemmas(client, ["zarpar", "navío"]) == {"zarpar": ["zarpar"], "navío": []}
    assert client.get("/api/items", params={"deck_id": rs}).json() == []


def test_main_deck_items_cant_build_on_review_set_lexemes(client: TestClient, deck_id: str) -> None:  # type: ignore[type-arg]
    rs = _review_set(client)
    lx = add_lexeme(client, rs, "zarpar", "to set sail")
    r = client.post(
        "/api/items",
        json={"deck_id": deck_id, "kind": "form", "form": {"lexeme_id": lx["id"], "form": "zarpo", "features": {}}},
    )
    assert r.status_code == 400 and "review set" in r.json()["detail"]


def test_only_review_sets_promote(client: TestClient, deck_id: str) -> None:  # type: ignore[type-arg]
    lx = add_lexeme(client, deck_id, "hablar", "to speak")
    assert client.post(f"/api/items/{lx['id']}/promote", json={}).status_code == 400
    rs = _review_set(client)
    assert client.post("/api/decks", json={"name": "x", "promote_to": rs}).status_code == 400
    assert client.post("/api/decks", json={"name": "y", "ephemeral": True, "promote_to": rs}).status_code == 400


def test_promoted_copy_gets_the_usual_cards(client: TestClient, deck_id: str) -> None:  # type: ignore[type-arg]
    rs = _review_set(client)
    r = client.post(
        "/api/items",
        json={
            "deck_id": rs,
            "kind": "lexeme",
            "language": "es",
            "lexeme": {"lemma": "navío", "pos": "noun", "gloss": "ship"},
            "template_ids": ["lexeme-recognize"],
        },
    )
    copy = client.post(f"/api/items/{r.json()['id']}/promote", json={}).json()["item"]
    assert sorted(c["template_id"] for c in _cards_of(client, copy["id"])) == ["lexeme-produce", "lexeme-recognize"]
