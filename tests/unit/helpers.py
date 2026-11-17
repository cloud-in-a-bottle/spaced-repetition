from litestar.testing import TestClient

DAY_MS = 86_400_000


def add_lexeme(
    client: TestClient, deck_id: str, lemma: str, gloss: str, pos: str = "verb", language: str = "es"
) -> dict:  # type: ignore[type-arg]
    r = client.post(
        "/api/items",
        json={
            "deck_id": deck_id,
            "kind": "lexeme",
            "language": language,
            "lexeme": {"lemma": lemma, "pos": pos, "gloss": gloss},
        },
    )
    assert r.status_code == 201, r.text
    return r.json()  # type: ignore[no-any-return]


def add_form(client: TestClient, deck_id: str, lexeme_id: str, form: str, features: dict[str, str]) -> dict:  # type: ignore[type-arg]
    r = client.post(
        "/api/items",
        json={
            "deck_id": deck_id,
            "kind": "form",
            "form": {"lexeme_id": lexeme_id, "form": form, "features": features},
        },
    )
    assert r.status_code == 201, r.text
    return r.json()  # type: ignore[no-any-return]


def sync(client: TestClient, cursor: int = 0, reviews: list[dict] | None = None) -> dict:  # type: ignore[type-arg]
    r = client.post("/api/sync", json={"cursor": cursor, "reviews": reviews or []})
    assert r.status_code == 201, r.text
    return r.json()  # type: ignore[no-any-return]
