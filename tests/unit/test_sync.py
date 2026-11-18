from litestar.testing import TestClient

from srs.domain.clock import now_ms
from tests.unit.helpers import DAY_MS
from tests.unit.helpers import add_form
from tests.unit.helpers import add_lexeme
from tests.unit.helpers import sync


def _recognize_card(client: TestClient, deck_id: str) -> dict:  # type: ignore[type-arg]
    add_lexeme(client, deck_id, "hablar", "to speak")
    return next(c for c in sync(client)["cards"] if c["template_id"] == "lexeme-recognize")


def _review(card_id: str, rid: str, rating: int, at: int) -> dict:  # type: ignore[type-arg]
    return {"id": rid, "card_id": card_id, "rating": rating, "reviewed_at": at}


def test_reviews_update_schedule_and_are_idempotent(client: TestClient, deck_id: str) -> None:  # type: ignore[type-arg]
    card = _recognize_card(client, deck_id)
    t0 = now_ms() - 10 * DAY_MS
    reviews = [_review(card["id"], "r1", 3, t0), _review(card["id"], "r2", 3, t0 + 600_000)]
    first = sync(client, 0, reviews)
    after = next(c for c in first["cards"] if c["id"] == card["id"])
    assert after["state"] == "review" and after["reps"] == 2
    # re-sending the same reviews (eg a retried sync) changes nothing
    again = sync(client, first["cursor"], reviews)
    assert again["cards"] == []


def test_order_of_arrival_does_not_matter(client: TestClient, deck_id: str) -> None:  # type: ignore[type-arg]
    """Two devices review offline; whichever syncs first, the result is the replay of all reviews in time order."""
    card = _recognize_card(client, deck_id)
    t0 = now_ms() - 30 * DAY_MS
    device_a = [_review(card["id"], "a1", 3, t0), _review(card["id"], "a2", 3, t0 + 2 * DAY_MS)]
    device_b = [_review(card["id"], "b1", 1, t0 + DAY_MS), _review(card["id"], "b2", 4, t0 + 5 * DAY_MS)]
    sync(client, 0, device_b)
    final = next(c for c in sync(client, 0, device_a)["cards"] if c["id"] == card["id"])

    other = next(c for c in sync(client, 0)["cards"] if c["template_id"] == "lexeme-produce")
    remap = [{**r, "card_id": other["id"], "id": "x" + r["id"]} for r in device_a + device_b]
    # same reviews (same ids, so same fuzz) on a fresh card, all at once
    in_one_go = next(c for c in sync(client, 0, remap)["cards"] if c["id"] == other["id"])
    assert final["reps"] == in_one_go["reps"] == 4
    assert final["stability"] == in_one_go["stability"]
    assert final["difficulty"] == in_one_go["difficulty"]


def test_unknown_card_rejected(client: TestClient, deck_id: str) -> None:  # type: ignore[type-arg]
    r = client.post("/api/sync", json={"cursor": 0, "reviews": [_review("nope", "r1", 3, now_ms())]})
    assert r.status_code == 400


def test_future_review_rejected(client: TestClient, deck_id: str) -> None:  # type: ignore[type-arg]
    card = _recognize_card(client, deck_id)
    r = client.post("/api/sync", json={"cursor": 0, "reviews": [_review(card["id"], "r1", 3, now_ms() + 3 * DAY_MS)]})
    assert r.status_code == 400


def test_settings_change_replays(client: TestClient, deck_id: str) -> None:  # type: ignore[type-arg]
    card = _recognize_card(client, deck_id)
    t0 = now_ms() - DAY_MS
    first = sync(client, 0, [_review(card["id"], "r1", 4, t0)])
    due_before = next(c for c in first["cards"] if c["id"] == card["id"])["due"]
    settings = client.get("/api/settings").json()
    settings["desired_retention"] = 0.7
    assert client.put("/api/settings", json=settings).status_code == 200
    changed = sync(client, first["cursor"])
    assert changed["settings"]["desired_retention"] == 0.7
    due_after = next(c for c in changed["cards"] if c["id"] == card["id"])["due"]
    assert due_after > due_before


def test_first_sync_includes_settings_and_decks(client: TestClient, deck_id: str) -> None:  # type: ignore[type-arg]
    first = sync(client)
    assert first["settings"] is not None
    assert [d["id"] for d in first["decks"]] == [deck_id]
    assert sync(client, first["cursor"])["settings"] is None


def test_cards_carry_part_of_speech(client: TestClient, deck_id: str) -> None:  # type: ignore[type-arg]
    lx = add_lexeme(client, deck_id, "rojo", "red", pos="noun")
    form = add_form(client, deck_id, lx["id"], "roja", {"gender": "feminine"})
    client.post("/api/items", json={"deck_id": deck_id, "kind": "fact", "fact": {"front": "2+2", "back": "4"}})
    by_item = {c["item_id"]: c["pos"] for c in sync(client)["cards"]}
    assert by_item[lx["id"]] == "noun"
    assert by_item[form["id"]] == "noun"  # a form files under its lexeme's part of speech
    assert None in by_item.values()  # facts have none

    cursor = sync(client)["cursor"]
    body = {k: lx[k] for k in ("deck_id", "kind", "language", "tags", "lexeme")}
    body["lexeme"] = {**lx["lexeme"], "pos": "adjective"}
    assert client.put(f"/api/items/{lx['id']}", json=body).status_code == 200
    changed = {c["item_id"]: c["pos"] for c in sync(client, cursor)["cards"]}
    assert changed == {lx["id"]: "adjective", form["id"]: "adjective"}
