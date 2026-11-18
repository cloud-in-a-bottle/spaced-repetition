-- How far into a text the owner has read: the furthest block (paragraph or subtitle line) they clicked a word in.
ALTER TABLE texts ADD COLUMN progress_block INTEGER;
