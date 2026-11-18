"""A tiny JSON client for the app's owner API: through `oh curl` (which adds the openhost token) for the deployed
app, or plain HTTP for a local dev server."""

import json
import subprocess
import urllib.request
from typing import Any

DEFAULT_APP_URL = "https://srs.host.zackpolizzi.com"


class SrsClient:
    def __init__(self, url: str = DEFAULT_APP_URL, local: bool | None = None) -> None:
        self.url = url.rstrip("/")
        self.local = local if local is not None else self.url.startswith(("http://localhost", "http://127.0.0.1"))

    def request(self, method: str, path: str, body: Any = None) -> Any:
        url = f"{self.url}/api{path}"
        data = None if body is None else json.dumps(body, ensure_ascii=False).encode()
        if self.local:
            req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=600) as r:  # noqa: S310 - our own server
                raw = r.read()
        else:
            args = [
                "oh",
                "curl",
                "--",
                "-sS",
                "--fail-with-body",
                "--max-time",
                "900",
                "-X",
                method,
                "-H",
                "Content-Type: application/json",
                url,
            ]
            if data is not None:
                args[4:4] = ["--data-binary", "@-"]
            done = subprocess.run(args, input=data, capture_output=True, check=False)  # noqa: S603
            if done.returncode != 0:
                raise RuntimeError(
                    f"{method} {path} failed: {done.stdout.decode()[:500]} {done.stderr.decode()[:500]}"
                )
            raw = done.stdout
        return json.loads(raw) if raw.strip() else None

    def get(self, path: str) -> Any:
        return self.request("GET", path)

    def post(self, path: str, body: Any) -> Any:
        return self.request("POST", path, body)

    def put(self, path: str, body: Any) -> Any:
        return self.request("PUT", path, body)

    def delete(self, path: str) -> Any:
        return self.request("DELETE", path)
