import attr

from srs.domain.item_data import FormData
from srs.domain.item_data import LexemeData
from srs.repo.items import Item

# Values a template can use: the item's own fields at top level (eg `lemma`, `gloss`), plus `kind`, `language`,
# `tags`, and for forms, `lexeme` (the inflected word's fields).
RenderValue = str | list[str] | dict[str, str] | dict[str, "RenderValue"] | None


def render_context(item: Item, lexeme: Item | None) -> dict[str, RenderValue]:
    ctx: dict[str, RenderValue] = attr.asdict(item.data)
    ctx["kind"] = item.kind
    ctx["language"] = item.language
    ctx["tags"] = item.tags
    if isinstance(item.data, FormData):
        if lexeme is None or not isinstance(lexeme.data, LexemeData):
            raise ValueError(f"form {item.id} needs its lexeme to render")
        ctx["lexeme"] = attr.asdict(lexeme.data)
    return ctx
