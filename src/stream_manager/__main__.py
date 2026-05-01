from __future__ import annotations

import asyncio
import logging
import sys
import uuid

from stream_manager import __version__
from stream_manager.config import BridgeConfig
from stream_manager.governance import NoOpGovernance
from stream_manager.message_bus import MessageBus
from stream_manager.router import Router


def main() -> int:
    config = BridgeConfig.from_env()
    logging.basicConfig(
        level=config.log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    log = logging.getLogger("stream_manager")
    log.info("StreamManager v%s starting (Spike A pipe)", __version__)

    bus = MessageBus(config.db_path)
    governance = NoOpGovernance(bus=bus)
    session_id = config.session_id or str(uuid.uuid4())
    router = Router(config, bus, governance, session_id)

    try:
        asyncio.run(router.run())
    except KeyboardInterrupt:
        log.info("shutdown requested")
    finally:
        log.info("bus stats at shutdown: %s", bus.stats())
        bus.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
