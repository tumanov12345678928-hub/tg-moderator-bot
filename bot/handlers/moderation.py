"""Moderation commands: ban/unban, mute/unmute, kick, warn/unwarn, purge."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from aiogram import F, Router
from aiogram.enums import ChatType, ParseMode
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, ChatPermissions, Message

from .. import emojis as em
from ..db import Database
from ..keyboards import warn_keyboard
from ..utils.parse_time import format_duration, parse_duration
from ..utils.permissions import bot_can_restrict, is_chat_admin, mention_html

log = logging.getLogger(__name__)
router = Router(name="moderation")
router.message.filter(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))


async def _ensure_admin(message: Message) -> bool:
    if message.from_user is None:
        return False
    if not await is_chat_admin(message.bot, message.chat.id, message.from_user.id):
        await message.reply(f"{em.E_CROSS} Команда доступна только админам чата.")
        return False
    if not await bot_can_restrict(message.bot, message.chat.id):
        await message.reply(
            f"{em.E_LOCK_CLOSED} Мне нужны права администратора с возможностью "
            "ограничивать участников."
        )
        return False
    return True


def _target_from_reply(message: Message) -> tuple[int, str] | None:
    """Return (user_id, display) from a reply target, if any."""
    reply = message.reply_to_message
    if reply is None or reply.from_user is None:
        return None
    user = reply.from_user
    if user.is_bot:
        return None
    return user.id, user.full_name or str(user.id)


def _parse_args(command: CommandObject | None) -> tuple[str | None, str]:
    """Split command args into ``(first_token, rest)``."""
    args = (command.args or "").strip() if command else ""
    if not args:
        return None, ""
    parts = args.split(maxsplit=1)
    first = parts[0]
    rest = parts[1] if len(parts) > 1 else ""
    return first, rest


# -- ban ---------------------------------------------------------------
@router.message(Command("ban"))
async def cmd_ban(message: Message, command: CommandObject) -> None:
    if not await _ensure_admin(message):
        return
    target = _target_from_reply(message)
    first, rest = _parse_args(command)

    user_id: int | None = None
    display: str = ""
    until: datetime | None = None
    reason: str = ""

    if target is not None:
        user_id, display = target
        if first is not None:
            duration = parse_duration(first)
            if duration is not None:
                until = datetime.now(timezone.utc) + timedelta(seconds=duration)
                reason = rest
            else:
                reason = (first + (" " + rest if rest else "")).strip()
    else:
        if first is None:
            await message.reply(
                f"{em.E_INFO} Ответь на сообщение пользователя или укажи ID:"
                " <code>/ban 123456 [время] [причина]</code>",
                parse_mode=ParseMode.HTML,
            )
            return
        try:
            user_id = int(first)
        except ValueError:
            await message.reply(f"{em.E_CROSS} Не могу распознать ID пользователя.")
            return
        display = str(user_id)
        if rest:
            parts = rest.split(maxsplit=1)
            duration = parse_duration(parts[0])
            if duration is not None:
                until = datetime.now(timezone.utc) + timedelta(seconds=duration)
                reason = parts[1] if len(parts) > 1 else ""
            else:
                reason = rest

    if user_id is None:
        return

    try:
        await message.bot.ban_chat_member(
            message.chat.id,
            user_id,
            until_date=until,
        )
    except Exception as exc:
        await message.reply(f"{em.E_CROSS} Не удалось забанить: <code>{exc}</code>", parse_mode=ParseMode.HTML)
        return

    mention = mention_html(user_id, display)
    duration_str = format_duration(int((until - datetime.now(timezone.utc)).total_seconds())) if until else "навсегда"
    text = f"{em.E_LOCK_CLOSED} <b>Бан</b>: {mention} на <i>{duration_str}</i>"
    if reason:
        text += f"\n{em.E_PENCIL} Причина: {reason}"
    await message.answer(text, parse_mode=ParseMode.HTML)


# -- unban -------------------------------------------------------------
@router.message(Command("unban"))
async def cmd_unban(message: Message, command: CommandObject) -> None:
    if not await _ensure_admin(message):
        return
    target = _target_from_reply(message)
    first, _ = _parse_args(command)

    user_id: int | None = None
    if target is not None:
        user_id = target[0]
    elif first is not None:
        try:
            user_id = int(first)
        except ValueError:
            user_id = None
    if user_id is None:
        await message.reply(
            f"{em.E_INFO} Ответь на сообщение пользователя или укажи ID: "
            "<code>/unban 123456</code>",
            parse_mode=ParseMode.HTML,
        )
        return
    try:
        await message.bot.unban_chat_member(message.chat.id, user_id, only_if_banned=True)
    except Exception as exc:
        await message.reply(f"{em.E_CROSS} Не удалось разбанить: <code>{exc}</code>", parse_mode=ParseMode.HTML)
        return
    await message.answer(
        f"{em.E_LOCK_OPEN} <b>Разбан</b>: {mention_html(user_id, str(user_id))}",
        parse_mode=ParseMode.HTML,
    )


# -- mute --------------------------------------------------------------
@router.message(Command("mute"))
async def cmd_mute(message: Message, command: CommandObject) -> None:
    if not await _ensure_admin(message):
        return
    target = _target_from_reply(message)
    if target is None:
        await message.reply(f"{em.E_INFO} Ответь на сообщение пользователя, которого нужно замьютить.")
        return
    user_id, display = target

    first, rest = _parse_args(command)
    until: datetime | None = None
    reason = ""
    if first is not None:
        duration = parse_duration(first)
        if duration is not None:
            until = datetime.now(timezone.utc) + timedelta(seconds=duration)
            reason = rest
        else:
            reason = (first + (" " + rest if rest else "")).strip()

    try:
        await message.bot.restrict_chat_member(
            message.chat.id,
            user_id,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=until,
        )
    except Exception as exc:
        await message.reply(f"{em.E_CROSS} Не удалось замьютить: <code>{exc}</code>", parse_mode=ParseMode.HTML)
        return

    duration_str = (
        format_duration(int((until - datetime.now(timezone.utc)).total_seconds()))
        if until
        else "бессрочно"
    )
    text = f"{em.E_LOCK_CLOSED} <b>Мьют</b>: {mention_html(user_id, display)} на <i>{duration_str}</i>"
    if reason:
        text += f"\n{em.E_PENCIL} Причина: {reason}"
    await message.answer(text, parse_mode=ParseMode.HTML)


# -- unmute ------------------------------------------------------------
_UNMUTE_PERMS = ChatPermissions(
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
)


@router.message(Command("unmute"))
async def cmd_unmute(message: Message, command: CommandObject) -> None:
    if not await _ensure_admin(message):
        return
    target = _target_from_reply(message)
    first, _ = _parse_args(command)
    user_id: int | None
    if target is not None:
        user_id = target[0]
    elif first is not None:
        try:
            user_id = int(first)
        except ValueError:
            user_id = None
    else:
        user_id = None
    if user_id is None:
        await message.reply(f"{em.E_INFO} Ответь на сообщение пользователя или укажи ID.")
        return
    try:
        await message.bot.restrict_chat_member(
            message.chat.id, user_id, permissions=_UNMUTE_PERMS
        )
    except Exception as exc:
        await message.reply(f"{em.E_CROSS} Не удалось снять мьют: <code>{exc}</code>", parse_mode=ParseMode.HTML)
        return
    await message.answer(
        f"{em.E_LOCK_OPEN} <b>Мьют снят</b>: {mention_html(user_id, str(user_id))}",
        parse_mode=ParseMode.HTML,
    )


# -- kick --------------------------------------------------------------
@router.message(Command("kick"))
async def cmd_kick(message: Message, command: CommandObject) -> None:
    if not await _ensure_admin(message):
        return
    target = _target_from_reply(message)
    if target is None:
        await message.reply(f"{em.E_INFO} Ответь на сообщение пользователя.")
        return
    user_id, display = target
    reason = (command.args or "").strip() if command else ""
    try:
        await message.bot.ban_chat_member(message.chat.id, user_id)
        await message.bot.unban_chat_member(message.chat.id, user_id, only_if_banned=True)
    except Exception as exc:
        await message.reply(f"{em.E_CROSS} Не удалось кикнуть: <code>{exc}</code>", parse_mode=ParseMode.HTML)
        return
    text = f"{em.E_PERSON_CROSS} <b>Кик</b>: {mention_html(user_id, display)}"
    if reason:
        text += f"\n{em.E_PENCIL} Причина: {reason}"
    await message.answer(text, parse_mode=ParseMode.HTML)


# -- warn --------------------------------------------------------------
@router.message(Command("warn"))
async def cmd_warn(message: Message, command: CommandObject, db: Database) -> None:
    if not await _ensure_admin(message):
        return
    target = _target_from_reply(message)
    if target is None:
        await message.reply(f"{em.E_INFO} Ответь на сообщение пользователя.")
        return
    user_id, display = target
    reason = (command.args or "").strip() if command else ""

    count = await db.add_warning(message.chat.id, user_id, message.from_user.id if message.from_user else 0, reason)
    settings = await db.get_settings(message.chat.id)
    mention = mention_html(user_id, display)

    if count >= settings.warn_limit:
        try:
            await message.bot.ban_chat_member(message.chat.id, user_id)
        except Exception as exc:
            await message.reply(
                f"{em.E_CROSS} Варн выдан, но не получилось забанить: <code>{exc}</code>",
                parse_mode=ParseMode.HTML,
            )
            return
        await db.clear_warnings(message.chat.id, user_id)
        text = (
            f"{em.E_LOCK_CLOSED} <b>Бан</b>: {mention} достиг лимита варнов"
            f" ({count}/{settings.warn_limit})."
        )
        if reason:
            text += f"\n{em.E_PENCIL} Последняя причина: {reason}"
        await message.answer(text, parse_mode=ParseMode.HTML)
        return

    text = f"{em.E_CROSS} <b>Варн</b> {count}/{settings.warn_limit} для {mention}"
    if reason:
        text += f"\n{em.E_PENCIL} Причина: {reason}"
    await message.answer(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=warn_keyboard(message.chat.id, user_id),
    )


@router.message(Command("unwarn"))
async def cmd_unwarn(message: Message, db: Database) -> None:
    if not await _ensure_admin(message):
        return
    target = _target_from_reply(message)
    if target is None:
        await message.reply(f"{em.E_INFO} Ответь на сообщение пользователя.")
        return
    user_id, display = target
    popped = await db.pop_last_warning(message.chat.id, user_id)
    if not popped:
        await message.reply(f"{em.E_INFO} У пользователя нет варнов.")
        return
    count = await db.count_warnings(message.chat.id, user_id)
    await message.answer(
        f"{em.E_CHECK} Снят один варн у {mention_html(user_id, display)}."
        f" Осталось: <b>{count}</b>.",
        parse_mode=ParseMode.HTML,
    )


@router.message(Command("warns"))
async def cmd_warns(message: Message, db: Database) -> None:
    target = _target_from_reply(message)
    if target is None and message.from_user is not None:
        user_id = message.from_user.id
        display = message.from_user.full_name
    elif target is not None:
        user_id, display = target
    else:
        await message.reply(f"{em.E_INFO} Ответь на сообщение пользователя.")
        return
    count = await db.count_warnings(message.chat.id, user_id)
    settings = await db.get_settings(message.chat.id)
    await message.reply(
        f"{em.E_STATS} Варнов у {mention_html(user_id, display)}:"
        f" <b>{count}/{settings.warn_limit}</b>",
        parse_mode=ParseMode.HTML,
    )


# -- warn inline callbacks --------------------------------------------
@router.callback_query(F.data.startswith("warn:"))
async def cb_warn(callback: CallbackQuery, db: Database) -> None:
    if callback.data is None or callback.from_user is None or callback.message is None:
        return
    parts = callback.data.split(":")
    if len(parts) != 4:
        await callback.answer()
        return
    _, action, chat_id_s, user_id_s = parts
    try:
        chat_id = int(chat_id_s)
        user_id = int(user_id_s)
    except ValueError:
        await callback.answer()
        return
    if not await is_chat_admin(callback.bot, chat_id, callback.from_user.id):
        await callback.answer(f"{em.E_CROSS} Только для админов", show_alert=True)
        return
    if action == "pop":
        ok = await db.pop_last_warning(chat_id, user_id)
        if not ok:
            await callback.answer(f"{em.E_INFO} Варнов уже нет", show_alert=True)
            return
        count = await db.count_warnings(chat_id, user_id)
        await callback.answer(f"{em.E_CHECK} Снят 1 варн. Осталось: {count}", show_alert=True)
    elif action == "clear":
        removed = await db.clear_warnings(chat_id, user_id)
        await callback.answer(f"{em.E_TRASH} Снято варнов: {removed}", show_alert=True)
    else:
        await callback.answer()


# -- purge -------------------------------------------------------------
@router.message(Command("purge"))
async def cmd_purge(message: Message) -> None:
    if not await _ensure_admin(message):
        return
    if message.reply_to_message is None:
        await message.reply(
            f"{em.E_INFO} Ответь на сообщение, начиная с которого нужно удалить."
        )
        return
    start_id = message.reply_to_message.message_id
    end_id = message.message_id
    if end_id <= start_id:
        return
    ids = list(range(start_id, end_id + 1))
    # Telegram deleteMessages allows up to 100 messages per call
    batch = 100
    removed = 0
    for i in range(0, len(ids), batch):
        chunk = ids[i : i + batch]
        try:
            await message.bot.delete_messages(message.chat.id, chunk)
            removed += len(chunk)
        except Exception as exc:
            log.warning("purge: delete_messages failed: %s", exc)
            for mid in chunk:
                try:
                    await message.bot.delete_message(message.chat.id, mid)
                    removed += 1
                except Exception:
                    continue
    try:
        await message.answer(
            f"{em.E_TRASH} Удалено сообщений: <b>{removed}</b>",
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        pass
