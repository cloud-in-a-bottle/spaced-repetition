-- Times are integer milliseconds since the unix epoch (UTC).
-- `seq` columns hold the value of the global change counter at the row's last change; clients sync rows with
-- seq greater than their cursor. Rows are never hard-deleted (`deleted` = 1 is a tombstone) so deletions sync too.

CREATE TABLE change_counter (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    value INTEGER NOT NULL
);
INSERT INTO change_counter (id, value) VALUES (1, 0);

CREATE TABLE settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    json TEXT NOT NULL,
    seq INTEGER NOT NULL
);

CREATE TABLE decks (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    deleted INTEGER NOT NULL DEFAULT 0,
    seq INTEGER NOT NULL
);
CREATE UNIQUE INDEX decks_name ON decks (name) WHERE deleted = 0;

CREATE TABLE templates (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    kind TEXT NOT NULL,
    skill TEXT NOT NULL,
    front TEXT NOT NULL,
    back TEXT NOT NULL,
    css TEXT NOT NULL,
    -- whether new items of this kind get a card for this template unless told otherwise
    default_enabled INTEGER NOT NULL,
    deleted INTEGER NOT NULL DEFAULT 0,
    seq INTEGER NOT NULL
);

CREATE TABLE items (
    id TEXT PRIMARY KEY,
    deck_id TEXT NOT NULL REFERENCES decks (id),
    kind TEXT NOT NULL,
    language TEXT,
    -- kind-specific fields, see srs.domain.item_data
    data TEXT NOT NULL,
    -- normalized lemma / form / phrase text, for knowledge lookups; NULL for facts
    lookup_key TEXT,
    -- for forms: the lexeme they inflect
    lexeme_id TEXT REFERENCES items (id),
    tags TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    deleted INTEGER NOT NULL DEFAULT 0,
    seq INTEGER NOT NULL
);
CREATE INDEX items_lookup ON items (language, kind, lookup_key) WHERE deleted = 0;
CREATE INDEX items_lexeme ON items (lexeme_id) WHERE deleted = 0;

CREATE TABLE cards (
    id TEXT PRIMARY KEY,
    item_id TEXT NOT NULL REFERENCES items (id),
    template_id TEXT NOT NULL REFERENCES templates (id),
    created_at INTEGER NOT NULL,
    suspended INTEGER NOT NULL DEFAULT 0,
    deleted INTEGER NOT NULL DEFAULT 0,
    -- rendered from the item + template; recomputed when either changes
    front_html TEXT NOT NULL,
    back_html TEXT NOT NULL,
    -- scheduling state: a pure function of this card's reviews, recomputed by replaying them
    state TEXT NOT NULL,
    step INTEGER,
    stability REAL,
    difficulty REAL,
    due INTEGER NOT NULL,
    last_review INTEGER,
    reps INTEGER NOT NULL,
    lapses INTEGER NOT NULL,
    seq INTEGER NOT NULL,
    UNIQUE (item_id, template_id)
);
CREATE INDEX cards_item ON cards (item_id);
CREATE INDEX cards_seq ON cards (seq);

-- Append-only. This is the source of truth for scheduling: a grow-only set that devices can merge without conflicts.
CREATE TABLE reviews (
    id TEXT PRIMARY KEY,
    card_id TEXT NOT NULL REFERENCES cards (id),
    rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 4),
    reviewed_at INTEGER NOT NULL,
    duration_ms INTEGER,
    -- where the review came from, eg "app" or "import"
    source TEXT NOT NULL,
    received_at INTEGER NOT NULL
);
CREATE INDEX reviews_card ON reviews (card_id, reviewed_at, id);
