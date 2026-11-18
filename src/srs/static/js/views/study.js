import { api } from "../api.js";
import { get, getAll, getMeta } from "../db.js";
import { formatInterval, h, mount } from "../dom.js";
import { applyReview } from "../fsrs.js";
import { nextCard, noteNewCardIntroduced, posLabel, unnoteNewCardIntroduced } from "../queue.js";
import { cardElement } from "../render.js";
import { newReview, recordReview, sync, undoReview } from "../sync.js";

// Just pass/fail: FSRS works fine without Hard and Easy, and deciding between them is a distraction.
const RATINGS = [
  [1, "Again", "1"],
  [3, "Good", "2"],
];

export async function studyView(deckId, pos = null) {
  const deck = deckId ? await get("decks", deckId) : null;
  const title = (deck ? deck.name : "All decks") + (pos ? ` · ${posLabel(pos)}` : "");
  const reviewSet = Boolean(deck?.ephemeral);
  const promoteTarget = reviewSet && deck.promote_to ? await get("decks", deck.promote_to) : null;
  let promoting = null; // null, "busy", or an error message
  const deckNames = new Map((await getAll("decks")).map((d) => [d.id, d.name]));
  let card = null;
  let revealed = false;
  let shownAt = 0;
  let lastId = null;
  let settings = await getMeta("settings");
  // All cards, kept in memory while studying so picking the next one doesn't re-read thousands from IndexedDB.
  // Answers update it immediately and are saved in the background, one after another.
  let cards = new Map((await getAll("cards")).map((c) => [c.id, c]));
  let saving = Promise.resolve();
  const history = []; // answers this session, for undo: {before, reviewId, newCardDay}

  function queueSave(fn) {
    saving = saving.then(fn).catch((err) => console.error("saving a review failed", err));
    return saving;
  }

  async function reloadCards() {
    await saving;
    settings = await getMeta("settings");
    cards = new Map((await getAll("cards")).map((c) => [c.id, c]));
  }

  async function showNext() {
    card = await nextCard({ deckId, pos }, Date.now(), lastId, [...cards.values()]);
    revealed = false;
    shownAt = Date.now();
    render();
  }

  function grade(rating) {
    if (!card || !revealed) return;
    const before = card;
    const review = newReview(before, rating, Date.now() - shownAt);
    cards.set(before.id, { ...before, ...applyReview(before, review, settings) });
    const entry = { before, reviewId: review.id, newCardDay: null };
    history.push(entry);
    lastId = before.id;
    queueSave(async () => {
      await recordReview(before, rating, review.duration_ms, review);
      if (before.state === "new" && !reviewSet) entry.newCardDay = await noteNewCardIntroduced(review.reviewed_at, settings);
    });
    showNext();
  }

  // Take back the last answer: the card goes back as it was, face down, and the review is voided.
  async function undo() {
    const entry = history.pop();
    if (!entry) return;
    await queueSave(async () => {
      await undoReview(entry.before, entry.reviewId);
      if (entry.newCardDay) await unnoteNewCardIntroduced(entry.newCardDay);
    });
    cards.set(entry.before.id, entry.before);
    card = entry.before;
    lastId = history.length ? history[history.length - 1].before.id : null;
    revealed = false;
    shownAt = Date.now();
    render();
  }

  const undoButton = () =>
    history.length
      ? h("button.link.undo", { onclick: undo, title: "Undo the last answer (u)" }, "Undo", h("span.key-hint", {}, "u"))
      : null;

  // Review-set cards can be copied into a main deck; the card stays in the set either way.
  async function promote() {
    if (!card || card.main_deck_id || promoting === "busy") return;
    promoting = "busy";
    render();
    try {
      const result = await api("POST", `/items/${card.item_id}/promote`, {});
      await sync();
      card = { ...card, main_deck_id: result.item.deck_id };
      promoting = null;
    } catch (err) {
      promoting = navigator.onLine ? `Couldn't add: ${err.message}` : "Adding needs a connection";
    }
    render();
  }

  function promoteControl() {
    if (card.main_deck_id) {
      const main = deckNames.get(card.main_deck_id);
      return h("span.promoted", { title: "This item is in a main deck" }, `✓ In ${main ?? "main deck"}`);
    }
    const label = promoting === "busy" ? "Adding…" : `+ Add to ${promoteTarget?.name ?? "main deck"}`;
    return h(
      "span.promote",
      {},
      h("button.link", { onclick: promote, disabled: promoting === "busy" }, label, h("span.key-hint", {}, "a")),
      promoting && promoting !== "busy" ? h("span.error", {}, promoting) : null,
    );
  }

  function reveal() {
    if (!card || revealed) return;
    revealed = true;
    render();
  }

  function render() {
    if (!card) {
      mount(
        h("section.study", {}, h("h1", {}, title), h("p.done", {}, "All done for now 🎉"),
          h("div.row", {}, h("a.button", { href: "#/" }, "Back to decks"), undoButton())),
      );
      return;
    }
    const now = Date.now();
    const buttons = RATINGS.map(([rating, label, key]) => {
      const next = applyReview(card, { id: "preview", rating, reviewed_at: now }, settings);
      return h(
        `button.grade.grade-${rating}`,
        { onclick: () => grade(rating) },
        h("span.grade-label", {}, label),
        h("span.grade-interval", {}, `${formatInterval(next.due - now)} · ${key}`),
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
          h("span", {}, undoButton(), h("a.muted", { href: `#/items/${card.item_id}` }, "edit")),
        ),
        reviewSet ? h("div.study-promote", {}, promoteControl()) : null,
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
    } else if (e.key === "u" || (e.key === "z" && (e.ctrlKey || e.metaKey))) {
      e.preventDefault();
      undo();
    } else if (reviewSet && e.key === "a") {
      promote();
    } else if (revealed) {
      const rating = RATINGS.find(([, , key]) => key === e.key);
      if (rating) grade(rating[0]);
    }
  }

  // If a sync brings new data while the card is face-down, pick again (the current card may have been edited).
  async function onChange() {
    await reloadCards();
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
