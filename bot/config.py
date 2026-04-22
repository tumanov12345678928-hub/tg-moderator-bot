from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv


def _parse_ids(raw: str | None) -> list[int]:
    if not raw:
        return []
    result: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            result.append(int(part))
        except ValueError:
            continue
    return result


@dataclass(slots=True)
class Config:
    bot_token: str
    owner_ids: list[int] = field(default_factory=list)
    db_path: str = "moderator.db"

    @classmethod
    def from_env(cls) -> "Config":
        load_dotenv()
        token = os.getenv("BOT_TOKEN", "").strip()
        if not token:
            raise RuntimeError("BOT_TOKEN is not set. Copy .env.example to .env and fill it in.")
        return cls(
            bot_token=token,
            owner_ids=_parse_ids(os.getenv("OWNER_IDS")),
            db_path=os.getenv("DB_PATH", "moderator.db").strip() or "moderator.db",
        )
