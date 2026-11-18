import pytest

from srs.reader.conjugation import english_form
from srs.reader.conjugation import verb_class

RENOUNCE = ["(transitive) to renounce, to give up"]


@pytest.mark.parametrize(
    ("description", "english"),
    [
        ("first-person singular preterite indicative of renunciar", "I renounced"),
        ("inflection of renunciar: third-person singular present indicative", "he/she/it renounces"),
        ("third-person plural present subjunctive of renunciar", "(that) they renounce"),
        (
            "first/third-person singular imperfect subjunctive of renunciar",
            "(if) I renounced / (if) he/she/it renounced",
        ),
        ("first-person plural present/preterite indicative of renunciar", "we renounce / we renounced"),
        ("second-person singular voseo imperative of renunciar", "renounce! (vos)"),
        ("second-person plural imperative of renunciar", "renounce! (vosotros)"),
        ("first-person plural conditional of renunciar", "we would renounce"),
        ("gerund of renunciar", "renouncing"),
        ("past participle of renunciar", "renounced"),
        ("feminine singular of renunciado", None),
        ("second-person plural imperative of renunciar combined with me", "renounce! (vosotros) (+ me)"),
        (
            "second-person singular imperative of renunciar combined with indirect object me and direct object lo",
            "renounce! (tú) (+ me, lo)",
        ),
    ],
)
def test_english_form(description: str, english: str | None) -> None:
    assert english_form(description, RENOUNCE) == english


def test_irregular_english_verbs() -> None:
    assert (
        english_form("first/third-person singular imperfect subjunctive of ser", ["to be"])
        == "(if) I were / (if) he/she/it were"
    )
    assert english_form("third-person singular preterite indicative of jurar", ["to swear, vow"]) == "he/she/it swore"
    assert english_form("first-person plural preterite indicative of rendir", ["to give up"]) == "we gave up"


def test_verb_class() -> None:
    assert verb_class(False, []).label == "regular"
    assert verb_class(True, ["e-ie"]).label == "irregular"
    assert verb_class(False, ["o-ue"]).label == "stem-changing"
    assert verb_class(False, ["c-qu"]).notes == ["c→qu (spelling)"]
    assert verb_class(False, ["c-qu"]).label == "regular"
    assert verb_class(False, ["i-í"]).notes == ["i→í (accent)"]
