from litestar.connection import ASGIConnection
from litestar.exceptions import NotAuthorizedException
from litestar.handlers.base import BaseRouteHandler


def owner_guard(connection: ASGIConnection, _: BaseRouteHandler) -> None:  # type: ignore[type-arg]
    """The openhost router already blocks non-owners from the app, but it also forwards cross-app service calls here
    (without an owner session). This makes sure only the owner reaches /api, whatever path a service call names."""
    if connection.app.state["assume_owner"]:
        return
    if connection.headers.get("x-openhost-is-owner") != "true":
        raise NotAuthorizedException("owner session required")
