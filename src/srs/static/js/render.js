// Card html comes pre-rendered (and escaped) from the server, with the template's css inlined. A shadow root keeps
// that css from leaking into the app, and vice versa.
export function cardElement(html) {
  const host = document.createElement("div");
  host.className = "card-host";
  host.attachShadow({ mode: "open" }).innerHTML = html;
  return host;
}
