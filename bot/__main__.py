"""Entry point for the moderator bot."""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from .config import Config
from .db import Database
from .handlers import common, filters, moderation, settings, welcome
from .middlewares.antiflood import AntiFloodMiddleware
from .middlewares.db import DatabaseMiddleware


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    config = Config.from_env()
    db = Database(config.db_path)
    await db.connect()

    bot = Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    # Inject DB into handlers
    db_mw = DatabaseMiddleware(db)
    dp.message.middleware(db_mw)
    dp.callback_query.middleware(db_mw)
    dp.chat_member.middleware(db_mw)

    # Anti-flood on group messages (requires DB first)
    dp.message.middleware(AntiFloodMiddleware())

    # Routers: order matters. Specific commands/callbacks first, generic
    # text filter last.
    dp.include_router(common.router)
    dp.include_router(moderation.router)
    dp.include_router(settings.router)
    dp.include_router(welcome.router)
    dp.include_router(filters.router)

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(
            bot,
            allowed_updates=[
                "message",
                "edited_message",
                "callback_query",
                "chat_member",
                "my_chat_member",
            ],
        )
    finally:
        await db.close()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
