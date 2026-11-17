from tools.anki_import.anki_reader import AnkiNote
from tools.anki_import.builder import Builder
from tools.anki_import.overrides import Overrides
from tools.anki_import.text import clean
from tools.anki_import.text import one_line

DECK = "Mandarin"


def import_hsk(note: AnkiNote, b: Builder, ov: Overrides) -> None:
    f = {k: one_line(v) for k, v in note.fields.items()}
    simplified = f["Simplified"]
    if not simplified:
        b.skip("HSK note with no characters", note)
        return
    mine = ov.mandarin_mine.get(simplified) if not f.get("Pinyin.1") else None
    raw_pos = f.get("Part of speech", "")
    pos = mine["pos"] if mine else ov.mandarin_pos.get(raw_pos)
    if pos is None:
        raise ValueError(f"unmapped HSK part of speech {raw_pos!r}; add it to overrides.toml")
    features: dict[str, str] = {}
    if f.get("Pinyin.1"):
        features["pinyin"] = f["Pinyin.1"]
    level = next((t.removeprefix("HSK") for t in note.tags if t.startswith("HSK") and t != "HSK"), None)
    if level:
        features["hsk_level"] = f"HSK {level}"
    if raw_pos and raw_pos != pos.replace("_", " "):
        features["pos_detail"] = raw_pos
    sentence = [clean(note.fields.get(k, "")) for k in ("SentenceSimplified", "SentencePinyin.1", "SentenceMeaning")]
    traditional = f.get("Traditional", "")
    b.add(
        item_id=f"zh-{pos}-{simplified}",
        deck=DECK,
        kind="lexeme",
        language="zh",
        data={
            "lemma": simplified,
            "pos": pos,
            "gloss": mine["gloss"] if mine else f["Meaning"],
            "features": features,
            "notes": "\n".join(s for s in sentence if s),
            "alternatives": [traditional] if traditional and traditional != simplified else [],
        },
        source=note,
        cards=[(c, "lexeme-recognize") for c in note.cards],
        original=f"{simplified} {f.get('Pinyin.1', '')} → {f['Meaning']}",
        flags=["from the personal 'Mine' subdeck; pos/gloss set by hand"] if mine else [],
    )
