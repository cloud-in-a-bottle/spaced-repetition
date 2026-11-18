import os
from pathlib import Path

import attr


@attr.s(auto_attribs=True, frozen=True)
class Config:
    db_path: Path
    # Skip the owner check on /api, for running locally without the openhost router in front.
    assume_owner: bool
    # Persistent directory for big derived files (offline dictionaries). Openhost's app_data dir when deployed.
    data_dir: Path = Path(".local")
    # For calling other apps' services (the secrets service holds the Anthropic API key) through the openhost router.
    router_url: str | None = None
    app_token: str | None = None
    # Local development only: use this key directly instead of asking the secrets service.
    anthropic_api_key: str | None = None

    @staticmethod
    def from_env() -> "Config":
        db_path = Path(os.environ["BOTTLE_SQLITE_MAIN"])
        return Config(
            db_path=db_path,
            assume_owner=os.environ.get("SRS_ASSUME_OWNER") == "1",
            data_dir=Path(os.environ.get("BOTTLE_APP_DATA_DIR") or db_path.parent),
            router_url=os.environ.get("BOTTLE_ROUTER_URL"),
            app_token=os.environ.get("BOTTLE_APP_TOKEN"),
            anthropic_api_key=os.environ.get("SRS_ANTHROPIC_API_KEY"),
        )
