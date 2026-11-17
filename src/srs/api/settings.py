from litestar import get
from litestar import put
from litestar.params import JSONBody

from srs.api.deps import Db
from srs.core.settings import update_settings
from srs.domain.settings import Settings
from srs.repo.changes import next_seq
from srs.repo.settings import load_settings


@get("/settings", sync_to_thread=True)
def settings_show(db: Db) -> Settings:
    with db.transaction() as conn:
        return load_settings(conn)


@put("/settings", sync_to_thread=True)
def settings_save(db: Db, data: JSONBody[Settings]) -> Settings:
    with db.transaction() as conn:
        update_settings(conn, data, next_seq(conn))
        return load_settings(conn)
