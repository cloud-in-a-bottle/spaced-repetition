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

export async function itemsView() {
  const decks = Object.fromEntries((await getAll("decks")).map((d) => [d.id, d.name]));
  const state = { q: "", kind: "" };
  const list = h("ul.item-list");

  async function load() {
    const params = new URLSearchParams();
    if (state.q) params.set("q", state.q);
    if (state.kind) params.set("kind", state.kind);
    try {
      const items = await api("GET", `/items?${params}`);
      list.replaceChildren(
        ...items.map((item) => {
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
        }),
      );
      if (!items.length) list.replaceChildren(h("li.muted", {}, "No items."));
    } catch (e) {
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
          placeholder: "Search…",
          oninput: (e) => {
            state.q = e.target.value;
            clearTimeout(timer);
            timer = setTimeout(load, 250);
          },
        }),
        h(
          "select",
          { onchange: (e) => ((state.kind = e.target.value), load()) },
          h("option", { value: "" }, "All kinds"),
          ["lexeme", "form", "phrase", "fact"].map((k) => h("option", { value: k }, k)),
        ),
      ),
      list,
    ),
  );
  await load();
}
