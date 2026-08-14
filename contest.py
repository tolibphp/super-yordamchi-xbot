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


def build_contest_results_channel_post(
    bot_username: str,
    contest: dict,
    winners: list[dict],
) -> tuple[str, InlineKeyboardMarkup]:
    """
    Kanalga joylanadigan ixcham, qisqa natijalar posti va 'Natijalarni tekshirish' tugmasini tayyorlaydi.
    Namunadagidek sodda, ortiqcha uzun matnlarsiz format.
    """
    lines = [
        "<b>Konkurs natijalari:</b> 🥳\n",
    ]
    if len(winners) > 1:
        lines.append("<b>G'oliblar:</b>")
    else:
        lines.append("<b>G'olib:</b>")

    for idx, w in enumerate(winners, 1):
        name = html.escape(w.get("first_name") or "Foydalanuvchi")
        uname = w.get("username")
        if uname:
            clean_u = uname if uname.startswith("@") else f"@{uname}"
            user_display = f"{name} ({clean_u})"
        else:
            user_display = f"{name}"
        lines.append(f"{idx}. {user_display}")

    text = "\n".join(lines)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="Natijalarni tekshirish 🔍",
                url=f"https://t.me/{bot_username}?start=results_{contest['id']}",
            )
        ]
    ])
    return text, kb


async def get_contest_results_view(contest_id: int) -> tuple[str, InlineKeyboardMarkup]:
    """
    Foydalanuvchi kanaldagi 'Natijalarni tekshirish' tugmasini bosib botga kirganda
    ko'rsatiladigan to'liq va shaffof natijalar kartasi.
    Ushbu xabarda 'Natijalarni tekshirish' tugmasi qayta bo'lmaydi.
    """
    import json
    contest = await get_contest(contest_id)
    if not contest:
        text = "⚠️ <b>Konkurs topilmadi yoki o'chirilgan.</b>"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Bosh Menyu", callback_data="user:menu")]
        ])
        return text, kb

    title = contest.get("title") or "Konkurs"
    prize = contest.get("prize_description") or "Qimmatbaho sovg'alar"
    participants_count = await get_contest_participants_count(contest_id)

    raw_winners = contest.get("winners_data")
    winners = []
    if raw_winners:
        try:
            winners = json.loads(raw_winners) if isinstance(raw_winners, str) else raw_winners
        except Exception:
            winners = []

    lines = [
        "📊 <b>KONKURS NATIJALARI TEKSHIRUVI</b>",
        "━━━━━━━━━━━━━━━━━━━━━",
        f"🏆 <b>Konkurs:</b> {title}",
        f"🎁 <b>Sovg'a:</b> {prize}",
        f"👥 <b>Jami qatnashuvchilar:</b> {participants_count} ta\n",
    ]

    if winners:
        if len(winners) > 1:
            lines.append("🎉 <b>Rasmiy g'oliblar:</b>")
        else:
            lines.append("🎉 <b>Rasmiy g'olib:</b>")

        for idx, w in enumerate(winners, 1):
            name = html.escape(w.get("first_name") or "Foydalanuvchi")
            uname = w.get("username")
            ticket = w.get("ticket_number", 1)
            u_tag = f"@{uname}" if uname else f"ID: {w.get('user_id')}"
            lines.append(f"{idx}. <b>{name}</b> ({u_tag}) — Chipta #{ticket}")
    else:
        lines.append("<i>G'oliblar ro'yxati shakllanmoqda...</i>")

    lines.append("\n━━━━━━━━━━━━━━━━━━━━━")
    lines.append("✅ <i>Ushbu natijalar shaffof tarzda tasdiqlangan.</i>")

    text = "\n".join(lines)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🎁 Barcha Konkurslar", callback_data="user:contests"),
            InlineKeyboardButton(text="⬅️ Bosh Menyu", callback_data="user:menu"),
        ]
    ])
    return text, kb


async def draw_contest_winners(
    bot: Bot,
    contest_id: int,
    winner_count: int = 1,
    save_to_db: bool = True,
) -> dict:
    """
    Konkurs g'oliblarini (bir yoki bir nechta) aniqlaydi:
    - winner_count: Aniqlanadigan g'oliblar soni
    - Qisqa kanal e'loni va 'Natijalarni tekshirish' tugmasini yaratadi
    - save_to_db: Natijalarni bazaga saqlash va konkursni yakunlash
    """
    contest = await get_contest(contest_id)
    if not contest:
        return {"success": False, "error": "Konkurs topilmadi"}

    participants = await get_contest_participants(contest_id)
    if not participants:
        if save_to_db:
            await end_contest(contest_id)
        return {
            "success": False,
            "error": "Konkursda hech qanday ishtirokchi ro'yxatdan o'tmagan.",
        }

    bot_info = await bot.get_me()
    bot_username = bot_info.username or ""

    winner_count = max(1, winner_count)
    total_p = len(participants)
    actual_count = min(winner_count, total_p)

    winners_list: list[dict] = []
    min_refs = contest.get("min_referrals", 0)

    # 1. Agar virusli (referal talab qilinadigan) konkurs bo'lsa:
    # 1-o'ringa eng ko'p referal yiqqan Top ishtirokchi chiqadi
    if min_refs > 0:
        sorted_by_ref = sorted(
            participants,
            key=lambda p: (p.get("referral_count", 0), p.get("points", 0)),
            reverse=True,
        )
        top_winner = sorted_by_ref[0]
        winners_list.append({
            "user_id": top_winner["user_id"],
            "username": top_winner.get("username"),
            "first_name": top_winner.get("first_name"),
            "ticket_number": top_winner.get("ticket_number", 1),
            "referral_count": top_winner.get("referral_count", 0),
        })

        remaining = [p for p in participants if p["user_id"] != top_winner["user_id"]]
        needed_random = actual_count - 1
        if needed_random > 0 and remaining:
            pool = []
            for p in remaining:
                t = 1 + p.get("extra_tickets", 0)
                for _ in range(t):
                    pool.append(p)
            
            selected_randoms = []
            while len(selected_randoms) < min(len(remaining), needed_random) and pool:
                chosen = random.choice(pool)
                selected_randoms.append(chosen)
                pool = [x for x in pool if x["user_id"] != chosen["user_id"]]

            for rw in selected_randoms:
                winners_list.append({
                    "user_id": rw["user_id"],
                    "username": rw.get("username"),
                    "first_name": rw.get("first_name"),
                    "ticket_number": rw.get("ticket_number", 1),
                    "referral_count": rw.get("referral_count", 0),
                })
    else:
        # Tezkor / Oddiy konkurs bo'lsa: Barcha g'oliblar tasodifiy (Random) aniqlanadi
        pool = []
        for p in participants:
            t = 1 + p.get("extra_tickets", 0)
            for _ in range(t):
                pool.append(p)
                
        selected_participants = []
        while len(selected_participants) < actual_count and pool:
            chosen = random.choice(pool)
            selected_participants.append(chosen)
            pool = [x for x in pool if x["user_id"] != chosen["user_id"]]

        for sp in selected_participants:
            winners_list.append({
                "user_id": sp["user_id"],
                "username": sp.get("username"),
                "first_name": sp.get("first_name"),
                "ticket_number": sp.get("ticket_number", 1),
                "referral_count": sp.get("referral_count", 0),
            })

    # Konkursni yakunlash va g'oliblarni bazaga saqlash
    if save_to_db:
        await end_contest(contest_id, winners_data=winners_list)

    # Qisqa kanal posti va tugmasi
    channel_post_text, channel_post_kb = build_contest_results_channel_post(
        bot_username=bot_username,
        contest=contest,
        winners=winners_list,
    )

    return {
        "success": True,
        "contest": contest,
        "participants_count": total_p,
        "winners": winners_list,
        "winner_count": len(winners_list),
        "channel_post_text": channel_post_text,
        "channel_post_kb": channel_post_kb,
        "announcement_text": channel_post_text,
    }
