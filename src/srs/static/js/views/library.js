import { api } from "../api.js";
import { h, mount } from "../dom.js";

// The reader's library: courses (eg a TV show) holding texts (eg one episode's subtitles). Online only.

function offlineNotice(err) {
  return h("p.error", {}, navigator.onLine ? `Couldn't load the library: ${err.message}` : "The reader needs a connection.");
}

export async function libraryView() {
  let courses;
  try {
    courses = await api("GET", "/library");
  } catch (err) {
    mount(h("section", {}, h("h1", {}, "Library"), offlineNotice(err)));
    return;
  }

  async function newCourse() {
    const title = prompt("Course title (eg the name of a show or book)");
    if (!title) return;
    const language = prompt("Language code", "es");
    if (!language) return;
    try {
      await api("POST", "/library/courses", { title, language });
      libraryView();
    } catch (err) {
      alert(err.message);
    }
  }

  async function removeCourse(c) {
    if (!confirm(`Delete ${c.title} and its ${c.texts.length} texts? Words you added to decks stay.`)) return;
    await api("DELETE", `/library/courses/${c.id}`);
    libraryView();
  }

  const courseBlock = (c) =>
    h("section.course", {},
      h("div.row", {},
        h("h2", {}, c.title, " ", h("span.lang-badge", {}, c.language)),
        h("span", {},
          h("a.button", { href: `#/read/new/${c.id}` }, "+ Add text"),
          h("button.link", { onclick: () => removeCourse(c) }, "delete")),
      ),
      c.description ? h("p.muted", {}, c.description) : null,
      c.texts.length
        ? h("ol.text-list", {}, c.texts.map((t) =>
            h("li", {},
              h("a", { href: `#/read/${t.id}` },
                h("span.text-pos", {}, t.position), " ", t.title),
              h("span.muted.text-meta", {},
                `${t.words.toLocaleString()} words`, t.format === "subtitles" ? " · subtitles" : "",
                t.read_at ? " · ✓ read" : t.progress_block !== null ? ` · ${Math.round((100 * (t.progress_block + 1)) / t.blocks)}% read` : ""))))
        : h("p.muted", {}, "No texts yet."));

  mount(
    h("section", {},
      h("div.row", {}, h("h1", {}, "Library"), h("button", { onclick: newCourse }, "+ New course")),
      courses.length ? courses.map(courseBlock) : h("p.muted", {}, "Add a course, then paste a text or upload subtitles (.srt) to read it with your deck's help."),
    ),
  );
}

export async function textImportView(courseId) {
  let courses;
  try {
    courses = await api("GET", "/library");
  } catch (err) {
    mount(h("section", {}, h("h1", {}, "Add text"), offlineNotice(err)));
    return;
  }
  const course = courses.find((c) => c.id === courseId);
  if (!course) {
    mount(h("p", {}, "No such course."));
    return;
  }
  const form = { title: "", position: course.texts.length + 1, format: "text", content: "" };
  const status = h("p.muted");
  const content = h("textarea", { rows: 14, placeholder: "Paste text here (paragraphs separated by blank lines), or choose a file.",
    oninput: (e) => (form.content = e.target.value) });
  const formatSelect = h("select", { onchange: (e) => (form.format = e.target.value) },
    h("option", { value: "text" }, "Text"), h("option", { value: "srt" }, "Subtitles (.srt)"));
  const titleInput = h("input", { required: true, oninput: (e) => (form.title = e.target.value) });

  async function pickFile(e) {
    const file = e.target.files[0];
    if (!file) return;
    form.content = await file.text();
    content.value = form.content;
    if (file.name.toLowerCase().endsWith(".srt")) {
      form.format = "srt";
      formatSelect.value = "srt";
    }
    if (!form.title) {
      form.title = file.name.replace(/\.[^.]+$/, "").replace(/[._]+/g, " ");
      titleInput.value = form.title;
    }
  }

  async function save(e) {
    e.preventDefault();
    try {
      const text = await api("POST", "/library/texts", { course_id: course.id, ...form, position: Number(form.position) });
      location.hash = `#/read/${text.id}`;
    } catch (err) {
      status.textContent = `Couldn't add it: ${err.message}`;
    }
  }

  mount(
    h("form.editor", { onsubmit: save },
      h("h1", {}, `Add text to ${course.title}`),
      h("label.field", {}, h("span.field-label", {}, "Title"), titleInput),
      h("div.row-fields", {},
        h("label.field", {}, h("span.field-label", {}, "Format"), formatSelect),
        h("label.field", {}, h("span.field-label", {}, "Position"),
          h("input", { type: "number", min: 1, value: form.position, oninput: (e) => (form.position = e.target.value) }))),
      h("label.field", {}, h("span.field-label", {}, "File"), h("input", { type: "file", accept: ".srt,.txt,text/plain", onchange: pickFile })),
      content,
      h("div.row", {}, h("button.primary", { type: "submit" }, "Add"), h("a", { href: "#/read" }, "Cancel")),
      status,
    ),
  );
}
