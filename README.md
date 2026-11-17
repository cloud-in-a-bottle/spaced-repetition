# srs

Spaced repetition for Cloud in a Bottle, scheduled with [FSRS](https://github.com/open-spaced-repetition/py-fsrs).
Unlike anki, it knows what each card is *about*, so other apps can ask what you know ("which of these Spanish words
does the owner know?").

## the model

- **Items** are the things you know. Each has a kind (`src/srs/domain/kinds.py`, `item_data.py`):
  - `lexeme`: a word. Language, lemma (root / dictionary form), part of speech, gloss, free-form features.
  - `form`: one inflection of a lexeme ("hablo" = hablar + tense=present, person=1st, number=singular).
  - `phrase`: a sentence and its translation, optionally linked to the lexemes it uses.
  - `fact`: plain front/back, for anything that isn't language material.
- **Templates** turn an item of one kind into a card exercising one **skill**: `recognize` (see it, recall the
  meaning), `produce` (meaning → it; for forms, conjugating), `recall` (facts). Templates are jinja, editable in the
  app; defaults are in `src/srs/render/default_templates.py`.
- A **card** is one (item, template) pair. Its schedule is FSRS state.
- **Reviews** are an append-only log, the source of truth for scheduling.

## offline sync

The PWA keeps the collection in IndexedDB and studies from it with no connection. The trick that keeps sync
simple: a card's schedule is a pure function of its reviews, replayed in time order (`src/srs/scheduling/replay.py`).
Reviews only ever get added, so the review log is a grow-only set (the simplest CRDT). Devices merge by sending the
reviews they made, and the server replays the affected cards. Two phones reviewing the same card offline both
count, and every device ends up with the same schedule.

- The client schedules locally with `static/js/fsrs.js`, a port of py-fsrs. `tests/unit/test_js_fsrs.py` checks it
  against the server on random review histories. The server's replay always wins on sync.
- Fuzz is seeded by the review id rather than random, so replay is deterministic.
- Everything else (items, templates, decks, settings) is edited online and synced down by a change counter (`seq`
  columns, with tombstones for deletes). Editing offline would need last-writer-wins on items; not built yet.
- Changing scheduling settings replays every card.

## knowledge service

Other apps call it through the openhost router. See `services/srs/openapi.yaml` for the spec and how to consume it.
For now it's read-only: look up words (lemmas or inflected forms) or list a language's lexemes, each with a
status (`new` / `learning` / `known`), per-skill FSRS state, and current recall probability. Needs the
`knowledge:read` grant.

## getting data in

There's no anki importer, on purpose: anki notes don't say what they are, so converting a deck is manual work (or a
script you write for your deck). Write the result as JSON and `POST /api/import`
(`src/srs/core/bulk_import.py`):

```json
{
  "decks": [{"id": "spanish", "name": "Spanish"}],
  "items": [
    {"id": "hablar", "deck_id": "spanish", "kind": "lexeme", "language": "es",
     "lexeme": {"lemma": "hablar", "pos": "verb", "gloss": "to speak"}},
    {"id": "hablo", "deck_id": "spanish", "kind": "form",
     "form": {"lexeme_id": "hablar", "form": "hablo", "features": {"tense": "present", "person": "1st"}}}
  ],
  "reviews": [
    {"id": "anki-1712345678901", "item_id": "hablar", "template_id": "lexeme-recognize",
     "rating": 3, "reviewed_at": 1712345678901}
  ]
}
```

Every entity carries its own id, so re-importing updates in place. Include your anki review history (revlog `id`
is the timestamp in ms; `ease` 1-4 is the rating) and FSRS replays it, so cards keep their memory state.

## development

```bash
just setup      # deps, pre-commit hooks, playwright chromium
just run        # http://localhost:8080 with a scratch db, owner check off
just test-unit  # fast: app in-process + js/python scheduler agreement (needs node)
just test       # everything, including the container behind the real openhost router (needs podman)
just check      # ruff + mypy
```

Layout (`src/srs/`): `domain/` (types, no I/O), `db/` (connection + numbered migrations), `repo/` (sql per table),
`core/` (operations that span tables, one transaction each), `scheduling/` (FSRS replay), `render/` (templates),
`knowledge/` (the queries behind the service), `api/` (owner http api), `service/` (cross-app service), `static/`
(the PWA: plain ES modules, no build step).
