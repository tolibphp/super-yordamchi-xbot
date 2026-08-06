"""
contest.py — Smart Viral Contest tizimi va g'oliblarni aniqlash (Draw) logikasi.

Funksiyalar:
- build_contest_post_content: Kanal/Guruhga yuboriladigan chiroyli konkurs e'lon posti
- build_share_data: 1-bosishda do'stlarga va guruhlarga ulashish (One-click share)
- draw_contest_winners: Top-1 va Random g'oliblarni aniqlash va rasmiy e'lon matnini tayyorlash
"""

import random
import logging
import html
import urllib.parse
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from database import (
    get_contest,
    get_contest_participants,
    end_contest,
)

logger = logging.getLogger(__name__)


def build_share_data(bot_username: str, user_id: int) -> tuple[str, str]:
    """
    Foydalanuvchi uchun 1-bosishda ulashish (Share URL) va tayyor reklama matnini yaratadi.
    Qaytaradi: (share_url, post_text)
    """
    ref_link = f"https://t.me/{bot_username}?start=ref_{user_id}"

    post_text = (
        "🔥 <b>Ajoyib Konkursda Qatnashing va Qimmatbaho Sovrinlarni Yuting!</b> 🎁\n\n"
        "💎 <b>Telegram Premium</b> va maxsus sovg'alar yutib olish imkoniyati!\n"
        "🚀 Shunchaki quyidagi havola orqali botga o'ting va kanalga a'zo bo'ling:\n\n"
        f"👉 <b>Qatnashish uchun bosing:</b>\n{ref_link}"
    )

    encoded_text = urllib.parse.quote(
        f"🔥 Ajoyib Konkursda qatnashing va Telegram Premium yutib oling! 🎁\n\n👉 {ref_link}"
    )
    share_url = f"https://t.me/share/url?url={urllib.parse.quote(ref_link)}&text={encoded_text}"

    return share_url, post_text


def build_contest_post_content(bot_username: str, contest: dict) -> tuple[str, InlineKeyboardMarkup]:
    """
    Kanalga yoki guruhga joylanadigan konkurs e'lon postining matni va tugmasini tayyorlaydi.
    """
    title = contest["title"]
    c_type = contest["contest_type"]
    min_refs = contest["min_referrals"]
    prize = contest["prize_description"] or "Qimmatbaho sovg'alar va Telegram Premium!"

    badge = "💎 TELEGRAM PREMIUM" if c_type == "premium" else ("🎁 TELEGRAM GIFT" if c_type == "gift" else "🎯 MAXSUS")

    text = (
        f"🚀 <b>YANGI VIRAL KONKURS BOSHLANDI!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🏆 <b>Konkurs:</b> {title}\n"
        f"🎖 <b>Toifa:</b> {badge}\n"
        f"🎁 <b>Sovg'a:</b> {prize}\n\n"
        f"📌 <b>QATNASHISH SHARTLARI:</b>\n"
        f"1️⃣ Kanalimizga to'liq a'zo bo'lish\n"
        f"2️⃣ Kamida <b>{min_refs} ta</b> do'stingizni taklif qilish\n\n"
        f"🔥 <b>G'oliblarni aniqlash:</b>\n"
        f"🥇 <b>1-O'rin (Top Referal):</b> Eng ko'p do'st taklif qilgan ishtirokchiga!\n"
        f"🎲 <b>Random Yutuq:</b> Shartni bajargan barcha ishtirokchilar orasidan tasodifiy omadli g'olibga!\n\n"
        f"👇 <b>Hoziroq pastdagi tugmani bosib qatnashing:</b>"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="🎁 Konkursda Qatnashish",
                url=f"https://t.me/{bot_username}?start=contest_{contest['id']}",
            )
        ],
        [
            InlineKeyboardButton(
                text="🚀 Do'stlarni taklif qilish",
                url=f"https://t.me/{bot_username}?start=share",
            )
        ],
    ])

    return text, kb


async def draw_contest_winners(bot: Bot, contest_id: int) -> dict:
    """
    Konkurs g'oliblarini aniqlaydi:
    1. Top Referral Winner (Eng ko'p faol odam chaqirgan qatnashuvchi)
    2. Random Lucky Winner (Shartni bajarganlar orasidan tasodifiy tanlash)
    Konkursni yakunlaydi va e'lon matnini tayyorlaydi.
    """
    contest = await get_contest(contest_id)
    if not contest:
        return {"success": False, "error": "Konkurs topilmadi"}

    participants = await get_contest_participants(contest_id)
    if not participants:
        await end_contest(contest_id)
        return {
            "success": False,
            "error": "Konkursda hech qanday ishtirokchi ro'yxatdan o'tmagan.",
        }

    # 1. Top Referral g'olibi (referral_count yoki points bo'yicha eng yuqori)
    sorted_by_ref = sorted(
        participants,
        key=lambda p: (p.get("referral_count", 0), p.get("points", 0)),
        reverse=True,
    )
    top_winner = sorted_by_ref[0]

    # 2. Random g'olib (agar bir nechta ishtirokchi bo'lsa, top winnerdan boshqasi tanlanadi)
    remaining = [p for p in participants if p["user_id"] != top_winner["user_id"]]
    if remaining:
        random_winner = random.choice(remaining)
    else:
        random_winner = top_winner

    # Konkursni yakunlash
    await end_contest(contest_id)

    # Chiroyli e'lon matni
    top_name = html.escape(top_winner["first_name"] or "Noma'lum")
    top_user_tag = f"@{top_winner['username']}" if top_winner["username"] else f'<a href="tg://user?id={top_winner["user_id"]}">{top_name}</a>'

    rand_name = html.escape(random_winner["first_name"] or "Noma'lum")
    rand_user_tag = f"@{random_winner['username']}" if random_winner["username"] else f'<a href="tg://user?id={random_winner["user_id"]}">{rand_name}</a>'

    title = contest["title"]
    prize = contest["prize_description"] or "Sovrin"

    announcement_text = (
        f"🏆 <b>KONKURS G'OLIBLARI E'LON QILINDI!</b> 🎉\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 <b>Konkurs:</b> {title}\n"
        f"🎁 <b>Sovg'a:</b> {prize}\n"
        f"👥 <b>Jami qatnashuvchilar:</b> {len(participants)} ta\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🥇 <b>TOP REFERRAL G'OLIBI:</b>\n"
        f"👤 {top_user_tag}\n"
        f"📊 Taklif qilgan do'stlari: <b>{top_winner.get('referral_count', 0)} ta</b>\n"
        f"🎟 Chipta raqami: <b>#{top_winner.get('ticket_number', 1)}</b>\n\n"
        f"🎲 <b>TASODIFIY (RANDOM) OMADLI G'OLIB:</b>\n"
        f"👤 {rand_user_tag}\n"
        f"🎟 Chipta raqami: <b>#{random_winner.get('ticket_number', 1)}</b>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎉 Barcha g'oliblarni chin yurakdan tabriklaymiz! Sovg'angizni qabul qilib olish uchun adminga murojaat qiling! 🎁"
    )

    return {
        "success": True,
        "contest": contest,
        "participants_count": len(participants),
        "top_winner": top_winner,
        "random_winner": random_winner,
        "announcement_text": announcement_text,
    }
