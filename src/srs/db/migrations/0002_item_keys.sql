-- Every spelling an item can be looked up by (its lemma / form / text plus alternatives), normalized.
CREATE TABLE item_keys (
    item_id TEXT NOT NULL REFERENCES items (id),
    key TEXT NOT NULL,
    PRIMARY KEY (item_id, key)
);
CREATE INDEX item_keys_key ON item_keys (key);
INSERT INTO item_keys (item_id, key) SELECT id, lookup_key FROM items WHERE lookup_key IS NOT NULL AND deleted = 0;
