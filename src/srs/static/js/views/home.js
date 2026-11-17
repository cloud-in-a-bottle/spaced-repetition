import { getAll } from "../db.js";
import { h, mount } from "../dom.js";
import { dueCounts } from "../queue.js";

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

export async function homeView() {
  async function render() {
    const decks = (await getAll("decks")).sort((a, b) => a.name.localeCompare(b.name));
    const counts = await dueCounts(Date.now());
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
          decks.map((d) => h("li", {}, h("a.deck-name", { href: `#/study/${d.id}` }, d.name), countsCell(counts[d.id]))),
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
