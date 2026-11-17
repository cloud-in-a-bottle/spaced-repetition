// The offline copy of the collection, in IndexedDB:
//   cards  — every live card as the server last sent it (with any not-yet-synced local reviews applied on top)
//   decks  — deck list
//   outbox — reviews made here that the server hasn't acknowledged yet
//   meta   — sync cursor, settings, and per-day counters
const DB_NAME = "srs";
const DB_VERSION = 1;

let dbPromise = null;

function open() {
  dbPromise ??= new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      db.createObjectStore("cards", { keyPath: "id" }).createIndex("deck_id", "deck_id");
      db.createObjectStore("decks", { keyPath: "id" });
      db.createObjectStore("outbox", { keyPath: "id" });
      db.createObjectStore("meta");
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
  return dbPromise;
}

function done(req) {
  return new Promise((resolve, reject) => {
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

function txDone(tx) {
  return new Promise((resolve, reject) => {
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
    tx.onabort = () => reject(tx.error);
  });
}

// Run fn(stores) inside one transaction over the named stores.
export async function transaction(storeNames, mode, fn) {
  const db = await open();
  const tx = db.transaction(storeNames, mode);
  const stores = Object.fromEntries(storeNames.map((n) => [n, tx.objectStore(n)]));
  const result = await fn(stores, done);
  await txDone(tx);
  return result;
}

export const getAll = (store) => transaction([store], "readonly", (s, d) => d(s[store].getAll()));
export const get = (store, key) => transaction([store], "readonly", (s, d) => d(s[store].get(key)));
export const getMeta = (key) => get("meta", key);
export const setMeta = (key, value) => transaction(["meta"], "readwrite", (s) => s.meta.put(value, key));
