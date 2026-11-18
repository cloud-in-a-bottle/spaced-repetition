import { api, SignedOut } from "./api.js";
import { getAll, getMeta, transaction } from "./db.js";
import { applyReview } from "./fsrs.js";

const listeners = new Set();
let status = { state: "idle", pending: 0, lastSync: null, error: null };
let running = null;

export function onSyncStatus(fn) {
  listeners.add(fn);
  fn(status);
  return () => listeners.delete(fn);
}

function setStatus(patch) {
  status = { ...status, ...patch };
  for (const fn of listeners) fn(status);
}

export async function refreshPendingCount() {
  setStatus({ pending: (await getAll("outbox")).length });
}

// Record a review locally: update the card's schedule now (so studying works offline) and queue it for the server.
export async function recordReview(card, rating, durationMs) {
  const settings = await getMeta("settings");
  const review = { id: crypto.randomUUID(), card_id: card.id, rating, reviewed_at: Date.now(), duration_ms: durationMs };
  // re-read the card in case a sync replaced it while it was on screen
  const updated = await transaction(["cards", "outbox"], "readwrite", async (s, done) => {
    const current = (await done(s.cards.get(card.id))) ?? card;
    const next = { ...current, ...applyReview(current, review, settings) };
    s.cards.put(next);
    s.outbox.put(review);
    return next;
  });
  await refreshPendingCount();
  sync().catch(() => {});
  return updated;
}

// Bump when synced cards gain a field, so clients pull everything again once (eg 2: cards carry `pos`).
const DATA_VERSION = 2;

async function syncOnce() {
  if ((await getMeta("data-version")) !== DATA_VERSION) {
    await transaction(["cards", "decks", "meta"], "readwrite", (s) => {
      s.cards.clear();
      s.decks.clear();
      s.meta.delete("cursor");
      s.meta.put(DATA_VERSION, "data-version");
    });
  }
  const outbox = await getAll("outbox");
  const cursor = (await getMeta("cursor")) ?? 0;
  const response = await api("POST", "/sync", { cursor, reviews: outbox });
  const sentIds = new Set(outbox.map((r) => r.id));
  const settings = response.settings ?? (await getMeta("settings"));
  await transaction(["cards", "decks", "outbox", "meta"], "readwrite", async (s, done) => {
    for (const id of sentIds) s.outbox.delete(id);
    // Reviews made while this request was in flight aren't in the server's state yet; re-apply them on top.
    const stillPending = (await done(s.outbox.getAll())).filter((r) => !sentIds.has(r.id));
    for (const card of response.cards) {
      if (card.deleted) {
        s.cards.delete(card.id);
        continue;
      }
      const mine = stillPending.filter((r) => r.card_id === card.id).sort((a, b) => a.reviewed_at - b.reviewed_at);
      s.cards.put(mine.reduce((c, r) => ({ ...c, ...applyReview(c, r, settings) }), card));
    }
    for (const deck of response.decks) {
      if (deck.deleted) s.decks.delete(deck.id);
      else s.decks.put(deck);
    }
    if (response.settings) s.meta.put(response.settings, "settings");
    s.meta.put(response.cursor, "cursor");
  });
  return response.cards.length > 0 || response.decks.length > 0 || response.settings !== null;
}

// Push queued reviews and pull changes. Returns whether anything changed locally. Concurrent calls share one run.
export function sync() {
  running ??= (async () => {
    setStatus({ state: "syncing", error: null });
    try {
      const changed = await syncOnce();
      setStatus({ state: "idle", lastSync: Date.now() });
      return changed;
    } catch (e) {
      const state = e instanceof SignedOut ? "signed-out" : navigator.onLine ? "error" : "offline";
      setStatus({ state, error: String(e.message ?? e) });
      throw e;
    } finally {
      running = null;
      await refreshPendingCount();
    }
  })();
  return running;
}

// Drop the local copy and pull everything again (eg after a server-side restore).
export async function resync() {
  await transaction(["cards", "decks", "meta"], "readwrite", (s) => {
    s.cards.clear();
    s.decks.clear();
    s.meta.delete("cursor");
  });
  return sync();
}
