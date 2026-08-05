"""
database.py — SQLite ma'lumotlar bazasi bilan ishlash (aiosqlite orqali async).
activity jadvali: foydalanuvchilar reaksiya va kommentariyalarini saqlaydi.
"""

import os

import aiosqlite
import logging
from datetime import datetime, timedelta, timezone

# Railway volume uchun: DB_PATH=/data/activity.db qilib sozlash mumkin
DB_PATH = os.getenv("DB_PATH", "activity.db")
logger = logging.getLogger(__name__)


async def init_db() -> None:
    """Bazani yaratadi (agar mavjud bo'lmasa) va activity jadvalini tuzadi."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS activity (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                username TEXT,
                first_name TEXT NOT NULL,
                activity_type TEXT NOT NULL CHECK(activity_type IN ('reaction', 'comment')),
                message_id INTEGER NOT NULL,
                created_at DATETIME DEFAULT (datetime('now'))
            )
        """)
        # Tez qidirish uchun indekslar
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_activity_user_id ON activity(user_id)
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_activity_created_at ON activity(created_at)
        """)
        await db.commit()
    logger.info("Ma'lumotlar bazasi tayyor.")


async def log_activity(
    user_id: int,
    username: str | None,
    first_name: str,
    activity_type: str,
    message_id: int,
) -> None:
    """Foydalanuvchi faolligini bazaga yozadi."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO activity (user_id, username, first_name, activity_type, message_id)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, username, first_name, activity_type, message_id),
        )
        await db.commit()
    logger.info(
        "Faollik yozildi: user_id=%s, tur=%s, message_id=%s",
        user_id, activity_type, message_id,
    )


async def get_active_users(days: int) -> list[dict]:
    """
    Oxirgi `days` kun ichida kamida 1 marta faollik ko'rsatgan 
    barcha noyob foydalanuvchilarni qaytaradi.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)
    since_str = since.strftime("%Y-%m-%d %H:%M:%S")

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT DISTINCT user_id, username, first_name
            FROM activity
            WHERE created_at >= ?
            """,
            (since_str,),
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
    logger.info("Oxirgi %d kunda %d ta faol foydalanuvchi topildi.", days, len(users))
    return users


async def get_top_users(days: int, limit: int = 5) -> list[dict]:
    """
    Oxirgi `days` kun ichidagi eng faol foydalanuvchilarni 
    (reaction + comment soni bo'yicha) qaytaradi.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)
    since_str = since.strftime("%Y-%m-%d %H:%M:%S")

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT user_id, username, first_name, COUNT(*) as total
            FROM activity
            WHERE created_at >= ?
            GROUP BY user_id
            ORDER BY total DESC
            LIMIT ?
            """,
            (since_str, limit),
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
