from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class BridgeConfig:
    host: str = "127.0.0.1"
    desktop_port: int = 8765
    cli_port: int = 8766
    db_path: str = ".bridge/adaptive_bridge.db"
    log_level: str = "INFO"
    session_id: str | None = None

    @classmethod
    def from_env(cls) -> BridgeConfig:
        return cls(
            host=os.getenv("BRIDGE_HOST", "127.0.0.1"),
            desktop_port=int(os.getenv("BRIDGE_DESKTOP_PORT", "8765")),
            cli_port=int(os.getenv("BRIDGE_CLI_PORT", "8766")),
            db_path=os.getenv("BRIDGE_DB_PATH", ".bridge/adaptive_bridge.db"),
            log_level=os.getenv("BRIDGE_LOG_LEVEL", "INFO"),
            session_id=os.getenv("BRIDGE_SESSION_ID"),
        )
