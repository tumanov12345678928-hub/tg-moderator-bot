"""Async SQLite storage layer."""
from __future__ import annotations

import time
from dataclasses import dataclass

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS chat_settings (
    chat_id           INTEGER PRIMARY KEY,
    welcome_enabled   INTEGER NOT NULL DEFAULT 1,
    captcha_enabled   INTEGER NOT NULL DEFAULT 0,
    antiflood_enabled INTEGER NOT NULL DEFAULT 1,
    antispam_enabled  INTEGER NOT NULL DEFAULT 1,
    words_enabled     INTEGER NOT NULL DEFAULT 1,
    warn_limit        INTEGER NOT NULL DEFAULT 3,
    flood_messages    INTEGER NOT NULL DEFAULT 5,
    flood_window      INTEGER NOT NULL DEFAULT 5,
    welcome_text      TEXT    NOT NULL DEFAULT '',
    updated_at        INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS warnings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id     INTEGER NOT NULL,
    user_id     INTEGER NOT NULL,
    admin_id    INTEGER NOT NULL,
    reason      TEXT    NOT NULL DEFAULT '',
    created_at  INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_warnings_chat_user ON warnings(chat_id, user_id);

CREATE TABLE IF NOT EXISTS forbidden_words (
    chat_id     INTEGER NOT NULL,
    word        TEXT    NOT NULL,
    PRIMARY KEY (chat_id, word)
);

CREATE TABLE IF NOT EXISTS pending_captcha (
    chat_id     INTEGER NOT NULL,
    user_id     INTEGER NOT NULL,
    joined_at   INTEGER NOT NULL,
    PRIMARY KEY (chat_id, user_id)
);
"""


@dataclass(slots=True)
class ChatSettings:
    chat_id: int
    welcome_enabled: bool = True
    captcha_enabled: bool = False
    antiflood_enabled: bool = True
    antispam_enabled: bool = True
    words_enabled: bool = True
    warn_limit: int = 3
    flood_messages: int = 5
    flood_window: int = 5
    welcome_text: str = ""


def _row_to_settings(row: aiosqlite.Row | tuple) -> ChatSettings:
    return ChatSettings(
        chat_id=row[0],
        welcome_enabled=bool(row[1]),
        captcha_enabled=bool(row[2]),
        antiflood_enabled=bool(row[3]),
        antispam_enabled=bool(row[4]),
        words_enabled=bool(row[5]),
        warn_limit=int(row[6]),
        flood_messages=int(row[7]),
        flood_window=int(row[8]),
        welcome_text=row[9] or "",
    )


class Database:
    def __init__(self, path: str) -> None:
        self.path = path
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self._conn = await aiosqlite.connect(self.path)
        await self._conn.executescript(SCHEMA)
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database is not connected")
        return self._conn

    # -- settings -----------------------------------------------------
    async def get_settings(self, chat_id: int) -> ChatSettings:
        async with self.conn.execute(
            "SELECT chat_id, welcome_enabled, captcha_enabled, antiflood_enabled,"
            " antispam_enabled, words_enabled, warn_limit, flood_messages,"
            " flood_window, welcome_text FROM chat_settings WHERE chat_id = ?",
            (chat_id,),
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            await self.conn.execute(
                "INSERT INTO chat_settings(chat_id, updated_at) VALUES (?, ?)",
                (chat_id, int(time.time())),
            )
            await self.conn.commit()
            return ChatSettings(chat_id=chat_id)
        return _row_to_settings(row)

    async def toggle_setting(self, chat_id: int, field: str) -> bool:
        allowed = {
            "welcome_enabled",
            "captcha_enabled",
            "antiflood_enabled",
            "antispam_enabled",
            "words_enabled",
        }
        if field not in allowed:
            raise ValueError(f"Unknown toggle field: {field}")
        settings = await self.get_settings(chat_id)
        new_value = 0 if getattr(settings, field) else 1
        await self.conn.execute(
            f"UPDATE chat_settings SET {field} = ?, updated_at = ? WHERE chat_id = ?",
            (new_value, int(time.time()), chat_id),
        )
        await self.conn.commit()
        return bool(new_value)

    async def set_int(self, chat_id: int, field: str, value: int) -> None:
        allowed = {"warn_limit", "flood_messages", "flood_window"}
        if field not in allowed:
            raise ValueError(f"Unknown int field: {field}")
        await self.get_settings(chat_id)  # ensure row exists
        await self.conn.execute(
            f"UPDATE chat_settings SET {field} = ?, updated_at = ? WHERE chat_id = ?",
            (value, int(time.time()), chat_id),
        )
        await self.conn.commit()

    async def set_welcome_text(self, chat_id: int, text: str) -> None:
        await self.get_settings(chat_id)
        await self.conn.execute(
            "UPDATE chat_settings SET welcome_text = ?, updated_at = ? WHERE chat_id = ?",
            (text, int(time.time()), chat_id),
        )
        await self.conn.commit()

    # -- warnings -----------------------------------------------------
    async def add_warning(
        self, chat_id: int, user_id: int, admin_id: int, reason: str
    ) -> int:
        await self.conn.execute(
            "INSERT INTO warnings(chat_id, user_id, admin_id, reason, created_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (chat_id, user_id, admin_id, reason, int(time.time())),
        )
        await self.conn.commit()
        return await self.count_warnings(chat_id, user_id)

    async def count_warnings(self, chat_id: int, user_id: int) -> int:
        async with self.conn.execute(
            "SELECT COUNT(*) FROM warnings WHERE chat_id = ? AND user_id = ?",
            (chat_id, user_id),
        ) as cur:
            row = await cur.fetchone()
        return int(row[0]) if row else 0

    async def clear_warnings(self, chat_id: int, user_id: int) -> int:
        async with self.conn.execute(
            "SELECT COUNT(*) FROM warnings WHERE chat_id = ? AND user_id = ?",
            (chat_id, user_id),
        ) as cur:
            row = await cur.fetchone()
        count = int(row[0]) if row else 0
        await self.conn.execute(
            "DELETE FROM warnings WHERE chat_id = ? AND user_id = ?",
            (chat_id, user_id),
        )
        await self.conn.commit()
        return count

    async def pop_last_warning(self, chat_id: int, user_id: int) -> bool:
        async with self.conn.execute(
            "SELECT id FROM warnings WHERE chat_id = ? AND user_id = ? ORDER BY id DESC LIMIT 1",
            (chat_id, user_id),
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            return False
        await self.conn.execute("DELETE FROM warnings WHERE id = ?", (row[0],))
        await self.conn.commit()
        return True

    # -- forbidden words ---------------------------------------------
    async def add_word(self, chat_id: int, word: str) -> None:
        await self.conn.execute(
            "INSERT OR IGNORE INTO forbidden_words(chat_id, word) VALUES (?, ?)",
            (chat_id, word.lower()),
        )
        await self.conn.commit()

    async def remove_word(self, chat_id: int, word: str) -> bool:
        cur = await self.conn.execute(
            "DELETE FROM forbidden_words WHERE chat_id = ? AND word = ?",
            (chat_id, word.lower()),
        )
        await self.conn.commit()
        return (cur.rowcount or 0) > 0

    async def list_words(self, chat_id: int) -> list[str]:
        async with self.conn.execute(
            "SELECT word FROM forbidden_words WHERE chat_id = ? ORDER BY word",
            (chat_id,),
        ) as cur:
            rows = await cur.fetchall()
        return [r[0] for r in rows]

    # -- captcha ------------------------------------------------------
    async def add_pending_captcha(self, chat_id: int, user_id: int) -> None:
        await self.conn.execute(
            "INSERT OR REPLACE INTO pending_captcha(chat_id, user_id, joined_at)"
            " VALUES (?, ?, ?)",
            (chat_id, user_id, int(time.time())),
        )
        await self.conn.commit()

    async def remove_pending_captcha(self, chat_id: int, user_id: int) -> bool:
        cur = await self.conn.execute(
            "DELETE FROM pending_captcha WHERE chat_id = ? AND user_id = ?",
            (chat_id, user_id),
        )
        await self.conn.commit()
        return (cur.rowcount or 0) > 0

    async def is_pending_captcha(self, chat_id: int, user_id: int) -> bool:
        async with self.conn.execute(
            "SELECT 1 FROM pending_captcha WHERE chat_id = ? AND user_id = ?",
            (chat_id, user_id),
        ) as cur:
            row = await cur.fetchone()
        return row is not None
