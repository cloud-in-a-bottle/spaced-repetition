import { get, getMeta } from "../db.js";
import { formatInterval, h, mount } from "../dom.js";
import { applyReview } from "../fsrs.js";
import { nextCard, noteNewCardIntroduced, posLabel } from "../queue.js";
import { cardElement } from "../render.js";
import { recordReview } from "../sync.js";

const RATINGS = [
  [1, "Again"],
  [2, "Hard"],
  [3, "Good"],
  [4, "Easy"],
];

export async function studyView(deckId, pos = null) {
  const deck = deckId ? await get("decks", deckId) : null;
  const title = (deck ? deck.name : "All decks") + (pos ? ` · ${posLabel(pos)}` : "");
  let card = null;
  let revealed = false;
  let shownAt = 0;
  let lastId = null;

  async function showNext() {
    card = await nextCard({ deckId, pos }, Date.now(), lastId);
    revealed = false;
    shownAt = Date.now();
    render();
  }

  async function grade(rating) {
    if (!card || !revealed) return;
    const wasNew = card.state === "new";
    const settings = await getMeta("settings");
    lastId = card.id;
    await recordReview(card, rating, Date.now() - shownAt);
    if (wasNew) await noteNewCardIntroduced(Date.now(), settings);
    await showNext();
  }

  function reveal() {
    if (!card || revealed) return;
    revealed = true;
    render();
  }

  async function render() {
    if (!card) {
      mount(
        h("section.study", {}, h("h1", {}, title), h("p.done", {}, "All done for now 🎉"), h("a.button", { href: "#/" }, "Back to decks")),
      );
      return;
    }
    const settings = await getMeta("settings");
    const now = Date.now();
    const buttons = RATINGS.map(([rating, label]) => {
      const next = applyReview(card, { id: "preview", rating, reviewed_at: now }, settings);
      return h(
        `button.grade.grade-${rating}`,
        { onclick: () => grade(rating) },
        h("span.grade-label", {}, label),
        h("span.grade-interval", {}, formatInterval(next.due - now)),
      );
    });
    mount(
      h(
        "section.study",
        {},
        h(
          "div.study-meta",
          {},
          h("span", {}, title),
          h("span.muted", {}, `${card.template_name} · ${card.state}`),
          h("a.muted", { href: `#/items/${card.item_id}` }, "edit"),
        ),
        cardElement(revealed ? card.back_html : card.front_html),
        h(
          "div.study-actions",
          {},
          revealed ? buttons : h("button.reveal", { onclick: reveal }, "Show answer", h("span.key-hint", {}, "space")),
        ),
      ),
    );
  }

  function onKey(e) {
    if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
    if (e.key === " " || e.key === "Enter") {
      e.preventDefault();
      if (!revealed) reveal();
      else grade(3);
    } else if (revealed && ["1", "2", "3", "4"].includes(e.key)) {
      grade(Number(e.key));
    }
  }

  // If a sync brings new data while the card is face-down, pick again (the current card may have been edited).
  function onChange() {
    if (!revealed) showNext();
  }

  document.addEventListener("keydown", onKey);
  window.addEventListener("srs:data-changed", onChange);
  await showNext();
  return () => {
    document.removeEventListener("keydown", onKey);
    window.removeEventListener("srs:data-changed", onChange);
  };
}
