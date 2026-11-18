-- Review sets: decks whose items are studied but kept out of what the knowledge service reports. `promote_to` is
-- the deck their items get copied into by "add to main deck" (null: the main deck with the most items in that
-- language).
ALTER TABLE decks ADD COLUMN ephemeral INTEGER NOT NULL DEFAULT 0;
ALTER TABLE decks ADD COLUMN promote_to TEXT REFERENCES decks (id);

-- Which review-set item each main-deck copy came from.
CREATE TABLE item_copies (
    source_item_id TEXT PRIMARY KEY REFERENCES items (id),
    item_id TEXT NOT NULL REFERENCES items (id)
);
