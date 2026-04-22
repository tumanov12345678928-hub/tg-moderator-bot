"""Inject the :class:`Database` instance into every handler."""
from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from ..db import Database


class DatabaseMiddleware(BaseMiddleware):
    def __init__(self, db: Database) -> None:
        super().__init__()
        self.db = db

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        data["db"] = self.db
        return await handler(event, data)
