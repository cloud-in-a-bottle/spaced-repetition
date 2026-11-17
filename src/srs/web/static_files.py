from importlib import resources
from pathlib import Path

from litestar import Response
from litestar import get
from litestar.datastructures import CacheControlHeader
from litestar.static_files import create_static_files_router

STATIC_DIR = Path(str(resources.files("srs") / "static"))

# The service worker does the caching (and versioning) for offline use, so the browser's http cache stays out of it.
_NO_CACHE = CacheControlHeader(no_cache=True)


def _file(name: str, media_type: str) -> Response[bytes]:
    return Response((STATIC_DIR / name).read_bytes(), media_type=media_type, headers={"Cache-Control": "no-cache"})


@get("/", sync_to_thread=False, include_in_schema=False)
def index() -> Response[bytes]:
    return _file("index.html", "text/html; charset=utf-8")


@get("/sw.js", sync_to_thread=False, include_in_schema=False)
def service_worker() -> Response[bytes]:
    # served from the root so its scope covers the whole app
    return _file("sw.js", "text/javascript")


@get("/manifest.webmanifest", sync_to_thread=False, include_in_schema=False)
def web_manifest() -> Response[bytes]:
    return _file("manifest.webmanifest", "application/manifest+json")


static_router = create_static_files_router(path="/static", directories=[STATIC_DIR], cache_control=_NO_CACHE)
