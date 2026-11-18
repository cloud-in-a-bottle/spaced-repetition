import gzip
import json
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from litestar.testing import TestClient

from srs.app import create_app
from srs.config import Config
from srs.dictionary.build import build_dictionary
from srs.reader.text_formats import parse_srt
from tests.unit.helpers import add_lexeme
from tests.unit.helpers import sync

WIKTIONARY = [
    {
        "word": "zarpar",
        "pos": "verb",
        "senses": [{"raw_glosses": ["(nautical) to set sail"], "glosses": ["to set sail"]}],
        "forms": [{"form": "no-table-tags", "source": "conjugation", "tags": ["table-tags"]}],
    },
    {
        "word": "tener",
        "pos": "verb",
        "senses": [{"glosses": ["to have"]}],
        "forms": [
            {"form": "irregular", "source": "conjugation", "tags": ["table-tags"]},
            {"form": "e-ie alternation", "source": "conjugation", "tags": ["class"]},
        ],
    },
    {
        "word": "tuve",
        "pos": "verb",
        "senses": [
            {"glosses": ["first-person singular preterite indicative of tener"], "form_of": [{"word": "tener"}]}
        ],
    },
    {
        "word": "zarpó",
        "pos": "verb",
        "senses": [
            {"glosses": ["third-person singular preterite indicative of zarpar"], "form_of": [{"word": "zarpar"}]}
        ],
    },
    {"word": "galeón", "pos": "noun", "senses": [{"glosses": ["galleon"], "tags": ["masculine"]}]},
    {"word": "barco", "pos": "noun", "senses": [{"glosses": ["boat, ship"], "tags": ["masculine"]}]},
    {"word": "barcos", "pos": "noun", "senses": [{"glosses": ["plural of barco"], "form_of": [{"word": "barco"}]}]},
    {"word": "el", "pos": "article", "senses": [{"glosses": ["the"]}]},
    {"word": "lista", "pos": "noun", "senses": [{"glosses": ["list"], "tags": ["feminine"]}]},
    {
        "word": "lista",
        "pos": "adj",
        "senses": [{"glosses": ["feminine singular of listo"], "form_of": [{"word": "listo"}]}],
    },
    {
        "word": "lista",
        "pos": "verb",
        "senses": [{"glosses": ["inflection of listar:"], "form_of": [{"word": "listar"}]}],
    },
    {"word": "listo", "pos": "adj", "senses": [{"glosses": ["ready; clever"]}]},
    {"word": "listar", "pos": "verb", "senses": [{"glosses": ["to list"]}]},
    {"word": "los", "pos": "article", "senses": [{"glosses": ["the (masculine plural)"]}]},
    {"word": "Lisboa", "pos": "name", "senses": [{"glosses": ["Lisbon"]}]},
    {
        "word": "dímelo",
        "pos": "verb",
        "senses": [
            {
                "glosses": ["imperative of decir combined with me and lo"],
                "form_of": [{"word": "decir combined with me and lo"}],
            }
        ],
    },
]
SRT = """1
00:00:01,000 --> 00:00:02,500
<i>El galeón zarpó.</i>

2
00:00:03,000 --> 00:00:04,000
de Lisboa. ¿Rocamora?
- Los barcos.
"""


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:  # type: ignore[type-arg]
    dump = tmp_path / "es.jsonl.gz"
    with gzip.open(dump, "wt") as f:
        f.writelines(json.dumps(e) + "\n" for e in WIKTIONARY)
    build_dictionary("es", tmp_path / "data" / "dictionaries" / "es.sqlite", dump)
    app = create_app(Config(db_path=tmp_path / "test.db", assume_owner=True, data_dir=tmp_path / "data"))
    with TestClient(app=app) as c:
        yield c


@pytest.fixture
def deck_id(client: TestClient) -> str:  # type: ignore[type-arg]
    return str(client.get("/api/decks").json()[0]["id"])


def _episode(client: TestClient) -> str:  # type: ignore[type-arg]
    course = client.put("/api/library/courses/mdt", json={"title": "El Ministerio del Tiempo", "language": "es"})
    assert course.status_code == 200, course.text
    r = client.put(
        "/api/library/texts/mdt-2",
        json={"course_id": "mdt", "title": "Episodio 2", "position": 2, "format": "srt", "content": SRT},
    )
    assert r.status_code == 200, r.text
    assert r.json()["blocks"] == 2 and r.json()["format"] == "subtitles"
    return "mdt-2"


def _know(client: TestClient, item: dict) -> None:  # type: ignore[type-arg]
    """Review an item's recognition card into long-term review, recently."""
    card = next(
        c for c in sync(client)["cards"] if c["item_id"] == item["id"] and c["template_id"] == "lexeme-recognize"
    )
    now = int(time.time() * 1000)
    reviews = [
        {
            "id": f"{card['id']}-{i}",
            "card_id": card["id"],
            "rating": 3,
            "reviewed_at": now - (3 - i) * 60_000,
            "duration_ms": 1,
        }
        for i in range(3)
    ]
    sync(client, 0, reviews)


def test_reading_shows_subtitles_with_word_statuses(client: TestClient, deck_id: str) -> None:  # type: ignore[type-arg]
    text_id = _episode(client)
    _know(
        client, add_lexeme(client, deck_id, "zarpar", "to set sail")
    )  # known; reached from "zarpó" via the dictionary
    add_lexeme(client, deck_id, "barco", "boat", pos="noun")  # in the deck but never studied
    client.put("/api/reader/marks", json={"language": "es", "words": ["el"], "status": "known"})

    r = client.get(f"/api/reader/texts/{text_id}").json()
    assert r["course_title"] == "El Ministerio del Tiempo" and r["dictionary"] is True
    assert r["blocks"][0]["start_ms"] == 1000 and r["blocks"][0]["end_ms"] == 2500
    assert "".join(t for t, _ in r["blocks"][0]["tokens"]) == "El galeón zarpó."  # markup dropped
    assert r["words"] == {
        "el": "known",  # marked
        "galeón": "new",
        "zarpó": "known",
        "de": "new",
        "lisboa": "name",  # only a name in the dictionary
        "rocamora": "name",  # not in the dictionary, always capitalized
        "los": "new",
        "barcos": "learning",  # plural of a deck word that isn't known yet
    }
    assert r["default_deck_id"] == deck_id


def test_review_set_words_stay_new(client: TestClient, deck_id: str) -> None:  # type: ignore[type-arg]
    rs = client.post("/api/decks", json={"name": "Episode 2", "ephemeral": True}).json()["id"]
    add_lexeme(client, rs, "galeón", "galleon", pos="noun")
    r = client.post("/api/reader/statuses", json={"language": "es", "words": ["galeón", "barcos"]})
    assert r.json() == {"galeón": "new", "barcos": "new"}
    d = client.get("/api/reader/word", params={"language": "es", "word": "galeón"}).json()
    assert [m["deck_id"] for m in d["review_sets"]] == [rs]  # still shown in the word panel


def test_word_details_suggest_the_lemma(client: TestClient, deck_id: str) -> None:  # type: ignore[type-arg]
    d = client.get("/api/reader/word", params={"language": "es", "word": "barcos"}).json()
    assert d["status"] == "new" and d["deck"] == []
    assert d["dictionary"][0]["form_of"] == [{"lemma": "barco", "description": "plural of barco", "english": None}]
    assert [e["word"] for e in d["lemma_entries"]] == ["barco"]
    assert d["suggestion"] == {"lemma": "barco", "pos": "noun", "gloss": "boat, ship", "gender": "masculine"}

    add_lexeme(client, deck_id, "barco", "boat", pos="noun")
    d = client.get("/api/reader/word", params={"language": "es", "word": "barcos"}).json()
    assert [(m["lemma"], m["via"], m["status"]) for m in d["deck"]] == [("barco", "dictionary", "learning")]

    # clitic forms resolve to the bare verb
    d = client.get("/api/reader/word", params={"language": "es", "word": "dímelo"}).json()
    assert d["dictionary"][0]["form_of"][0]["lemma"] == "decir"


def test_marks_can_be_cleared(client: TestClient, deck_id: str) -> None:  # type: ignore[type-arg]
    for status, expected in [("ignored", "ignored"), (None, "new")]:
        client.put("/api/reader/marks", json={"language": "es", "words": ["galeón"], "status": status})
        assert client.post("/api/reader/statuses", json={"language": "es", "words": ["galeón"]}).json() == {
            "galeón": expected
        }


def test_analyze_counts_words(client: TestClient, deck_id: str) -> None:  # type: ignore[type-arg]
    r = client.post(
        "/api/reader/analyze",
        json={
            "language": "es",
            "format": "srt",
            "content": SRT + SRT.replace("1\n", "3\n", 1).replace("2\n00:00:03", "4\n00:00:03"),
        },
    )
    top = r.json()[0]
    assert top["count"] == 2 and top["status"] in ("new", "name")


def test_library_lists_courses_and_navigates(client: TestClient, deck_id: str) -> None:  # type: ignore[type-arg]
    _episode(client)
    client.post(
        "/api/library/texts",
        json={
            "course_id": "mdt",
            "title": "Episodio 1",
            "position": 1,
            "format": "text",
            "content": "Hola.\n\nAdiós.",
        },
    )
    [course] = client.get("/api/library").json()
    assert [t["title"] for t in course["texts"]] == ["Episodio 1", "Episodio 2"]
    r = client.get("/api/reader/texts/mdt-2").json()
    assert r["previous_id"] == course["texts"][0]["id"] and r["next_id"] is None
    assert client.delete("/api/library/courses/mdt").status_code == 204
    assert client.get("/api/library").json() == []


def test_translation_without_a_key_is_unavailable(client: TestClient, deck_id: str) -> None:  # type: ignore[type-arg]
    r = client.post("/api/reader/translate", json={"language": "es", "kind": "text", "text": "Hola"})
    assert r.status_code == 503 and "key" in r.json()["detail"]


def test_without_a_dictionary_only_mid_sentence_capitals_are_names(tmp_path: Path) -> None:
    app = create_app(Config(db_path=tmp_path / "t.db", assume_owner=True, data_dir=tmp_path / "data"))
    with TestClient(app=app) as client:
        r = client.post("/api/reader/statuses", json={"language": "es", "words": ["Los barcos de Lisboa. Hola."]})
        assert r.json() == {"barcos": "new", "de": "new", "hola": "new", "lisboa": "name", "los": "new"}


def test_verb_forms_get_english_and_a_verb_class(client: TestClient, deck_id: str) -> None:  # type: ignore[type-arg]
    d = client.get("/api/reader/word", params={"language": "es", "word": "zarpó"}).json()
    [form] = d["dictionary"][0]["form_of"]
    assert form["english"] == "he/she/it set sail"
    assert d["lemma_entries"][0]["verb_class"] == {"label": "regular", "notes": []}

    d = client.get("/api/reader/word", params={"language": "es", "word": "tuve"}).json()
    assert d["dictionary"][0]["form_of"][0]["english"] == "I had"
    assert d["lemma_entries"][0]["verb_class"] == {"label": "irregular", "notes": ["e→ie"]}


def test_srt_line_wraps_and_split_sentences_are_joined() -> None:
    srt = (
        "1\n00:00:01,000 --> 00:00:02,000\nJulián, cógelo, que no\nencuentro mi cartera.\n\n"
        "2\n00:00:03,000 --> 00:00:04,000\n¿Quién es?\nDebe de ser tu amante.\n\n"
        "3\n00:00:05,000 --> 00:00:06,000\n¡Rocamora!\n- ¿Qué?\n\n"
        "4\n00:00:07,000 --> 00:00:08,000\nPara estar en 2015 pasando calamidades,\n\n"
        "5\n00:00:09,000 --> 00:00:10,000\nen mi tiempo me cunde más.\n"
    )
    assert [(b.text, b.start_ms, b.end_ms) for b in parse_srt(srt)] == [
        ("Julián, cógelo, que no encuentro mi cartera.", 1000, 2000),  # a wrap
        ("¿Quién es?\nDebe de ser tu amante.", 3000, 4000),  # a finished sentence keeps its line
        ("¡Rocamora!\n- ¿Qué?", 5000, 6000),  # so does a new speaker
        ("Para estar en 2015 pasando calamidades, en mi tiempo me cunde más.", 7000, 10000),  # merged cues
    ]


def test_known_marks_go_on_roots(client: TestClient, deck_id: str) -> None:  # type: ignore[type-arg]
    statuses = lambda *ws: client.post("/api/reader/statuses", json={"language": "es", "words": list(ws)}).json()  # noqa: E731
    # knowing one form knows the root, and so every other form
    client.put("/api/reader/marks", json={"language": "es", "words": ["barcos"], "status": "known"})
    assert statuses("barco", "barcos") == {"barco": "known", "barcos": "known"}
    d = client.get("/api/reader/word", params={"language": "es", "word": "barcos"}).json()
    assert (d["mark"], d["mark_root"], d["roots"]) == ("known", "barco", ["barco"])
    # clearing from any form clears the root
    client.put("/api/reader/marks", json={"language": "es", "words": ["barcos"], "status": None})
    assert statuses("barco", "barcos") == {"barco": "new", "barcos": "new"}

    # ignoring is per spelling
    client.put("/api/reader/marks", json={"language": "es", "words": ["zarpó"], "status": "ignored"})
    assert statuses("zarpó", "zarpar") == {"zarpó": "ignored", "zarpar": "new"}


def test_a_word_with_two_roots_lets_you_pick(client: TestClient, deck_id: str) -> None:  # type: ignore[type-arg]
    d = client.get("/api/reader/word", params={"language": "es", "word": "lista"}).json()
    assert d["roots"] == ["lista", "listar", "listo"]
    # unpicked, a headword is its own root
    client.put("/api/reader/marks", json={"language": "es", "words": ["lista"], "status": "known"})
    r = client.post("/api/reader/statuses", json={"language": "es", "words": ["lista", "listo", "listar"]}).json()
    assert r == {"lista": "known", "listo": "new", "listar": "new"}
    client.put("/api/reader/marks", json={"language": "es", "words": ["lista"], "status": None})
    client.put("/api/reader/marks", json={"language": "es", "words": ["lista"], "status": "known", "roots": ["listo"]})
    r = client.post("/api/reader/statuses", json={"language": "es", "words": ["lista", "listo", "listar"]}).json()
    assert r == {"lista": "known", "listo": "known", "listar": "new"}


def test_reading_progress_only_moves_forward(client: TestClient, deck_id: str) -> None:  # type: ignore[type-arg]
    text_id = _episode(client)
    assert client.get(f"/api/reader/texts/{text_id}").json()["progress_block"] is None
    progress = lambda block, force=False: client.put(  # noqa: E731
        f"/api/library/texts/{text_id}/progress", json={"block": block, "force": force}
    ).json()["progress_block"]
    assert progress(1) == 1
    assert progress(0) == 1  # going back to reread doesn't lose your place
    assert progress(99) == 1  # clamped to the last block
    assert progress(0, force=True) == 0
    assert client.get("/api/library").json()[0]["texts"][0]["progress_block"] == 0
