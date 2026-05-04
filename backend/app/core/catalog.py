from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from backend.app.core.config import load_settings
from backend.app.models.scpi import Catalog


@lru_cache(maxsize=1)
def load_catalog() -> Catalog:
    settings = load_settings()
    path = Path(settings.catalog_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    return Catalog.model_validate(data)


def refresh_catalog_cache() -> None:
    load_catalog.cache_clear()



def catalog_summary() -> dict[str, object]:
    catalog = load_catalog()
    verified = sum(1 for cmd in catalog.commands if cmd.verified)
    return {
        "instrument": catalog.instrument,
        "version": catalog.version,
        "total_commands": len(catalog.commands),
        "verified_commands": verified,
    }



def is_command_known(command_line: str) -> bool:
    catalog = load_catalog()
    normalized = command_line.strip().upper()
    for entry in catalog.commands:
        key = entry.command.strip().upper()
        if normalized.startswith(key):
            return True
    return False
