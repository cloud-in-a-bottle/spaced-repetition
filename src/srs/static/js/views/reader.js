import { api } from "../api.js";
import { getAll } from "../db.js";
import { h, mount } from "../dom.js";
import { recordReview, sync } from "../sync.js";

// Reading a text with the deck's help: words you know well are plain, new words (in no deck) and weak ones
// (in a deck but poorly recalled or never studied) are highlighted; review sets don't count. Clicking a word opens a panel
// with what the deck and the offline dictionary know, translation in context, and buttons to add it or mark it.

const STATUS_LABEL = {
  known: "Known",
  learning: "Learning",
  new: "New",
  ignored: "Ignored",
  name: "Name",
  review_set: "review set",
};

const POS_OPTIONS = ["noun", "verb", "adjective", "adverb", "pronoun", "determiner", "preposition", "conjunction",
  "numeral", "interjection", "proper_noun", "classifier", "particle", "auxiliary", "other"];

const EXTERNAL = {
  es: (w) => [["SpanishDict", `https://www.spanishdict.com/translate/${encodeURIComponent(w)}`],
    ["WordReference", `https://www.wordreference.com/es/en/translation.asp?spen=${encodeURIComponent(w)}`]],
  fr: (w) => [["WordReference", `https://www.wordreference.com/fren/${encodeURIComponent(w)}`]],
  de: (w) => [["WordReference", `https://www.wordreference.com/deen/${encodeURIComponent(w)}`]],
  it: (w) => [["WordReference", `https://www.wordreference.com/iten/${encodeURIComponent(w)}`]],
  pt: (w) => [["WordReference", `https://www.wordreference.com/pten/${encodeURIComponent(w)}`]],
};

function formatTime(ms) {
  const s = Math.floor(ms / 1000);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export async function readerView(textId) {
  document.body.classList.add("reading");
  let reading;
  try {
    reading = await api("GET", `/reader/texts/${textId}`);
  } catch (err) {
    mount(h("section", {}, h("p.error", {}, navigator.onLine ? `Couldn't open it: ${err.message}` : "The reader needs a connection.")));
    return () => document.body.classList.remove("reading");
  }
  const decks = (await getAll("decks")).sort((a, b) => a.name.localeCompare(b.name));
  let words = reading.words;
  let selected = null; // {key, word, sentence, el}
  const spansByKey = new Map();
  let progress = reading.progress_block; // furthest line read: where you last clicked a word furthest in

  // --- the text ---

  function wordSpan(text, key) {
    const span = h(`span.w.s-${words[key]}`, { "data-key": key }, text);
    span.addEventListener("click", (e) => {
      e.stopPropagation();
      select(span);
    });
    if (!spansByKey.has(key)) spansByKey.set(key, []);
    spansByKey.get(key).push(span);
    return span;
  }

  function blockText(block) {
    return block.tokens.map(([t]) => t).join("");
  }

  async function translateBlock(i, holder) {
    holder.replaceChildren(h("span.muted", {}, "Translating…"));
    try {
      const r = await api("POST", "/reader/translate", { language: reading.language, kind: "text", text: blockText(reading.blocks[i]) });
      holder.replaceChildren(r.translation);
    } catch (err) {
      holder.replaceChildren(h("span.error", {}, err.message));
    }
  }

  const body = reading.blocks.map((block, i) => {
    const holder = h("div.block-translation");
    return h("div.block", { "data-i": i },
      reading.format === "subtitles" && block.start_ms !== null ? h("span.block-time", {}, formatTime(block.start_ms)) : null,
      h("p.block-text", {}, block.tokens.map(([text, key]) => (key ? wordSpan(text, key) : text))),
      h("button.block-translate", { title: "Translate this line (Claude)", "aria-label": "Translate", onclick: () => translateBlock(i, holder) }, "EN"),
      holder,
    );
  });

  function counts() {
    const c = { known: 0, learning: 0, new: 0, total: 0 };
    for (const block of reading.blocks) {
      for (const [, key] of block.tokens) {
        if (!key) continue;
        c.total += 1;
        const s = words[key];
        if (s === "new") c.new += 1;
        else if (s === "learning") c.learning += 1;
        else c.known += 1;
      }
    }
    return c;
  }

  const stats = h("div.reader-stats");
  function renderStats() {
    const c = counts();
    const newKeys = Object.values(words).filter((s) => s === "new").length;
    const pct = c.total ? Math.round((100 * c.known) / c.total) : 0;
    stats.replaceChildren(
      h("span", {}, `${pct}% of words known`),
      h("span.s-new.legend-chip", {}, `${newKeys} new`),
      h("span.s-learning.legend-chip", {}, `${Object.values(words).filter((s) => s === "learning").length} learning`),
    );
  }

  function applyStatuses() {
    for (const [key, spans] of spansByKey) {
      for (const span of spans) span.className = `w s-${words[key]}${selected?.key === key ? " selected" : ""}`;
    }
    renderStats();
  }

  async function refreshWords() {
    words = await api("GET", `/reader/texts/${textId}/words`);
    applyStatuses();
  }

  async function markAllNewKnown() {
    const keys = Object.keys(words).filter((k) => words[k] === "new");
    if (!keys.length) return;
    if (!confirm(`Mark all ${keys.length} highlighted new words as known? (Words you're learning stay highlighted.)`)) return;
    await api("PUT", "/reader/marks", { language: reading.language, words: keys, status: "known" });
    await refreshWords();
  }

  async function markRead() {
    await api("PUT", `/library/texts/${textId}/read`, { read: true });
    readButton.textContent = "✓ Marked as read";
    readButton.disabled = true;
  }
  const readButton = h("button", { onclick: markRead }, "Mark as read");

  // --- the word panel ---

  const panel = h("aside.word-panel", { hidden: true });

  function sentenceAround(span) {
    return span.closest(".block").querySelector(".block-text").textContent;
  }

  // --- where you've read to ---

  const blockEls = () => document.querySelectorAll(".reader-text .block");
  const progressLink = h("div.reader-progress.small");

  function renderProgress() {
    for (const el of document.querySelectorAll(".block.progress-mark")) el.classList.remove("progress-mark");
    if (progress === null) {
      progressLink.replaceChildren();
      return;
    }
    blockEls()[progress]?.classList.add("progress-mark");
    const pct = Math.round((100 * (progress + 1)) / reading.blocks.length);
    progressLink.replaceChildren(
      h("a", { href: "#", onclick: (e) => { e.preventDefault(); jumpToProgress(); } }, "Jump to where you left off"),
      h("span.muted", {}, ` · line ${progress + 1} of ${reading.blocks.length} (${pct}%) · `),
      h("button.link", { onclick: () => saveProgress(0, true), title: "Move your place back to the start" }, "start over"),
    );
  }

  function jumpToProgress() {
    const el = blockEls()[progress];
    if (!el) return;
    el.scrollIntoView({ behavior: "smooth", block: "center" });
    el.classList.add("flash");
    setTimeout(() => el.classList.remove("flash"), 1500);
  }

  function saveProgress(block, force = false) {
    if (!force && progress !== null && block <= progress) return;
    progress = block;
    renderProgress();
    api("PUT", `/library/texts/${textId}/progress`, { block, force }).catch(() => {});
  }

  function select(span) {
    for (const s of document.querySelectorAll(".w.selected")) s.classList.remove("selected");
    saveProgress(Number(span.closest(".block").dataset.i));
    const key = span.dataset.key;
    selected = { key, word: span.textContent, sentence: sentenceAround(span) };
    for (const s of spansByKey.get(key)) s.classList.add("selected");
    showPanel();
  }

  function closePanel() {
    selected = null;
    panel.hidden = true;
    for (const s of document.querySelectorAll(".w.selected")) s.classList.remove("selected");
  }

  // "known" goes on the word's root(s) (all its forms count, like cards); `roots` picks one when there are several
  async function setMark(status, roots = null) {
    await api("PUT", "/reader/marks", { language: reading.language, words: [selected.key], status, roots });
    await refreshWords();
    showPanel();
  }

  function dictionarySection(d) {
    // each distinct form description once, with its English rendering ("I renounced") when there is one
    const forms = [...new Map(d.dictionary.flatMap((e) => e.form_of).map((f) => [f.description, f])).values()];
    const headwords = [...d.dictionary.filter((e) => e.senses.length), ...d.lemma_entries];
    if (!forms.length && !headwords.length) return h("p.muted", {}, reading.dictionary ? "Not in the dictionary." : "No offline dictionary installed (Settings → Dictionaries).");
    return h("div.dict", {},
      forms.map((f) => h("p.dict-form", {}, f.english ? [h("span.dict-english", {}, f.english), " · "] : null, f.description)),
      headwords.map((e) =>
        h("div.dict-entry", {},
          h("div", {}, h("strong", {}, e.word), " ", h("span.muted", {}, e.pos.replace("_", " "), e.gender ? `, ${e.gender}` : ""),
            e.verb_class ? [" ", h(`span.verb-class.vc-${e.verb_class.label}`, { title: e.verb_class.notes.join(", ") || "follows the regular pattern" },
              e.verb_class.label + (e.verb_class.notes.length ? ` (${e.verb_class.notes.join(", ")})` : ""))] : null),
          h("ol.dict-senses", {}, e.senses.slice(0, 5).map((s) => h("li", {}, s))))));
  }

  // The card that reading a word exercises: its recognition card (word -> meaning), preferring one that isn't
  // suspended; else whatever card the word has.
  async function readingCard(itemId) {
    const cards = (await getAll("cards")).filter((c) => c.item_id === itemId);
    const rank = (c) => (c.skill === "recognize" ? 0 : 2) + (c.suspended ? 1 : 0);
    return cards.sort((a, b) => rank(a) - rank(b))[0] ?? null;
  }

  // Recognizing a word while reading is a successful review of it: record a Good, like the Study tab would.
  // Some words have no cards of their own (eg verbs imported only for their conjugations): give one a word ->
  // meaning card, keeping whatever cards it has.
  async function addRecognitionCard(itemId) {
    const item = await api("GET", `/items/${itemId}`);
    const templates = new Set(item.cards.filter((c) => !c.deleted).map((c) => c.template_id));
    templates.add(`${item.kind}-recognize`);
    await api("PUT", `/items/${itemId}`, {
      deck_id: item.deck_id, kind: item.kind, language: item.language, tags: item.tags,
      [item.kind]: item[item.kind], template_ids: [...templates],
    });
    await sync();
  }

  async function markReviewed(m, button) {
    button.disabled = true;
    button.textContent = "Recording…";
    try {
      let card = await readingCard(m.item_id);
      if (!card) {
        const ok = confirm(`${m.lemma} has no cards of its own yet (only its conjugations, if any). ` +
          "Add a word → meaning card for it and record this review?");
        if (!ok) {
          button.disabled = false;
          button.textContent = "Mark as reviewed";
          return;
        }
        await addRecognitionCard(m.item_id);
        card = await readingCard(m.item_id);
        if (!card) throw new Error("the card didn't arrive; try again");
      }
      await recordReview(card, 3, 0);
      await sync();
      await refreshWords();
      showPanel();
    } catch (err) {
      button.textContent = navigator.onLine ? `Couldn't record it: ${err.message}` : "Recorded; will sync when online";
    }
  }

  function deckSection(d) {
    const rows = [...d.deck, ...d.review_sets];
    if (!rows.length) return null;
    const deckName = (id) => decks.find((x) => x.id === id)?.name ?? "deck";
    return h("div.panel-deck", {},
      rows.map((m) =>
        h("div.deck-match", {},
          h("span", {}, h("strong", {}, m.lemma), " ", h("span.muted", {}, m.pos.replace("_", " "))),
          h("span", {}, " — ", m.gloss),
          h("div.muted.small", {},
            deckName(m.deck_id), " · ", STATUS_LABEL[m.status] ?? m.status,
            m.recall ? ` · ${Math.round(m.recall * 100)}% recall` : "",
            m.via === "dictionary" ? " · via dictionary form" : "", " · ",
            h("a", { href: `#/items/${m.item_id}` }, "edit")),
          m.status === "learning"
            ? h("button.small.mark-reviewed", { title: "Record a successful review (Good) of this word's recognition card",
                onclick: (e) => markReviewed(m, e.currentTarget) }, "Mark as reviewed")
            : null)));
  }

  function addForm(d) {
    const s = d.suggestion ?? { lemma: selected.word.toLowerCase(), pos: "other", gloss: "", gender: null };
    const mains = decks.filter((x) => !x.ephemeral);
    const sets = decks.filter((x) => x.ephemeral);
    const form = { lemma: s.lemma, pos: s.pos, gloss: s.gloss, gender: s.gender ?? "", deck: reading.default_deck_id ?? mains[0]?.id };
    const status = h("span.muted.small");
    const genderField = h("select", { onchange: (e) => (form.gender = e.target.value) },
      ["", "masculine", "feminine", "common"].map((g) => h("option", { value: g, selected: g === form.gender }, g || "gender")));
    async function add(e) {
      e.preventDefault();
      if (!form.gloss.trim()) {
        status.textContent = "Add a meaning first.";
        return;
      }
      const features = form.pos === "noun" && form.gender
        ? { gender: form.gender, article: form.gender === "feminine" ? "la" : "el" }
        : {};
      try {
        await api("POST", "/items", {
          deck_id: form.deck, kind: "lexeme", language: reading.language, tags: [],
          lexeme: { lemma: form.lemma.trim(), pos: form.pos, gloss: form.gloss.trim(), features,
            notes: `From ${reading.course_title}: ${reading.title}\n“${selected.sentence.trim()}”` },
        });
        sync().catch(() => {});
        await refreshWords();
        showPanel();
      } catch (err) {
        status.textContent = err.message;
      }
    }
    return h("form.add-form", { onsubmit: add },
      h("div.add-row", {},
        h("input", { value: form.lemma, "aria-label": "Dictionary form", oninput: (e) => (form.lemma = e.target.value) }),
        h("select", { "aria-label": "Part of speech", onchange: (e) => (form.pos = e.target.value) },
          POS_OPTIONS.map((p) => h("option", { value: p, selected: p === form.pos }, p.replace("_", " "))))),
      h("input", { value: form.gloss, placeholder: "meaning", "aria-label": "Meaning", oninput: (e) => (form.gloss = e.target.value) }),
      h("div.add-row", {},
        form.pos === "noun" || s.gender ? genderField : null,
        h("select", { "aria-label": "Deck", onchange: (e) => (form.deck = e.target.value) },
          h("optgroup", { label: "Decks" }, mains.map((x) => h("option", { value: x.id, selected: x.id === form.deck }, x.name))),
          sets.length ? h("optgroup", { label: "Review sets" }, sets.map((x) => h("option", { value: x.id }, x.name))) : null),
        h("button.primary", { type: "submit" }, "Add")),
      status);
  }

  async function translateWord(holder) {
    holder.replaceChildren(h("span.muted", {}, "Asking Claude…"));
    try {
      const r = await api("POST", "/reader/translate", { language: reading.language, kind: "word", text: selected.word, context: selected.sentence.trim() });
      holder.replaceChildren(h("strong", {}, r.translation), h("span.muted.small", {}, " in this sentence"));
    } catch (err) {
      holder.replaceChildren(h("span.error", {}, err.message));
    }
  }

  async function showPanel() {
    if (!selected) return;
    const current = selected;
    panel.hidden = false;
    panel.replaceChildren(h("p.muted", {}, "Looking up…"));
    let d;
    try {
      d = await api("GET", `/reader/word?language=${encodeURIComponent(reading.language)}&word=${encodeURIComponent(current.word)}`);
    } catch (err) {
      panel.replaceChildren(h("p.error", {}, err.message));
      return;
    }
    if (selected !== current) return;
    const translation = h("div.panel-translation");
    const inDeck = d.deck.length > 0;
    const external = (EXTERNAL[reading.language] ?? (() => []))(current.word);
    panel.replaceChildren(...[
      h("div.panel-head", {},
        h("span.panel-word", {}, current.word),
        h(`span.status-chip.s-${d.status}`, {}, STATUS_LABEL[d.status] ?? d.status),
        h("button.link.panel-close", { onclick: closePanel, title: "Close (Esc)", "aria-label": "Close" }, "×")),
      deckSection(d),
      dictionarySection(d),
      h("div.panel-actions", {},
        h("button", { onclick: () => translateWord(translation) }, "Translate in context"),
        external.map(([name, url]) => h("a.small", { href: url, target: "_blank", rel: "noopener" }, name))),
      translation,
      inDeck ? null : h("h3.panel-title", {}, "Add to a deck"),
      inDeck ? null : addForm(d),
      h("div.panel-marks", {},
        d.mark === "known" || d.mark === "ignored"
          ? [h("span.muted.small", {}, d.mark_root ? `Known (as ${d.mark_root}). ` : `Marked ${d.mark}. `),
             h("button.link", { onclick: () => setMark(null) }, "undo")]
          : inDeck
            ? null
            : [
                d.roots.length > 1
                  ? d.roots.map((r) => h("button", { onclick: () => setMark("known", [r]), title: `Mark ${r} and all its forms known` }, `I know ${r}`))
                  : h("button", { onclick: () => setMark("known"), title: d.roots[0] && d.roots[0] !== d.key ? `Marks ${d.roots[0]} and all its forms known` : "" }, "I know this"),
                h("button", { onclick: () => setMark("ignored"), title: "Don't highlight this spelling (names, foreign words)" }, "Ignore"),
              ]),
    ].filter(Boolean));
  }

  function onKey(e) {
    if (e.key === "Escape") closePanel();
  }
  document.addEventListener("keydown", onKey);

  mount(
    h("div.reader", {},
      h("div.reader-main", {},
        h("div.reader-head", {},
          h("div.muted.small", {}, h("a", { href: "#/read" }, "Library"), " › ", reading.course_title),
          h("h1", {}, reading.title),
          stats,
          progressLink,
          reading.dictionary ? null : h("p.muted.small", {}, "Tip: install the offline dictionary (Settings → Dictionaries) so inflected words are matched to your deck and get definitions.")),
        h(`div.reader-text${reading.format === "subtitles" ? ".subtitles" : ""}`, { onclick: closePanel }, body),
        h("div.reader-foot", {},
          h("button", { onclick: markAllNewKnown }, "Mark remaining new words as known"),
          readButton,
          h("span.reader-nav", {},
            reading.previous_id ? h("a", { href: `#/read/${reading.previous_id}` }, "← Previous") : null,
            reading.next_id ? h("a", { href: `#/read/${reading.next_id}` }, "Next →") : null))),
      panel,
    ),
  );
  renderStats();
  renderProgress();

  return () => {
    document.removeEventListener("keydown", onKey);
    document.body.classList.remove("reading");
  };
}
