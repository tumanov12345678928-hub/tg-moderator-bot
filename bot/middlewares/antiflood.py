"""Anti-flood middleware.

Tracks the last few messages of each ``(chat_id, user_id)`` pair and
mutes offenders when they exceed the configured threshold within a
sliding window.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware, Bot
from aiogram.enums import ChatType
from aiogram.types import ChatPermissions, Message, TelegramObject

from .. import emojis as em
from ..db import Database
from ..utils.permissions import is_chat_admin, mention_html

log = logging.getLogger(__name__)

# Grace period: once a user is flagged we don't flag them again for this many seconds
_COOLDOWN = 30


class AntiFloodMiddleware(BaseMiddleware):
    def __init__(self) -> None:
        super().__init__()
        self._history: dict[tuple[int, int], deque[float]] = defaultdict(deque)
        self._last_trigger: dict[tuple[int, int], float] = {}
        self._lock = asyncio.Lock()

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not isinstance(event, Message):
            return await handler(event, data)
        if event.chat.type not in {ChatType.GROUP, ChatType.SUPERGROUP}:
            return await handler(event, data)
        if event.from_user is None or event.from_user.is_bot:
            return await handler(event, data)

        db: Database = data["db"]
        settings = await db.get_settings(event.chat.id)
        if not settings.antiflood_enabled:
            return await handler(event, data)

        bot: Bot = data["bot"]
        # Skip admins
        if await is_chat_admin(bot, event.chat.id, event.from_user.id):
            return await handler(event, data)

        key = (event.chat.id, event.from_user.id)
        now = time.monotonic()
        async with self._lock:
            history = self._history[key]
            history.append(now)
            cutoff = now - settings.flood_window
            while history and history[0] < cutoff:
                history.popleft()
            triggered = len(history) >= settings.flood_messages
            last = self._last_trigger.get(key, 0.0)
            in_cooldown = (now - last) < _COOLDOWN

        if triggered and not in_cooldown:
            self._last_trigger[key] = now
            await self._punish(bot, event, settings.flood_window)
            return  # Drop the offending message

        return await handler(event, data)

    async def _punish(self, bot: Bot, message: Message, window: int) -> None:
        assert message.from_user is not None
        until = datetime.now(timezone.utc) + timedelta(minutes=5)
        try:
            await bot.restrict_chat_member(
                message.chat.id,
                message.from_user.id,
                permissions=ChatPermissions(can_send_messages=False),
                until_date=until,
            )
        except Exception as exc:  # pragma: no cover - network
            log.warning("antiflood: failed to mute user: %s", exc)
            return
        mention = mention_html(
            message.from_user.id,
            message.from_user.full_name or str(message.from_user.id),
        )
        try:
            await message.answer(
                f"{em.E_LOCK_CLOSED} <b>Анти-флуд:</b> {mention} замьючен на 5 минут"
                f" за флуд ({window}с окно).",
            )
        except Exception:  # pragma: no cover
            pass
