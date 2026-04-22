"""Inline + reply keyboards with premium emoji icons.

All buttons attach ``icon_custom_emoji_id`` with a premium emoji ID
instead of putting a plain unicode emoji into the button text.
"""
from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from . import emojis as em
from .db import ChatSettings


def _ib(text: str, *, icon: str, url: str | None = None, callback_data: str | None = None) -> InlineKeyboardButton:
    """Build an inline button with a premium icon."""
    kwargs: dict[str, str] = {"text": text, "icon_custom_emoji_id": icon}
    if url is not None:
        kwargs["url"] = url
    if callback_data is not None:
        kwargs["callback_data"] = callback_data
    return InlineKeyboardButton(**kwargs)  # type: ignore[arg-type]


def _rb(text: str, *, icon: str | None = None) -> KeyboardButton:
    kwargs: dict[str, str] = {"text": text}
    if icon is not None:
        kwargs["icon_custom_emoji_id"] = icon
    return KeyboardButton(**kwargs)  # type: ignore[arg-type]


def main_reply_keyboard() -> ReplyKeyboardMarkup:
    """Main reply keyboard for private chats with the bot."""
    return ReplyKeyboardMarkup(
        resize_keyboard=True,
        keyboard=[
            [
                _rb("Помощь", icon=em.INFO),
                _rb("Настройки", icon=em.SETTINGS),
            ],
            [
                _rb("Статус", icon=em.STATS),
            ],
        ],
    )


def _toggle_label(name: str, enabled: bool) -> str:
    return f"{name}: {'ВКЛ' if enabled else 'ВЫКЛ'}"


def settings_keyboard(s: ChatSettings) -> InlineKeyboardMarkup:
    """Admin settings panel for a chat."""
    rows = [
        [
            _ib(
                _toggle_label("Приветствие", s.welcome_enabled),
                icon=em.PARTY,
                callback_data=f"st:toggle:welcome_enabled:{s.chat_id}",
            ),
            _ib(
                _toggle_label("Капча", s.captcha_enabled),
                icon=em.LOCK_CLOSED,
                callback_data=f"st:toggle:captcha_enabled:{s.chat_id}",
            ),
        ],
        [
            _ib(
                _toggle_label("Анти-флуд", s.antiflood_enabled),
                icon=em.LOADING,
                callback_data=f"st:toggle:antiflood_enabled:{s.chat_id}",
            ),
            _ib(
                _toggle_label("Анти-спам", s.antispam_enabled),
                icon=em.MEGAPHONE,
                callback_data=f"st:toggle:antispam_enabled:{s.chat_id}",
            ),
        ],
        [
            _ib(
                _toggle_label("Фильтр слов", s.words_enabled),
                icon=em.CODE,
                callback_data=f"st:toggle:words_enabled:{s.chat_id}",
            ),
        ],
        [
            _ib(
                f"Лимит варнов: {s.warn_limit}",
                icon=em.TAG,
                callback_data=f"st:cycle:warn_limit:{s.chat_id}",
            ),
            _ib(
                f"Флуд: {s.flood_messages}/{s.flood_window}c",
                icon=em.CLOCK,
                callback_data=f"st:cycle:flood:{s.chat_id}",
            ),
        ],
        [
            _ib(
                "Список слов",
                icon=em.FILE,
                callback_data=f"st:words:{s.chat_id}",
            ),
            _ib(
                "Текст приветствия",
                icon=em.WRITE,
                callback_data=f"st:welcome_text:{s.chat_id}",
            ),
        ],
        [
            _ib("Закрыть", icon=em.CROSS, callback_data="st:close"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def captcha_keyboard(chat_id: int, user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            _ib(
                "Я не бот",
                icon=em.CHECK,
                callback_data=f"cap:ok:{chat_id}:{user_id}",
            )
        ]]
    )


def warn_keyboard(chat_id: int, user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_ib(
                "Снять 1 варн",
                icon=em.CHECK,
                callback_data=f"warn:pop:{chat_id}:{user_id}",
            )],
            [_ib(
                "Снять все варны",
                icon=em.TRASH,
                callback_data=f"warn:clear:{chat_id}:{user_id}",
            )],
        ]
    )


def confirm_keyboard(action: str, chat_id: int, user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            _ib(
                "Подтвердить",
                icon=em.CHECK,
                callback_data=f"cf:yes:{action}:{chat_id}:{user_id}",
            ),
            _ib("Отмена", icon=em.CROSS, callback_data="cf:no"),
        ]]
    )
