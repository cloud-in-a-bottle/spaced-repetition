from litestar.di import NamedDependency

from srs.db.database import Database

# Handlers declare `db: Db` to get the app's database (provided in srs.app).
Db = NamedDependency[Database]
