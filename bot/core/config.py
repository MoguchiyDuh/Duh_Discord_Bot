from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        msg = f"Missing required environment variable: {name}"
        raise RuntimeError(msg)
    return value


def _optional(name: str) -> str | None:
    value = os.environ.get(name, "").strip()
    return value or None


@dataclass(frozen=True, slots=True)
class Settings:
    discord_token: str
    genius_api_key: str | None
    log_level: str
    data_dir: Path
    sync_guild_id: int | None
    pot_provider_url: str | None
    max_queue: int = 50
    max_search_results: int = 5
    max_playlist_fetch: int = 500
    idle_timeout: float = 300.0
    search_timeout: float = 60.0
    resolve_timeout: float = 30.0

    @property
    def cookies_path(self) -> Path:
        return self.data_dir / "cookies.txt"

    @property
    def log_dir(self) -> Path:
        return self.data_dir / "logs"

    @staticmethod
    def load() -> Settings:
        data_dir = Path(os.environ.get("DATA_DIR", "data")).resolve()
        sync_guild = _optional("SYNC_GUILD_ID")
        return Settings(
            discord_token=_require("DISCORD_TOKEN"),
            genius_api_key=_optional("GENIUS_API_KEY"),
            log_level=os.environ.get("LOG_LEVEL", "INFO").upper(),
            data_dir=data_dir,
            sync_guild_id=int(sync_guild) if sync_guild else None,
            pot_provider_url=_optional("POT_PROVIDER_URL"),
        )
