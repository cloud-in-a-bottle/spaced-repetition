import json

import httpx
from openhost_test_harness import OpenhostStack
from playwright.sync_api import Page
from playwright.sync_api import expect


def test_health_endpoint(stack: OpenhostStack) -> None:
    response = httpx.get(f"{stack.app_url}/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_owner_api_through_router(stack: OpenhostStack) -> None:
    """The router marks owner requests with X-OpenHost-Is-Owner, which /api requires."""
    decks = stack.owner_session.get(f"{stack.url}/api/decks")
    assert decks.status_code == 200, decks.text
    deck_id = decks.json()[0]["id"]
    item = stack.owner_session.post(
        f"{stack.url}/api/items",
        json={
            "deck_id": deck_id,
            "kind": "lexeme",
            "language": "es",
            "lexeme": {"lemma": "gato", "pos": "noun", "gloss": "cat"},
        },
    )
    assert item.status_code == 201, item.text
    synced = stack.owner_session.post(f"{stack.url}/api/sync", json={"cursor": 0, "reviews": []}).json()
    assert any("gato" in c["front_html"] for c in synced["cards"])


def test_owner_api_needs_owner_header(stack: OpenhostStack) -> None:
    # straight to the container, as a service call would arrive: no owner header
    assert httpx.get(f"{stack.app_url}/api/decks").status_code == 401


def test_service_lookup(stack: OpenhostStack) -> None:
    headers = {
        "X-OpenHost-Consumer-Id": "consumer",
        "X-OpenHost-Consumer-Name": "consumer",
        "X-OpenHost-Permissions": json.dumps([{"grant": "knowledge:read", "scope": "global"}]),
    }
    r = httpx.post(
        f"{stack.app_url}/service/v1/lexemes/lookup", json={"language": "es", "words": ["xyz"]}, headers=headers
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"results": [{"word": "xyz", "matches": []}]}


def test_home_page_renders(stack: OpenhostStack, page: Page) -> None:
    stack.playwright_login(page)
    page.goto(stack.url)
    expect(page.get_by_text("All decks")).to_be_visible()
    expect(page.locator("#sync-status")).to_have_text("Synced")
