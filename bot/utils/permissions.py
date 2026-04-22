"""Helpers for permission checks."""
from __future__ import annotations

from aiogram import Bot
from aiogram.enums import ChatMemberStatus
from aiogram.types import ChatMember

_ADMIN_STATUSES = {ChatMemberStatus.CREATOR, ChatMemberStatus.ADMINISTRATOR}


async def get_member(bot: Bot, chat_id: int, user_id: int) -> ChatMember | None:
    try:
        return await bot.get_chat_member(chat_id, user_id)
    except Exception:
        return None


async def is_chat_admin(bot: Bot, chat_id: int, user_id: int) -> bool:
    member = await get_member(bot, chat_id, user_id)
    if member is None:
        return False
    return member.status in _ADMIN_STATUSES


async def bot_can_restrict(bot: Bot, chat_id: int) -> bool:
    me = await bot.me()
    member = await get_member(bot, chat_id, me.id)
    if member is None or member.status != ChatMemberStatus.ADMINISTRATOR:
        return False
    return bool(getattr(member, "can_restrict_members", False))


def mention_html(user_id: int, name: str) -> str:
    safe = (
        name.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    ) or f"id{user_id}"
    return f'<a href="tg://user?id={user_id}">{safe}</a>'
