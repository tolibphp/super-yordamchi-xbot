"""
database.py — SQLite ma'lumotlar bazasi bilan ishlash (aiosqlite orqali async).

Jadvallar:
- linked_chats: botni qaysi kanal/guruhlarga ulanganligi
- activity: foydalanuvchilar reaksiya va kommentariyalari
- game_winners: 777 o'yini g'oliblari (bir postga faqat 1 g'olib)
"""

import os
import aiosqlite
import logging
from datetime import datetime, timedelta, timezone

# Railway volume uchun: DB_PATH=/data/activity.db qilib sozlash mumkin
DB_PATH = os.getenv("DB_PATH", "activity.db")
logger = logging.getLogger(__name__)


async def init_db() -> None:
    """Bazani yaratadi va barcha jadvallarni tuzadi."""
    async with aiosqlite.connect(DB_PATH) as db:
        # Ulangan kanallar va guruhlar
        await db.execute("""
            CREATE TABLE IF NOT EXISTS linked_chats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id INTEGER NOT NULL,
                chat_id INTEGER NOT NULL UNIQUE,
                chat_type TEXT NOT NULL CHECK(chat_type IN ('channel', 'group')),
                chat_title TEXT,
                added_at DATETIME DEFAULT (datetime('now'))
            )
        """)

        # Faollik jadvali (chat_id bilan — qaysi guruhda)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS activity (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                username TEXT,
                first_name TEXT NOT NULL,
                activity_type TEXT NOT NULL CHECK(activity_type IN ('reaction', 'comment')),
                message_id INTEGER NOT NULL,
                chat_id INTEGER NOT NULL DEFAULT 0,
                created_at DATETIME DEFAULT (datetime('now'))
            )
        """)

        # 777 o'yini g'oliblari
        await db.execute("""
            CREATE TABLE IF NOT EXISTS game_winners (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                reply_to_message_id INTEGER NOT NULL,
                winner_user_id INTEGER NOT NULL,
                winner_first_name TEXT,
                created_at DATETIME DEFAULT (datetime('now')),
                UNIQUE(chat_id, reply_to_message_id)
            )
        """)

        # Indekslar
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_activity_user_id ON activity(user_id)
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_activity_created_at ON activity(created_at)
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_activity_chat_id ON activity(chat_id)
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_linked_chats_owner ON linked_chats(owner_id)
        """)
        await db.commit()
    logger.info("Ma'lumotlar bazasi tayyor.")


# ─────────────────────────────────────────────
# LINKED CHATS — ulangan kanal/guruhlar
# ─────────────────────────────────────────────

async def add_linked_chat(
    owner_id: int,
    chat_id: int,
    chat_type: str,
    chat_title: str | None,
) -> None:
    """Yangi kanal/guruhni bazaga qo'shadi yoki yangilaydi."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO linked_chats (owner_id, chat_id, chat_type, chat_title)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET
                owner_id = excluded.owner_id,
                chat_type = excluded.chat_type,
                chat_title = excluded.chat_title
            """,
            (owner_id, chat_id, chat_type, chat_title),
        )
        await db.commit()
    logger.info("Chat ulandi: owner=%s, chat_id=%s, type=%s", owner_id, chat_id, chat_type)


async def remove_linked_chat(chat_id: int) -> None:
    """Kanal/guruhni bazadan olib tashlaydi."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM linked_chats WHERE chat_id = ?", (chat_id,))
        await db.commit()
    logger.info("Chat uzildi: chat_id=%s", chat_id)


async def is_linked_chat(chat_id: int) -> bool:
    """Berilgan chat_id bazada bormi tekshiradi."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT 1 FROM linked_chats WHERE chat_id = ? LIMIT 1",
            (chat_id,),
        )
        row = await cursor.fetchone()
    return row is not None


async def get_linked_channel_for_group(group_chat_id: int) -> int | None:
    """
    Guruhga bog'langan kanalni topadi.
    Bir xil owner_id ga tegishli kanallardan birinchisini qaytaradi.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        # Avval guruhning owner_id sini olish
        cursor = await db.execute(
            "SELECT owner_id FROM linked_chats WHERE chat_id = ? AND chat_type = 'group'",
            (group_chat_id,),
        )
        row = await cursor.fetchone()
        if not row:
            return None

        owner_id = row[0]

        # Shu ownerga tegishli kanalni topish
        cursor = await db.execute(
            "SELECT chat_id FROM linked_chats WHERE owner_id = ? AND chat_type = 'channel' LIMIT 1",
            (owner_id,),
        )
        row = await cursor.fetchone()
        return row[0] if row else None


async def get_owner_chats(owner_id: int) -> list[dict]:
    """Berilgan owner_id ga tegishli barcha kanallar va guruhlarni qaytaradi."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT chat_id, chat_type, chat_title FROM linked_chats WHERE owner_id = ?",
            (owner_id,),
        )
        rows = await cursor.fetchall()
    return [
        {"chat_id": row["chat_id"], "chat_type": row["chat_type"], "chat_title": row["chat_title"]}
        for row in rows
    ]


async def get_all_linked_chats() -> list[dict]:
    """Botga ulangan barcha kanallar va guruhlarni qaytaradi (bot egasi uchun)."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT chat_id, chat_type, chat_title, owner_id FROM linked_chats ORDER BY added_at DESC"
        )
        rows = await cursor.fetchall()
    return [
        {
            "chat_id": row["chat_id"],
            "chat_type": row["chat_type"],
            "chat_title": row["chat_title"],
            "owner_id": row["owner_id"],
        }
        for row in rows
    ]


# ─────────────────────────────────────────────
# ACTIVITY — faollik
# ─────────────────────────────────────────────

async def log_activity(
    user_id: int,
    username: str | None,
    first_name: str,
    activity_type: str,
    message_id: int,
    chat_id: int = 0,
) -> None:
    """Foydalanuvchi faolligini bazaga yozadi."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO activity (user_id, username, first_name, activity_type, message_id, chat_id)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, username, first_name, activity_type, message_id, chat_id),
        )
        await db.commit()
    logger.info(
        "Faollik yozildi: user_id=%s, tur=%s, chat_id=%s",
        user_id, activity_type, chat_id,
    )


async def get_active_users(days: int, chat_id: int = 0) -> list[dict]:
    """
    Oxirgi `days` kun ichida berilgan chatda kamida 1 marta
    faollik ko'rsatgan barcha noyob foydalanuvchilarni qaytaradi.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)
    since_str = since.strftime("%Y-%m-%d %H:%M:%S")

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT DISTINCT user_id, username, first_name
            FROM activity
            WHERE created_at >= ? AND chat_id = ?
            """,
            (since_str, chat_id),
        )
        rows = await cursor.fetchall()

    users = [
        {
            "user_id": row["user_id"],
            "username": row["username"],
            "first_name": row["first_name"],
        }
        for row in rows
    ]
    logger.info("Oxirgi %d kunda %d ta faol foydalanuvchi topildi (chat=%s).", days, len(users), chat_id)
    return users


async def get_top_users(days: int, chat_id: int = 0, limit: int = 5) -> list[dict]:
    """
    Oxirgi `days` kun ichidagi berilgan chatda eng faol foydalanuvchilarni qaytaradi.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)
    since_str = since.strftime("%Y-%m-%d %H:%M:%S")

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT user_id, username, first_name, COUNT(*) as total
            FROM activity
            WHERE created_at >= ? AND chat_id = ?
            GROUP BY user_id
            ORDER BY total DESC
            LIMIT ?
            """,
            (since_str, chat_id, limit),
        )
        rows = await cursor.fetchall()

    return [
        {
            "user_id": row["user_id"],
            "username": row["username"],
            "first_name": row["first_name"],
            "total": row["total"],
        }
        for row in rows
    ]


# ─────────────────────────────────────────────
# 777 O'YIN — g'oliblar
# ─────────────────────────────────────────────

async def check_777_winner_exists(chat_id: int, reply_to_message_id: int) -> bool:
    """Shu post ostida allaqachon 777 g'olib bormi tekshiradi."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT 1 FROM game_winners WHERE chat_id = ? AND reply_to_message_id = ? LIMIT 1",
            (chat_id, reply_to_message_id),
        )
        row = await cursor.fetchone()
    return row is not None


async def save_777_winner(
    chat_id: int,
    reply_to_message_id: int,
    winner_user_id: int,
    winner_first_name: str,
) -> bool:
    """
    777 g'olibini bazaga yozadi.
    Agar shu postda allaqachon g'olib bo'lsa False qaytaradi.
    """
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                """
                INSERT INTO game_winners (chat_id, reply_to_message_id, winner_user_id, winner_first_name)
                VALUES (?, ?, ?, ?)
                """,
                (chat_id, reply_to_message_id, winner_user_id, winner_first_name),
            )
            await db.commit()
        logger.info("777 g'olib yozildi: user=%s, chat=%s, msg=%s", winner_user_id, chat_id, reply_to_message_id)
        return True
    except aiosqlite.IntegrityError:
        # UNIQUE constraint — bu postda allaqachon g'olib bor
        logger.info("777 g'olib allaqachon bor: chat=%s, msg=%s", chat_id, reply_to_message_id)
        return False
