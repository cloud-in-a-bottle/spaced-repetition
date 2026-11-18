# tools/reading

Scratch tooling for preparing reading material and review sets by hand. It talks to the deployed app through
`oh curl` (pass `--url http://127.0.0.1:PORT` for a local server).

```bash
uv run python -m tools.reading analyze episode.srt            # what you know, what's new, most frequent first
uv run python -m tools.reading add-text episode.srt --course-id ministerio-del-tiempo \
    --course-title "El Ministerio del Tiempo" --text-id mdt-s01e03 --title "1×03 · …" --position 3
uv run python -m tools.reading seed-known -n 1000              # mark the 1000 commonest words known (--clear undoes)
uv run python -m tools.reading mark-lingq known-lingqs.csv      # LingQ export -> reader "known" marks (--status clear undoes)
uv run python -m tools.reading install-dictionary --language es
```

As a library:

- `client.SrsClient`: JSON calls to the owner API (`get`, `post`, `put`, `delete`).
- `content`: `analyze` (statuses straight from the app, so they match the reader's highlighting), `to_learn`,
  `print_report`, `ensure_course`, `add_text`.
- `review_sets.review_set_bundle(deck_id, name, words, promote_to=...)` + `import_bundle`: a throwaway study deck
  from a word list (recognition cards only by default).
- `claude`: Claude Haiku helpers ported from the old spanish-reader app (`translate_text`, `translate_word`,
  `translate_phrase`, `extract_pdf_text`, `detect_language`) plus `gloss_words` (flashcard entries for a review set,
  glossed in context). They need local Anthropic credentials; `via_app` translates through the deployed app's key
  instead.
- `marks`: reader marks (`mark`, `seed_common_known`).

The typical episode flow: `analyze` the subtitles, take the most frequent `new`/`learning` words, gloss them
(`gloss_words`, or by hand), build a review set with `review_set_bundle`, `import_bundle` it, and `add-text` the
subtitles to the library.
