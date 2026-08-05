"""
winner.py — G'olib tanlash va e'lon qilish logikasi.
Haftalik va oylik konkurslar uchun tasodifiy g'olib aniqlaydi.
"""

import logging
import random
from aiogram import Bot

from config import CHAT_ID, ADMIN_ID
from database import get_active_users
from membership import check_membership

logger = logging.getLogger(__name__)


def _format_weekly_winner(user: dict) -> str:
    """Haftalik g'olib uchun HTML formatdagi post matni."""
    user_id = user["user_id"]
    first_name = user["first_name"]

    return (
        "🎉 <b>HAFTALIK G'OLIB E'LON QILINDI!</b> 🎉\n"
        "\n"
        f'Tabriklaymiz, <a href="tg://user?id={user_id}">{first_name}</a>! 🏆\n'
        "\n"
        "Siz shu hafta eng faol a'zolardan biri bo'ldingiz va tasodifiy tanlov "
        "natijasida g'olib deb topildingiz! 🎁\n"
        "\n"
        "Sovg'angizni olish uchun admin bilan bog'laning 👇\n"
        f'<a href="tg://user?id={ADMIN_ID}">Admin</a>\n'
        "\n"
        "Barchaga rahmat, faollikni davom ettiramiz! 💪"
    )


def _format_monthly_winner(user: dict) -> str:
    """Oylik g'olib uchun HTML formatdagi post matni."""
    user_id = user["user_id"]
    first_name = user["first_name"]

    return (
        "🎉 <b>OYLIK G'OLIB — TELEGRAM PREMIUM YUTDINGIZ! 💎</b> 🎉\n"
        "\n"
        f'Tabriklaymiz, <a href="tg://user?id={user_id}">{first_name}</a>! 🏆\n'
        "\n"
        "Siz shu oy eng faol a'zolardan biri bo'ldingiz va tasodifiy tanlov "
        "natijasida g'olib deb topildingiz! 🎁\n"
        "\n"
        "Sovg'angizni olish uchun admin bilan bog'laning 👇\n"
        f'<a href="tg://user?id={ADMIN_ID}">Admin</a>\n'
        "\n"
        "Barchaga rahmat, faollikni davom ettiramiz! 💪"
    )


async def pick_winner(bot: Bot, days: int, period: str) -> None:
    """
    Berilgan kun oralig'ida faol va eligible bo'lgan foydalanuvchilar
    orasidan tasodifiy g'olib tanlaydi va chatga e'lon qiladi.

    :param bot: Aiogram Bot instansiya
    :param days: Necha kunlik oraliq (7 = haftalik, 30 = oylik)
    :param period: "haftalik" yoki "oylik" — format tanlash uchun
    """
    # 1. Faol foydalanuvchilarni bazadan olish
    active_users = await get_active_users(days=days)

    if not active_users:
        await bot.send_message(
            chat_id=ADMIN_ID,
            text=f"⚠️ Bu {'hafta' if period == 'haftalik' else 'oy'} "
                 f"shartlarga javob beruvchi faol a'zo topilmadi.",
        )
        logger.warning("Faol foydalanuvchilar topilmadi (%s, %d kun).", period, days)
        return

    # 2. Har birining a'zoligini tekshirish
    eligible_users: list[dict] = []
    for user in active_users:
        is_member = await check_membership(bot, user["user_id"])
        if is_member:
            eligible_users.append(user)

    if not eligible_users:
        await bot.send_message(
            chat_id=ADMIN_ID,
            text=f"⚠️ Bu {'hafta' if period == 'haftalik' else 'oy'} "
                 f"faol a'zolardan hech biri ikki guruhga ham a'zo emas.",
        )
        logger.warning("Eligible foydalanuvchilar topilmadi (%s).", period)
        return

    # 3. Tasodifiy g'olib tanlash
    winner = random.choice(eligible_users)
    logger.info(
        "%s g'olibI tanlandi: user_id=%s, first_name=%s",
        period.upper(), winner["user_id"], winner["first_name"],
    )

    # 4. E'lon postini chatga yuborish
    if period == "haftalik":
        text = _format_weekly_winner(winner)
    else:
        text = _format_monthly_winner(winner)

    await bot.send_message(chat_id=CHAT_ID, text=text, parse_mode="HTML")
    logger.info("%s g'olib e'lon qilindi chatga (CHAT_ID=%s).", period, CHAT_ID)
