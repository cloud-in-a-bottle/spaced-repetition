import { api } from "../api.js";
import { getAll, getMeta } from "../db.js";
import { h, mount } from "../dom.js";
import { resync, sync } from "../sync.js";

function numberField(label, value, onchange, attrs = {}) {
  return h("label.field", {}, h("span.field-label", {}, label),
    h("input", { type: "number", value, oninput: (e) => onchange(Number(e.target.value)), ...attrs }));
}

function listField(label, values, onchange, hint) {
  return h("label.field", {}, h("span.field-label", {}, label),
    h("input", { value: values.join(", "), oninput: (e) => onchange(e.target.value.split(",").map((v) => v.trim()).filter(Boolean).map(Number)) }),
    h("span.muted.field-hint", {}, hint));
}

export async function settingsView() {
  const settings = structuredClone(await getMeta("settings"));
  const status = h("p.muted");

  async function save(e) {
    e.preventDefault();
    try {
      await api("PUT", "/settings", settings);
      await sync();
      status.textContent = "Saved. All cards were rescheduled under the new settings.";
    } catch (err) {
      status.textContent = `Couldn't save: ${err.message}`;
    }
  }

  async function decksSection() {
    const decks = (await getAll("decks")).sort((a, b) => a.name.localeCompare(b.name));
    const run = async (fn) => {
      try {
        await fn();
        await sync();
        settingsView();
      } catch (err) {
        alert(err.message);
      }
    };
    const main = decks.filter((d) => !d.ephemeral);
    const deleteMessage = (d) =>
      d.ephemeral
        ? `Delete the review set ${d.name} and all its items? Anything you added to a main deck stays there.`
        : `Delete ${d.name}?`;
    // "Add to main deck" target for a review set; blank = the main deck with most items in the word's language
    const promoteSelect = (d) =>
      h("select", { onchange: (e) => run(() => api("PUT", `/decks/${d.id}`, { name: d.name, promote_to: e.target.value || null })) },
        h("option", { value: "" }, "add words to: (auto)"),
        main.map((m) => h("option", { value: m.id, selected: m.id === d.promote_to }, `add words to: ${m.name}`)));
    const row = (d) => h("li", {}, d.name,
      h("button.link", { onclick: () => {
        const name = prompt("Rename deck", d.name);
        if (name) run(() => api("PUT", `/decks/${d.id}`, { name, promote_to: d.promote_to }));
      } }, "rename"),
      h("button.link", { onclick: () => confirm(deleteMessage(d)) && run(() => api("DELETE", `/decks/${d.id}`)) }, "delete"),
      d.ephemeral ? promoteSelect(d) : null);
    const reviewSets = decks.filter((d) => d.ephemeral);
    return h("section", {},
      h("h2", {}, "Decks"),
      h("ul.deck-admin", {}, main.map(row)),
      h("button", { onclick: () => {
        const name = prompt("New deck name");
        if (name) run(() => api("POST", "/decks", { name }));
      } }, "+ New deck"),
      h("h2", {}, "Review sets"),
      h("p.muted", {}, "Throwaway decks for cramming, eg the words of one episode. They don't count toward what you know, ",
        "ignore the new-cards-per-day limit, and each card has a button to add it to a main deck."),
      reviewSets.length ? h("ul.deck-admin", {}, reviewSets.map(row)) : null,
      h("button", { onclick: () => {
        const name = prompt("New review set name");
        if (name) run(() => api("POST", "/decks", { name, ephemeral: true }));
      } }, "+ New review set"),
    );
  }

  async function dictionariesSection() {
    const section = h("section", {}, h("h2", {}, "Dictionaries"));
    let timer = null;
    async function render() {
      let list;
      try {
        list = await api("GET", "/dictionaries");
      } catch (err) {
        section.replaceChildren(h("h2", {}, "Dictionaries"), h("p.muted", {}, `Unavailable offline (${err.message}).`));
        return;
      }
      const label = (d) => ({ installed: "installed", missing: "not installed", installing: `building… ${d.status.entries.toLocaleString()} entries`, failed: `failed: ${d.status.error}` })[d.status.state];
      section.replaceChildren(
        h("h2", {}, "Dictionaries"),
        h("p.muted", {}, "Offline dictionaries for the reader, built from Wiktionary (via kaikki.org; CC BY-SA). ",
          "They give definitions and match inflected words (zarpó → zarpar) to your deck. About 100 MB to download and a few minutes to build."),
        h("ul.deck-admin", {}, list.map((d) => h("li", {}, d.language, " — ", label(d),
          d.status.state === "installing" ? null
            : h("button.link", { onclick: async () => { await api("POST", `/dictionaries/${d.language}/install`); render(); } },
                d.status.state === "installed" ? "update" : "install")))));
      clearTimeout(timer);
      if (list.some((d) => d.status.state === "installing")) timer = setTimeout(render, 3000);
    }
    render();
    return section;
  }

  mount(
    h("div", {},
      h("form.editor", { onsubmit: save },
        h("h1", {}, "Settings"),
        numberField("Desired retention", settings.desired_retention, (v) => (settings.desired_retention = v), { step: 0.01, min: 0.5, max: 0.99 }),
        numberField("New cards per day", settings.new_cards_per_day, (v) => (settings.new_cards_per_day = v), { min: 0 }),
        numberField("Maximum interval (days)", settings.maximum_interval_days, (v) => (settings.maximum_interval_days = v), { min: 1 }),
        numberField("Next day starts at (hour)", settings.day_starts_at_hour, (v) => (settings.day_starts_at_hour = v), { min: 0, max: 23 }),
        listField("Learning steps (minutes)", settings.learning_steps_minutes, (v) => (settings.learning_steps_minutes = v), "eg 1, 10"),
        listField("Relearning steps (minutes)", settings.relearning_steps_minutes, (v) => (settings.relearning_steps_minutes = v), "eg 10"),
        h("button.primary", { type: "submit" }, "Save"),
        status,
      ),
      await decksSection(),
      await dictionariesSection(),
      h("section", {},
        h("h2", {}, "More"),
        h("p", {}, h("a", { href: "#/templates" }, "Edit card templates")),
        h("button", { onclick: () => resync().then(() => alert("Re-downloaded everything.")).catch((e) => alert(e.message)) },
          "Re-download all data"),
      ),
    ),
  );
}
