"""
contest.py — Smart Viral Contest tizimi, vizual kanal posti va g'oliblarni aniqlash logikasi.

Funksiyalar:
- build_contest_post_content: Aynan namunadagidek raqamlangan kanallar va jonli tugmali post
- update_contest_channel_posts: Kanaldagi e'lon tugmasidagi qatnashuvchilar sonini (Live Counter) yangilash
- build_share_data: 1-bosishda do'stlarga va guruhlarga ulashish
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
    get_contest_participants_count,
    get_contest_channel_posts,
    end_contest,
)

logger = logging.getLogger(__name__)

_NUMBER_EMOJIS = {
    1: "1️⃣", 2: "2️⃣", 3: "3️⃣", 4: "4️⃣", 5: "5️⃣",
    6: "6️⃣", 7: "7️⃣", 8: "8️⃣", 9: "9️⃣", 10: "🔟",
}


def _get_number_emoji(num: int) -> str:
    """Raqamni emoji ko'rinishida qaytaradi."""
    return _NUMBER_EMOJIS.get(num, f"{num}️⃣")


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


def build_contest_post_content(
    bot_username: str,
    contest: dict,
    channels: list[dict] | None = None,
    participant_count: int = 0,
) -> tuple[str, InlineKeyboardMarkup]:
    """
    Kanalga joylanadigan konkurs e'lon postining matni va jonli hisoblagich tugmasini tayyorlaydi.
    Namunaviy rasmdagi formatda chiroyli va tartibli shakllantiriladi.
    """
    title = contest["title"]
    c_type = contest.get("contest_type", "gift")
    min_refs = contest.get("min_referrals", 0)
    prize = contest.get("prize_description") or "Qimmatbaho sovg'alar va Telegram Premium!"

    # Kanallar ro'yxatini chiroyli raqamlar bilan shakllantirish
    channel_lines = []
    if channels:
        for idx, ch in enumerate(channels, 1):
            num_emo = _get_number_emoji(idx)
            uname = ch.get("channel_username")
            t_title = ch.get("channel_title") or ch.get("title") or "Kanal"
            if uname:
                clean_uname = uname if uname.startswith("@") else f"@{uname}"
                channel_lines.append(f"{num_emo} - {clean_uname}")
            else:
                channel_lines.append(f"{num_emo} - <b>{t_title}</b>")

    channels_block = "\n".join(channel_lines) if channel_lines else "<i>(Rasmiy kanallarimiz)</i>"

    # Shart matni
    if min_refs > 0:
        shart_text = f"📌 <b>Qatnashish sharti:</b>\nPastdagi kanallarga obuna bo'ling va kamida <b>{min_refs} ta do'st</b> taklif qilib <b>«QATNASHISH»</b> tugmasini bosing ⬇️"
    else:
        shart_text = "📌 <b>Qatnashish sharti:</b>\nPastdagi kanallarga obuna bo'lib <b>«QATNASHISH»</b> tugmasini bosing ⬇️"

    text = (
        f"🎉 <b>{title}</b>\n"
        f"🎁 <b>Sovg'a:</b> {prize}\n\n"
        f"{shart_text}\n\n"
        f"{channels_block}\n\n"
        f"✨ <i>Barchaga omad tilaymiz!</i>"
    )

    # Jonli tugma: QATNASHISH (15)
    btn_label = f"🎁 QATNASHISH ({participant_count})" if participant_count > 0 else "🎁 QATNASHISH (0)"
    keyboard_rows = [
        [
            InlineKeyboardButton(
                text=f"{btn_label} ↗️",
                url=f"https://t.me/{bot_username}?start=contest_{contest['id']}",
            )
        ]
    ]

    if min_refs > 0:
        keyboard_rows.append([
            InlineKeyboardButton(
                text="🚀 Do'stlarni taklif qilish",
                url=f"https://t.me/{bot_username}?start=share",
            )
        ])

    kb = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
    return text, kb


async def update_contest_channel_posts(bot: Bot, contest_id: int) -> None:
    """
    Konkursga yangi a'zo qo'shilganda kanal postidagi 'QATNASHISH (X)' tugmasini
    real vaqtda (Live Counter) avtomatik yangilab qo'yadi.
    """
    try:
        contest = await get_contest(contest_id)
        if not contest or not contest.get("is_active"):
            return

        count = await get_contest_participants_count(contest_id)
        posts = await get_contest_channel_posts(contest_id)
        if not posts:
            return

        bot_info = await bot.get_me()
        bot_uname = bot_info.username or ""

        btn_label = f"🎁 QATNASHISH ({count})"
        min_refs = contest.get("min_referrals", 0)

        kb_rows = [
            [
                InlineKeyboardButton(
                    text=f"{btn_label} ↗️",
                    url=f"https://t.me/{bot_uname}?start=contest_{contest_id}",
                )
            ]
        ]
        if min_refs > 0:
            kb_rows.append([
                InlineKeyboardButton(
                    text="🚀 Do'stlarni taklif qilish",
                    url=f"https://t.me/{bot_uname}?start=share",
                )
            ])
        new_kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)

        for p in posts:
            try:
                await bot.edit_message_reply_markup(
                    chat_id=p["chat_id"],
                    message_id=p["message_id"],
                    reply_markup=new_kb,
                )
            except Exception as e:
                logger.debug("Live counter yangilashda xato (%s:%s): %s", p.get("chat_id"), p.get("message_id"), e)
    except Exception as e:
        logger.error("update_contest_channel_posts umumiy xato: %s", e)


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
