from litestar.di import NamedDependency

from srs.db.database import Database
from srs.dictionary.store import Dictionaries
from srs.translate import Translator

# Handlers declare these to get the app's shared objects (provided in srs.app).
Db = NamedDependency[Database]
Dicts = NamedDependency[Dictionaries]
Translations = NamedDependency[Translator]
