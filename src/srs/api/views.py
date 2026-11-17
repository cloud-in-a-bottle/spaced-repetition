import attr

from srs.core.sync import SyncCard
from srs.domain.item_data import FactData
from srs.domain.item_data import FormData
from srs.domain.item_data import LexemeData
from srs.domain.item_data import PhraseData
from srs.domain.kinds import ItemKind
from srs.domain.schedule import CardState
from srs.repo.cards import Card
from srs.repo.items import Item


@attr.s(auto_attribs=True, frozen=True)
class CardSummary:
    id: str
    template_id: str
    suspended: bool
    state: CardState
    due: int
    reps: int


@attr.s(auto_attribs=True, frozen=True)
class ItemView:
    """Same shape as ItemInput (so the UI can edit and send it back), plus timestamps and the item's cards."""

    id: str
    deck_id: str
    kind: ItemKind
    language: str | None
    tags: list[str]
    lexeme: LexemeData | None
    form: FormData | None
    phrase: PhraseData | None
    fact: FactData | None
    created_at: int
    updated_at: int
    cards: list[CardSummary]


def item_view(item: Item, cards: list[Card]) -> ItemView:
    d = item.data
    return ItemView(
        id=item.id,
        deck_id=item.deck_id,
        kind=item.kind,
        language=item.language,
        tags=item.tags,
        lexeme=d if isinstance(d, LexemeData) else None,
        form=d if isinstance(d, FormData) else None,
        phrase=d if isinstance(d, PhraseData) else None,
        fact=d if isinstance(d, FactData) else None,
        created_at=item.created_at,
        updated_at=item.updated_at,
        cards=[
            CardSummary(
                id=c.id,
                template_id=c.template_id,
                suspended=c.suspended,
                state=c.schedule.state,
                due=c.schedule.due,
                reps=c.schedule.reps,
            )
            for c in cards
            if not c.deleted
        ],
    )


@attr.s(auto_attribs=True, frozen=True)
class SyncCardView:
    id: str
    item_id: str
    deck_id: str
    template_id: str
    template_name: str
    kind: str
    skill: str
    created_at: int
    suspended: bool
    deleted: bool
    front_html: str
    back_html: str
    state: CardState
    step: int | None
    stability: float | None
    difficulty: float | None
    due: int
    last_review: int | None
    reps: int
    lapses: int


def sync_card_view(sc: SyncCard) -> SyncCardView:
    c = sc.card
    s = c.schedule
    return SyncCardView(
        id=c.id,
        item_id=c.item_id,
        deck_id=sc.deck_id,
        template_id=c.template_id,
        template_name=sc.template_name,
        kind=sc.item_kind,
        skill=sc.skill,
        created_at=c.created_at,
        suspended=c.suspended,
        deleted=c.deleted,
        front_html=c.front_html,
        back_html=c.back_html,
        state=s.state,
        step=s.step,
        stability=s.stability,
        difficulty=s.difficulty,
        due=s.due,
        last_review=s.last_review,
        reps=s.reps,
        lapses=s.lapses,
    )
