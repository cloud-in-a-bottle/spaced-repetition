export class SignedOut extends Error {}

export class ApiError extends Error {
  constructor(status, detail) {
    super(detail);
    this.status = status;
  }
}

// JSON call to the app's own backend. An expired openhost session shows up as a redirect to the login page, which
// we refuse to follow (redirect: "manual") so it can be reported instead of parsed as data.
export async function api(method, path, body) {
  const response = await fetch(`/api${path}`, {
    method,
    credentials: "include",
    redirect: "manual",
    headers: body === undefined ? {} : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (response.type === "opaqueredirect" || response.status === 401) throw new SignedOut("signed out");
  if (response.status === 204) return null;
  const data = await response.json();
  if (!response.ok) throw new ApiError(response.status, data.detail ?? JSON.stringify(data));
  return data;
}
