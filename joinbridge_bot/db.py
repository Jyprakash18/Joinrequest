from __future__ import annotations
from contextlib import asynccontextmanager

import aiosqlite


SCHEMA = """
CREATE TABLE IF NOT EXISTS source_chats (
    chat_id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    username TEXT,
    delivery_mode TEXT NOT NULL DEFAULT 'copy',
    latest_message_id INTEGER,
    latest_message_chat_id INTEGER,
    latest_message_note TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    user_chat_id INTEGER,
    username TEXT,
    first_name TEXT,
    last_name TEXT,
    is_bot_started INTEGER NOT NULL DEFAULT 0,
    is_blocked INTEGER NOT NULL DEFAULT 0,
    first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS join_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_chat_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    user_chat_id INTEGER NOT NULL,
    dm_status TEXT NOT NULL,
    approval_status TEXT NOT NULL DEFAULT 'pending',
    message_id_sent INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(source_chat_id) REFERENCES source_chats(chat_id),
    FOREIGN KEY(user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS broadcasts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_user_id INTEGER NOT NULL,
    text TEXT NOT NULL,
    sent_count INTEGER NOT NULL DEFAULT 0,
    failed_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_join_events_chat ON join_events(source_chat_id);
CREATE INDEX IF NOT EXISTS idx_join_events_user ON join_events(user_id);
"""


class Database:
    def __init__(self, path: str):
        self.path = path

    async def connect(self) -> aiosqlite.Connection:
        conn = await aiosqlite.connect(self.path)
        conn.row_factory = aiosqlite.Row
        return conn

    async def init(self) -> None:
        async with await self.connect() as conn:
            await conn.executescript(SCHEMA)
            await conn.commit()

    async def upsert_source_chat(self, chat_id: int, title: str, username: str | None, delivery_mode: str) -> None:
        async with await self.connect() as conn:
            await conn.execute(
                """
                INSERT INTO source_chats (chat_id, title, username, delivery_mode)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(chat_id) DO UPDATE SET
                    title = excluded.title,
                    username = excluded.username,
                    delivery_mode = COALESCE(source_chats.delivery_mode, excluded.delivery_mode),
                    updated_at = CURRENT_TIMESTAMP
                """,
                (chat_id, title, username, delivery_mode),
            )
            await conn.commit()

    async def set_delivery_mode(self, chat_id: int, mode: str) -> None:
        async with await self.connect() as conn:
            await conn.execute(
                "UPDATE source_chats SET delivery_mode = ?, updated_at = CURRENT_TIMESTAMP WHERE chat_id = ?",
                (mode, chat_id),
            )
            await conn.commit()

    async def set_latest_message(self, chat_id: int, message_chat_id: int, message_id: int, note: str | None) -> None:
        async with await self.connect() as conn:
            await conn.execute(
                """
                UPDATE source_chats
                SET latest_message_chat_id = ?, latest_message_id = ?, latest_message_note = ?, updated_at = CURRENT_TIMESTAMP
                WHERE chat_id = ?
                """,
                (message_chat_id, message_id, note, chat_id),
            )
            await conn.commit()

    async def get_source_chat(self, chat_id: int):
        async with await self.connect() as conn:
            cursor = await conn.execute("SELECT * FROM source_chats WHERE chat_id = ?", (chat_id,))
            return await cursor.fetchone()

    async def upsert_user(self, user_id: int, user_chat_id: int | None, username: str | None, first_name: str | None, last_name: str | None, bot_started: bool = False) -> None:
        async with await self.connect() as conn:
            await conn.execute(
                """
                INSERT INTO users (user_id, user_chat_id, username, first_name, last_name, is_bot_started)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    user_chat_id = COALESCE(excluded.user_chat_id, users.user_chat_id),
                    username = excluded.username,
                    first_name = excluded.first_name,
                    last_name = excluded.last_name,
                    is_bot_started = CASE WHEN excluded.is_bot_started = 1 THEN 1 ELSE users.is_bot_started END,
                    last_seen_at = CURRENT_TIMESTAMP
                """,
                (user_id, user_chat_id, username, first_name, last_name, int(bot_started)),
            )
            await conn.commit()

    async def mark_blocked(self, user_id: int) -> None:
        async with await self.connect() as conn:
            await conn.execute("UPDATE users SET is_blocked = 1, last_seen_at = CURRENT_TIMESTAMP WHERE user_id = ?", (user_id,))
            await conn.commit()

    async def log_join_event(self, source_chat_id: int, user_id: int, user_chat_id: int, dm_status: str, approval_status: str, message_id_sent: int | None) -> None:
        async with await self.connect() as conn:
            await conn.execute(
                """
                INSERT INTO join_events (source_chat_id, user_id, user_chat_id, dm_status, approval_status, message_id_sent)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (source_chat_id, user_id, user_chat_id, dm_status, approval_status, message_id_sent),
            )
            await conn.commit()

    async def get_global_stats(self) -> dict:
        async with await self.connect() as conn:
            queries = {
                "total_source_chats": "SELECT COUNT(*) FROM source_chats",
                "total_users": "SELECT COUNT(*) FROM users",
                "active_users": "SELECT COUNT(*) FROM users WHERE is_bot_started = 1 AND is_blocked = 0",
                "total_joins": "SELECT COUNT(*) FROM join_events",
                "delivered_dms": "SELECT COUNT(*) FROM join_events WHERE dm_status = 'sent'",
                "approved_joins": "SELECT COUNT(*) FROM join_events WHERE approval_status = 'approved'",
            }
            result = {}
            for key, query in queries.items():
                cursor = await conn.execute(query)
                row = await cursor.fetchone()
                result[key] = row[0] if row else 0
            return result

    async def get_chat_stats(self, chat_id: int) -> dict:
        async with await self.connect() as conn:
            chat_cur = await conn.execute("SELECT * FROM source_chats WHERE chat_id = ?", (chat_id,))
            chat_row = await chat_cur.fetchone()
            if not chat_row:
                return {}
            queries = {
                "joins": "SELECT COUNT(*) FROM join_events WHERE source_chat_id = ?",
                "delivered": "SELECT COUNT(*) FROM join_events WHERE source_chat_id = ? AND dm_status = 'sent'",
                "approved": "SELECT COUNT(*) FROM join_events WHERE source_chat_id = ? AND approval_status = 'approved'",
            }
            result = {"title": chat_row["title"], "delivery_mode": chat_row["delivery_mode"], "latest_message_id": chat_row["latest_message_id"]}
            for key, query in queries.items():
                cursor = await conn.execute(query, (chat_id,))
                row = await cursor.fetchone()
                result[key] = row[0] if row else 0
            return result

    async def get_broadcast_targets(self) -> list[aiosqlite.Row]:
        async with await self.connect() as conn:
            cursor = await conn.execute(
                "SELECT user_id, user_chat_id FROM users WHERE is_bot_started = 1 AND is_blocked = 0 AND user_chat_id IS NOT NULL"
            )
            return await cursor.fetchall()

    async def log_broadcast(self, admin_user_id: int, text: str, sent_count: int, failed_count: int) -> None:
        async with await self.connect() as conn:
            await conn.execute(
                "INSERT INTO broadcasts (admin_user_id, text, sent_count, failed_count) VALUES (?, ?, ?, ?)",
                (admin_user_id, text, sent_count, failed_count),
            )
            await conn.commit()
