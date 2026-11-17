import { api } from "../api.js";
import { h, mount } from "../dom.js";
import { sync } from "../sync.js";

export async function templatesView() {
  let templates;
  try {
    templates = await api("GET", "/templates");
  } catch (e) {
    mount(h("p.error", {}, `Editing needs a connection: ${e.message}`));
    return;
  }

  function editor(t) {
    const draft = { ...t };
    const status = h("span.muted");
    const area = (key, rows) => h("label.field", {}, h("span.field-label", {}, key),
      h("textarea.code", { rows, value: draft[key], oninput: (e) => (draft[key] = e.target.value) }));
    return h("details.template", {},
      h("summary", {}, h("span.kind-badge", {}, t.kind), ` ${t.name} `, h("span.muted", {}, `(${t.skill})`)),
      h("form.editor", { onsubmit: async (e) => {
        e.preventDefault();
        try {
          const { id, deleted, seq, ...body } = draft;
          await api("PUT", `/templates/${id}`, body);
          await sync();
          status.textContent = "Saved; cards re-rendered.";
        } catch (err) {
          status.textContent = err.message;
        }
      } },
        h("label.field", {}, h("span.field-label", {}, "name"), h("input", { value: draft.name, oninput: (e) => (draft.name = e.target.value) })),
        area("front", 4), area("back", 4), area("css", 6),
        h("label.check", {}, h("input", { type: "checkbox", checked: draft.default_enabled,
          onchange: (e) => (draft.default_enabled = e.target.checked) }), " give new items this card by default"),
        h("div.row", {}, h("button.primary", { type: "submit" }, "Save"), status)),
    );
  }

  mount(h("section", {},
    h("h1", {}, "Card templates"),
    h("p.muted", {}, "Jinja templates. Fields of the item are available by name (eg {{ lemma }}, {{ gloss }}, {{ features|features }}); forms also get {{ lexeme.lemma }}. The back can include {{ front_side }}."),
    templates.map(editor)));
}
