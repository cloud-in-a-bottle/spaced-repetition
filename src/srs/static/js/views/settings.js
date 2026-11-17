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
    return h("section", {},
      h("h2", {}, "Decks"),
      h("ul.deck-admin", {}, decks.map((d) => h("li", {}, d.name,
        h("button.link", { onclick: () => {
          const name = prompt("Rename deck", d.name);
          if (name) run(() => api("PUT", `/decks/${d.id}`, { name }));
        } }, "rename"),
        h("button.link", { onclick: () => confirm(`Delete ${d.name}?`) && run(() => api("DELETE", `/decks/${d.id}`)) }, "delete")))),
      h("button", { onclick: () => {
        const name = prompt("New deck name");
        if (name) run(() => api("POST", "/decks", { name }));
      } }, "+ New deck"),
    );
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
      h("section", {},
        h("h2", {}, "More"),
        h("p", {}, h("a", { href: "#/templates" }, "Edit card templates")),
        h("button", { onclick: () => resync().then(() => alert("Re-downloaded everything.")).catch((e) => alert(e.message)) },
          "Re-download all data"),
      ),
    ),
  );
}
