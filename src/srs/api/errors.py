from litestar import Request
from litestar import Response
from litestar.types import ExceptionHandlersMap

from srs.domain.errors import InvalidRequest
from srs.domain.errors import NotFound


def _invalid(_: Request, exc: InvalidRequest) -> Response[dict[str, str]]:  # type: ignore[type-arg]
    return Response({"error": "invalid_request", "detail": str(exc)}, status_code=400)


def _not_found(_: Request, exc: NotFound) -> Response[dict[str, str]]:  # type: ignore[type-arg]
    return Response({"error": "not_found", "detail": f"no such {exc}"}, status_code=404)


EXCEPTION_HANDLERS: ExceptionHandlersMap = {InvalidRequest: _invalid, NotFound: _not_found}
