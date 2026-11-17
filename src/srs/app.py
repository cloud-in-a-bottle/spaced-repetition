import attr
from litestar import Litestar
from litestar import Router
from litestar import get
from litestar.datastructures import State
from litestar.di import Provide
from litestar.logging import LoggingConfig

from srs.api.bulk_import import bulk_import
from srs.api.decks import deck_create
from srs.api.decks import deck_delete
from srs.api.decks import deck_rename
from srs.api.decks import decks_index
from srs.api.errors import EXCEPTION_HANDLERS
from srs.api.guards import owner_guard
from srs.api.items import card_suspend
from srs.api.items import item_create
from srs.api.items import item_delete
from srs.api.items import item_save
from srs.api.items import item_show
from srs.api.items import items_index
from srs.api.schema import schema_show
from srs.api.settings import settings_save
from srs.api.settings import settings_show
from srs.api.sync import sync
from srs.api.templates import template_save
from srs.api.templates import templates_index
from srs.config import Config
from srs.core.bootstrap import bootstrap
from srs.db.database import Database
from srs.domain.clock import now_ms
from srs.service.errors import permission_required_handler
from srs.service.knowledge import lexemes_index
from srs.service.knowledge import lexemes_lookup
from srs.service.permissions import PermissionRequired
from srs.web.static_files import index
from srs.web.static_files import service_worker
from srs.web.static_files import static_router
from srs.web.static_files import web_manifest


@attr.s(auto_attribs=True, frozen=True)
class HealthStatus:
    status: str


@get("/health", sync_to_thread=False)
def health() -> HealthStatus:
    return HealthStatus(status="ok")


def create_app(config: Config) -> Litestar:
    db = Database(config.db_path)
    with db.transaction() as conn:
        bootstrap(conn, now_ms())

    owner_api = Router(
        path="/api",
        guards=[owner_guard],
        route_handlers=[
            sync,
            items_index,
            item_show,
            item_create,
            item_save,
            item_delete,
            card_suspend,
            decks_index,
            deck_create,
            deck_rename,
            deck_delete,
            templates_index,
            template_save,
            settings_show,
            settings_save,
            schema_show,
            bulk_import,
        ],
    )
    # Cross-app service (see services/srs/openapi.yaml), mounted where cloudinabottle.toml's provides.endpoint says.
    service = Router(
        path="/service",
        route_handlers=[lexemes_lookup, lexemes_index],
        exception_handlers={PermissionRequired: permission_required_handler},
    )
    return Litestar(
        route_handlers=[health, index, service_worker, web_manifest, static_router, owner_api, service],
        exception_handlers=EXCEPTION_HANDLERS,
        dependencies={"db": Provide(lambda: db, sync_to_thread=False)},
        state=State({"assume_owner": config.assume_owner}),
        on_shutdown=[lambda: db.close()],
        logging_config=LoggingConfig(log_exceptions="always"),
    )


def app() -> Litestar:
    """Factory for hypercorn (`srs.app:app()`)."""
    return create_app(Config.from_env())
