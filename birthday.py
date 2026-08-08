"""
birthday.py — Tug'ilgan kun hisoblagichi, guruhlar uchun kunlik e'lon va tabriklar moduli.
O'zbekiston vaqti (UTC+5) bo'yicha hisob-kitob qiladi.
"""

import logging
import html
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from database import (
    get_birthday_insights,
    get_all_linked_chats,
    get_user_birthday,
    parse_birthday_string,
    calculate_days_until_birthday,
)

logger = logging.getLogger(__name__)


def build_daily_birthday_group_post(
    bot_username: str,
    today_list: list[dict],
    upcoming_list: list[dict],
) -> tuple[str, InlineKeyboardMarkup]:
    """
    Guruhlar uchun kunlik tug'ilgan kun xabari va countdown postini tayyorlaydi.
    """
    lines = []

    # 1. Bugun tug'ilgan kun egalari
    if today_list:
        lines.append("🎂🎉 <b>BUGUN TUG'ILGAN KUN!</b> 🎉🎂")
        lines.append("━━━━━━━━━━━━━━━━━━━━━")
        for u in today_list:
            safe_name = html.escape(u["first_name"])
            u_link = f'<a href="tg://user?id={u["user_id"]}">{safe_name}</a>'
            lines.append(f"⭐️ Bugun <b>{u_link}</b> ning tavallud ayyomi! 🥳")
        lines.append("\n<i>Chin qalbimizdan tabriklaymiz! Sizga mustahkam sog'liq, ulkan muvaffaqiyat va baxt tilaymiz! 🎁✨</i>")
        lines.append("━━━━━━━━━━━━━━━━━━━━━\n")
    else:
        lines.append("🎂 <b>TUG'ILGAN KUNLAR HISOBLAGICHI</b> ⏳")
        lines.append("━━━━━━━━━━━━━━━━━━━━━")

    # 2. Eng yaqin tug'ilgan kunlar (Top-5)
    if upcoming_list:
        lines.append("⏳ <b>Yaqinlashib kelayotgan tug'ilgan kunlar:</b>\n")
        medals = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]
        for idx, u in enumerate(upcoming_list):
            m_icon = medals[idx] if idx < len(medals) else "🔹"
            safe_name = html.escape(u["first_name"])
            u_link = f'<a href="tg://user?id={u["user_id"]}">{safe_name}</a>'
            days = u["days_left"]

            if days == 1:
                day_label = "<b>Ertaga!</b>"
            elif days == 2:
                day_label = "<b>Indinga! (2 kundan so'ng)</b>"
            else:
                day_label = f"<b>{days} kundan so'ng</b>"

            lines.append(f"{m_icon} {u_link} — {day_label} ({u['birthday_str']})")
    else:
        lines.append("<i>Hozircha yaqin kunlarda tug'ilgan kunlar kiritilmagan.</i>")

    lines.append("\n━━━━━━━━━━━━━━━━━━━━━")
    lines.append("💡 <i>Siz ham o'z sanangizni botda belgilang!</i>")

    # Inline tugma: Men ham kiritish
    bot_url = f"https://t.me/{bot_username}?start=birthday" if bot_username else "https://t.me/"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎂 Mening tug'ilgan kunim ↗️", url=bot_url)],
    ])

    return "\n".join(lines), kb


async def broadcast_daily_birthdays(bot: Bot, bot_username: str) -> None:
    """Barcha ulangan guruhlarga kunlik tug'ilgan kun postini e'lon qiladi."""
    try:
        today_list, upcoming_list = await get_birthday_insights(limit=5)
        # Agar na bugun va na yaqin orada hech kim bo'lmasa, guruhlarni bezovta qilmaymiz
        if not today_list and not upcoming_list:
            return

        post_text, kb = build_daily_birthday_group_post(bot_username, today_list, upcoming_list)
        all_chats = await get_all_linked_chats()
        group_chats = [c for c in all_chats if c["chat_type"] == "group"]

        for g in group_chats:
            try:
                await bot.send_message(
                    chat_id=g["chat_id"],
                    text=post_text,
                    parse_mode="HTML",
                    reply_markup=kb,
                    disable_web_page_preview=True,
                )
            except Exception as e:
                logger.warning("Guruhga tug'ilgan kun xabarini yuborishda xato (%s): %s", g["chat_id"], e)
    except Exception as e:
        logger.error("Kunlik tug'ilgan kun xabarnomasida xatolik: %s", e)
