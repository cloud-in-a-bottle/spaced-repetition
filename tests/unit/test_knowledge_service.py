import json

from litestar.testing import TestClient

from srs.domain.clock import now_ms
from tests.unit.helpers import DAY_MS
from tests.unit.helpers import add_form
from tests.unit.helpers import add_lexeme
from tests.unit.helpers import sync


def _service_headers(*grants: str) -> dict[str, str]:
    return {
        "X-OpenHost-Consumer-Id": "app-123",
        "X-OpenHost-Consumer-Name": "language-app",
        "X-OpenHost-Permissions": json.dumps([{"grant": g, "scope": "global"} for g in grants]),
    }


def _lookup(client: TestClient, words: list[str], headers: dict[str, str]):  # type: ignore[no-untyped-def,type-arg]
    return client.post("/service/v1/lexemes/lookup", json={"language": "es", "words": words}, headers=headers)


def test_requires_grant(client: TestClient, deck_id: str) -> None:  # type: ignore[type-arg]
    r = _lookup(client, ["hablar"], _service_headers())
    assert r.status_code == 403
    assert r.json() == {
        "error": "permission_required",
        "required_grant": {"grant": "knowledge:read", "scope": "global"},
    }


def test_requires_router_headers(client: TestClient, deck_id: str) -> None:  # type: ignore[type-arg]
    assert _lookup(client, ["hablar"], {}).status_code == 403


def test_lookup_by_lemma_and_form(client: TestClient, deck_id: str) -> None:  # type: ignore[type-arg]
    lx = add_lexeme(client, deck_id, "hablar", "to speak")
    form = add_form(client, deck_id, lx["id"], "hablo", {"person": "1st"})
    add_lexeme(client, deck_id, "casa", "house", pos="noun")
    cards = sync(client)["cards"]
    recognize = next(c for c in cards if c["item_id"] == lx["id"] and c["template_id"] == "lexeme-recognize")
    t0 = now_ms() - 5 * DAY_MS
    sync(
        client,
        0,
        [
            {"id": "r1", "card_id": recognize["id"], "rating": 3, "reviewed_at": t0},
            {"id": "r2", "card_id": recognize["id"], "rating": 3, "reviewed_at": t0 + 600_000},
        ],
    )

    r = _lookup(client, ["Hablar", "hablo", "casa", "perro"], _service_headers("knowledge:read"))
    assert r.status_code == 200, r.text
    hablar, hablo, casa, perro = r.json()["results"]

    assert hablar["word"] == "Hablar"
    [m] = hablar["matches"]
    assert m["matched_lemma"] and m["matched_form_ids"] == []
    assert m["lexeme"]["lemma"] == "hablar" and m["lexeme"]["pos"] == "verb"
    assert m["lexeme"]["status"] == "known"
    assert 0 < m["lexeme"]["recall_probability"] < 1
    assert {s["skill"] for s in m["lexeme"]["skills"]} == {"recognize", "produce"}
    assert m["lexeme"]["forms"][0]["form"] == "hablo"

    [m] = hablo["matches"]
    assert not m["matched_lemma"] and m["matched_form_ids"] == [form["id"]] and m["lexeme"]["lemma"] == "hablar"

    assert casa["matches"][0]["lexeme"]["status"] == "new"
    assert perro["matches"] == []


def test_language_is_respected(client: TestClient, deck_id: str) -> None:  # type: ignore[type-arg]
    add_lexeme(client, deck_id, "die", "the", pos="determiner", language="de")
    [res] = _lookup(client, ["die"], _service_headers("knowledge:read")).json()["results"]
    assert res["matches"] == []


def test_list_lexemes_with_status_filter(client: TestClient, deck_id: str) -> None:  # type: ignore[type-arg]
    add_lexeme(client, deck_id, "hablar", "to speak")
    h = _service_headers("knowledge:read")
    r = client.get("/service/v1/lexemes", params={"language": "es"}, headers=h)
    assert r.status_code == 200, r.text
    assert [lx["lemma"] for lx in r.json()["lexemes"]] == ["hablar"]
    r = client.get("/service/v1/lexemes", params={"language": "es", "status": "known"}, headers=h)
    assert r.json()["lexemes"] == []


def test_owner_api_rejects_non_owner(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from srs.app import create_app  # noqa: PLC0415
    from srs.config import Config  # noqa: PLC0415

    app = create_app(Config(db_path=tmp_path / "x.db", assume_owner=False))
    with TestClient(app=app) as c:
        assert c.get("/api/decks").status_code == 401
        assert c.get("/api/decks", headers={"X-OpenHost-Is-Owner": "true"}).status_code == 200


def test_lookup_matches_alternatives(client: TestClient, deck_id: str) -> None:  # type: ignore[type-arg]
    lx = add_lexeme(client, deck_id, "salir", "to leave")
    r = client.post(
        "/api/items",
        json={
            "deck_id": deck_id,
            "kind": "form",
            "form": {
                "lexeme_id": lx["id"],
                "form": "salieran",
                "alternatives": ["saliesen"],
                "features": {"mood": "subjunctive", "tense": "imperfect"},
            },
        },
    )
    assert r.status_code == 201, r.text
    [res] = _lookup(client, ["Saliesen"], _service_headers("knowledge:read")).json()["results"]
    assert res["matches"][0]["matched_form_ids"] == [r.json()["id"]]
