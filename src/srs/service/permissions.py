import json

import attr
from litestar.connection import ASGIConnection
from litestar.exceptions import HTTPException
from litestar.handlers.base import BaseRouteHandler

KNOWLEDGE_READ = "knowledge:read"


@attr.s(auto_attribs=True, frozen=True)
class RequiredGrant:
    grant: str
    scope: str


class PermissionRequired(HTTPException):
    status_code = 403

    def __init__(self, grant: str) -> None:
        super().__init__(detail="permission_required")
        self.required_grant = RequiredGrant(grant=grant, scope="global")


def granted(permissions_header: str | None) -> set[str]:
    """String grants from the router's X-OpenHost-Permissions header (a json array of {grant, scope})."""
    if permissions_header is None:
        return set()
    entries = json.loads(permissions_header)
    return {e["grant"] for e in entries if isinstance(e.get("grant"), str)}


def require_grant(grant: str):  # type: ignore[no-untyped-def]
    """Guard for service routes. The router strips X-OpenHost-* headers from outside requests, so their presence means
    the router forwarded a service call from the consumer app it names."""

    def guard(connection: ASGIConnection, _: BaseRouteHandler) -> None:  # type: ignore[type-arg]
        if connection.headers.get("x-openhost-consumer-id") is None:
            raise PermissionRequired(grant)
        if grant not in granted(connection.headers.get("x-openhost-permissions")):
            raise PermissionRequired(grant)

    return guard
