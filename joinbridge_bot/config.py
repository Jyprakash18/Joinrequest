from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(slots=True)
class Settings:
    bot_token: str
    bot_username: str
    admin_user_ids: set[int]
    database_path: str
    default_delivery_mode: str
    auto_approve: bool



def _parse_admin_ids(raw: str) -> set[int]:
    values = set()
    for part in raw.split(','):
        part = part.strip()
        if not part:
            continue
        values.add(int(part))
    return values



def load_settings() -> Settings:
    load_dotenv()
    token = os.getenv("BOT_TOKEN", "").strip()
    username = os.getenv("BOT_USERNAME", "").strip().lstrip("@")
    admin_ids_raw = os.getenv("ADMIN_USER_IDS", "")
    db_path = os.getenv("DATABASE_PATH", "data/joinbridge.db").strip()
    delivery_mode = os.getenv("DEFAULT_DELIVERY_MODE", "copy").strip().lower()
    auto_approve = os.getenv("AUTO_APPROVE", "false").strip().lower() == "true"

    if not token:
        raise RuntimeError("BOT_TOKEN is required")
    if not username:
        raise RuntimeError("BOT_USERNAME is required")
    if delivery_mode not in {"copy", "forward"}:
        raise RuntimeError("DEFAULT_DELIVERY_MODE must be copy or forward")

    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    return Settings(
        bot_token=token,
        bot_username=username,
        admin_user_ids=_parse_admin_ids(admin_ids_raw),
        database_path=db_path,
        default_delivery_mode=delivery_mode,
        auto_approve=auto_approve,
    )
