import { api } from "./api.js";
import { getMeta, setMeta, transaction } from "./db.js";

// Reading offline: texts downloaded with every word's details (stored under "offline-text:<id>" in the meta store),
// and reader changes made without a connection (marks, reading position, new words) queued as API requests that
// are sent, in order, when it's back.

const INDEX = "offline-texts"; // [{id, title, course_title, downloaded_at}]
const QUEUE = "pending-requests"; // [{method, path, body}]

export function isNetworkError(err) {
  return err instanceof TypeError || !navigator.onLine;
}

export async function downloadedTexts() {
  return (await getMeta(INDEX)) ?? [];
}

export async function offlineText(id) {
  return (await getMeta(`offline-text:${id}`)) ?? null;
}

export async function downloadText(id) {
  const bundle = await api("GET", `/reader/texts/${id}/offline`);
  await saveBundle(bundle);
  return bundle;
}

async function saveBundle(bundle) {
  const r = bundle.reading;
  const index = (await downloadedTexts()).filter((t) => t.id !== r.id);
  index.push({ id: r.id, title: r.title, course_title: r.course_title, downloaded_at: Date.now() });
  await transaction(["meta"], "readwrite", (s) => {
    s.meta.put(bundle, `offline-text:${r.id}`);
    s.meta.put(index, INDEX);
  });
}

// Keep a downloaded copy current with what the server just said (statuses, reading position).
export async function refreshDownloaded(reading, details = null) {
  const bundle = await offlineText(reading.id);
  if (!bundle) return;
  await saveBundle({ reading, details: details ? { ...bundle.details, ...details } : bundle.details });
}

export async function removeDownload(id) {
  const index = (await downloadedTexts()).filter((t) => t.id !== id);
  await transaction(["meta"], "readwrite", (s) => {
    s.meta.delete(`offline-text:${id}`);
    s.meta.put(index, INDEX);
  });
}

// Try the request now; if there's no connection, queue it and return undefined.
export async function apiOrQueue(method, path, body) {
  try {
    return await api(method, path, body);
  } catch (err) {
    if (!isNetworkError(err)) throw err;
    const queue = (await getMeta(QUEUE)) ?? [];
    await setMeta(QUEUE, [...queue, { method, path, body }]);
    return undefined;
  }
}

export async function pendingRequests() {
  return ((await getMeta(QUEUE)) ?? []).length;
}

let flushing = null;

// Send queued requests in order. Stops at the first network failure (still offline); drops requests the server
// rejects outright, since retrying them can't succeed.
export function flushQueue() {
  flushing ??= (async () => {
    try {
      for (;;) {
        const queue = (await getMeta(QUEUE)) ?? [];
        if (!queue.length) return;
        const [next, ...rest] = queue;
        try {
          await api(next.method, next.path, next.body);
        } catch (err) {
          if (isNetworkError(err)) return;
          console.warn("dropping a queued reader change the server rejected", next, err);
        }
        await setMeta(QUEUE, rest);
      }
    } finally {
      flushing = null;
    }
  })();
  return flushing;
}
