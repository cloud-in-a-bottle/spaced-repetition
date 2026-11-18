import { getAll } from "./db.js";
import { mount, h } from "./dom.js";
import { onSyncStatus, refreshPendingCount, sync } from "./sync.js";
import { homeView } from "./views/home.js";
import { itemEditorView } from "./views/item_editor.js";
import { itemsView } from "./views/items.js";
import { settingsView } from "./views/settings.js";
import { studyView } from "./views/study.js";
import { templatesView } from "./views/templates.js";

const routes = [
  [/^#?\/?$/, () => homeView()],
  [/^#\/study\/([^/]+)(?:\/([^/]+))?$/, ([deckId, pos]) => studyView(deckId === "all" ? null : deckId, pos ?? null)],
  [/^#\/items$/, () => itemsView()],
  [/^#\/items\/new$/, () => itemEditorView(null)],
  [/^#\/items\/(.+)$/, ([id]) => itemEditorView(id)],
  [/^#\/settings$/, () => settingsView()],
  [/^#\/templates$/, () => templatesView()],
];

let cleanup = null;

async function route() {
  cleanup?.();
  cleanup = null;
  const hash = location.hash || "#/";
  for (const [pattern, view] of routes) {
    const match = hash.match(pattern);
    if (match) {
      const result = await view(match.slice(1).map((v) => (v === undefined ? undefined : decodeURIComponent(v))));
      cleanup = typeof result === "function" ? result : null;
      return;
    }
  }
  mount(h("p", {}, "Not found."));
}

function describe(status) {
  const pending = status.pending ? ` · ${status.pending} to upload` : "";
  switch (status.state) {
    case "syncing":
      return `Syncing…${pending}`;
    case "offline":
      return `Offline${pending}`;
    case "signed-out":
      return "Signed out — reload to log in";
    case "error":
      return `Sync failed${pending}`;
    default:
      return status.lastSync ? `Synced${pending}` : `Not synced${pending}`;
  }
}

function setupSyncIndicator() {
  const el = document.getElementById("sync-status");
  onSyncStatus((status) => {
    el.textContent = describe(status);
    el.dataset.state = status.state;
    el.title = status.error ?? "Sync now";
  });
  el.addEventListener("click", () => {
    if (el.dataset.state === "signed-out") location.reload();
    else sync().catch(() => {});
  });
}

async function syncAndRefresh() {
  try {
    if (await sync()) window.dispatchEvent(new Event("srs:data-changed"));
  } catch {
    // shown in the status indicator
  }
}

async function main() {
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(console.error);
  setupSyncIndicator();
  await refreshPendingCount();
  window.addEventListener("hashchange", route);
  window.addEventListener("online", syncAndRefresh);
  document.addEventListener("visibilitychange", () => document.visibilityState === "visible" && syncAndRefresh());
  setInterval(syncAndRefresh, 5 * 60_000);
  const haveData = (await getAll("decks")).length > 0;
  if (haveData) {
    route();
    syncAndRefresh();
  } else {
    mount(h("p.muted", {}, "Loading your collection…"));
    await syncAndRefresh();
    route();
  }
}

main();
