"""Admin settings panel (/settings) with inline toggles."""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.enums import ChatType, ParseMode
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from .. import emojis as em
from ..db import Database
from ..keyboards import settings_keyboard
from ..utils.permissions import is_chat_admin

log = logging.getLogger(__name__)
router = Router(name="settings")


class SettingsStates(StatesGroup):
    waiting_welcome_text = State()


def _panel_header() -> str:
    return f"<b>{em.E_SETTINGS} Настройки чата</b>\n"


@router.message(Command("settings"))
async def cmd_settings(message: Message, db: Database) -> None:
    if message.chat.type == ChatType.PRIVATE:
        await message.answer(
            f"{em.E_INFO} Команда доступна только в группах.",
            parse_mode=ParseMode.HTML,
        )
        return
    if message.from_user is None or not await is_chat_admin(
        message.bot, message.chat.id, message.from_user.id
    ):
        await message.reply(f"{em.E_CROSS} Настройки доступны только админам чата.")
        return
    settings = await db.get_settings(message.chat.id)
    await message.answer(
        _panel_header(),
        parse_mode=ParseMode.HTML,
        reply_markup=settings_keyboard(settings),
    )


async def _refresh_panel(callback: CallbackQuery, db: Database, chat_id: int) -> None:
    if callback.message is None:
        return
    settings = await db.get_settings(chat_id)
    try:
        await callback.message.edit_text(
            _panel_header(),
            parse_mode=ParseMode.HTML,
            reply_markup=settings_keyboard(settings),
        )
    except Exception:
        pass


@router.callback_query(F.data.startswith("st:toggle:"))
async def cb_toggle(callback: CallbackQuery, db: Database) -> None:
    if callback.data is None or callback.from_user is None:
        return
    parts = callback.data.split(":")
    if len(parts) != 4:
        await callback.answer()
        return
    _, _, field, chat_id_s = parts
    try:
        chat_id = int(chat_id_s)
    except ValueError:
        await callback.answer()
        return
    if not await is_chat_admin(callback.bot, chat_id, callback.from_user.id):
        await callback.answer(f"{em.E_CROSS} Только для админов", show_alert=True)
        return
    try:
        new_val = await db.toggle_setting(chat_id, field)
    except ValueError:
        await callback.answer()
        return
    await callback.answer(
        f"{em.E_CHECK if new_val else em.E_CROSS} "
        f"{'Включено' if new_val else 'Выключено'}"
    )
    await _refresh_panel(callback, db, chat_id)


_WARN_LIMIT_CYCLE = [3, 5, 7, 10]
_FLOOD_CYCLE = [(3, 5), (5, 5), (5, 10), (10, 10), (3, 3)]


@router.callback_query(F.data.startswith("st:cycle:"))
async def cb_cycle(callback: CallbackQuery, db: Database) -> None:
    if callback.data is None or callback.from_user is None:
        return
    parts = callback.data.split(":")
    if len(parts) != 4:
        await callback.answer()
        return
    _, _, field, chat_id_s = parts
    try:
        chat_id = int(chat_id_s)
    except ValueError:
        await callback.answer()
        return
    if not await is_chat_admin(callback.bot, chat_id, callback.from_user.id):
        await callback.answer(f"{em.E_CROSS} Только для админов", show_alert=True)
        return

    settings = await db.get_settings(chat_id)
    if field == "warn_limit":
        try:
            idx = _WARN_LIMIT_CYCLE.index(settings.warn_limit)
        except ValueError:
            idx = -1
        new_value = _WARN_LIMIT_CYCLE[(idx + 1) % len(_WARN_LIMIT_CYCLE)]
        await db.set_int(chat_id, "warn_limit", new_value)
        await callback.answer(f"{em.E_CHECK} Лимит варнов: {new_value}")
    elif field == "flood":
        current = (settings.flood_messages, settings.flood_window)
        try:
            idx = _FLOOD_CYCLE.index(current)
        except ValueError:
            idx = -1
        msgs, window = _FLOOD_CYCLE[(idx + 1) % len(_FLOOD_CYCLE)]
        await db.set_int(chat_id, "flood_messages", msgs)
        await db.set_int(chat_id, "flood_window", window)
        await callback.answer(f"{em.E_CHECK} Флуд: {msgs}/{window}c")
    else:
        await callback.answer()
        return
    await _refresh_panel(callback, db, chat_id)


@router.callback_query(F.data.startswith("st:words:"))
async def cb_words(callback: CallbackQuery, db: Database) -> None:
    if callback.data is None or callback.from_user is None:
        return
    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer()
        return
    try:
        chat_id = int(parts[2])
    except ValueError:
        await callback.answer()
        return
    if not await is_chat_admin(callback.bot, chat_id, callback.from_user.id):
        await callback.answer(f"{em.E_CROSS} Только для админов", show_alert=True)
        return
    words = await db.list_words(chat_id)
    if not words:
        await callback.answer(f"{em.E_INFO} Список пуст", show_alert=True)
        return
    shown = ", ".join(words[:50])
    if len(words) > 50:
        shown += f" … +{len(words) - 50}"
    await callback.answer(shown[:200], show_alert=True)


@router.callback_query(F.data.startswith("st:welcome_text:"))
async def cb_welcome_text(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    if callback.data is None or callback.from_user is None or callback.message is None:
        return
    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer()
        return
    try:
        chat_id = int(parts[2])
    except ValueError:
        await callback.answer()
        return
    if not await is_chat_admin(callback.bot, chat_id, callback.from_user.id):
        await callback.answer(f"{em.E_CROSS} Только для админов", show_alert=True)
        return
    await state.set_state(SettingsStates.waiting_welcome_text)
    await state.update_data(chat_id=chat_id, panel_msg_id=callback.message.message_id)
    await callback.message.answer(
        f"{em.E_WRITE or em.E_PENCIL} Отправь новый текст приветствия."
        " Используй <code>{mention}</code> для упоминания и <code>{emoji}</code> для премиум-смайла."
        " Напиши <code>сброс</code> чтобы вернуть дефолт.",
        parse_mode=ParseMode.HTML,
    )
    await callback.answer()


@router.message(SettingsStates.waiting_welcome_text)
async def set_welcome_text(message: Message, state: FSMContext, db: Database) -> None:
    data = await state.get_data()
    chat_id = data.get("chat_id")
    if chat_id is None or message.text is None:
        await state.clear()
        return
    text = message.text.strip()
    if text.lower() in {"сброс", "reset", "default"}:
        text = ""
    await db.set_welcome_text(int(chat_id), text)
    await state.clear()
    await message.reply(
        f"{em.E_CHECK} Текст приветствия обновлён."
        + (" Используется дефолтный." if not text else ""),
        parse_mode=ParseMode.HTML,
    )


@router.callback_query(F.data == "st:close")
async def cb_close(callback: CallbackQuery) -> None:
    if callback.message is None:
        return
    try:
        await callback.message.delete()
    except Exception:
        try:
            await callback.message.edit_text(f"{em.E_CHECK} Закрыто.")
        except Exception:
            pass
    await callback.answer()
