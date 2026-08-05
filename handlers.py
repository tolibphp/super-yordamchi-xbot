"""
handlers.py — Telegram update handlerlar.
Reaksiyalarni, kommentariyalarni kuzatadi va admin buyruqlarini bajaradi.
"""

import logging
from aiogram import Router, Bot, F
from aiogram.types import Message, MessageReactionUpdated
from aiogram.filters import Command, CommandStart

from config import ADMIN_ID, CHAT_ID, CHANNEL_ID
from database import log_activity, get_top_users
from winner import pick_winner

logger = logging.getLogger(__name__)
router = Router()


# ─────────────────────────────────────────────
# ASOSIY BUYRUQLAR (barcha foydalanuvchilar uchun)
# ─────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    """Botga /start bosilganda javob beradi."""
    await message.answer(
        "👋 Salom! Men faollik kuzatuvchi botman.\n\n"
        "📊 Kanal va guruhdagi reaksiya va kommentlarni kuzatib boraman.\n"
        "🏆 Har hafta/oyda eng faol a'zolar orasidan g'olib tanlayman.\n\n"
        "Faol bo'ling va yutib oling! 💪"
    )
    logger.info("User %s /start bosdi.", message.from_user.id if message.from_user else "?")


@router.message(Command("ping"))
async def cmd_ping(message: Message) -> None:
    """Bot ishlayotganini tekshirish uchun."""
    await message.reply("✅ Bot ishlayapti!")


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    """Buyruqlar ro'yxatini ko'rsatadi."""
    text = (
        "📋 <b>Buyruqlar:</b>\n\n"
        "/start — Botni ishga tushirish\n"
        "/ping — Bot ishlayaptimi tekshirish\n"
        "/help — Shu yordam xabari\n"
    )
    if message.from_user and message.from_user.id == ADMIN_ID:
        text += (
            "\n🔐 <b>Admin buyruqlari:</b>\n\n"
            "/haftalik_golib — Haftalik g'olib tanlash\n"
            "/oylik_golib — Oylik g'olib tanlash\n"
            "/statistika — Haftalik top 5 faol a'zo\n"
            "/tekshir — Bot sozlamalarini tekshirish\n"
        )
    await message.reply(text, parse_mode="HTML")


# ─────────────────────────────────────────────
# ADMIN BUYRUQLARI
# ─────────────────────────────────────────────

def _is_admin(message: Message) -> bool:
    """Xabar yuboruvchi admin ekanligini tekshiradi."""
    return message.from_user is not None and message.from_user.id == ADMIN_ID


@router.message(Command("tekshir"))
async def cmd_tekshir(message: Message, bot: Bot) -> None:
    """Admin buyrug'i: bot sozlamalari va ulanishlarni tekshiradi."""
    if not _is_admin(message):
        return

    lines = ["🔍 <b>Bot sozlamalari tekshiruvi:</b>\n"]

    # Bot ma'lumotlari
    try:
        me = await bot.get_me()
        lines.append(f"✅ Bot: @{me.username} ({me.first_name})")
    except Exception as e:
        lines.append(f"❌ Bot ma'lumotlarini olishda xato: {e}")

    # Kanal tekshiruvi
    try:
        chat = await bot.get_chat(CHANNEL_ID)
        lines.append(f"✅ Kanal: {chat.title} (ID: {CHANNEL_ID})")
    except Exception as e:
        lines.append(f"❌ Kanalga ulanib bo'lmadi (ID: {CHANNEL_ID}): {e}")

    # Guruh tekshiruvi
    try:
        chat = await bot.get_chat(CHAT_ID)
        lines.append(f"✅ Guruh: {chat.title} (ID: {CHAT_ID})")
    except Exception as e:
        lines.append(f"❌ Guruhga ulanib bo'lmadi (ID: {CHAT_ID}): {e}")

    # Admin ID
    lines.append(f"\n👤 Admin ID: {ADMIN_ID}")
    lines.append(f"💬 Chat ID: {CHAT_ID}")
    lines.append(f"📢 Channel ID: {CHANNEL_ID}")

    await message.reply("\n".join(lines), parse_mode="HTML")


@router.message(Command("haftalik_golib"))
async def cmd_haftalik_golib(message: Message, bot: Bot) -> None:
    """Admin buyrug'i: so'nggi 7 kunda faol va eligible foydalanuvchilardan g'olib tanlaydi."""
    if not _is_admin(message):
        return

    await message.reply("⏳ Haftalik g'olib aniqlanmoqda...")
    logger.info("Admin /haftalik_golib buyrug'ini berdi.")

    try:
        await pick_winner(bot=bot, days=7, period="haftalik")
    except Exception as e:
        logger.error("Haftalik g'olib tanlashda xato: %s", e, exc_info=True)
        await message.reply(f"❌ Xatolik yuz berdi: {e}")


@router.message(Command("oylik_golib"))
async def cmd_oylik_golib(message: Message, bot: Bot) -> None:
    """Admin buyrug'i: so'nggi 30 kunda faol va eligible foydalanuvchilardan g'olib tanlaydi."""
    if not _is_admin(message):
        return

    await message.reply("⏳ Oylik g'olib aniqlanmoqda...")
    logger.info("Admin /oylik_golib buyrug'ini berdi.")

    try:
        await pick_winner(bot=bot, days=30, period="oylik")
    except Exception as e:
        logger.error("Oylik g'olib tanlashda xato: %s", e, exc_info=True)
        await message.reply(f"❌ Xatolik yuz berdi: {e}")


@router.message(Command("statistika"))
async def cmd_statistika(message: Message) -> None:
    """Admin buyrug'i: joriy haftadagi eng faol 5 kishini ko'rsatadi."""
    if not _is_admin(message):
        return

    logger.info("Admin /statistika buyrug'ini berdi.")

    try:
        top_users = await get_top_users(days=7, limit=5)

        if not top_users:
            await message.reply("📊 Bu hafta hali hech qanday faollik qayd etilmadi.")
            return

        lines = ["📊 <b>Haftalik faollik statistikasi (Top 5)</b>\n"]
        for i, user in enumerate(top_users, start=1):
            medal = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"][i - 1]
            name = user["first_name"]
            username = f" (@{user['username']})" if user["username"] else ""
            total = user["total"]
            lines.append(f"{medal} <b>{name}</b>{username} — {total} ta faollik")

        await message.reply("\n".join(lines), parse_mode="HTML")

    except Exception as e:
        logger.error("Statistika olishda xato: %s", e, exc_info=True)
        await message.reply(f"❌ Xatolik yuz berdi: {e}")


# ─────────────────────────────────────────────
# FAOLLIK KUZATISH (reaction + comment)
# Muhim: bu handlerlar eng OXIRIDA turishi kerak,
# aks holda /buyruqlarni ham ushlab qoladi!
# ─────────────────────────────────────────────

@router.message_reaction()
async def on_reaction(event: MessageReactionUpdated) -> None:
    """
    Kanal postiga yoki guruh xabariga bosilgan reaksiyani ushlaydi.
    Faqat yangi reaksiya qo'shilganda yozadi (olib tashlashni emas).
    """
    # Faqat yangi reaksiya qo'shilgan bo'lsa
    if not event.new_reaction:
        return

    user = event.user
    if user is None:
        # Anonim reaksiya (ba'zi hollarda user None bo'lishi mumkin)
        logger.debug("Anonim reaksiya, o'tkazib yuborildi. message_id=%s", event.message_id)
        return

    await log_activity(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name or "Noma'lum",
        activity_type="reaction",
        message_id=event.message_id,
    )
    logger.info("Reaction yozildi: user=%s, msg=%s", user.id, event.message_id)


@router.message(F.chat.id == CHAT_ID)
async def on_comment(message: Message) -> None:
    """
    Muhokama guruhidagi (CHAT_ID) har bir xabarni (kommentariyani) kuzatadi.
    Bu handler eng OXIRIDA ro'yxatdan o'tgan — shuning uchun
    /buyruqlar avval ishlanadi, bu faqat oddiy xabarlarni ushlaydi.
    """
    if message.from_user is None:
        return

    # Bot xabarlarini hisobga olmaslik
    if message.from_user.is_bot:
        return

    # Buyruqlarni faollik sifatida yozmaslik
    if message.text and message.text.startswith("/"):
        return

    await log_activity(
        user_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name or "Noma'lum",
        activity_type="comment",
        message_id=message.message_id,
    )
    logger.info("Comment yozildi: user=%s, msg=%s", message.from_user.id, message.message_id)

