from __future__ import annotations

import asyncio
import logging

from bot.core.bot import DuhBot
from bot.core.config import Settings
from bot.core.log import setup_logging

logger = logging.getLogger(__name__)


async def main() -> None:
    settings = Settings.load()
    setup_logging(settings.log_level, settings.log_dir)
    logger.info("Data dir: %s", settings.data_dir)

    bot = DuhBot(settings)
    async with bot:
        await bot.start(settings.discord_token)


def run() -> None:
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except RuntimeError as exc:
        raise SystemExit(f"configuration error: {exc}")


if __name__ == "__main__":
    run()
