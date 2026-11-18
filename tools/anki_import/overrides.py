import tomllib
from pathlib import Path

import attr


@attr.s(auto_attribs=True, frozen=True)
class TermOverride:
    pos: str
    lemma: str | None
    alternatives: list[str]
    tags: list[str]
    note: str | None
    gender: str | None


@attr.s(auto_attribs=True, frozen=True)
class Overrides:
    settings: dict[str, object]
    spelling: dict[str, str]
    term_fixes: dict[str, str]
    feminine_with_el: frozenset[str]
    terms: dict[str, TermOverride]
    conjugation_only_verbs: dict[str, str]
    conjugated_notes: dict[str, dict[str, object]]
    mandarin_pos: dict[str, str]
    mandarin_mine: dict[str, dict[str, str]]


def load_overrides(path: Path) -> Overrides:
    """Tables: [settings] (an srs settings body), [spanish.spelling], [spanish.term_fixes], spanish.feminine_with_el,
    [spanish.terms."<term>"] (pos, lemma, alternatives, tags, note, gender), [spanish.conjugation_only_verbs]
    (infinitive = gloss), [spanish.conjugated_notes], [mandarin.pos] (HSK pos -> srs pos) and [mandarin.mine]."""
    raw = tomllib.loads(path.read_text())
    es = raw["spanish"]
    return Overrides(
        settings=raw["settings"],
        spelling=es["spelling"],
        term_fixes=es["term_fixes"],
        feminine_with_el=frozenset(es["feminine_with_el"]),
        terms={
            k: TermOverride(
                pos=v["pos"],
                lemma=v.get("lemma"),
                alternatives=v.get("alternatives", []),
                tags=v.get("tags", []),
                note=v.get("note"),
                gender=v.get("gender"),
            )
            for k, v in es["terms"].items()
        },
        conjugation_only_verbs=es["conjugation_only_verbs"],
        conjugated_notes=es["conjugated_notes"],
        mandarin_pos=raw["mandarin"]["pos"],
        mandarin_mine=raw["mandarin"]["mine"],
    )
