from litestar.testing import TestClient

from tests.unit.helpers import add_form
from tests.unit.helpers import add_lexeme
from tests.unit.helpers import sync


def test_lexeme_gets_default_cards(client: TestClient, deck_id: str) -> None:  # type: ignore[type-arg]
    item = add_lexeme(client, deck_id, "hablar", "to speak")
    assert {c["template_id"] for c in item["cards"]} == {"lexeme-recognize", "lexeme-produce"}
    cards = {c["template_id"]: c for c in sync(client)["cards"]}
    assert "hablar" in cards["lexeme-recognize"]["front_html"]
    assert "to speak" not in cards["lexeme-recognize"]["front_html"]
    assert "to speak" in cards["lexeme-recognize"]["back_html"]
    assert cards["lexeme-recognize"]["state"] == "new"


def test_form_renders_with_its_lexeme(client: TestClient, deck_id: str) -> None:  # type: ignore[type-arg]
    lx = add_lexeme(client, deck_id, "hablar", "to speak")
    form = add_form(client, deck_id, lx["id"], "hablo", {"tense": "present", "person": "1st", "number": "singular"})
    assert form["language"] == "es"
    card = next(c for c in sync(client)["cards"] if c["item_id"] == form["id"])
    assert "hablar" in card["front_html"] and "present · 1st · singular" in card["front_html"]
    assert "hablo" in card["back_html"]


def test_editing_lexeme_rerenders_forms(client: TestClient, deck_id: str) -> None:  # type: ignore[type-arg]
    lx = add_lexeme(client, deck_id, "hablar", "to speak")
    form = add_form(client, deck_id, lx["id"], "hablo", {"person": "1st"})
    cursor = sync(client)["cursor"]
    body = {k: lx[k] for k in ("deck_id", "kind", "language", "tags", "lexeme")}
    body["lexeme"] = {**lx["lexeme"], "lemma": "hablarr"}
    assert client.put(f"/api/items/{lx['id']}", json=body).status_code == 200
    changed = sync(client, cursor)["cards"]
    form_card = next(c for c in changed if c["item_id"] == form["id"])
    assert "hablarr" in form_card["front_html"]


def test_html_in_fields_is_escaped(client: TestClient, deck_id: str) -> None:  # type: ignore[type-arg]
    add_lexeme(client, deck_id, "<script>x</script>", "y")
    card = next(c for c in sync(client)["cards"] if c["template_id"] == "lexeme-recognize")
    assert "<script>x" not in card["front_html"] and "&lt;script&gt;" in card["front_html"]


def test_kind_data_mismatch_rejected(client: TestClient, deck_id: str) -> None:  # type: ignore[type-arg]
    r = client.post("/api/items", json={"deck_id": deck_id, "kind": "lexeme", "fact": {"front": "a", "back": "b"}})
    assert r.status_code == 400


def test_lexeme_needs_language(client: TestClient, deck_id: str) -> None:  # type: ignore[type-arg]
    r = client.post(
        "/api/items",
        json={"deck_id": deck_id, "kind": "lexeme", "lexeme": {"lemma": "a", "pos": "noun", "gloss": "b"}},
    )
    assert r.status_code == 400


def test_choose_templates_and_toggle(client: TestClient, deck_id: str) -> None:  # type: ignore[type-arg]
    r = client.put(
        "/api/items/fixed-id",
        json={
            "deck_id": deck_id,
            "kind": "fact",
            "fact": {"front": "2+2", "back": "4"},
            "template_ids": ["fact-recall"],
        },
    )
    assert r.status_code == 200, r.text
    assert len(r.json()["cards"]) == 1
    r = client.put(
        "/api/items/fixed-id",
        json={"deck_id": deck_id, "kind": "fact", "fact": {"front": "2+2", "back": "4"}, "template_ids": []},
    )
    assert r.json()["cards"] == []
    deleted = [c for c in sync(client)["cards"] if c["item_id"] == "fixed-id"]
    assert len(deleted) == 1 and deleted[0]["deleted"]


def test_delete_item_tombstones_cards(client: TestClient, deck_id: str) -> None:  # type: ignore[type-arg]
    lx = add_lexeme(client, deck_id, "casa", "house", pos="noun")
    cursor = sync(client)["cursor"]
    assert client.delete(f"/api/items/{lx['id']}").status_code == 204
    changed = sync(client, cursor)["cards"]
    assert len(changed) == 2 and all(c["deleted"] for c in changed)
