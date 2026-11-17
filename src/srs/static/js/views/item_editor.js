import { api } from "../api.js";
import { getAll } from "../db.js";
import { h, mount } from "../dom.js";
import { sync } from "../sync.js";

const LAST_LANGUAGE_KEY = "srs:last-language";
const LAST_DECK_KEY = "srs:last-deck";

function remember(key, value) {
  try {
    localStorage.setItem(key, value);
  } catch {
    // not important
  }
}

function recall(key) {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

// "tense=present\nperson=1st" <-> {tense: "present", person: "1st"}
function parseFeatures(text) {
  const out = {};
  for (const line of text.split("\n")) {
    const i = line.indexOf("=");
    if (i > 0) out[line.slice(0, i).trim()] = line.slice(i + 1).trim();
  }
  return out;
}
const formatFeatures = (f) => Object.entries(f ?? {}).map(([k, v]) => `${k}=${v}`).join("\n");

function alternativesField(obj) {
  return field("Other spellings", h("input", { value: obj.alternatives.join(", "),
    oninput: (e) => (obj.alternatives = e.target.value.split(",").map((t) => t.trim()).filter(Boolean)) }),
    "comma separated; other apps' lookups match these too");
}

function field(label, input, hint) {
  return h("label.field", {}, h("span.field-label", {}, label), input, hint ? h("span.muted.field-hint", {}, hint) : null);
}

// After adding an item the form starts over, keeping the kind (and for forms, the lexeme) so runs of similar items
// (eg a verb's conjugations) are quick to enter.
let carry = { kind: "lexeme", lexemeId: "", lexemeLabel: "" };

function blankItem(schema) {
  return {
    kind: carry.kind,
    deck_id: recall(LAST_DECK_KEY),
    language: recall(LAST_LANGUAGE_KEY) ?? "",
    tags: [],
    lexeme: { lemma: "", pos: schema.parts_of_speech[0], gloss: "", features: {}, notes: "", alternatives: [] },
    form: { lexeme_id: carry.lexemeId, form: "", features: {}, gloss: "", notes: "", alternatives: [] },
    phrase: { text: "", translation: "", notes: "", lexeme_ids: [] },
    fact: { front: "", back: "", notes: "" },
    cards: null,
  };
}

export async function itemEditorView(itemId) {
  let schema, templates, existing;
  try {
    [schema, templates, existing] = await Promise.all([
      api("GET", "/schema"),
      api("GET", "/templates"),
      itemId ? api("GET", `/items/${itemId}`) : Promise.resolve(null),
    ]);
  } catch (e) {
    mount(h("p.error", {}, `Editing needs a connection: ${e.message}`));
    return;
  }
  const decks = (await getAll("decks")).sort((a, b) => a.name.localeCompare(b.name));
  const item = { ...blankItem(schema), ...(existing ?? {}) };
  for (const k of ["lexeme", "form", "phrase", "fact"]) item[k] ??= blankItem(schema)[k];
  if (!decks.some((d) => d.id === item.deck_id)) item.deck_id = decks[0]?.id;
  const enabled = new Set(existing ? existing.cards.map((c) => c.template_id) : templates.filter((t) => t.default_enabled).map((t) => t.id));
  let lexemeLabel = existing ? "" : carry.lexemeLabel;
  if (existing?.kind === "form") {
    const lx = await api("GET", `/items/${existing.form.lexeme_id}`);
    lexemeLabel = `${lx.lexeme.lemma} (${lx.lexeme.gloss})`;
  }
  const errorBox = h("p.error");

  function kindFields() {
    const bind = (obj, key) => ({ value: obj[key], oninput: (e) => (obj[key] = e.target.value) });
    switch (item.kind) {
      case "lexeme":
        return [
          field("Lemma (root / dictionary form)", h("input", { ...bind(item.lexeme, "lemma"), required: true, autofocus: true })),
          field(
            "Part of speech",
            h("select", { onchange: (e) => (item.lexeme.pos = e.target.value) },
              schema.parts_of_speech.map((p) => h("option", { value: p, selected: p === item.lexeme.pos }, p))),
          ),
          field("Meaning / gloss", h("input", { ...bind(item.lexeme, "gloss"), required: true })),
          alternativesField(item.lexeme),
          field("Features", h("textarea", { rows: 2, value: formatFeatures(item.lexeme.features),
            oninput: (e) => (item.lexeme.features = parseFeatures(e.target.value)) }), "one per line, eg gender=feminine"),
          field("Notes", h("textarea", { rows: 2, ...bind(item.lexeme, "notes") })),
        ];
      case "form":
        return [
          lexemePicker(),
          field("Form", h("input", { ...bind(item.form, "form"), required: true })),
          alternativesField(item.form),
          field("Features", h("textarea", { rows: 4, value: formatFeatures(item.form.features),
            oninput: (e) => (item.form.features = parseFeatures(e.target.value)) }),
            "one per line, eg tense=present, person=1st, number=singular"),
          field("Meaning (optional)", h("input", bind(item.form, "gloss"))),
          field("Notes", h("textarea", { rows: 2, ...bind(item.form, "notes") })),
        ];
      case "phrase":
        return [
          field("Phrase", h("textarea", { rows: 2, ...bind(item.phrase, "text"), required: true })),
          field("Translation", h("textarea", { rows: 2, ...bind(item.phrase, "translation"), required: true })),
          field("Notes", h("textarea", { rows: 2, ...bind(item.phrase, "notes") })),
        ];
      case "fact":
        return [
          field("Front", h("textarea", { rows: 3, ...bind(item.fact, "front"), required: true })),
          field("Back", h("textarea", { rows: 3, ...bind(item.fact, "back"), required: true })),
          field("Notes", h("textarea", { rows: 2, ...bind(item.fact, "notes") })),
        ];
    }
  }

  function lexemePicker() {
    const results = h("ul.picker-results");
    const chosen = h("span.picked", {}, lexemeLabel || "none chosen");
    let timer = null;
    const search = h("input", {
      type: "search",
      placeholder: "Search lexemes…",
      oninput: (e) => {
        clearTimeout(timer);
        timer = setTimeout(async () => {
          const items = await api("GET", `/items?kind=lexeme&q=${encodeURIComponent(e.target.value)}`);
          results.replaceChildren(
            ...items.slice(0, 10).map((lx) =>
              h("li", {}, h("button.link", {
                type: "button",
                onclick: () => {
                  item.form.lexeme_id = lx.id;
                  lexemeLabel = `${lx.lexeme.lemma} (${lx.lexeme.gloss})`;
                  chosen.textContent = lexemeLabel;
                  results.replaceChildren();
                },
              }, `${lx.lexeme.lemma} — ${lx.lexeme.gloss} [${lx.language}]`)),
            ),
          );
        }, 200);
      },
    });
    return field("Lexeme this is a form of", h("div", {}, chosen, search, results));
  }

  function templateChecks() {
    return templates
      .filter((t) => t.kind === item.kind)
      .map((t) =>
        h("label.check", {},
          h("input", { type: "checkbox", checked: enabled.has(t.id),
            onchange: (e) => (e.target.checked ? enabled.add(t.id) : enabled.delete(t.id)) }),
          ` ${t.name} `, h("span.muted", {}, `(${t.skill})`)),
      );
  }

  async function save(e) {
    e.preventDefault();
    const kindTemplates = templates.filter((t) => t.kind === item.kind).map((t) => t.id);
    const body = {
      deck_id: item.deck_id,
      kind: item.kind,
      language: item.language || null,
      tags: item.tags,
      [item.kind]: item[item.kind],
      template_ids: kindTemplates.filter((id) => enabled.has(id)),
    };
    try {
      const saved = await (existing ? api("PUT", `/items/${existing.id}`, body) : api("POST", "/items", body));
      remember(LAST_DECK_KEY, item.deck_id);
      if (item.language) remember(LAST_LANGUAGE_KEY, item.language);
      await sync().catch(() => {});
      carry = { kind: item.kind, lexemeId: item.form.lexeme_id, lexemeLabel };
      if (existing) history.back();
      else itemEditorView(null).then(() => flash(`Added ${saved.kind}.`));
    } catch (err) {
      errorBox.textContent = err.message;
    }
  }

  async function remove() {
    if (!confirm("Delete this item and its cards?")) return;
    try {
      await api("DELETE", `/items/${existing.id}`);
      await sync().catch(() => {});
      location.hash = "#/items";
    } catch (err) {
      errorBox.textContent = err.message;
    }
  }

  function flash(text) {
    const note = document.querySelector(".flash");
    if (note) note.textContent = text;
  }

  function render() {
    mount(
      h("form.editor", { onsubmit: save },
        h("h1", {}, existing ? `Edit ${item.kind}` : "Add item"),
        h("p.flash.muted"),
        existing ? null : field("Kind",
          h("select", { onchange: (e) => ((item.kind = e.target.value), render()) },
            schema.kinds.map((k) => h("option", { value: k.kind, selected: k.kind === item.kind }, k.kind)))),
        h("div.row-fields", {},
          field("Deck", h("select", { onchange: (e) => (item.deck_id = e.target.value) },
            decks.map((d) => h("option", { value: d.id, selected: d.id === item.deck_id }, d.name)))),
          item.kind === "form" ? null : field("Language", h("input", { value: item.language ?? "", size: 6,
            placeholder: "eg es", oninput: (e) => (item.language = e.target.value.trim()) }), "ISO 639 code"),
        ),
        kindFields(),
        field("Tags", h("input", { value: item.tags.join(", "),
          oninput: (e) => (item.tags = e.target.value.split(",").map((t) => t.trim()).filter(Boolean)) })),
        h("fieldset", {}, h("legend", {}, "Cards"), templateChecks()),
        errorBox,
        h("div.row", {},
          h("button.primary", { type: "submit" }, existing ? "Save" : "Add"),
          existing ? h("button.danger", { type: "button", onclick: remove }, "Delete") : null),
      ),
    );
  }
  render();
}
