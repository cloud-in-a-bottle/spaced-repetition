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
from srs.api.decks import deck_update
from srs.api.decks import decks_index
from srs.api.errors import EXCEPTION_HANDLERS
from srs.api.guards import owner_guard
from srs.api.items import card_suspend
from srs.api.items import item_create
from srs.api.items import item_delete
from srs.api.items import item_promote
from srs.api.items import item_save
from srs.api.items import item_show
from srs.api.items import items_index
from srs.api.reader import course_create
from srs.api.reader import course_delete
from srs.api.reader import course_save
from srs.api.reader import dictionaries_index
from srs.api.reader import dictionary_install
from srs.api.reader import library_index
from srs.api.reader import reading_analyze
from srs.api.reader import reading_marks
from srs.api.reader import reading_show
from srs.api.reader import reading_statuses
from srs.api.reader import reading_translate
from srs.api.reader import reading_word
from srs.api.reader import reading_words
from srs.api.reader import text_create
from srs.api.reader import text_delete
from srs.api.reader import text_mark_read
from srs.api.reader import text_save
from srs.api.schema import schema_show
from srs.api.settings import settings_save
from srs.api.settings import settings_show
from srs.api.sync import sync
from srs.api.templates import template_save
from srs.api.templates import templates_index
from srs.config import Config
from srs.core.bootstrap import bootstrap
from srs.db.database import Database
from srs.dictionary.store import Dictionaries
from srs.domain.clock import now_ms
from srs.service.errors import permission_required_handler
from srs.service.knowledge import lexemes_index
from srs.service.knowledge import lexemes_lookup
from srs.service.permissions import PermissionRequired
from srs.translate import Translator
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
    dictionaries = Dictionaries(config.data_dir)
    translator = Translator(config)
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
            item_promote,
            card_suspend,
            decks_index,
            deck_create,
            deck_update,
            deck_delete,
            templates_index,
            template_save,
            settings_show,
            settings_save,
            schema_show,
            bulk_import,
            library_index,
            course_create,
            course_save,
            course_delete,
            text_create,
            text_save,
            text_delete,
            text_mark_read,
            reading_show,
            reading_statuses,
            reading_word,
            reading_words,
            reading_marks,
            reading_analyze,
            reading_translate,
            dictionaries_index,
            dictionary_install,
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
        dependencies={
            "db": Provide(lambda: db, sync_to_thread=False),
            "dicts": Provide(lambda: dictionaries, sync_to_thread=False),
            "translator": Provide(lambda: translator, sync_to_thread=False),
        },
        state=State({"assume_owner": config.assume_owner}),
        on_shutdown=[lambda: db.close()],
        logging_config=LoggingConfig(log_exceptions="always"),
    )


def app() -> Litestar:
    """Factory for hypercorn (`srs.app:app()`)."""
    return create_app(Config.from_env())
