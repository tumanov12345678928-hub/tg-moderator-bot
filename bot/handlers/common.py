"""Generic /start, /help, and helper command handlers."""
from __future__ import annotations

from aiogram import Router
from aiogram.enums import ChatType, ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from .. import emojis as em
from ..keyboards import main_reply_keyboard

router = Router(name="common")


HELP_TEXT = (
    f"<b>{em.E_BOT} Бот-модератор</b>\n\n"
    "Добавь меня в чат и выдай права администратора с возможностью блокировать участников.\n\n"
    f"<b>{em.E_MEGAPHONE} Команды для админов чата:</b>\n"
    "• <code>/ban</code> [время] [причина] — забанить (ответом на сообщение)\n"
    "• <code>/unban</code> — разбанить (ответом или по ID)\n"
    "• <code>/mute</code> [время] [причина] — замьютить\n"
    "• <code>/unmute</code> — снять мьют\n"
    "• <code>/kick</code> [причина] — выгнать из чата\n"
    "• <code>/warn</code> [причина] — выдать варн (3 варна → бан)\n"
    "• <code>/unwarn</code> — снять один варн\n"
    "• <code>/warns</code> — показать количество варнов\n"
    "• <code>/purge</code> — удалить сообщения от указанного до текущего\n"
    "• <code>/addword</code>, <code>/delword</code>, <code>/words</code> — фильтр слов\n"
    "• <code>/settings</code> — панель настроек\n\n"
    f"<b>{em.E_CLOCK} Формат времени:</b> <code>30</code> (сек), <code>10m</code>, "
    "<code>1h30m</code>, <code>2d</code>, <code>1w</code>.\n"
)


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    if message.chat.type == ChatType.PRIVATE:
        await message.answer(
            f"<b>{em.E_BOT} Привет!</b> Я — бот-модератор с премиум-эмодзи.\n\n"
            f"Добавь меня в чат и выдай права админа. Используй {em.E_INFO} "
            "<code>/help</code> для списка команд.",
            parse_mode=ParseMode.HTML,
            reply_markup=main_reply_keyboard(),
        )
    else:
        await message.answer(
            f"{em.E_BOT} Я онлайн. Админы — используйте <code>/settings</code> "
            f"для панели управления, <code>/help</code> для списка команд.",
            parse_mode=ParseMode.HTML,
        )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP_TEXT, parse_mode=ParseMode.HTML)


@router.message(lambda m: m.text in {"Помощь", "Помощь ℹ"})
async def btn_help(message: Message) -> None:
    await cmd_help(message)
