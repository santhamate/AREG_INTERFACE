from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    app_name: str = "AREG Control Interface API"
    app_version: str = "0.1.0"
    hislip_host: str = "127.0.0.1"
    hislip_port: int = 4880
    socket_host: str = "127.0.0.1"
    socket_port: int = 5025
    command_timeout_ms: int = 3000
    catalog_path: Path = Path("backend/catalogs/areg_commands.json")
    command_source_path: Path = Path(__file__).resolve().parents[3] / "backend" / "commands.yaml"



def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}



def load_settings() -> Settings:
    command_source_env = os.getenv("AREG_COMMAND_SOURCE_PATH")
    return Settings(
        hislip_host=os.getenv("AREG_HISLIP_HOST", "127.0.0.1"),
        hislip_port=int(os.getenv("AREG_HISLIP_PORT", "4880")),
        socket_host=os.getenv("AREG_SOCKET_HOST", "127.0.0.1"),
        socket_port=int(os.getenv("AREG_SOCKET_PORT", "5025")),
        command_timeout_ms=int(os.getenv("AREG_COMMAND_TIMEOUT_MS", "3000")),
        command_source_path=Path(command_source_env) if command_source_env else Path(__file__).resolve().parents[3] / "backend" / "commands.yaml",
    )
