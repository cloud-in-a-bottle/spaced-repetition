from litestar import Request
from litestar import Response

from srs.service.permissions import PermissionRequired


def permission_required_handler(_: Request, exc: PermissionRequired) -> Response[dict[str, object]]:  # type: ignore[type-arg]
    """The body shape the router looks for, so it can add a grant_url the consumer can send the owner to."""
    body: dict[str, object] = {
        "error": "permission_required",
        "required_grant": {"grant": exc.required_grant.grant, "scope": exc.required_grant.scope},
    }
    return Response(body, status_code=403)
