import json

import attr

from srs.domain.item_data import FactData
from srs.domain.item_data import FormData
from srs.domain.item_data import ItemData
from srs.domain.item_data import LexemeData
from srs.domain.item_data import PhraseData
from srs.domain.kinds import ItemKind
from srs.domain.kinds import PartOfSpeech

_KIND_BY_TYPE: dict[type, ItemKind] = {
    LexemeData: ItemKind.LEXEME,
    FormData: ItemKind.FORM,
    PhraseData: ItemKind.PHRASE,
    FactData: ItemKind.FACT,
}


def kind_of(data: ItemData) -> ItemKind:
    return _KIND_BY_TYPE[type(data)]


def encode_item_data(data: ItemData) -> str:
    return json.dumps(attr.asdict(data), ensure_ascii=False)


def decode_item_data(kind: ItemKind, raw: str) -> ItemData:
    d = json.loads(raw)
    match kind:
        case ItemKind.LEXEME:
            return LexemeData(
                lemma=d["lemma"],
                pos=PartOfSpeech(d["pos"]),
                gloss=d["gloss"],
                features=d["features"],
                notes=d["notes"],
            )
        case ItemKind.FORM:
            return FormData(
                lexeme_id=d["lexeme_id"], form=d["form"], features=d["features"], gloss=d["gloss"], notes=d["notes"]
            )
        case ItemKind.PHRASE:
            return PhraseData(
                text=d["text"], translation=d["translation"], notes=d["notes"], lexeme_ids=d["lexeme_ids"]
            )
        case ItemKind.FACT:
            return FactData(front=d["front"], back=d["back"], notes=d["notes"])
