"""
handlers.py — Telegram update handlerlar.
Multi-user: har kim o'z kanal/guruhida botdan foydalana oladi.
777 o'yini, /qollanma, inline knopkalar, my_chat_member kuzatuvi.
"""

import logging
from aiogram import Router, Bot, F
from aiogram.types import (
    Message,
    MessageReactionUpdated,
    ChatMemberUpdated,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.filters import Command, CommandStart, ChatMemberUpdatedFilter, IS_NOT_MEMBER, MEMBER, ADMINISTRATOR
from aiogram.enums import ChatType

from config import ADMIN_ID
from database import (
    log_activity,
    get_top_users,
    add_linked_chat,
    remove_linked_chat,
    is_linked_chat,
    get_linked_channel_for_group,
    save_777_winner,
    check_777_winner_exists,
)
from winner import pick_winner

logger = logging.getLogger(__name__)
router = Router()

# Bot username'ini saqlash uchun (ishga tushganda to'ldiriladi)
_bot_username: str = ""


async def set_bot_username(bot: Bot) -> None:
    """Bot username'ini olish va saqlash."""
    global _bot_username
    me = await bot.get_me()
    _bot_username = me.username or ""


# ─────────────────────────────────────────────
# ASOSIY BUYRUQLAR
# ─────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(message: Message, bot: Bot) -> None:
    """Botga /start bosilganda salom, knopkalar va kanal reklama."""
    if not _bot_username:
        await set_bot_username(bot)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="📢 Kanalga admin qilish",
                url=f"https://t.me/{_bot_username}?startchannel=true",
            ),
        ],
        [
            InlineKeyboardButton(
                text="💬 Guruhga admin qilish",
                url=f"https://t.me/{_bot_username}?startgroup=true",
            ),
        ],
    ])

    await message.answer(
        "👋 <b>Salom! Men faollik kuzatuvchi va g'olib aniqlovchi botman.</b>\n\n"
        "📊 Kanal va guruhdagi reaksiya va kommentlarni kuzatib boraman\n"
        "🏆 Har hafta/oyda eng faol a'zolar orasidan g'olib tanlayman\n"
        "🎰 <b>777 Jackpot o'yini</b> — kamentariyaga 🎰 stikerini tashlab, birinchi 777 tushirgan ishtirokchi yutadi!\n\n"
        "👇 <b>Boshlash uchun botni kanalingiz va guruhingizga admin qiling:</b>\n\n"
        "📢 Bizning kanalimiz: @Tolibjon_Life\n"
        "✅ Obuna bo'ling va faollikda qatnashing!\n\n"
        "ℹ️ /qollanma orqali to'liq ma'lumot olish mumkin",
        parse_mode="HTML",
        reply_markup=keyboard,
    )
    logger.info("User %s /start bosdi.", message.from_user.id if message.from_user else "?")


@router.message(Command("ping"))
async def cmd_ping(message: Message) -> None:
    """Bot ishlayotganini tekshirish."""
    await message.reply("✅ Bot ishlayapti!")


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    """Buyruqlar ro'yxati."""
    text = (
        "📋 <b>Buyruqlar:</b>\n\n"
        "/start — Botni ishga tushirish\n"
        "/qollanma — To'liq foydalanish yo'riqnomasi\n"
        "/ping — Bot ishlayaptimi tekshirish\n"
        "/help — Shu yordam xabari\n"
        "\n🔐 <b>Guruh admin buyruqlari:</b>\n\n"
        "/haftalik_golib — Haftalik g'olib tanlash\n"
        "/oylik_golib — Oylik g'olib tanlash\n"
        "/statistika — Haftalik top 5 faol a'zo\n"
    )
    await message.reply(text, parse_mode="HTML")


@router.message(Command("qollanma"))
async def cmd_qollanma(message: Message) -> None:
    """Botning to'liq foydalanish qo'llanmasi."""
    text = (
        "📖 <b>BOT QO'LLANMASI</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"

        "🤖 <b>Bot nima qiladi?</b>\n"
        "Bu bot sizning Telegram kanalingiz va muhokama guruhingiz "
        "uchun faollik kuzatuvchi va g'olib aniqlovchi yordamchidir.\n\n"

        "━━━━━━━━━━━━━━━━━━━━━\n"
        "📌 <b>1-QADAM: Botni ulash</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "1️⃣ /start bosing va <b>«📢 Kanalga admin qilish»</b> tugmasini bosing\n"
        "2️⃣ Kanalingizni tanlang — bot admin bo'ladi\n"
        "3️⃣ /start bosing va <b>«💬 Guruhga admin qilish»</b> tugmasini bosing\n"
        "4️⃣ Muhokama guruhingizni tanlang — bot admin bo'ladi\n"
        "✅ Bot avtomatik ravishda kanal va guruhni bazaga yozadi\n\n"

        "━━━━━━━━━━━━━━━━━━━━━\n"
        "📊 <b>2-QADAM: Faollik kuzatuvi</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Bot avtomatik ravishda kuzatadi:\n"
        "👍 Kanal postlariga bosilgan <b>reaksiyalarni</b>\n"
        "💬 Muhokama guruhidagi <b>kommentariyalarni</b>\n"
        "Hamma faollik bazaga yoziladi — siz hech narsa qilmaysiz!\n\n"

        "━━━━━━━━━━━━━━━━━━━━━\n"
        "🏆 <b>3-QADAM: G'olib tanlash</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Guruhda quyidagi buyruqlarni yozing:\n"
        "/haftalik_golib — oxirgi 7 kunlik faol a'zolardan g'olib\n"
        "/oylik_golib — oxirgi 30 kunlik faol a'zolardan g'olib\n"
        "/statistika — top 5 eng faol a'zo\n\n"
        "⚡ G'olib faqat <b>kanal + guruhga a'zo</b> bo'lganlar orasidan tanlanadi!\n\n"

        "━━━━━━━━━━━━━━━━━━━━━\n"
        "🎰 <b>777 JACKPOT O'YINI</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Foydalanuvchilar guruhda yoki post kamentariyasida 🎰 animatsiyali "
        "stiker/emojisini tashlaydi (baraban aylanadi: uzum, limon, 777).\n\n"
        "Kim birinchi bo'lib <b>777 (Jackpot)</b> tushirsa, bot darhol uni "
        "reply qilib tabriklaydi va g'olib deb e'lon qiladi! 🎉\n"
        "Har bir post/mavzu ostida faqat <b>1 ta g'olib</b> qabul qilinadi.\n\n"

        "━━━━━━━━━━━━━━━━━━━━━\n"
        "⚠️ <b>MUHIM ESLATMALAR</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "• Bot kanal va guruhda <b>admin</b> bo'lishi shart\n"
        "• Reaksiyalar faqat bot admin bo'lgandan <b>keyin</b> ko'rinadi\n"
        "• Buyruqlar faqat <b>guruh adminlari</b> uchun ishlaydi\n\n"

        "📢 Bizning kanalimiz: @Tolibjon_Life\n"
        "✅ Obuna bo'ling va faollikda qatnashing!"
    )
    await message.reply(text, parse_mode="HTML")


# ─────────────────────────────────────────────
# BOT KANAL/GURUHGA QO'SHILGANDA AVTOMATIK SEZISH
# ─────────────────────────────────────────────

@router.my_chat_member(
    ChatMemberUpdatedFilter(member_status_changed=IS_NOT_MEMBER >> ADMINISTRATOR)
)
async def on_bot_added_as_admin(event: ChatMemberUpdated, bot: Bot) -> None:
    """Bot kanalga yoki guruhga admin qilib qo'shilganda — bazaga yozadi."""
    chat = event.chat
    added_by = event.from_user

    if chat.type == ChatType.CHANNEL:
        chat_type = "channel"
        label = "📢 Kanal"
    elif chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
        chat_type = "group"
        label = "💬 Guruh"
    else:
        return

    await add_linked_chat(
        owner_id=added_by.id,
        chat_id=chat.id,
        chat_type=chat_type,
        chat_title=chat.title,
    )

    # Qo'shgan odamga xabar yuborish
    try:
        await bot.send_message(
            chat_id=added_by.id,
            text=f"✅ {label} ulandi!\n\n"
                 f"📌 <b>{chat.title}</b>\n"
                 f"🆔 <code>{chat.id}</code>\n\n"
                 f"Bot endi shu {label.lower()} da faollikni kuzatadi.",
            parse_mode="HTML",
        )
    except Exception as e:
        logger.warning("Foydalanuvchiga xabar yuborib bo'lmadi (user=%s): %s", added_by.id, e)

    logger.info(
        "Bot %s ga admin qilindi: chat_id=%s, title=%s, by=%s",
        chat_type, chat.id, chat.title, added_by.id,
    )


@router.my_chat_member(
    ChatMemberUpdatedFilter(member_status_changed=MEMBER >> IS_NOT_MEMBER)
)
async def on_bot_removed(event: ChatMemberUpdated) -> None:
    """Bot kanal/guruhdan chiqarilganda — bazadan o'chiradi."""
    await remove_linked_chat(event.chat.id)
    logger.info("Bot chiqarildi: chat_id=%s, title=%s", event.chat.id, event.chat.title)


@router.my_chat_member(
    ChatMemberUpdatedFilter(member_status_changed=ADMINISTRATOR >> IS_NOT_MEMBER)
)
async def on_bot_removed_from_admin(event: ChatMemberUpdated) -> None:
    """Bot admin huquqidan mahrum qilinganda — bazadan o'chiradi."""
    await remove_linked_chat(event.chat.id)
    logger.info("Bot adminlikdan olindi: chat_id=%s, title=%s", event.chat.id, event.chat.title)


# ─────────────────────────────────────────────
# GURUH ADMIN BUYRUQLARI (har qanday guruh admini)
# ─────────────────────────────────────────────

async def _is_group_admin(message: Message, bot: Bot) -> bool:
    """Xabar yuboruvchi shu guruhda admin ekanligini tekshiradi."""
    if not message.from_user:
        return False
    # Bot egasi har doim admin
    if message.from_user.id == ADMIN_ID:
        return True
    try:
        member = await bot.get_chat_member(message.chat.id, message.from_user.id)
        return member.status in ("creator", "administrator")
    except Exception:
        return False


@router.message(Command("tekshir"))
async def cmd_tekshir(message: Message, bot: Bot) -> None:
    """Bot sozlamalarini tekshirish (faqat bot egasi)."""
    if not message.from_user or message.from_user.id != ADMIN_ID:
        return

    from database import get_owner_chats

    lines = ["🔍 <b>Bot sozlamalari tekshiruvi:</b>\n"]

    try:
        me = await bot.get_me()
        lines.append(f"✅ Bot: @{me.username} ({me.first_name})")
    except Exception as e:
        lines.append(f"❌ Bot xatosi: {e}")

    # Bazadagi barcha ulangan chatlar
    all_chats = await get_owner_chats(ADMIN_ID)
    if all_chats:
        lines.append(f"\n📋 Ulangan chatlar ({len(all_chats)}):")
        for chat in all_chats:
            emoji = "📢" if chat["chat_type"] == "channel" else "💬"
            lines.append(f"  {emoji} {chat['chat_title']} (<code>{chat['chat_id']}</code>)")
    else:
        lines.append("\n⚠️ Hali hech qanday kanal/guruh ulanmagan.")

    await message.reply("\n".join(lines), parse_mode="HTML")


@router.message(Command("haftalik_golib"))
async def cmd_haftalik_golib(message: Message, bot: Bot) -> None:
    """Guruhda haftalik g'olib tanlash (faqat guruh adminlari)."""
    # Faqat guruhlarda ishlaydi
    if message.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        await message.reply("⚠️ Bu buyruq faqat guruhlarda ishlaydi.")
        return

    if not await _is_group_admin(message, bot):
        return

    # Bu guruh bazada bormi tekshirish
    if not await is_linked_chat(message.chat.id):
        await message.reply("⚠️ Bu guruh botga ulanmagan. Avval botni admin qiling.")
        return

    await message.reply("⏳ Haftalik g'olib aniqlanmoqda...")
    logger.info("Admin %s /haftalik_golib berdi (chat=%s).", message.from_user.id, message.chat.id)

    try:
        await pick_winner(
            bot=bot,
            days=7,
            period="haftalik",
            chat_id=message.chat.id,
            admin_id=message.from_user.id,
        )
    except Exception as e:
        logger.error("Haftalik g'olib xatosi: %s", e, exc_info=True)
        await message.reply(f"❌ Xatolik: {e}")


@router.message(Command("oylik_golib"))
async def cmd_oylik_golib(message: Message, bot: Bot) -> None:
    """Guruhda oylik g'olib tanlash (faqat guruh adminlari)."""
    if message.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        await message.reply("⚠️ Bu buyruq faqat guruhlarda ishlaydi.")
        return

    if not await _is_group_admin(message, bot):
        return

    if not await is_linked_chat(message.chat.id):
        await message.reply("⚠️ Bu guruh botga ulanmagan. Avval botni admin qiling.")
        return

    await message.reply("⏳ Oylik g'olib aniqlanmoqda...")
    logger.info("Admin %s /oylik_golib berdi (chat=%s).", message.from_user.id, message.chat.id)

    try:
        await pick_winner(
            bot=bot,
            days=30,
            period="oylik",
            chat_id=message.chat.id,
            admin_id=message.from_user.id,
        )
    except Exception as e:
        logger.error("Oylik g'olib xatosi: %s", e, exc_info=True)
        await message.reply(f"❌ Xatolik: {e}")


@router.message(Command("statistika"))
async def cmd_statistika(message: Message, bot: Bot) -> None:
    """Guruhda haftalik statistika (faqat guruh adminlari)."""
    if message.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        await message.reply("⚠️ Bu buyruq faqat guruhlarda ishlaydi.")
        return

    if not await _is_group_admin(message, bot):
        return

    logger.info("Admin %s /statistika berdi (chat=%s).", message.from_user.id, message.chat.id)

    try:
        top_users = await get_top_users(days=7, chat_id=message.chat.id, limit=5)

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
        logger.error("Statistika xatosi: %s", e, exc_info=True)
        await message.reply(f"❌ Xatolik: {e}")


# ─────────────────────────────────────────────
# FAOLLIK KUZATISH + 777 O'YIN
# Bu handlerlar eng OXIRIDA — buyruqlarni bloklamasligi uchun
# ─────────────────────────────────────────────

@router.message_reaction()
async def on_reaction(event: MessageReactionUpdated) -> None:
    """Reaksiyalarni kuzatadi va bazaga yozadi."""
    if not event.new_reaction:
        return

    user = event.user
    if user is None:
        logger.debug("Anonim reaksiya, o'tkazildi. msg=%s", event.message_id)
        return

    # Faqat bazadagi chatlarda kuzatish
    if not await is_linked_chat(event.chat.id):
        return

    await log_activity(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name or "Noma'lum",
        activity_type="reaction",
        message_id=event.message_id,
        chat_id=event.chat.id,
    )
    logger.info("Reaction: user=%s, chat=%s, msg=%s", user.id, event.chat.id, event.message_id)


@router.message(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))
async def on_group_message(message: Message, bot: Bot) -> None:
    """
    Guruhdagi xabarlarni kuzatadi:
    - Oddiy kommentlarni bazaga yozadi
    - 777 o'yinini tekshiradi
    """
    if message.from_user is None or message.from_user.is_bot:
        return

    # Buyruqlarni o'tkazib yuborish
    if message.text and message.text.startswith("/"):
        return

    # Faqat bazadagi guruhlarda ishlash
    if not await is_linked_chat(message.chat.id):
        return

    # ── 777 JACKPOT (🎰 DICE) O'YIN TEKSHIRUVI ──
    if message.dice and message.dice.emoji == "🎰":
        if message.dice.value == 64:  # 64 = Uchta 7 (777 Jackpot)
            reply_msg_id = message.message_id
            if message.reply_to_message:
                reply_msg_id = message.reply_to_message.message_id
            elif message.message_thread_id:
                reply_msg_id = message.message_thread_id

            # Bu post/mavzu ostida g'olib bormi?
            already_won = await check_777_winner_exists(message.chat.id, reply_msg_id)
            if not already_won:
                saved = await save_777_winner(
                    chat_id=message.chat.id,
                    reply_to_message_id=reply_msg_id,
                    winner_user_id=message.from_user.id,
                    winner_first_name=message.from_user.first_name or "Noma'lum",
                )
                if saved:
                    first_name = message.from_user.first_name or "Noma'lum"
                    user_id = message.from_user.id
                    await message.reply(
                        f"🎰🎰🎰 <b>JACKPOT! 777 TUSHDI!</b>\n\n"
                        f"🎉 Tabriklaymiz, "
                        f'<a href="tg://user?id={user_id}">{first_name}</a>! '
                        f"Siz birinchi bo'lib <b>777</b> tushirdingiz va yutdingiz! 🏆\n\n"
                        f"Sovg'angizni olish uchun admin bilan bog'laning! 🎁",
                        parse_mode="HTML",
                    )
                    logger.info("777 Jackpot g'olib: user=%s, chat=%s", user_id, message.chat.id)

    # ── FAOLLIKNI BAZAGA YOZISH ──
    await log_activity(
        user_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name or "Noma'lum",
        activity_type="comment",
        message_id=message.message_id,
        chat_id=message.chat.id,
    )
