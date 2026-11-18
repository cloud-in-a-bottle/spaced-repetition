-- The reader's library: courses (eg a TV show) holding texts (eg one episode's subtitles), read with word statuses
-- drawn from the deck.
CREATE TABLE courses (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    language TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE TABLE texts (
    id TEXT PRIMARY KEY,
    course_id TEXT NOT NULL REFERENCES courses (id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    position INTEGER NOT NULL,
    -- `text` (paragraphs) or `subtitles` (timed cues)
    format TEXT NOT NULL,
    -- JSON list of blocks: {"text": ..., "start_ms"?: ..., "end_ms"?: ...}
    blocks TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    read_at INTEGER
);
CREATE INDEX texts_course ON texts (course_id, position);

-- Words the owner marked in the reader without putting them in a deck: `known` (no highlight) or `ignored`
-- (names, foreign words). Keyed by normalized spelling.
CREATE TABLE word_marks (
    language TEXT NOT NULL,
    key TEXT NOT NULL,
    status TEXT NOT NULL,
    updated_at INTEGER NOT NULL,
    PRIMARY KEY (language, key)
);

-- Claude translations, so each word-in-sentence or passage is only paid for once.
CREATE TABLE translations (
    language TEXT NOT NULL,
    kind TEXT NOT NULL,
    source TEXT NOT NULL,
    context TEXT NOT NULL,
    translation TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    PRIMARY KEY (language, kind, source, context)
);
