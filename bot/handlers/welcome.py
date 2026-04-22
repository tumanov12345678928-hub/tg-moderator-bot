"""Welcome messages and captcha for new members."""
from __future__ import annotations

import asyncio
import logging

from aiogram import F, Router
from aiogram.enums import ChatType, ParseMode
from aiogram.types import CallbackQuery, ChatMemberUpdated, ChatPermissions, Message

from .. import emojis as em
from ..db import Database
from ..keyboards import captcha_keyboard
from ..utils.permissions import bot_can_restrict, mention_html

log = logging.getLogger(__name__)
router = Router(name="welcome")

CAPTCHA_TIMEOUT_SECONDS = 120


DEFAULT_WELCOME = (
    "{emoji} Добро пожаловать, {mention}! Прочитай правила и веди себя адекватно."
)


def _format_welcome(template: str, mention: str) -> str:
    if not template:
        template = DEFAULT_WELCOME
    try:
        return template.format(mention=mention, emoji=em.E_PARTY)
    except (KeyError, IndexError):
        return DEFAULT_WELCOME.format(mention=mention, emoji=em.E_PARTY)


@router.message(F.new_chat_members, F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))
async def on_new_members(message: Message, db: Database) -> None:
    settings = await db.get_settings(message.chat.id)
    bot_user = await message.bot.me()

    for user in message.new_chat_members or []:
        if user.id == bot_user.id or user.is_bot:
            continue
        mention = mention_html(user.id, user.full_name or str(user.id))

        if settings.captcha_enabled and await bot_can_restrict(message.bot, message.chat.id):
            try:
                await message.bot.restrict_chat_member(
                    message.chat.id,
                    user.id,
                    permissions=ChatPermissions(can_send_messages=False),
                )
            except Exception as exc:
                log.warning("captcha restrict failed: %s", exc)
            await db.add_pending_captcha(message.chat.id, user.id)
            sent = await message.answer(
                f"{em.E_LOCK_CLOSED} {mention}, подтвердите что вы не бот в течение"
                f" {CAPTCHA_TIMEOUT_SECONDS // 60} минут, иначе будете исключены.",
                parse_mode=ParseMode.HTML,
                reply_markup=captcha_keyboard(message.chat.id, user.id),
            )
            asyncio.create_task(
                _captcha_timeout(message.bot, db, message.chat.id, user.id, sent.message_id)
            )
            continue

        if settings.welcome_enabled:
            await message.answer(
                _format_welcome(settings.welcome_text, mention),
                parse_mode=ParseMode.HTML,
            )


async def _captcha_timeout(bot, db: Database, chat_id: int, user_id: int, msg_id: int) -> None:
    await asyncio.sleep(CAPTCHA_TIMEOUT_SECONDS)
    if not await db.is_pending_captcha(chat_id, user_id):
        return
    await db.remove_pending_captcha(chat_id, user_id)
    try:
        await bot.ban_chat_member(chat_id, user_id)
        await bot.unban_chat_member(chat_id, user_id, only_if_banned=True)
    except Exception as exc:
        log.warning("captcha kick failed: %s", exc)
    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=msg_id,
            text=f"{em.E_CROSS} Пользователь не прошёл капчу и был исключён.",
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        pass


@router.callback_query(F.data.startswith("cap:ok:"))
async def cb_captcha(callback: CallbackQuery, db: Database) -> None:
    if callback.data is None or callback.from_user is None or callback.message is None:
        return
    parts = callback.data.split(":")
    if len(parts) != 4:
        await callback.answer()
        return
    try:
        chat_id = int(parts[2])
        user_id = int(parts[3])
    except ValueError:
        await callback.answer()
        return
    if callback.from_user.id != user_id:
        await callback.answer(
            f"{em.E_CROSS} Эта кнопка не для тебя", show_alert=True
        )
        return
    if not await db.is_pending_captcha(chat_id, user_id):
        await callback.answer()
        return
    await db.remove_pending_captcha(chat_id, user_id)
    try:
        await callback.bot.restrict_chat_member(
            chat_id,
            user_id,
            permissions=ChatPermissions(
                can_send_messages=True,
                can_send_audios=True,
                can_send_documents=True,
                can_send_photos=True,
                can_send_videos=True,
                can_send_video_notes=True,
                can_send_voice_notes=True,
                can_send_polls=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True,
                can_change_info=False,
                can_invite_users=True,
                can_pin_messages=False,
                can_manage_topics=False,
            ),
        )
    except Exception as exc:
        log.warning("captcha unmute failed: %s", exc)
    settings = await db.get_settings(chat_id)
    mention = mention_html(user_id, callback.from_user.full_name or str(user_id))
    text = _format_welcome(settings.welcome_text, mention) if settings.welcome_enabled else (
        f"{em.E_CHECK} {mention} прошёл капчу."
    )
    try:
        await callback.message.edit_text(text, parse_mode=ParseMode.HTML)
    except Exception:
        pass
    await callback.answer(f"{em.E_CHECK} Добро пожаловать!")


@router.chat_member()
async def on_chat_member_update(event: ChatMemberUpdated, db: Database) -> None:
    """Cleanup pending-captcha rows if a user leaves."""
    if event.new_chat_member.status in {"left", "kicked"}:
        await db.remove_pending_captcha(event.chat.id, event.new_chat_member.user.id)
