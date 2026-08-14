"""
database.py — SQLite ma'lumotlar bazasi bilan ishlash (aiosqlite orqali async).

Jadvallar:
- linked_chats: botni qaysi kanal/guruhlarga ulanganligi
- activity: foydalanuvchilar reaksiya va kommentariyalari (guruh/kanal)
- game_winners: 777 o'yini g'oliblari
- mandatory_channels: majburiy a'zo bo'linishi kerak bo'lgan kanallar
- bot_settings: bot sozlamalari (majburiy obuna, kunlik post linki va h.k.)
- bot_users: barcha bot foydalanuvchilari, referal ballari va darajalari
- referrals: taklif qilingan do'stlar va ularning statusi (active / dropped)
- contests: dinamik konkurslar (Premium, Gift, Custom)
- contest_participants: konkurs ishtirokchilari va chiptalari
- daily_post_rewards: kunlik post o'qish uchun mukofotlar
- promo_codes / promo_claims: yashirin promokodlar tizimi
"""

import os
import aiosqlite
import logging
import random
from datetime import datetime, timedelta, timezone

# Railway volume uchun: DB_PATH=/data/activity.db qilib sozlash mumkin
DB_PATH = os.getenv("DB_PATH", "activity.db")
logger = logging.getLogger(__name__)


async def init_db() -> None:
    """Bazani yaratadi va barcha jadvallarni tuzadi."""
    db_dir = os.path.dirname(DB_PATH)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)

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

        # Guruh a'zolari (Tag All funksiyasi uchun)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS group_members (
                chat_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                username TEXT,
                first_name TEXT NOT NULL,
                last_active DATETIME DEFAULT (datetime('now')),
                PRIMARY KEY (chat_id, user_id)
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

        # Majburiy kanallar jadvali
        await db.execute("""
            CREATE TABLE IF NOT EXISTS mandatory_channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id TEXT NOT NULL UNIQUE,
                channel_title TEXT,
                channel_username TEXT,
                created_at DATETIME DEFAULT (datetime('now'))
            )
        """)

        # Bot sozlamalari jadvali
        await db.execute("""
            CREATE TABLE IF NOT EXISTS bot_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)

        # Standart sozlama: majburiy obuna yoniq
        await db.execute("""
            INSERT OR IGNORE INTO bot_settings (key, value)
            VALUES ('mandatory_sub_enabled', '1')
        """)

        # ── SMART VIRAL CONTEST JADVALLARI ──

        # Bot foydalanuvchilari profili
        await db.execute("""
            CREATE TABLE IF NOT EXISTS bot_users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT NOT NULL,
                referred_by INTEGER DEFAULT 0,
                points INTEGER DEFAULT 0,
                referral_count INTEGER DEFAULT 0,
                bonus_points INTEGER DEFAULT 0,
                vip_status INTEGER DEFAULT 0,
                joined_at DATETIME DEFAULT (datetime('now')),
                last_active DATETIME DEFAULT (datetime('now'))
            )
        """)

        # Migration: birthday ustuni yo'q bo'lsa qo'shish
        try:
            await db.execute("ALTER TABLE bot_users ADD COLUMN birthday TEXT DEFAULT NULL")
        except Exception:
            pass

        # Referallar jadvali (Anti-Drop va jarima kuzatuvi)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS referrals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_id INTEGER NOT NULL,
                referred_id INTEGER NOT NULL UNIQUE,
                status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'dropped')),
                created_at DATETIME DEFAULT (datetime('now')),
                dropped_at DATETIME
            )
        """)

        # Konkurslar jadvali
        await db.execute("""
            CREATE TABLE IF NOT EXISTS contests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                contest_type TEXT NOT NULL DEFAULT 'gift',
                min_referrals INTEGER NOT NULL DEFAULT 30,
                prize_description TEXT,
                post_messages TEXT DEFAULT '[]',
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at DATETIME DEFAULT (datetime('now')),
                ended_at DATETIME
            )
        """)
        # Migration: post_messages va winners_data ustunlari yo'q bo'lsa qo'shish
        try:
            await db.execute("ALTER TABLE contests ADD COLUMN post_messages TEXT DEFAULT '[]'")
        except Exception:
            pass
        try:
            await db.execute("ALTER TABLE contests ADD COLUMN winners_data TEXT DEFAULT NULL")
        except Exception:
            pass

        # Konkurs qatnashuvchilari
        await db.execute("""
            CREATE TABLE IF NOT EXISTS contest_participants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                contest_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                ticket_number INTEGER NOT NULL,
                joined_at DATETIME DEFAULT (datetime('now')),
                UNIQUE(contest_id, user_id)
            )
        """)

        # Kunlik post o'qish qaydlari
        await db.execute("""
            CREATE TABLE IF NOT EXISTS daily_post_rewards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                reward_date TEXT NOT NULL,
                created_at DATETIME DEFAULT (datetime('now')),
                UNIQUE(user_id, reward_date)
            )
        """)

        # Promokodlar
        await db.execute("""
            CREATE TABLE IF NOT EXISTS promo_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL UNIQUE,
                reward_points INTEGER NOT NULL DEFAULT 2,
                max_uses INTEGER NOT NULL DEFAULT 50,
                used_count INTEGER NOT NULL DEFAULT 0,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at DATETIME DEFAULT (datetime('now'))
            )
        """)

        # Migration: promo_codes ga reward_type qo'shish ('points' yoki 'referrals')
        try:
            await db.execute("ALTER TABLE promo_codes ADD COLUMN reward_type TEXT DEFAULT 'points'")
        except Exception:
            pass

        # Migration: promo_codes ga post ma'lumotlarini qo'shish
        try:
            await db.execute("ALTER TABLE promo_codes ADD COLUMN post_chat_id INTEGER DEFAULT 0")
            await db.execute("ALTER TABLE promo_codes ADD COLUMN post_msg_id INTEGER DEFAULT 0")
            await db.execute("ALTER TABLE promo_codes ADD COLUMN post_html TEXT DEFAULT NULL")
        except Exception:
            pass

        # Promokod ishlatganlar
        await db.execute("""
            CREATE TABLE IF NOT EXISTS promo_claims (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                promo_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                claimed_at DATETIME DEFAULT (datetime('now')),
                UNIQUE(promo_id, user_id)
            )
        """)

        # ── OMAD G'ILDIRAGI JADVALI ──
        await db.execute("""
            CREATE TABLE IF NOT EXISTS daily_wheel_spins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                spin_date TEXT NOT NULL,
                reward_type TEXT NOT NULL,
                reward_value INTEGER NOT NULL,
                created_at DATETIME DEFAULT (datetime('now')),
                UNIQUE(user_id, spin_date)
            )
        """)

        # ── GURUHDAGI FAOLLIKNI HISOB-KITOBLARI (CHAT MINING) ──
        await db.execute("""
            CREATE TABLE IF NOT EXISTS group_chat_activity (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                chat_id INTEGER NOT NULL,
                msg_count INTEGER DEFAULT 0,
                total_points_earned INTEGER DEFAULT 0,
                last_msg_at DATETIME DEFAULT (datetime('now')),
                UNIQUE(user_id, chat_id)
            )
        """)

        # ── VAZIFALAR MARKAZI (TASKS) ──
        await db.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id TEXT NOT NULL,
                channel_title TEXT,
                channel_url TEXT,
                reward_points INTEGER DEFAULT 0,
                is_active INTEGER DEFAULT 1,
                created_at DATETIME DEFAULT (datetime('now'))
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_tasks (
                user_id INTEGER NOT NULL,
                task_id INTEGER NOT NULL,
                completed_at DATETIME DEFAULT (datetime('now')),
                UNIQUE(user_id, task_id)
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
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_referrals_referrer ON referrals(referrer_id)
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_referrals_status ON referrals(status)
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_contest_part_cid ON contest_participants(contest_id)
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_wheel_user_date ON daily_wheel_spins(user_id, spin_date)
        """)
        await db.commit()
    logger.info("Ma'lumotlar bazasi va Smart Viral Contest jadvallari tayyor.")


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
    """Guruhga tegishli bo'lgan kanal chat_id sini topadi (bitta owner_id bo'yicha)."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT owner_id FROM linked_chats WHERE chat_id = ? AND chat_type = 'group' LIMIT 1",
            (group_chat_id,),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        owner_id = row[0]

        cursor = await db.execute(
            "SELECT chat_id FROM linked_chats WHERE owner_id = ? AND chat_type = 'channel' LIMIT 1",
            (owner_id,),
        )
        channel_row = await cursor.fetchone()
        if channel_row:
            return channel_row[0]
    return None


async def get_all_linked_chats() -> list[dict]:
    """Barcha ulangan kanal va guruhlarni qaytaradi."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT chat_id, chat_type, chat_title, added_at FROM linked_chats ORDER BY added_at DESC"
        )
        rows = await cursor.fetchall()
    return [dict(r) for r in rows]


# ─────────────────────────────────────────────
# FAOLLIK (ACTIVITY) — guruh/kanal faolligi
# ─────────────────────────────────────────────

async def log_activity(
    user_id: int,
    username: str | None,
    first_name: str,
    activity_type: str,
    message_id: int,
    chat_id: int = 0,
) -> None:
    """Foydalanuvchi faolligini (reaksiya yoki komment) bazaga yozadi."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO activity (user_id, username, first_name, activity_type, message_id, chat_id)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, username, first_name, activity_type, message_id, chat_id),
        )
        # Shuningdek bot_users jadvalida ham aktivlik vaqtini yangilaymiz
        await db.execute(
            """
            INSERT INTO bot_users (user_id, username, first_name, last_active)
            VALUES (?, ?, ?, datetime('now'))
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name,
                last_active = datetime('now')
            """,
            (user_id, username, first_name),
        )
        await db.commit()
    logger.info("Faollik yozildi: user_id=%s, tur=%s, chat_id=%s", user_id, activity_type, chat_id)


async def get_top_users(
    days: int,
    chat_id: int | None = None,
    channel_id: int | None = None,
    limit: int = 5,
) -> list[dict]:
    """Oxirgi `days` kun ichidagi eng faol foydalanuvchilarni qaytaradi."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    since_str = since.strftime("%Y-%m-%d %H:%M:%S")

    where_clauses = ["created_at >= ?"]
    params: list = [since_str]

    if chat_id is not None and channel_id is not None:
        where_clauses.append("(chat_id = ? OR chat_id = ?)")
        params.extend([chat_id, channel_id])
    elif chat_id is not None:
        where_clauses.append("chat_id = ?")
        params.append(chat_id)

    where_sql = " AND ".join(where_clauses)
    query = f"""
        SELECT
            user_id,
            username,
            first_name,
            COUNT(*) AS total
        FROM activity
        WHERE {where_sql}
        GROUP BY user_id
        ORDER BY total DESC
        LIMIT ?
    """
    params.append(limit)

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(query, params)
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


async def get_active_users(
    days: int,
    chat_id: int | None = None,
    channel_id: int | None = None,
) -> list[dict]:
    """Oxirgi `days` kun ichidagi barcha faol foydalanuvchilar ro'yxatini qaytaradi."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    since_str = since.strftime("%Y-%m-%d %H:%M:%S")

    where_clauses = ["created_at >= ?"]
    params: list = [since_str]

    if chat_id is not None and channel_id is not None:
        where_clauses.append("(chat_id = ? OR chat_id = ?)")
        params.extend([chat_id, channel_id])
    elif chat_id is not None:
        where_clauses.append("chat_id = ?")
        params.append(chat_id)

    where_sql = " AND ".join(where_clauses)
    query = f"""
        SELECT
            user_id,
            username,
            first_name,
            COUNT(*) AS total
        FROM activity
        WHERE {where_sql}
        GROUP BY user_id
        ORDER BY total DESC
    """

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(query, params)
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
# 777 O'YINI (GAME WINNERS)
# ─────────────────────────────────────────────

async def check_777_winner_exists(chat_id: int, reply_to_message_id: int) -> bool:
    """Shu post ostidagi kamentlarda 777 g'olibi allaqachon bormi tekshiradi."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            SELECT 1 FROM game_winners
            WHERE chat_id = ? AND reply_to_message_id = ?
            LIMIT 1
            """,
            (chat_id, reply_to_message_id),
        )
        row = await cursor.fetchone()
    return row is not None


async def save_777_winner(
    chat_id: int,
    reply_to_message_id: int,
    winner_user_id: int,
    winner_first_name: str,
) -> None:
    """777 o'yini g'olibini bazaga yozadi."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT OR IGNORE INTO game_winners
            (chat_id, reply_to_message_id, winner_user_id, winner_first_name)
            VALUES (?, ?, ?, ?)
            """,
            (chat_id, reply_to_message_id, winner_user_id, winner_first_name),
        )
        await db.commit()
    logger.info("777 g'olib yozildi: chat_id=%s, msg_id=%s, winner=%s", chat_id, reply_to_message_id, winner_user_id)


# ─────────────────────────────────────────────
# MAJBURIY OBUNA VA SOZLAMALAR
# ─────────────────────────────────────────────

async def add_mandatory_channel(
    channel_id: str,
    channel_title: str,
    channel_username: str | None = None,
) -> None:
    """Majburiy a'zo bo'linadigan kanal qo'shadi."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO mandatory_channels (channel_id, channel_title, channel_username)
            VALUES (?, ?, ?)
            ON CONFLICT(channel_id) DO UPDATE SET
                channel_title = excluded.channel_title,
                channel_username = excluded.channel_username
            """,
            (channel_id, channel_title, channel_username),
        )
        await db.commit()
    logger.info("Majburiy kanal qo'shildi: %s (%s)", channel_title, channel_id)


async def remove_mandatory_channel(channel_id_str: str) -> bool:
    """Majburiy kanalni bazadan o'chiradi."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM mandatory_channels WHERE channel_id = ?",
            (channel_id_str,),
        )
        await db.commit()
        deleted = cursor.rowcount > 0
    logger.info("Majburiy kanal o'chirildi (%s): %s", channel_id_str, deleted)
    return deleted


async def get_mandatory_channels() -> list[dict]:
    """Barcha majburiy kanallar ro'yxatini qaytaradi."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT id, channel_id, channel_title, channel_username, created_at FROM mandatory_channels ORDER BY id ASC"
        )
        rows = await cursor.fetchall()
    return [
        {
            "id": row["id"],
            "channel_id": row["channel_id"],
            "channel_title": row["channel_title"] or "Noma'lum kanal",
            "channel_username": row["channel_username"],
            "created_at": row["created_at"],
        }
        for row in rows
    ]


async def is_mandatory_sub_enabled() -> bool:
    """Majburiy obuna yoqilganligini tekshiradi."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT value FROM bot_settings WHERE key = 'mandatory_sub_enabled' LIMIT 1"
        )
        row = await cursor.fetchone()
    if row:
        return row[0] == "1"
    return True


async def set_mandatory_sub_enabled(enabled: bool) -> None:
    """Majburiy obunani yoqadi yoki o'chiradi."""
    val = "1" if enabled else "0"
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO bot_settings (key, value)
            VALUES ('mandatory_sub_enabled', ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (val,),
        )
        await db.commit()
    logger.info("Majburiy obuna holati o'zgartirildi: %s", enabled)


async def get_bot_setting(key: str, default: str = "") -> str:
    """Bot sozlamasini oladi."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT value FROM bot_settings WHERE key = ? LIMIT 1", (key,))
        row = await cursor.fetchone()
    return row[0] if row else default


async def set_bot_setting(key: str, value: str) -> None:
    """Bot sozlamasini saqlaydi."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO bot_settings (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )
        await db.commit()


# ─────────────────────────────────────────────
# SMART VIRAL CONTEST — FOYDALANUVCHILAR VA REFERAL
# ─────────────────────────────────────────────

async def get_or_create_user(
    user_id: int,
    username: str | None,
    first_name: str,
    referred_by: int = 0,
) -> tuple[dict, bool]:
    """
    Foydalanuvchini bazadan oladi yoki yangisini yaratadi.
    Qaytaradi: (user_dict, is_new_user: bool)
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        # 1. Avval mavjudligini tekshiramiz
        cursor = await db.execute("SELECT * FROM bot_users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()

        if row:
            # Mavjud foydalanuvchi ma'lumotlarini yangilash
            await db.execute(
                """
                UPDATE bot_users SET
                    username = ?,
                    first_name = ?,
                    last_active = datetime('now')
                WHERE user_id = ?
                """,
                (username, first_name, user_id),
            )
            await db.commit()
            cursor = await db.execute("SELECT * FROM bot_users WHERE user_id = ?", (user_id,))
            updated_row = await cursor.fetchone()
            return dict(updated_row), False

        # 2. Yangi foydalanuvchi yaratish (ON CONFLICT bilan parallel requestlarda xato bermaydi)
        ref_val = referred_by if (referred_by != user_id and referred_by > 0) else 0
        await db.execute(
            """
            INSERT INTO bot_users (user_id, username, first_name, referred_by, points, referral_count, bonus_points, vip_status, last_active)
            VALUES (?, ?, ?, ?, 0, 0, 0, 0, datetime('now'))
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name,
                last_active = datetime('now')
            """,
            (user_id, username, first_name, ref_val),
        )
        await db.commit()

        cursor = await db.execute("SELECT * FROM bot_users WHERE user_id = ?", (user_id,))
        new_row = await cursor.fetchone()
        return dict(new_row), True


async def process_referral_reward(
    referrer_id: int,
    new_user_id: int,
    new_user_name: str | None,
    new_user_first_name: str,
) -> tuple[bool, int, dict | None, dict | None]:
    """
    Yangi do'st kanalga muvaffaqiyatli obuna bo'lganda:
    1. 1-darajali taklif qilganga +1 ball va pog'onali bonuslarni beradi.
    2. 2-darajali taklif qilgan (grand-referrer) ga passiv +1 bonus ball beradi.
    Qaytaradi: (awarded, total_points, milestone_dict or None, tier2_dict or None)
    """
    if referrer_id == new_user_id or referrer_id <= 0:
        return False, 0, None, None

    async with aiosqlite.connect(DB_PATH) as db:
        # Allaqachon bu referal uchun mukofot berilganmi tekshirish
        cursor = await db.execute(
            "SELECT id, status FROM referrals WHERE referred_id = ?",
            (new_user_id,),
        )
        existing_ref = await cursor.fetchone()

        if existing_ref:
            # Allaqachon mavjud
            return False, 0, None, None

        # Referallarga yozish
        await db.execute(
            """
            INSERT INTO referrals (referrer_id, referred_id, status)
            VALUES (?, ?, 'active')
            """,
            (referrer_id, new_user_id),
        )

        # Referrer profilini yangilash (+1 ball, +1 referral_count)
        await db.execute(
            """
            UPDATE bot_users SET
                points = points + 1,
                referral_count = referral_count + 1
            WHERE user_id = ?
            """,
            (referrer_id,),
        )

        # Yangilangan holatni olish
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM bot_users WHERE user_id = ?", (referrer_id,))
        referrer = await cursor.fetchone()
        if not referrer:
            await db.commit()
            return True, 1, None, None

        ref_dict = dict(referrer)
        current_refs = ref_dict["referral_count"]
        milestone = None

        # Pog'onali bonuslar (Milestone checks)
        # 3 ta do'st: Random chipta statusi
        if current_refs == 3:
            milestone = {
                "level": 3,
                "bonus": 0,
                "title": "🎟 Omadli Chipta (Random sovringa yo'llanma) ochildi!",
            }
        # 10 ta do'st: +5 bonus ball
        elif current_refs == 10:
            await db.execute(
                "UPDATE bot_users SET points = points + 5, bonus_points = bonus_points + 5 WHERE user_id = ?",
                (referrer_id,),
            )
            milestone = {
                "level": 10,
                "bonus": 5,
                "title": "🎉 10 ta do'st bonusi: +5 qo'shimcha ball berildi!",
            }
        # 25 ta do'st: VIP status va +15 bonus ball
        elif current_refs == 25:
            await db.execute(
                "UPDATE bot_users SET points = points + 15, bonus_points = bonus_points + 15, vip_status = 1 WHERE user_id = ?",
                (referrer_id,),
            )
            milestone = {
                "level": 25,
                "bonus": 15,
                "title": "👑 VIP STATUS va +15 qo'shimcha ball berildi!",
            }

        # ── 2-POG'ONALI (TIER 2) REFERAL BONUSI ──
        tier2_info = None
        grand_referrer_id = ref_dict.get("referred_by", 0)
        if grand_referrer_id and grand_referrer_id > 0 and grand_referrer_id != referrer_id:
            await db.execute(
                "UPDATE bot_users SET points = points + 1, bonus_points = bonus_points + 1 WHERE user_id = ?",
                (grand_referrer_id,),
            )
            tier2_info = {
                "grand_referrer_id": grand_referrer_id,
                "bonus": 1,
            }

        await db.commit()

        # So'nggi umumiy ballni olish
        cursor = await db.execute("SELECT points FROM bot_users WHERE user_id = ?", (referrer_id,))
        final_row = await cursor.fetchone()
        final_points = final_row[0] if final_row else ref_dict["points"]

        return True, final_points, milestone, tier2_info


async def process_referral_drop(leaving_user_id: int) -> tuple[int | None, str | None, int | None]:
    """
    Foydalanuvchi kanaldan chiqib ketganda (Anti-Drop):
    Taklif qiluvchidan -1 ball olinadi va ogohlantirish uchun ma'lumot qaytariladi.
    Qaytaradi: (referrer_id, referred_first_name, remaining_points)
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        # Referal holatini topish
        cursor = await db.execute(
            "SELECT id, referrer_id, status FROM referrals WHERE referred_id = ? AND status = 'active' LIMIT 1",
            (leaving_user_id,),
        )
        ref_row = await cursor.fetchone()
        if not ref_row:
            return None, None, None

        referrer_id = ref_row["referrer_id"]

        # Referal statusini 'dropped' ga o'tkazamiz
        await db.execute(
            "UPDATE referrals SET status = 'dropped', dropped_at = datetime('now') WHERE id = ?",
            (ref_row["id"],),
        )

        # Referrer balini -1 va referral_count ni -1 qilamiz (0 dan pastga tushmaydi)
        await db.execute(
            """
            UPDATE bot_users SET
                points = MAX(0, points - 1),
                referral_count = MAX(0, referral_count - 1)
            WHERE user_id = ?
            """,
            (referrer_id,),
        )

        # Chiqqan odam ismini olish
        cursor = await db.execute("SELECT first_name, username FROM bot_users WHERE user_id = ?", (leaving_user_id,))
        user_row = await cursor.fetchone()
        user_name = user_row["first_name"] if user_row else "Foydalanuvchi"

        # Referrer qolgan balini olish
        cursor = await db.execute("SELECT points FROM bot_users WHERE user_id = ?", (referrer_id,))
        ref_user = await cursor.fetchone()
        remaining_points = ref_user["points"] if ref_user else 0

        await db.commit()
        return referrer_id, user_name, remaining_points


async def get_user_profile(user_id: int) -> dict | None:
    """Foydalanuvchining to'liq profilini qaytaradi."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM bot_users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        if not row:
            return None
        return dict(row)


async def get_top_referrers(limit: int = 10) -> list[dict]:
    """Eng ko'p referal chaqirgan (va eng ko'p ballga ega) top ishtirokchilar."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT user_id, username, first_name, points, referral_count, vip_status
            FROM bot_users
            WHERE referral_count > 0
            ORDER BY referral_count DESC, points DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = await cursor.fetchall()
    return [dict(r) for r in rows]


# ─────────────────────────────────────────────
# KUNLIK POST VA PROMOKODLAR
# ─────────────────────────────────────────────

async def claim_daily_post_reward(user_id: int) -> tuple[bool, str]:
    """
    Foydalanuvchi bugungi postni ko'rgani uchun +1 ball oladi (kuniga faqat 1 marta).
    Qaytaradi: (success, message)
    """
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                "INSERT INTO daily_post_rewards (user_id, reward_date) VALUES (?, ?)",
                (user_id, today_str),
            )
            await db.execute(
                "UPDATE bot_users SET points = points + 1, bonus_points = bonus_points + 1 WHERE user_id = ?",
                (user_id,),
            )
            await db.commit()
            return True, "🎉 Bugungi postni ko'rganingiz uchun sizga +1 ball berildi!"
        except Exception:
            return False, "⚠️ Siz bugungi post uchun ajratilgan ballni allaqachon olgansiz! Ertaga yana urinib ko'ring."


async def find_user_by_id_or_username(user_identifier: str | int) -> dict | None:
    """Foydalanuvchini ID yoki @username orqali qidiradi."""
    raw_str = str(user_identifier).strip()
    if raw_str.startswith("@"):
        clean_user = raw_str[1:].lower()
    else:
        clean_user = raw_str.lower()

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if clean_user.isdigit():
            cursor = await db.execute("SELECT * FROM bot_users WHERE user_id = ?", (int(clean_user),))
        else:
            cursor = await db.execute("SELECT * FROM bot_users WHERE LOWER(username) = ?", (clean_user,))
        row = await cursor.fetchone()
        if row:
            return dict(row)
    return None


async def manual_add_user_referrals(user_identifier: str | int, amount: int) -> tuple[bool, str, dict | None]:
    """
    Admin tomonidan foydalanuvchiga to'g'ridan-to'g'ri referal va ball qo'shish.
    Qaytaradi: (success, message, user_dict)
    """
    user = await find_user_by_id_or_username(user_identifier)
    if not user:
        return False, f"❌ Foydalanuvchi topilmadi: {user_identifier}", None

    uid = user["user_id"]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE bot_users SET
                referral_count = MAX(0, referral_count + ?),
                points = MAX(0, points + ?),
                bonus_points = bonus_points + ?
            WHERE user_id = ?
            """,
            (amount, amount, max(0, amount), uid),
        )
        await db.commit()

        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM bot_users WHERE user_id = ?", (uid,))
        updated_row = await cursor.fetchone()

    updated_dict = dict(updated_row) if updated_row else user
    sign = "+" if amount > 0 else ""
    return True, f"✅ Foydalanuvchi {user.get('first_name', '')} (@{user.get('username') or uid}) ga {sign}{amount} ta referal va ball qo'shildi!", updated_dict


async def manual_add_user_points(user_identifier: str | int, amount: int) -> tuple[bool, str, dict | None]:
    """
    Admin tomonidan foydalanuvchiga to'g'ridan-to'g'ri ball qo'shish.
    Qaytaradi: (success, message, user_dict)
    """
    user = await find_user_by_id_or_username(user_identifier)
    if not user:
        return False, f"❌ Foydalanuvchi topilmadi: {user_identifier}", None

    uid = user["user_id"]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE bot_users SET
                points = MAX(0, points + ?),
                bonus_points = bonus_points + ?
            WHERE user_id = ?
            """,
            (amount, max(0, amount), uid),
        )
        await db.commit()

        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM bot_users WHERE user_id = ?", (uid,))
        updated_row = await cursor.fetchone()

    updated_dict = dict(updated_row) if updated_row else user
    sign = "+" if amount > 0 else ""
    return True, f"✅ Foydalanuvchi {user.get('first_name', '')} ga {sign}{amount} ball qo'shildi!", updated_dict


async def create_promo_code(
    code: str,
    reward_type: str = "points",
    reward_points: int = 2,
    max_uses: int = 50,
) -> bool:
    """Yangi yashirin promokod yaratish (Ball yoki Referal beruvchi)."""
    clean_code = code.strip().upper()
    r_type = "referrals" if reward_type == "referrals" else "points"
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                """
                INSERT INTO promo_codes (code, reward_type, reward_points, max_uses, used_count, is_active)
                VALUES (?, ?, ?, ?, 0, 1)
                ON CONFLICT(code) DO UPDATE SET
                    reward_type = excluded.reward_type,
                    reward_points = excluded.reward_points,
                    max_uses = excluded.max_uses,
                    used_count = 0,
                    is_active = 1
                """,
                (clean_code, r_type, reward_points, max_uses),
            )
            
            cursor = await db.execute("SELECT id FROM promo_codes WHERE code = ?", (clean_code,))
            row = await cursor.fetchone()
            if row:
                promo_id = row[0]
                await db.execute("DELETE FROM promo_claims WHERE promo_id = ?", (promo_id,))
                
            await db.commit()
            return True
        except Exception as e:
            logger.error("Promokod yaratishda xato: %s", e)
            return False


async def update_promo_post_info(code: str, chat_id: int, msg_id: int, html_text: str) -> None:
    """Promokod qaysi kanalga post qilinganini saqlash."""
    clean_code = code.strip().upper()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE promo_codes
            SET post_chat_id = ?, post_msg_id = ?, post_html = ?
            WHERE code = ?
            """,
            (chat_id, msg_id, html_text, clean_code)
        )
        await db.commit()

async def get_promo_by_code(code: str) -> dict | None:
    clean_code = code.strip().upper()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM promo_codes WHERE code = ?", (clean_code,))
        row = await cursor.fetchone()
        return dict(row) if row else None

async def claim_promo_code(user_id: int, code_str: str) -> tuple[bool, str, int, str]:
    """
    Foydalanuvchi promokodni kiritganda tekshirish va ball/referal berish.
    Qaytaradi: (success, message, reward_amount, reward_type)
    """
    clean_code = code_str.strip().upper()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM promo_codes WHERE code = ? AND is_active = 1", (clean_code,))
        promo = await cursor.fetchone()

        if not promo:
            return False, "❌ Bunday promokod mavjud emas yoki muddati tugagan.", 0, "points"

        promo_dict = dict(promo)
        if promo_dict["used_count"] >= promo_dict["max_uses"]:
            return False, f"⚠️ Ushbu promokoddan foydalanish soni ({promo_dict['max_uses']} ta) allaqachon tugagan!", 0, "points"

        # Foydalanuvchi avval ishlatganmi?
        cursor = await db.execute(
            "SELECT 1 FROM promo_claims WHERE promo_id = ? AND user_id = ?",
            (promo_dict["id"], user_id),
        )
        if await cursor.fetchone():
            return False, "⚠️ Siz ushbu promokoddan allaqachon foydalangansiz!", 0, "points"

        reward_type = promo_dict.get("reward_type") or "points"
        pts = promo_dict["reward_points"]

        await db.execute("INSERT INTO promo_claims (promo_id, user_id) VALUES (?, ?)", (promo_dict["id"], user_id))
        await db.execute("UPDATE promo_codes SET used_count = used_count + 1 WHERE id = ?", (promo_dict["id"],))

        if reward_type == "referrals":
            # Referal qo'shish (referral_count + points)
            await db.execute(
                """
                UPDATE bot_users SET
                    referral_count = referral_count + ?,
                    points = points + ?,
                    bonus_points = bonus_points + ?
                WHERE user_id = ?
                """,
                (pts, pts, pts, user_id),
            )
            await db.commit()
            return True, f"🎉 Tabriklaymiz! Promokod faollashtirildi: profilingizga <b>+{pts} ta referal (do'st)</b> qo'shildi! Bu sizga konkurslarda qatnashish imkonini oshiradi! 🚀", pts, "referrals"
        else:
            # Oddiy ball qo'shish
            await db.execute(
                """
                UPDATE bot_users SET
                    points = points + ?,
                    bonus_points = bonus_points + ?
                WHERE user_id = ?
                """,
                (pts, pts, user_id),
            )
            await db.commit()
            return True, f"🎉 Tabriklaymiz! Promokod faollashtirildi: sizga <b>+{pts} ball</b> qo'shildi!", pts, "points"


# ── OMAD G'ILDIRAGI FUNKSIYALARI ──

def _get_uzb_today_str() -> str:
    """Toshkent vaqti bo'yicha YYYY-MM-DD sanani qaytaradi."""
    uzb_now = datetime.now(timezone(timedelta(hours=5)))
    return uzb_now.strftime("%Y-%m-%d")


async def get_user_wheel_status(user_id: int) -> bool:
    """Foydalanuvchi bugun g'ildirakni aylantira oladimi (True = aylantira oladi)."""
    today_str = _get_uzb_today_str()
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT 1 FROM daily_wheel_spins WHERE user_id = ? AND spin_date = ?",
            (user_id, today_str),
        )
        row = await cursor.fetchone()
        return row is None


async def spin_lucky_wheel(user_id: int) -> tuple[bool, str, str, int]:
    """
    Kunlik omad g'ildiragini aylantiradi.
    Qaytaradi: (success, result_message, reward_type, reward_value)
    """
    today_str = _get_uzb_today_str()
    async with aiosqlite.connect(DB_PATH) as db:
        # Avval aylantirganmi tekshirish
        cursor = await db.execute(
            "SELECT 1 FROM daily_wheel_spins WHERE user_id = ? AND spin_date = ?",
            (user_id, today_str),
        )
        if await cursor.fetchone():
            return False, "⏳ Siz bugungi bepul imkoniyatingizdan foydalanib bo'ldingiz. Ertaga yana urinib ko'ring!", "none", 0

        # Yutuqlar ehtimollik jadvali
        # 1: +1 ball (40%)
        # 2: +2 ball (25%)
        # 3: +1 bepul referal (15%)
        # 4: +3 ball (10%)
        # 5: Omadli Chipta / +5 ball (5%)
        # 6: 0 ball (5%)
        outcomes = [
            ("points", 1, "🎯 <b>+1 Ball</b> yutib oldingiz!", 40),
            ("points", 2, "🚀 <b>+2 Ball</b> yutib oldingiz!", 25),
            ("referrals", 1, "👥 <b>+1 Bepul Referal (Do'st)</b> yutib oldingiz!", 15),
            ("points", 3, "🌟 <b>+3 Ball</b> yutib oldingiz!", 10),
            ("points", 5, "🎟 <b>Omadli Chipta (+5 Ball)</b> yutib oldingiz! Super!", 5),
            ("none", 0, "🔄 <b>Omadingiz kelmadi!</b> Ertaga albatta urinib ko'ring.", 5),
        ]

        population = [i for i in range(len(outcomes))]
        weights = [o[3] for o in outcomes]
        chosen_idx = random.choices(population, weights=weights, k=1)[0]
        r_type, r_val, r_msg, _ = outcomes[chosen_idx]

        # Yutuqni bazaga kiritish
        await db.execute(
            """
            INSERT INTO daily_wheel_spins (user_id, spin_date, reward_type, reward_value)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, today_str, r_type, r_val),
        )

        if r_type == "points" and r_val > 0:
            await db.execute(
                "UPDATE bot_users SET points = points + ?, bonus_points = bonus_points + ? WHERE user_id = ?",
                (r_val, r_val, user_id),
            )
        elif r_type == "referrals" and r_val > 0:
            await db.execute(
                """
                UPDATE bot_users SET
                    referral_count = referral_count + ?,
                    points = points + ?,
                    bonus_points = bonus_points + ?
                WHERE user_id = ?
                """,
                (r_val, r_val, r_val, user_id),
            )

        await db.commit()
        return True, r_msg, r_type, r_val


# ── HAFTALIK LIDERLAR REYTINGI ──

async def get_weekly_top_referrers(limit: int = 10) -> list[dict]:
    """Oxirgi 7 kundagi eng faol referal taklif qilgan liderlar."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT u.user_id, u.username, u.first_name, COUNT(r.id) as weekly_refs, u.points, u.vip_status
            FROM referrals r
            JOIN bot_users u ON r.referrer_id = u.user_id
            WHERE r.status = 'active' AND r.created_at >= datetime('now', '-7 days')
            GROUP BY r.referrer_id
            ORDER BY weekly_refs DESC, u.points DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = await cursor.fetchall()
        if rows:
            return [dict(r) for r in rows]

        # Agar oxirgi 7 kunda bo'lmasa, umumiy topdan oladi
        cursor = await db.execute(
            """
            SELECT user_id, username, first_name, referral_count as weekly_refs, points, vip_status
            FROM bot_users
            WHERE referral_count > 0
            ORDER BY referral_count DESC, points DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


# ── GURUH FAOLLIGI VA "TAG ALL" TIZIMI ──

async def update_group_member(chat_id: int, user_id: int, first_name: str, username: str = None) -> None:
    """Guruh foydalanuvchilarini ro'yxatga olish (yoki oxirgi faolligini yangilash)."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO group_members (chat_id, user_id, first_name, username, last_active)
            VALUES (?, ?, ?, ?, datetime('now'))
            ON CONFLICT(chat_id, user_id) DO UPDATE SET 
                first_name = excluded.first_name,
                username = excluded.username,
                last_active = datetime('now')
        """, (chat_id, user_id, first_name, username))
        await db.commit()


async def get_group_members(chat_id: int) -> list[dict]:
    """Berilgan guruhning barcha a'zolarini qaytaradi (Tag All uchun)."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT user_id, first_name, username 
            FROM group_members 
            WHERE chat_id = ?
            ORDER BY last_active DESC
        """, (chat_id,))
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def record_group_chat_activity(user_id: int, chat_id: int) -> tuple[bool, int, int]:
    """
    Guruhda yozilgan xabarni qayd qiladi.
    Har 15 ta xabar uchun avtomatik +1 ball beradi.
    Qaytaradi: (awarded_bonus_now: bool, current_msg_count: int, total_points_earned: int)
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM group_chat_activity WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id),
        )
        row = await cursor.fetchone()

        if not row:
            await db.execute(
                """
                INSERT INTO group_chat_activity (user_id, chat_id, msg_count, total_points_earned)
                VALUES (?, ?, 1, 0)
                """,
                (user_id, chat_id),
            )
            await db.commit()
            return False, 1, 0

        act = dict(row)
        new_count = act["msg_count"] + 1
        awarded = False
        total_earned = act.get("total_points_earned", 0)

        # Har 15 ta xabarda +1 ball
        if new_count >= 15:
            new_count = 0
            total_earned += 1
            awarded = True
            await db.execute(
                "UPDATE bot_users SET points = points + 1, bonus_points = bonus_points + 1 WHERE user_id = ?",
                (user_id,),
            )

        await db.execute(
            """
            UPDATE group_chat_activity SET
                msg_count = ?,
                total_points_earned = ?,
                last_msg_at = datetime('now')
            WHERE user_id = ? AND chat_id = ?
            """,
            (new_count, total_earned, user_id, chat_id),
        )
        await db.commit()
        return awarded, new_count, total_earned


# ─────────────────────────────────────────────
# DINAMIK KONKURSLAR VA ISHTIROKCHILAR
# ─────────────────────────────────────────────

async def create_contest(
    title: str,
    contest_type: str,
    min_referrals: int,
    prize_description: str,
) -> int:
    """Yangi konkurs yaratadi va ID sini qaytaradi."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            INSERT INTO contests (title, contest_type, min_referrals, prize_description, is_active)
            VALUES (?, ?, ?, ?, 1)
            """,
            (title, contest_type, min_referrals, prize_description),
        )
        await db.commit()
        return cursor.lastrowid


async def get_active_contests() -> list[dict]:
    """Hozirgi barcha faol konkurslar ro'yxatini qaytaradi."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM contests WHERE is_active = 1 ORDER BY id DESC"
        )
        rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def get_contest(contest_id: int) -> dict | None:
    """Aynan bitta konkurs ma'lumotlarini oladi."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM contests WHERE id = ?", (contest_id,))
        row = await cursor.fetchone()
        if not row:
            return None
        return dict(row)


async def register_user_for_contest(contest_id: int, user_id: int) -> tuple[bool, str, int | None]:
    """
    Foydalanuvchini konkursga ro'yxatdan o'tkazadi.
    1. Konkurs faolligi tekshiriladi.
    2. Foydalanuvchining faol referallari soni yetarliligi (min_referrals) tekshiriladi.
    3. Allaqachon qatnashgan bo'lsa chiptasi ko'rsatiladi.
    4. Muvaffaqiyatli bo'lsa yangi unikal chipta raqami beriladi.
    """
    contest = await get_contest(contest_id)
    if not contest or not contest["is_active"]:
        return False, "⚠️ Ushbu konkurs yakunlangan yoki mavjud emas.", None

    user = await get_user_profile(user_id)
    user_ref_count = user["referral_count"] if user else 0
    min_refs = contest["min_referrals"]

    # Referallar soni yetarlimi? (Faqat min_refs > 0 bo'lganda tekshiriladi)
    if min_refs > 0 and user_ref_count < min_refs:
        needed = min_refs - user_ref_count
        return (
            False,
            f"⚠️ <b>Ushbu konkursda qatnashish uchun kamida {min_refs} ta do'stingizni taklif qilgan bo'lishingiz kerak!</b>\n\n"
            f"📊 Sizning hozirgi referallaringiz: <b>{user_ref_count} ta</b>\n"
            f"🎯 Qatnashish uchun yana <b>{needed} ta</b> do'st taklif qilishingiz kerak.\n\n"
            f"Pastdagi «🚀 Do'stlarga ulashish» tugmasi orqali do'stlaringizni taklif qiling!",
            None,
        )

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        # Allaqachon qatnashganmi?
        cursor = await db.execute(
            "SELECT ticket_number FROM contest_participants WHERE contest_id = ? AND user_id = ?",
            (contest_id, user_id),
        )
        existing = await cursor.fetchone()
        if existing:
            return True, f"✅ Siz ushbu konkursda allaqachon ro'yxatdan o'tgansiz!\n🎟 Sizning chiptangiz: <b>#{existing['ticket_number']}</b>", existing["ticket_number"]

        # Yangi chipta raqami
        cursor = await db.execute(
            "SELECT COUNT(*) FROM contest_participants WHERE contest_id = ?",
            (contest_id,),
        )
        count = (await cursor.fetchone())[0]
        ticket_number = count + 1

        await db.execute(
            """
            INSERT INTO contest_participants (contest_id, user_id, ticket_number)
            VALUES (?, ?, ?)
            """,
            (contest_id, user_id, ticket_number),
        )
        await db.commit()

        return (
            True,
            f"🎉 <b>Tabriklaymiz! Siz konkursda muvaffaqiyatli ro'yxatdan o'tdingiz!</b>\n\n"
            f"🏆 Konkurs: <b>{contest['title']}</b>\n"
            f"🎟 Sizning omadli chipta raqamingiz: <b>#{ticket_number}</b>\n\n"
            f"Omad tilaymiz! G'oliblar konkurs yakunida bot orqali e'lon qilinadi.",
            ticket_number,
        )


async def get_contest_participants(contest_id: int) -> list[dict]:
    """Konkursda qatnashayotgan barcha foydalanuvchilar va ularning ballarini oladi."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT
                p.ticket_number,
                p.joined_at,
                u.user_id,
                u.username,
                u.first_name,
                u.points,
                u.referral_count,
                IFNULL(cs.extra_tickets, 0) as extra_tickets
            FROM contest_participants p
            JOIN bot_users u ON p.user_id = u.user_id
            LEFT JOIN comment_streaks cs ON p.user_id = cs.user_id
            WHERE p.contest_id = ?
            ORDER BY p.ticket_number ASC
            """,
            (contest_id,),
        )
        rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def end_contest(contest_id: int, winners_data: list[dict] | dict | None = None) -> bool:
    """Konkursni yakunlangan deb belgilaydi va g'oliblar ro'yxatini saqlaydi."""
    import json
    w_json = json.dumps(winners_data) if winners_data is not None else None
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE contests SET is_active = 0, winners_data = ?, ended_at = datetime('now') WHERE id = ?",
            (w_json, contest_id),
        )
        await db.commit()
    
    await reset_all_comment_tickets()
    return True


async def get_contest_participants_count(contest_id: int) -> int:
    """Konkurs qatnashuvchilari sonini qaytaradi (Live counter uchun)."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM contest_participants WHERE contest_id = ?",
            (contest_id,),
        )
        row = await cursor.fetchone()
        return row[0] if row else 0


async def save_contest_channel_post(contest_id: int, chat_id: int | str, message_id: int) -> None:
    """Kanalga yuborilgan konkurs postini saqlaydi (Live counter yangilab turish uchun)."""
    import json
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT post_messages FROM contests WHERE id = ?", (contest_id,))
        row = await cursor.fetchone()
        raw = row["post_messages"] if row and row["post_messages"] else "[]"
        try:
            posts = json.loads(raw)
        except Exception:
            posts = []
        posts.append({"chat_id": str(chat_id), "message_id": message_id})
        await db.execute("UPDATE contests SET post_messages = ? WHERE id = ?", (json.dumps(posts), contest_id))
        await db.commit()


async def get_contest_channel_posts(contest_id: int) -> list[dict]:
    """Konkurs uchun kanal postlari ro'yxatini qaytaradi."""
    import json
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT post_messages FROM contests WHERE id = ?", (contest_id,))
        row = await cursor.fetchone()
        if not row or not row["post_messages"]:
            return []
        try:
            return json.loads(row["post_messages"])
        except Exception:
            return []


async def get_all_bot_user_ids() -> list[int]:
    """Barcha bot foydalanuvchilarining ID lari (broadcast uchun)."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT user_id FROM bot_users")
        rows = await cursor.fetchall()
    return [r[0] for r in rows]


# ─────────────────────────────────────────────
# ADMIN STATISTIKASI
# ─────────────────────────────────────────────

async def get_admin_stats() -> dict:
    """Admin panel uchun to'liq statistika."""
    async with aiosqlite.connect(DB_PATH) as db:
        # Jami bot foydalanuvchilari
        cursor = await db.execute("SELECT COUNT(*) FROM bot_users")
        total_bot_users = (await cursor.fetchone())[0]

        # Jami faol referallar
        cursor = await db.execute("SELECT COUNT(*) FROM referrals WHERE status = 'active'")
        total_active_referrals = (await cursor.fetchone())[0]

        # Jami faolliklar (reaksiya, kament)
        cursor = await db.execute("SELECT COUNT(*) FROM activity")
        total_activities = (await cursor.fetchone())[0]

        # Ulangan kanallar va guruhlar
        cursor = await db.execute("SELECT COUNT(*) FROM linked_chats WHERE chat_type = 'channel'")
        total_channels = (await cursor.fetchone())[0]

        cursor = await db.execute("SELECT COUNT(*) FROM linked_chats WHERE chat_type = 'group'")
        total_groups = (await cursor.fetchone())[0]

        # Majburiy kanallar soni
        cursor = await db.execute("SELECT COUNT(*) FROM mandatory_channels")
        total_mandatory = (await cursor.fetchone())[0]

        # Faol konkurslar soni
        cursor = await db.execute("SELECT COUNT(*) FROM contests WHERE is_active = 1")
        active_contests = (await cursor.fetchone())[0]

    return {
        "total_users": total_bot_users,
        "total_active_referrals": total_active_referrals,
        "total_activities": total_activities,
        "total_channels": total_channels,
        "total_groups": total_groups,
        "total_mandatory": total_mandatory,
        "active_contests": active_contests,
    }


# ─────────────────────────────────────────────
# 🎂 TUG'ILGAN KUN HISOB-KITOBI VA TIZIMI
# ─────────────────────────────────────────────

UZB_MONTH_NAMES = {
    1: "yanvar", 2: "fevral", 3: "mart", 4: "aprel", 5: "may", 6: "iyun",
    7: "iyul", 8: "avgust", 9: "sentyabr", 10: "oktyabr", 11: "noyabr", 12: "dekabr",
}

UZB_MONTH_NUMBERS = {
    "yanvar": 1, "fevral": 2, "mart": 3, "aprel": 4, "may": 5, "iyun": 6,
    "iyul": 7, "avgust": 8, "sentyabr": 9, "oktyabr": 10, "noyabr": 11, "dekabr": 12,
    "yan": 1, "fev": 2, "mar": 3, "apr": 4, "iyul": 7, "avg": 8, "sen": 9, "okt": 10, "noy": 11, "dek": 12,
    "январь": 1, "февраль": 2, "март": 3, "апрель": 4, "май": 5, "июнь": 6,
    "июль": 7, "август": 8, "сентябрь": 9, "октябрь": 10, "ноябрь": 11, "декабрь": 12,
}


def parse_birthday_string(text: str) -> tuple[int, int, str] | None:
    """
    Turli formatdagi tug'ilgan kun matnini tahlil qiladi.
    Formatlar:
    - 15.08, 15/08, 15-08
    - 15.08.2000, 2000-08-15
    - 15-avgust, 15 avgust, 15 avg
    Qaytaradi: (day: int, month: int, formatted_str: str) masalan (15, 8, "15-avgust")
    """
    if not text:
        return None

    cleaned = text.strip().lower()

    # 1. So'zli format: "15 avgust" yoki "15-avgust"
    import re
    word_match = re.match(r"^(\d{1,2})[\s\-_/\.]([a-zA-Zа-яА-ЯёЁ\']+)", cleaned)
    if word_match:
        d = int(word_match.group(1))
        m_word = word_match.group(2).strip()
        m = UZB_MONTH_NUMBERS.get(m_word)
        if m and 1 <= d <= 31:
            try:
                # Sananing to'g'riligini tekshirish (masalan 31 fevral xato)
                datetime(2024, m, d)
                m_name = UZB_MONTH_NAMES[m]
                return d, m, f"{d}-{m_name}"
            except ValueError:
                return None

    # 2. Raqamli format: "15.08" yoki "15.08.2000" yoki "15-08" yoki "15/08"
    parts = re.split(r"[\.\-/\s]+", cleaned)
    if len(parts) >= 2:
        try:
            if len(parts[0]) == 4:
                # "2000-08-15" (ISO format)
                d = int(parts[2])
                m = int(parts[1])
            else:
                # "15.08" yoki "15.08.2000"
                d = int(parts[0])
                m = int(parts[1])

            if 1 <= d <= 31 and 1 <= m <= 12:
                datetime(2024, m, d)
                m_name = UZB_MONTH_NAMES[m]
                return d, m, f"{d}-{m_name}"
        except Exception:
            return None

    return None


def calculate_days_until_birthday(day: int, month: int) -> int:
    """O'zbekiston vaqti (UTC+5) bilan keyingi tug'ilgan kungacha necha kun qolganini hisoblaydi."""
    uzb_now = datetime.now(timezone(timedelta(hours=5)))
    today_date = uzb_now.date()
    current_year = today_date.year

    try:
        bday_this_year = datetime(current_year, month, day).date()
    except ValueError:
        # Masalan 29-fevral kabisa bo'lmagan yilda
        bday_this_year = datetime(current_year, 2, 28).date()

    if bday_this_year < today_date:
        next_year = current_year + 1
        try:
            bday_next = datetime(next_year, month, day).date()
        except ValueError:
            bday_next = datetime(next_year, 2, 28).date()
        return (bday_next - today_date).days
    else:
        return (bday_this_year - today_date).days


async def set_user_birthday(user_id: int, birthday_str: str) -> bool:
    """Foydalanuvchining tug'ilgan kunini bazaga saqlaydi."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "UPDATE bot_users SET birthday = ? WHERE user_id = ?",
            (birthday_str, user_id),
        )
        await db.commit()
        return cursor.rowcount > 0


async def get_user_birthday(user_id: int) -> str | None:
    """Foydalanuvchining tug'ilgan kunini oladi."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT birthday FROM bot_users WHERE user_id = ? LIMIT 1",
            (user_id,),
        )
        row = await cursor.fetchone()
    return row[0] if row and row[0] else None


async def get_birthday_insights(limit: int = 5) -> tuple[list[dict], list[dict]]:
    """
    Bugun tug'ilgan kun egalarini va eng yaqin kelayotgan tug'ilgan kunlar (Top-N) hisoblagichini qaytaradi.
    Qaytaradi: (today_birthdays, upcoming_birthdays)
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT user_id, username, first_name, birthday FROM bot_users WHERE birthday IS NOT NULL AND birthday != ''"
        )
        rows = await cursor.fetchall()

    today_list = []
    upcoming_list = []

    for r in rows:
        bday_str = r["birthday"]
        parsed = parse_birthday_string(bday_str)
        if not parsed:
            continue
        d, m, fmt_date = parsed
        days_left = calculate_days_until_birthday(d, m)

        user_info = {
            "user_id": r["user_id"],
            "username": r["username"],
            "first_name": r["first_name"],
            "birthday_str": fmt_date,
            "days_left": days_left,
            "day": d,
            "month": m,
        }

        if days_left == 0:
            today_list.append(user_info)
        else:
            upcoming_list.append(user_info)

    # Yaqinlik bo'yicha saralash
    upcoming_list.sort(key=lambda x: x["days_left"])

    return today_list, upcoming_list[:limit]


# ── VAZIFALAR MARKAZI (TASKS) FUNKSIYALARI ──

async def add_task(channel_id: str, channel_title: str, channel_url: str, reward_points: int) -> bool:
    """Yangi vazifa (kanal obunasi) qo'shish."""
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                "INSERT INTO tasks (channel_id, channel_title, channel_url, reward_points, is_active) VALUES (?, ?, ?, ?, 1)",
                (channel_id, channel_title, channel_url, reward_points)
            )
            await db.commit()
            return True
        except Exception:
            return False

async def get_active_tasks() -> list[dict]:
    """Barcha faol vazifalarni olish."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM tasks WHERE is_active = 1 ORDER BY id ASC")
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

async def get_all_tasks() -> list[dict]:
    """Barcha vazifalarni olish (admin uchun)."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM tasks ORDER BY id ASC")
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

async def delete_task(task_id: int) -> bool:
    """Vazifani o'chirish."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        await db.execute("DELETE FROM user_tasks WHERE task_id = ?", (task_id,))
        await db.commit()
        return True

async def check_user_task_completed(user_id: int, task_id: int) -> bool:
    """Foydalanuvchi bu vazifani bajarganligini tekshirish."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT 1 FROM user_tasks WHERE user_id = ? AND task_id = ?", (user_id, task_id))
        row = await cursor.fetchone()
        return bool(row)

async def mark_user_task_completed(user_id: int, task_id: int) -> bool:
    """Vazifani bajarilgan deb belgilash."""
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute("INSERT INTO user_tasks (user_id, task_id) VALUES (?, ?)", (user_id, task_id))
            await db.commit()
            return True
        except Exception:
            return False

async def reset_weekly_leaderboard() -> None:
    """Haftalik reytingni noldan boshlash (weekly_refs ni 0 qilish)."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE bot_users SET weekly_refs = 0")
        await db.commit()


# ── TOLIBJON TOP STREAK LOGIC ──

async def process_tolibjon_comment(user_id: int, post_id: int) -> dict:
    """
    Foydalanuvchining 'Tolibjon Top' kamentini post bazasida hisoblaydi.
    Qaytaradi dict status bilan.
    """
    import datetime
    
    def _get_uzb_today() -> datetime.date:
        return (datetime.datetime.utcnow() + datetime.timedelta(hours=5)).date()
        
    today = _get_uzb_today()
    today_str = today.isoformat()

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        
        # 1. Bitta postga 1 marta yoza olishini tekshiramiz
        try:
            await db.execute(
                "INSERT INTO tolibjon_post_logs (user_id, post_id, created_at) VALUES (?, ?, ?)",
                (user_id, post_id, today_str)
            )
        except aiosqlite.IntegrityError:
            # Allaqachon yozgan bu postga
            return {"status": "already_commented_on_post"}
            
        # 2. Streak tekshiruvi
        cursor = await db.execute("SELECT * FROM comment_streaks WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        
        if not row:
            await db.execute(
                "INSERT INTO comment_streaks (user_id, streak_days, last_comment_date, daily_count, extra_tickets) VALUES (?, 1, ?, 1, 0)",
                (user_id, today_str)
            )
            await db.commit()
            return {"status": "first_comment_today", "streak": 1, "points_added": 0}
            
        last_date = row["last_comment_date"]
        streak_days = row["streak_days"]
        extra_tickets = row["extra_tickets"]
        
        if last_date == today_str:
            # Bugun boshqa postda yozgan, shuning uchun bu post uchun +5 ball
            await db.execute("UPDATE bot_users SET points = points + 5 WHERE user_id = ?", (user_id,))
            await db.commit()
            return {"status": "extra_points", "points_added": 5, "streak": streak_days}
            
        # Kecha yoki oldinroq yozgan
        if last_date:
            last_date_obj = datetime.date.fromisoformat(last_date)
            missed_days = (today - last_date_obj).days - 1
            if missed_days > 0:
                streak_days = max(0, streak_days - missed_days)
        
        streak_days += 1
        
        if streak_days >= 15:
            extra_tickets += 1
            streak_days = 0
            res_status = "ticket_earned"
        else:
            res_status = "first_comment_today"
            
        await db.execute(
            "UPDATE comment_streaks SET streak_days = ?, last_comment_date = ?, daily_count = 1, extra_tickets = ? WHERE user_id = ?",
            (streak_days, today_str, extra_tickets, user_id)
        )
        await db.commit()
        return {"status": res_status, "streak": streak_days, "points_added": 0}

async def get_user_extra_tickets(user_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT extra_tickets FROM comment_streaks WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        return row[0] if row else 0

async def reset_all_comment_tickets() -> None:
    """Konkurs yakunlangach barcha chiptalar va streaklarni nollaydi"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE comment_streaks SET extra_tickets = 0, streak_days = 0")
        await db.commit()
