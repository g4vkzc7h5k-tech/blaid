"""
Blade - entry point.

Startup sequence:
  Load environment -> configure logging -> create bot -> init database
  -> load cogs (via setup_hook) -> connect to Discord -> on_ready.
"""

from __future__ import annotations

import asyncio
import logging
import sys

from config import config, validate_config
from core.bot import Blade
from database.database import close_database, init_database


def configure_logging() -> None:
    level = logging.DEBUG if config.debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


async def main() -> None:
    configure_logging()
    log = logging.getLogger("blade.main")

    try:
        validate_config()
    except RuntimeError as exc:
        log.error(str(exc))
        sys.exit(1)

    log.info("Blade starting...")

    try:
        await init_database()
    except Exception:
        log.exception("Database initialization failed. Blade cannot start.")
        sys.exit(1)

    bot = Blade()

    try:
        async with bot:
            await bot.start(config.discord_token)
    except KeyboardInterrupt:
        pass
    finally:
        await close_database()
        log.info("Blade shut down cleanly.")


if __name__ == "__main__":
    asyncio.run(main())
