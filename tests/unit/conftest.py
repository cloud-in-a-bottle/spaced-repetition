from collections.abc import Iterator
from pathlib import Path

import pytest
from litestar.testing import TestClient

from srs.app import create_app
from srs.config import Config


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:  # type: ignore[type-arg]
    app = create_app(Config(db_path=tmp_path / "test.db", assume_owner=True))
    with TestClient(app=app) as c:
        yield c


@pytest.fixture
def deck_id(client: TestClient) -> str:  # type: ignore[type-arg]
    decks = client.get("/api/decks").json()
    return str(decks[0]["id"])
