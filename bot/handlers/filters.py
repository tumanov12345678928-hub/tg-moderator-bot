"""Forbidden words and anti-spam filter."""
from __future__ import annotations

import logging
import re

from aiogram import F, Router
from aiogram.enums import ChatType, ParseMode
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from .. import emojis as em
from ..db import Database
from ..utils.permissions import is_chat_admin

log = logging.getLogger(__name__)
router = Router(name="filters")
router.message.filter(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))


_URL_RE = re.compile(r"https?://\S+|t\.me/\S+", re.IGNORECASE)
_MENTION_RE = re.compile(r"@[A-Za-z0-9_]{5,}")


async def _is_admin(message: Message) -> bool:
    if message.from_user is None:
        return False
    return await is_chat_admin(message.bot, message.chat.id, message.from_user.id)


# -- word management ---------------------------------------------------
@router.message(Command("addword"))
async def cmd_addword(message: Message, command: CommandObject, db: Database) -> None:
    if not await _is_admin(message):
        return
    if not command.args:
        await message.reply(f"{em.E_INFO} Использование: <code>/addword слово</code>", parse_mode=ParseMode.HTML)
        return
    for word in command.args.split():
        await db.add_word(message.chat.id, word)
    await message.reply(f"{em.E_CHECK} Добавлено в фильтр.")


@router.message(Command("delword"))
async def cmd_delword(message: Message, command: CommandObject, db: Database) -> None:
    if not await _is_admin(message):
        return
    if not command.args:
        await message.reply(f"{em.E_INFO} Использование: <code>/delword слово</code>", parse_mode=ParseMode.HTML)
        return
    removed_any = False
    for word in command.args.split():
        if await db.remove_word(message.chat.id, word):
            removed_any = True
    await message.reply(
        f"{em.E_CHECK} Удалено из фильтра." if removed_any else f"{em.E_INFO} Слов не найдено."
    )


@router.message(Command("words"))
async def cmd_words(message: Message, db: Database) -> None:
    if not await _is_admin(message):
        return
    words = await db.list_words(message.chat.id)
    if not words:
        await message.reply(f"{em.E_INFO} Список запрещённых слов пуст.")
        return
    shown = ", ".join(f"<code>{w}</code>" for w in words[:100])
    extra = f"\n… и ещё {len(words) - 100}" if len(words) > 100 else ""
    await message.reply(
        f"{em.E_CODE} <b>Запрещённые слова ({len(words)}):</b>\n{shown}{extra}",
        parse_mode=ParseMode.HTML,
    )


# -- filter handlers ---------------------------------------------------
def _contains_forbidden(text: str, words: list[str]) -> str | None:
    if not words or not text:
        return None
    lowered = text.lower()
    for word in words:
        if word and word in lowered:
            return word
    return None


@router.message(F.text | F.caption)
async def filter_messages(message: Message, db: Database) -> None:
    if message.from_user is None or message.from_user.is_bot:
        return
    if await is_chat_admin(message.bot, message.chat.id, message.from_user.id):
        return

    settings = await db.get_settings(message.chat.id)
    text = (message.text or message.caption or "").strip()
    if not text:
        return

    if settings.words_enabled:
        words = await db.list_words(message.chat.id)
        match = _contains_forbidden(text, words)
        if match is not None:
            try:
                await message.delete()
            except Exception:
                pass
            try:
                await message.answer(
                    f"{em.E_TRASH} Сообщение удалено: содержит запрещённое слово"
                    f" <code>{match}</code>.",
                    parse_mode=ParseMode.HTML,
                )
            except Exception:
                pass
            return

    if settings.antispam_enabled:
        # Heuristic: short-lived members posting links/mentions get their message deleted.
        has_link = bool(_URL_RE.search(text))
        has_mention = bool(_MENTION_RE.search(text))
        if has_link or has_mention:
            try:
                member = await message.bot.get_chat_member(message.chat.id, message.from_user.id)
            except Exception:
                member = None
            # Telegram doesn't expose join date on ChatMember; use a simple heuristic:
            # if the user has no profile photo + link/mention + very short text, drop it.
            is_suspicious = has_link and len(text) < 80
            if member is not None and is_suspicious:
                try:
                    await message.delete()
                except Exception:
                    pass
                try:
                    await message.answer(
                        f"{em.E_MEGAPHONE} Анти-спам: сообщение с ссылкой удалено."
                        " Напишите админам, если это ошибка.",
                    )
                except Exception:
                    pass
