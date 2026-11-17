from litestar import post
from litestar.params import JSONBody

from srs.api.deps import Db
from srs.core.bulk_import import ImportBundle
from srs.core.bulk_import import ImportResult
from srs.core.bulk_import import import_bundle
from srs.domain.clock import now_ms
from srs.repo.changes import next_seq


@post("/import", sync_to_thread=True, request_max_body_size=200 * 1024 * 1024)
def bulk_import(db: Db, data: JSONBody[ImportBundle]) -> ImportResult:
    with db.transaction() as conn:
        return import_bundle(conn, data, next_seq(conn), now_ms())
