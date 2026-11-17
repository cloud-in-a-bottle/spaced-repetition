from collections import defaultdict

import attr

from tools.anki_import.anki_reader import AnkiReview
from tools.anki_import.builder import Builder

_MANUAL = 4


@attr.s(auto_attribs=True, frozen=True)
class ReviewStats:
    imported: int
    dropped_before_reset: int
    dropped_manual: int


def build_reviews(revlog: list[AnkiReview], b: Builder) -> tuple[list[dict[str, object]], ReviewStats]:
    """Anki review log -> import reviews. Manual entries (reschedules, 'forget') aren't reviews; a 'forget' also
    discards the card's earlier history, as it did in anki."""
    target: dict[int, tuple[str, str]] = {}
    for item in b.items.values():
        for card_id, template in item.anki_cards.items():
            target[card_id] = (item.id, template)
    by_card: dict[int, list[AnkiReview]] = defaultdict(list)
    for r in revlog:
        if r.card_id in target:
            by_card[r.card_id].append(r)
    out: list[dict[str, object]] = []
    before_reset = manual = 0
    for card_id, entries in by_card.items():
        entries.sort(key=lambda r: r.id)
        resets = [i for i, r in enumerate(entries) if r.type == _MANUAL and r.ease == 0]
        if resets:
            before_reset += resets[-1]
            entries = entries[resets[-1] + 1 :]
        item_id, template_id = target[card_id]
        for r in entries:
            if r.type == _MANUAL or not 1 <= r.ease <= 4:
                manual += 1
                continue
            out.append(
                {
                    "id": f"anki-{r.id}",
                    "item_id": item_id,
                    "template_id": template_id,
                    "rating": r.ease,
                    "reviewed_at": r.id,
                    "duration_ms": r.time_ms,
                }
            )
    return out, ReviewStats(imported=len(out), dropped_before_reset=before_reset, dropped_manual=manual)
