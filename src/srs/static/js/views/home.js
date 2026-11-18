import { getAll } from "../db.js";
import { h, mount } from "../dom.js";
import { dueCounts, partsOfSpeech, posKey, posLabel } from "../queue.js";

function countsCell(c) {
  c ??= { learning: 0, review: 0, new: 0 };
  return h(
    "span.counts",
    {},
    h("span.count-new", { title: "new" }, c.new),
    h("span.count-learning", { title: "learning" }, c.learning),
    h("span.count-review", { title: "review" }, c.review),
  );
}

// Which decks show their parts of speech; a per-device convenience, so localStorage (which may be unavailable).
const EXPANDED_KEY = "srs:expanded-decks";

function loadExpanded() {
  try {
    return new Set(JSON.parse(localStorage.getItem(EXPANDED_KEY) ?? "[]"));
  } catch {
    return new Set();
  }
}

function saveExpanded(expanded) {
  try {
    localStorage.setItem(EXPANDED_KEY, JSON.stringify([...expanded]));
  } catch {
    // not remembered; fine
  }
}

export async function homeView() {
  const expanded = loadExpanded();

  async function render() {
    const decks = (await getAll("decks")).sort((a, b) => a.name.localeCompare(b.name));
    const counts = await dueCounts(Date.now());
    const posByDeck = await partsOfSpeech();
    // Decks with more than one part of speech list each, so you can study just the nouns, say.
    const deckRows = (d) => {
      const parts = posByDeck[d.id] ?? [];
      const link = h("a.deck-name", { href: `#/study/${d.id}` }, d.name);
      if (parts.length < 2) return [h("li", {}, link, countsCell(counts[d.id]))];
      const open = expanded.has(d.id);
      const toggle = h(
        "button.pos-toggle",
        {
          title: open ? "Hide parts of speech" : "Study one part of speech",
          "aria-expanded": String(open),
          onclick: () => {
            if (open) expanded.delete(d.id);
            else expanded.add(d.id);
            saveExpanded(expanded);
            render();
          },
        },
        h("span.chevron"),
      );
      const row = h("li", {}, h("span.deck-head", {}, toggle, link), countsCell(counts[d.id]));
      if (!open) return [row];
      return [
        row,
        ...parts.map((pos) =>
          h(
            "li.deck-pos",
            {},
            h("a.deck-name", { href: `#/study/${d.id}/${pos}` }, posLabel(pos)),
            countsCell(counts[posKey(d.id, pos)]),
          ),
        ),
      ];
    };
    mount(
      h(
        "section",
        {},
        h("div.row", {}, h("h1", {}, "Decks"), h("a.button", { href: "#/items/new" }, "+ Add item")),
        h(
          "ul.deck-list",
          {},
          h(
            "li",
            {},
            h("a.deck-name", { href: "#/study/all" }, h("strong", {}, "All decks")),
            countsCell(counts[null]),
          ),
          decks.flatMap(deckRows),
        ),
        h("p.muted.legend", {}, h("span.count-new", {}, "new"), " · ", h("span.count-learning", {}, "learning"), " · ",
          h("span.count-review", {}, "due")),
      ),
    );
  }
  await render();
  const onChange = () => render();
  window.addEventListener("srs:data-changed", onChange);
  return () => window.removeEventListener("srs:data-changed", onChange);
}
