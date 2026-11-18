import { api } from "../api.js";
import { getAll } from "../db.js";
import { h, mount } from "../dom.js";

export function itemSummary(item) {
  switch (item.kind) {
    case "lexeme":
      return [item.lexeme.lemma, `${item.lexeme.pos} · ${item.lexeme.gloss}`];
    case "form":
      return [item.form.form, Object.values(item.form.features).join(" · ")];
    case "phrase":
      return [item.phrase.text, item.phrase.translation];
    case "fact":
      return [item.fact.front, item.fact.back];
  }
  return [item.id, ""];
}

const PAGE = 100;

function itemRow(item, decks) {
  const [title, detail] = itemSummary(item);
  return h(
    "li",
    {},
    h(
      "a",
      { href: `#/items/${item.id}` },
      h("span.kind-badge", {}, item.kind),
      item.language ? h("span.lang-badge", {}, item.language) : null,
      h("strong", {}, title),
      h("span.muted", {}, ` ${detail}`),
      h("span.muted.deck-tag", {}, decks[item.deck_id] ?? ""),
    ),
  );
}

// The server pages through items (there are thousands), newest first; search and filters apply on the server.
export async function itemsView() {
  const deckList = (await getAll("decks")).sort((a, b) => a.name.localeCompare(b.name));
  const decks = Object.fromEntries(deckList.map((d) => [d.id, d.name]));
  const state = { q: "", kind: "", deck: "" };
  const list = h("ul.item-list");
  const more = h("div.items-more");
  let loaded = 0;
  let generation = 0; // ignore responses to searches that have since changed

  async function load(append = false) {
    const mine = ++generation;
    if (!append) loaded = 0;
    const params = new URLSearchParams({ limit: String(PAGE + 1), offset: String(loaded) });
    if (state.q) params.set("q", state.q);
    if (state.kind) params.set("kind", state.kind);
    if (state.deck) params.set("deck_id", state.deck);
    more.replaceChildren(h("span.muted", {}, "Loading…"));
    try {
      const items = await api("GET", `/items?${params}`);
      if (mine !== generation) return;
      const page = items.slice(0, PAGE);
      const rows = page.map((item) => itemRow(item, decks));
      if (append) list.append(...rows);
      else list.replaceChildren(...rows);
      loaded += page.length;
      if (!loaded) list.replaceChildren(h("li.muted", {}, "No items."));
      more.replaceChildren(items.length > PAGE ? h("button", { onclick: () => load(true) }, "Show more") : null);
    } catch (e) {
      if (mine !== generation) return;
      more.replaceChildren();
      list.replaceChildren(h("li.error", {}, `Couldn't load items (editing needs a connection): ${e.message}`));
    }
  }

  let timer = null;
  mount(
    h(
      "section",
      {},
      h("div.row", {}, h("h1", {}, "Items"), h("a.button", { href: "#/items/new" }, "+ Add item")),
      h(
        "div.filters",
        {},
        h("input", {
          type: "search",
          placeholder: "Search words, meanings, notes…",
          oninput: (e) => {
            state.q = e.target.value.trim();
            clearTimeout(timer);
            timer = setTimeout(() => load(), 250);
          },
        }),
        h(
          "select",
          { onchange: (e) => ((state.deck = e.target.value), load()) },
          h("option", { value: "" }, "All decks"),
          deckList.map((d) => h("option", { value: d.id }, d.name)),
        ),
        h(
          "select",
          { onchange: (e) => ((state.kind = e.target.value), load()) },
          h("option", { value: "" }, "All kinds"),
          ["lexeme", "form", "phrase", "fact"].map((k) => h("option", { value: k }, k)),
        ),
      ),
      list,
      more,
    ),
  );
  await load();
}
