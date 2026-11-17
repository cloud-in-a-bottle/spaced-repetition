from srs.domain.item_data import FactData
from srs.domain.item_data import FormData
from srs.domain.item_data import ItemData
from srs.domain.item_data import LexemeData
from srs.domain.item_data import PhraseData
from srs.domain.normalize import lookup_key


def lookup_keys(data: ItemData) -> list[str]:
    """Normalized spellings other apps can find this item by, primary first. Empty for facts."""
    match data:
        case LexemeData():
            texts = [data.lemma, *data.alternatives]
        case FormData():
            texts = [data.form, *data.alternatives]
        case PhraseData():
            texts = [data.text]
        case FactData():
            texts = []
    return list(dict.fromkeys(lookup_key(t) for t in texts if t.strip()))
