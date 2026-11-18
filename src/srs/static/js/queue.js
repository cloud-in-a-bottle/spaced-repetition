import { getAll, getMeta, setMeta } from "./db.js";

// A study day runs from `day_starts_at_hour` local time to the same hour the next day (like anki).
export function studyDay(now, settings) {
  const start = new Date(now);
  start.setHours(settings.day_starts_at_hour, 0, 0, 0);
  if (start.getTime() > now) start.setDate(start.getDate() - 1);
  const end = new Date(start);
  end.setDate(end.getDate() + 1);
  return { key: start.toISOString().slice(0, 10), start: start.getTime(), end: end.getTime() };
}

const LEARN_AHEAD_MS = 20 * 60_000;

async function newCardsIntroduced(dayKey) {
  const counter = (await getMeta("new-introduced")) ?? {};
  return counter[dayKey] ?? 0;
}

export async function noteNewCardIntroduced(now, settings) {
  const { key } = studyDay(now, settings);
  const counter = (await getMeta("new-introduced")) ?? {};
  await setMeta("new-introduced", { [key]: (counter[key] ?? 0) + 1 });
}

// What to study: a deck (null = all decks), optionally narrowed to one part of speech.
function matches(card, { deckId = null, pos = null }) {
  return (deckId === null || card.deck_id === deckId) && (pos === null || card.pos === pos);
}

// Key for a deck's part-of-speech subset in dueCounts.
export function posKey(deckId, pos) {
  return `${deckId}|${pos}`;
}

// Due counts: { [deckId]: {learning, review, new} }, per part of speech under posKey(deckId, pos), and the totals
// under null.
export async function dueCounts(now) {
  const settings = await getMeta("settings");
  if (!settings) return {};
  const day = studyDay(now, settings);
  const newLeft = Math.max(0, settings.new_cards_per_day - (await newCardsIntroduced(day.key)));
  const counts = {};
  const bump = (card, kind) => {
    const keys = [card.deck_id, null];
    if (card.pos) keys.push(posKey(card.deck_id, card.pos));
    for (const key of keys) {
      counts[key] ??= { learning: 0, review: 0, new: 0 };
      counts[key][kind] += 1;
    }
  };
  for (const card of await getAll("cards")) {
    const kind = classify(card, now, day);
    if (kind) bump(card, kind);
  }
  for (const c of Object.values(counts)) c.new = Math.min(c.new, newLeft);
  return counts;
}

function classify(card, now, day) {
  if (card.suspended) return null;
  if (card.state === "new") return "new";
  if (card.state === "review") return card.due < day.end ? "review" : null;
  return card.due <= now + LEARN_AHEAD_MS ? "learning" : null;
}

// The next card to show for `filter` ({deckId, pos}; see matches), or null when done for today.
// Order: learning cards that are due, then reviews (most overdue first), then new cards (oldest first). Learning
// cards due within the next 20 minutes are shown early if nothing else is left.
export async function nextCard(filter, now, excludeId = null) {
  const settings = await getMeta("settings");
  const day = studyDay(now, settings);
  const cards = (await getAll("cards")).filter((c) => matches(c, filter) && !c.suspended && c.id !== excludeId);
  const byDue = (a, b) => a.due - b.due;
  const learningNow = cards.filter((c) => (c.state === "learning" || c.state === "relearning") && c.due <= now);
  if (learningNow.length) return learningNow.sort(byDue)[0];
  const reviews = cards.filter((c) => c.state === "review" && c.due < day.end);
  if (reviews.length) return reviews.sort(byDue)[0];
  if ((await newCardsIntroduced(day.key)) < settings.new_cards_per_day) {
    const fresh = cards.filter((c) => c.state === "new").sort((a, b) => a.created_at - b.created_at || (a.id < b.id ? -1 : 1));
    if (fresh.length) return fresh[0];
  }
  const learningSoon = cards.filter(
    (c) => (c.state === "learning" || c.state === "relearning") && c.due <= now + LEARN_AHEAD_MS,
  );
  return learningSoon.length ? learningSoon.sort(byDue)[0] : null;
}

// The parts of speech in each deck, most cards first: { [deckId]: [pos, ...] }. Suspended cards count, so the list
// doesn't shift as you study.
export async function partsOfSpeech() {
  const tally = {};
  for (const card of await getAll("cards")) {
    if (!card.pos) continue;
    tally[card.deck_id] ??= {};
    tally[card.deck_id][card.pos] = (tally[card.deck_id][card.pos] ?? 0) + 1;
  }
  return Object.fromEntries(
    Object.entries(tally).map(([deckId, t]) => [deckId, Object.keys(t).sort((a, b) => t[b] - t[a])]),
  );
}

const POS_LABELS = { proper_noun: "proper nouns", auxiliary: "auxiliaries", other: "other" };

export function posLabel(pos) {
  return POS_LABELS[pos] ?? `${pos}s`;
}
