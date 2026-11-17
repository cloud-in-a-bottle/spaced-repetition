import attr

from srs.domain.errors import InvalidRequest
from srs.domain.item_data import FactData
from srs.domain.item_data import FormData
from srs.domain.item_data import ItemData
from srs.domain.item_data import LexemeData
from srs.domain.item_data import PhraseData
from srs.domain.kinds import ItemKind


@attr.s(auto_attribs=True, frozen=True)
class ItemInput:
    """An item as clients send it. Exactly one of the kind-specific fields is set, matching `kind`.

    `id` may be chosen by the client (eg to make bulk imports idempotent); a new one is generated otherwise.
    `template_ids` picks which templates get cards: on create it defaults to the kind's default-enabled templates, on
    update it defaults to leaving the current set alone.
    """

    deck_id: str
    kind: ItemKind
    language: str | None = None
    tags: list[str] = attr.Factory(list)
    lexeme: LexemeData | None = None
    form: FormData | None = None
    phrase: PhraseData | None = None
    fact: FactData | None = None
    id: str | None = None
    template_ids: list[str] | None = None

    def data(self) -> ItemData:
        by_kind: dict[ItemKind, ItemData | None] = {
            ItemKind.LEXEME: self.lexeme,
            ItemKind.FORM: self.form,
            ItemKind.PHRASE: self.phrase,
            ItemKind.FACT: self.fact,
        }
        extra = [k for k, v in by_kind.items() if v is not None and k != self.kind]
        if extra:
            raise InvalidRequest(f"item of kind {self.kind} must not set {', '.join(extra)}")
        data = by_kind[self.kind]
        if data is None:
            raise InvalidRequest(f"item of kind {self.kind} must set `{self.kind}`")
        return data
