import os
from pathlib import Path

import attr


@attr.s(auto_attribs=True, frozen=True)
class Config:
    db_path: Path
    # Skip the owner check on /api, for running locally without the openhost router in front.
    assume_owner: bool

    @staticmethod
    def from_env() -> "Config":
        return Config(
            db_path=Path(os.environ["BOTTLE_SQLITE_MAIN"]),
            assume_owner=os.environ.get("SRS_ASSUME_OWNER") == "1",
        )
