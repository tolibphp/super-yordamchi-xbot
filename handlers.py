"""
handlers.py — Telegram update handlerlar.
Multi-user: har kim o'z kanal/guruhida botdan foydalana oladi.
777 o'yini, /qollanma, inline knopkalar, my_chat_member kuzatuvi.
"""

import logging
import asyncio
import html
from aiogram import Router, Bot, F
from aiogram.types import (
    Message,
    CallbackQuery,
    MessageReactionUpdated,
    ChatMemberUpdated,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.filters import Command, CommandStart, ChatMemberUpdatedFilter, IS_NOT_MEMBER, MEMBER, ADMINISTRATOR
from aiogram.enums import ChatType
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

from config import ADMIN_ID
from database import (
    log_activity,
    get_top_users,
    add_linked_chat,
    remove_linked_chat,
    is_linked_chat,
    get_linked_channel_for_group,
    get_all_linked_chats,
    save_777_winner,
    check_777_winner_exists,
    add_mandatory_channel,
    remove_mandatory_channel,
    get_mandatory_channels,
    is_mandatory_sub_enabled,
    set_mandatory_sub_enabled,
    get_admin_stats,
)
from membership import check_membership, check_all_mandatory_subs
from winner import pick_winner

logger = logging.getLogger(__name__)
router = Router()

# Bot username'ini saqlash uchun (ishga tushganda to'ldiriladi)
_bot_username: str = ""


class AdminStates(StatesGroup):
    """Admin panel uchun FSM holatlari."""
    waiting_for_channel_input = State()



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
        "/help — Shu yordam xabari\n\n"
        "👑 <b>Admin buyruqlari:</b>\n"
        "/admin — Majburiy obuna va boshqaruv paneli\n"
        "/haftalik_golib — Haftalik g'olib tanlash\n"
        "/oylik_golib — Oylik g'olib tanlash\n"
        "/statistika — Haftalik top 5 faol a'zo\n"
        "/tekshir — Ulangan chatlar diagnostikasi\n"
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
        "uchun faollik kuzatuvchi, majburiy obuna nazoratchisi va g'olib aniqlovchi super yordamchidir.\n\n"

        "━━━━━━━━━━━━━━━━━━━━━\n"
        "📌 <b>1-QADAM: Botni ulash</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "1️⃣ /start bosing va <b>«📢 Kanalga admin qilish»</b> tugmasini bosing\n"
        "2️⃣ Kanalingizni tanlang — bot admin bo'ladi\n"
        "3️⃣ /start bosing va <b>«💬 Guruhga admin qilish»</b> tugmasini bosing\n"
        "4️⃣ Muhokama guruhingizni tanlang — bot admin bo'ladi\n"
        "✅ Bot avtomatik ravishda kanal va guruhni bazaga yozadi\n\n"

        "━━━━━━━━━━━━━━━━━━━━━\n"
        "🔐 <b>2-QADAM: Majburiy obuna sozlash</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Botda /admin buyrug'ini yuboring:\n"
        "➕ <b>Kanal qo'shish</b> — guruhingizda faqat kanalga obuna bo'lganlar yoza olishi uchun kanal ulang.\n"
        "🗑 <b>Kanal o'chirish</b> — kerak bo'lmagan kanallarni olib tashlang.\n"
        "🔘 <b>Obunani yoqish/o'chirish</b> — istalgan payt majburiy obunani to'xtatib turishingiz mumkin.\n\n"

        "━━━━━━━━━━━━━━━━━━━━━\n"
        "📊 <b>3-QADAM: Faollik va Ballar</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Bot avtomatik ravishda kuzatadi:\n"
        "👍 Kanal postlariga bosilgan <b>reaksiyalarni</b> (1 ball)\n"
        "💬 Kanal postlari ostidagi <b>kommentariyalarni</b> (1 ball)\n"
        "<i>Eslatma: Oddiy guruh suhbatlariga emas, faqat kanal posti kamentlariga ball beriladi!</i>\n\n"

        "━━━━━━━━━━━━━━━━━━━━━\n"
        "🏆 <b>4-QADAM: G'olib tanlash</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Guruhda quyidagi buyruqlarni yozing:\n"
        "/haftalik_golib — oxirgi 7 kunlik faol a'zolardan g'olib\n"
        "/oylik_golib — oxirgi 30 kunlik faol a'zolardan g'olib\n"
        "/statistika — top 5 eng faol a'zo\n\n"
        "⚡ G'olib faqat <b>kanal + guruhga a'zo</b> bo'lganlar orasidan tanlanadi!\n\n"

        "━━━━━━━━━━━━━━━━━━━━━\n"
        "🎰 <b>5-QADAM: 777 JACKPOT O'YINI</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Foydalanuvchilar post kamentariyasida 🎰 animatsiyali "
        "stiker/emojisini tashlaydi (baraban aylanadi).\n\n"
        "Kim birinchi bo'lib <b>777 (Jackpot)</b> tushirsa, bot uni darhol "
        "tabriklaydi va g'olib deb e'lon qiladi! 🎉\n\n"

        "━━━━━━━━━━━━━━━━━━━━━\n"
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
# ADMIN VA GURUH BUYRUQLARI
# ─────────────────────────────────────────────

async def _is_group_admin(message: Message, bot: Bot) -> bool:
    """Xabar yuboruvchi shu guruhda admin ekanligini tekshiradi."""
    if not message.from_user:
        return False
    # Bot egasi (agar ko'rsatilgan bo'lsa) har doim admin
    if ADMIN_ID and message.from_user.id == ADMIN_ID:
        return True
    try:
        member = await bot.get_chat_member(message.chat.id, message.from_user.id)
        return member.status in ("creator", "administrator")
    except Exception:
        return False


async def _build_admin_menu_text_and_kb() -> tuple[str, InlineKeyboardMarkup]:
    """Admin panel uchun asosiy xabar matni va knopkalarni tayyorlaydi."""
    stats = await get_admin_stats()
    is_sub_on = await is_mandatory_sub_enabled()
    sub_status_str = "🟢 Yoniq" if is_sub_on else "🔴 O'chiq"

    text = (
        "👑 <b>BOT ADMIN PANELI</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        f"⚙️ <b>Majburiy obuna:</b> {sub_status_str}\n"
        f"📢 <b>Majburiy kanallar:</b> {stats['total_mandatory']} ta\n"
        f"👥 <b>Faol foydalanuvchilar:</b> {stats['total_users']} ta\n"
        f"💬 <b>Ulangan guruhlar:</b> {stats['total_groups']} ta\n"
        f"📢 <b>Ulangan kanallar:</b> {stats['total_channels']} ta\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "Quyidagi tugmalar orqali botni boshqaring:"
    )

    toggle_btn_text = "🔴 Obunani o'chirish" if is_sub_on else "🟢 Obunani yoqish"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📋 Kanallar ro'yxati", callback_data="admin:list_channels"),
            InlineKeyboardButton(text="➕ Kanal qo'shish", callback_data="admin:add_channel"),
        ],
        [
            InlineKeyboardButton(text="🗑 Kanalni o'chirish", callback_data="admin:del_channel_list"),
            InlineKeyboardButton(text=toggle_btn_text, callback_data="admin:toggle_sub"),
        ],
        [
            InlineKeyboardButton(text="📊 To'liq statistika", callback_data="admin:stats"),
            InlineKeyboardButton(text="❌ Yopish", callback_data="admin:close"),
        ],
    ])
    return text, kb


@router.message(Command("admin"))
async def cmd_admin(message: Message, bot: Bot) -> None:
    """Admin panelni ochadi."""
    if not message.from_user:
        return

    is_allowed = False
    if ADMIN_ID and message.from_user.id == ADMIN_ID:
        is_allowed = True
    elif message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
        is_allowed = await _is_group_admin(message, bot)
    elif not ADMIN_ID:
        is_allowed = True

    if not is_allowed:
        await message.reply("⛔ Bu buyruq faqat bot adminlari uchun!")
        return

    text, kb = await _build_admin_menu_text_and_kb()
    await message.reply(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data == "admin:menu")
async def cb_admin_menu(query: CallbackQuery, state: FSMContext) -> None:
    """Admin panel asosiy menyusiga qaytish."""
    await state.clear()
    text, kb = await _build_admin_menu_text_and_kb()
    if query.message:
        await query.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await query.answer()


@router.callback_query(F.data == "admin:list_channels")
async def cb_admin_list_channels(query: CallbackQuery) -> None:
    """Majburiy kanallar ro'yxatini ko'rsatish."""
    channels = await get_mandatory_channels()
    if not channels:
        text = "📢 <b>Majburiy kanallar ro'yxati:</b>\n\n⚠️ Hozircha majburiy kanallar qo'shilmagan."
    else:
        text_lines = ["📢 <b>Majburiy kanallar ro'yxati:</b>\n"]
        for i, ch in enumerate(channels, start=1):
            user_tag = ch["channel_username"] or ch["channel_id"]
            text_lines.append(
                f"{i}) <b>{ch['channel_title']}</b> ({user_tag})\n   🆔 <code>{ch['channel_id']}</code>"
            )
        text = "\n".join(text_lines)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Yangi kanal qo'shish", callback_data="admin:add_channel")],
        [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="admin:menu")],
    ])
    if query.message:
        await query.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await query.answer()


@router.callback_query(F.data == "admin:add_channel")
async def cb_admin_add_channel(query: CallbackQuery, state: FSMContext) -> None:
    """Yangi majburiy kanal qo'shish jarayonini boshlash."""
    await state.set_state(AdminStates.waiting_for_channel_input)
    text = (
        "➕ <b>Majburiy kanal qo'shish</b>\n\n"
        "Kanalning <b>@username</b> yoki <b>ID</b> sini yuboring:\n"
        "<i>Masalan: @Tolibjon_Life yoki -1001234567890</i>\n\n"
        "⚠️ <b>Muhim:</b> Bot o'sha kanalda <b>Admin</b> bo'lishi shart, "
        "aks holda bot obunani tekshira olmaydi!"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="admin:menu")],
    ])
    if query.message:
        await query.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await query.answer()


@router.message(AdminStates.waiting_for_channel_input)
async def on_admin_channel_input(message: Message, bot: Bot, state: FSMContext) -> None:
    """Admin kanal username yoki ID sini yuborganda uni tekshirib bazaga qo'shadi."""
    raw_input = (message.text or "").strip()
    if not raw_input:
        await message.reply("⚠️ Iltimos, kanal username yoki ID sini yuboring.")
        return

    if raw_input in ("/cancel", "/bekor"):
        await state.clear()
        text, kb = await _build_admin_menu_text_and_kb()
        await message.reply("❌ Bekor qilindi.", reply_markup=kb)
        return

    try:
        chat_id_to_check: int | str
        try:
            chat_id_to_check = int(raw_input)
        except ValueError:
            chat_id_to_check = raw_input if raw_input.startswith("@") else f"@{raw_input}"

        chat = await bot.get_chat(chat_id_to_check)
        title = chat.title or "Noma'lum kanal"
        username = f"@{chat.username}" if chat.username else str(chat.id)

        # Bot adminligini tekshirib ko'rish
        me = await bot.get_me()
        try:
            member = await bot.get_chat_member(chat_id=chat.id, user_id=me.id)
            if member.status not in ("administrator", "creator"):
                await message.reply(
                    f"⚠️ Bot <b>{title}</b> kanalida admin emas!\n"
                    f"Iltimos, avval botni kanalga admin qiling va qayta yuboring.",
                    parse_mode="HTML",
                )
                return
        except Exception as e:
            logger.warning("Kanal adminlik tekshirishda xato: %s", e)

        await add_mandatory_channel(
            channel_id=str(chat.id),
            channel_title=title,
            channel_username=username,
        )
        await state.clear()

        text = (
            f"✅ <b>Kanal muvaffaqiyatli qo'shildi!</b>\n\n"
            f"📢 <b>Nomi:</b> {title}\n"
            f"🔗 <b>Username:</b> {username}\n"
            f"🆔 <code>{chat.id}</code>"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📋 Kanallar ro'yxati", callback_data="admin:list_channels")],
            [InlineKeyboardButton(text="⬅️ Admin panel", callback_data="admin:menu")],
        ])
        await message.reply(text, parse_mode="HTML", reply_markup=kb)

    except Exception as e:
        logger.error("Kanal qo'shishda xato: %s", e)
        await message.reply(
            f"❌ Kanalni topib bo'lmadi yoki xatolik yuz berdi: {e}\n\n"
            f"<i>Kanal username yoki ID si to'g'riligini va bot kanalda admin ekanligini tekshiring.</i>",
            parse_mode="HTML",
        )


@router.callback_query(F.data == "admin:del_channel_list")
async def cb_admin_del_channel_list(query: CallbackQuery) -> None:
    """Majburiy kanallardan birini o'chirish uchun ro'yxat."""
    channels = await get_mandatory_channels()
    if not channels:
        text = "🗑 <b>Kanalni o'chirish:</b>\n\n⚠️ Hozircha o'chirish uchun majburiy kanallar yo'q."
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="admin:menu")],
        ])
    else:
        text = "🗑 <b>O'chirmoqchi bo'lgan kanalni tanlang:</b>"
        buttons = []
        for ch in channels:
            title = ch["channel_title"] or ch["channel_id"]
            buttons.append([
                InlineKeyboardButton(
                    text=f"🗑 {title}",
                    callback_data=f"admin:del:{ch['channel_id']}",
                )
            ])
        buttons.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data="admin:menu")])
        kb = InlineKeyboardMarkup(inline_keyboard=buttons)

    if query.message:
        await query.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await query.answer()


@router.callback_query(F.data.startswith("admin:del:"))
async def cb_admin_del_channel_exec(query: CallbackQuery) -> None:
    """Kanalni majburiy ro'yxatdan o'chirish."""
    target_cid = query.data.split(":", 2)[2]
    deleted = await remove_mandatory_channel(target_cid)
    if deleted:
        await query.answer("✅ Kanal majburiy ro'yxatdan o'chirildi!", show_alert=True)
    else:
        await query.answer("⚠️ Kanal topilmadi.", show_alert=True)
    await cb_admin_del_channel_list(query)


@router.callback_query(F.data == "admin:toggle_sub")
async def cb_admin_toggle_sub(query: CallbackQuery) -> None:
    """Majburiy obuna tizimini yoqish/o'chirish."""
    current = await is_mandatory_sub_enabled()
    new_val = not current
    await set_mandatory_sub_enabled(new_val)
    status_text = "yoqildi 🟢" if new_val else "o'chirildi 🔴"
    await query.answer(f"Majburiy obuna {status_text}!", show_alert=False)
    text, kb = await _build_admin_menu_text_and_kb()
    if query.message:
        await query.message.edit_text(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data == "admin:stats")
async def cb_admin_stats(query: CallbackQuery) -> None:
    """To'liq statistikani ko'rsatish."""
    stats = await get_admin_stats()
    all_chats = await get_all_linked_chats()
    is_sub_on = await is_mandatory_sub_enabled()

    lines = [
        "📊 <b>BOT TO'LIQ STATISTIKASI</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n",
        f"⚙️ <b>Majburiy obuna:</b> {'🟢 Yoniq' if is_sub_on else '🔴 O\'chiq'}",
        f"📢 <b>Majburiy kanallar:</b> {stats['total_mandatory']} ta",
        f"👥 <b>Faol foydalanuvchilar:</b> {stats['total_users']} ta",
        f"💬 <b>Ulangan guruhlar:</b> {stats['total_groups']} ta",
        f"📢 <b>Ulangan kanallar:</b> {stats['total_channels']} ta",
        f"📝 <b>Jami qayd etilgan faolliklar:</b> {stats['total_activities']} ta",
        "\n━━━━━━━━━━━━━━━━━━━━━\n",
    ]

    if all_chats:
        lines.append("📋 <b>Ulangan chatlar:</b>")
        for c in all_chats[:10]:
            icon = "📢" if c["chat_type"] == "channel" else "💬"
            lines.append(f"{icon} {c['chat_title'] or 'Nomsiz'} (<code>{c['chat_id']}</code>)")
        if len(all_chats) > 10:
            lines.append(f"<i>...va yana {len(all_chats) - 10} ta chat</i>")

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="admin:menu")],
    ])
    if query.message:
        await query.message.edit_text("\n".join(lines), parse_mode="HTML", reply_markup=kb)
    await query.answer()


@router.callback_query(F.data == "admin:close")
async def cb_admin_close(query: CallbackQuery) -> None:
    """Admin panelni yopish."""
    if query.message:
        await query.message.delete()
    await query.answer("Yopildi")


async def _auto_delete_msg(bot: Bot, chat_id: int, message_id: int, delay: int = 60) -> None:
    """Xabarni delay soniyadan so'ng avtomatik o'chiradi."""
    await asyncio.sleep(delay)
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception:
        pass


@router.callback_query(F.data.startswith("check_sub:"))
async def cb_check_sub(query: CallbackQuery, bot: Bot) -> None:
    """Foydalanuvchi majburiy obunani 'Holatni tekshirish' orqali tekshirganda."""
    data_parts = query.data.split(":")
    target_user_id = int(data_parts[1]) if len(data_parts) > 1 and data_parts[1].isdigit() else 0
    clicked_user_id = query.from_user.id

    is_subbed, missing = await check_all_mandatory_subs(bot, clicked_user_id)
    if is_subbed:
        await query.answer(
            "✅ Tabriklaymiz, siz barcha kanallarga a'zo bo'ldingiz! Endi guruhda bemalol yoza olasiz. 🎉",
            show_alert=True,
        )
        if query.message and (clicked_user_id == target_user_id or target_user_id == 0):
            try:
                await query.message.delete()
            except Exception:
                pass
    else:
        await query.answer(
            "❌ Siz hali barcha kanallarga a'zo bo'lmadingiz!\nIltimos, yuqoridagi barcha kanallarga a'zo bo'lib qayta tekshiring.",
            show_alert=True,
        )


@router.message(Command("tekshir"))
async def cmd_tekshir(message: Message, bot: Bot) -> None:
    """Bot sozlamalarini va barcha ulangan chatlarni tekshirish (faqat bot egasi)."""
    if not ADMIN_ID or not message.from_user or message.from_user.id != ADMIN_ID:
        return

    lines = ["🔍 <b>Bot diagnostikasi va ulangan chatlar:</b>\n"]

    try:
        me = await bot.get_me()
        lines.append(f"🤖 <b>Bot:</b> @{me.username} ({me.first_name})")
        lines.append(f"👑 <b>Bot egasi ID:</b> <code>{ADMIN_ID}</code>")
    except Exception as e:
        lines.append(f"❌ Bot xatosi: {e}")

    all_chats = await get_all_linked_chats()
    if all_chats:
        channels = [c for c in all_chats if c["chat_type"] == "channel"]
        groups = [c for c in all_chats if c["chat_type"] == "group"]

        lines.append(f"\n📊 <b>Jami ulangan chatlar: {len(all_chats)} ta</b>")
        if channels:
            lines.append(f"\n📢 <b>Kanallar ({len(channels)} ta):</b>")
            for c in channels:
                lines.append(f"  • {c['chat_title'] or 'Nomsiz'} (<code>{c['chat_id']}</code>)")

        if groups:
            lines.append(f"\n💬 <b>Guruhlar ({len(groups)} ta):</b>")
            for g in groups:
                lines.append(f"  • {g['chat_title'] or 'Nomsiz'} (<code>{g['chat_id']}</code>)")
    else:
        lines.append("\n⚠️ Hozircha hech qanday kanal yoki guruh ulanmagan.")
        lines.append("<i>Botni kanal/guruhga admin qilishingiz bilan bu yerda chiqadi.</i>")

    await message.reply("\n".join(lines), parse_mode="HTML")


@router.message(Command("haftalik_golib"))
async def cmd_haftalik_golib(message: Message, bot: Bot) -> None:
    """Guruhda haftalik g'olib tanlash (faqat guruh adminlari)."""
    if message.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        await message.reply("⚠️ Bu buyruq faqat guruhlarda ishlaydi.")
        return

    if not await _is_group_admin(message, bot):
        return

    if not await is_linked_chat(message.chat.id):
        await add_linked_chat(
            owner_id=ADMIN_ID or 0,
            chat_id=message.chat.id,
            chat_type="group",
            chat_title=message.chat.title,
        )

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
        await add_linked_chat(
            owner_id=ADMIN_ID or 0,
            chat_id=message.chat.id,
            chat_type="group",
            chat_title=message.chat.title,
        )

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
# FAOLLIK KUZATISH, MAJBURIY OBUNA VA 777 O'YINI
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

    # Agar bu chat bazada bo'lmasa, avtomatik ro'yxatga olamiz
    if not await is_linked_chat(event.chat.id):
        chat_type = "channel" if event.chat.type == ChatType.CHANNEL else "group"
        await add_linked_chat(
            owner_id=ADMIN_ID or 0,
            chat_id=event.chat.id,
            chat_type=chat_type,
            chat_title=event.chat.title,
        )

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
    1. Majburiy obuna tekshiruvi (obuna bo'lmaganlarning xabari o'chiriladi va ogohlantirish beriladi)
    2. 777 (🎰) Jackpot o'yinini tekshiradi va birinchi tushirgan g'olibni tabriklaydi
    3. Faqat KANAL POSTI KOMMENTARIYASIda yozilgan xabarlargagina ball beradi (oddiy guruh suhbatlariga ball hisoblanmaydi)
    """
    if message.from_user is None or message.from_user.is_bot:
        return

    # Buyruqlarni o'tkazib yuborish
    if message.text and message.text.startswith("/"):
        return

    # Agar bu guruh bazada bo'lmasa, avtomatik ro'yxatga olamiz
    if not await is_linked_chat(message.chat.id):
        await add_linked_chat(
            owner_id=ADMIN_ID or 0,
            chat_id=message.chat.id,
            chat_type="group",
            chat_title=message.chat.title,
        )

    # ── 1. MAJBURIY OBUNA TEKSHIRUVI ──
    # Guruh adminlari va bot egasini majburiy obunadan ozod qilamiz
    is_admin = await _is_group_admin(message, bot)
    if not is_admin:
        is_subbed, missing = await check_all_mandatory_subs(bot, message.from_user.id)
        if not is_subbed and missing:
            # Foydalanuvchi yozgan xabarni guruhdan o'chiramiz
            try:
                await message.delete()
            except Exception as e:
                logger.warning("Foydalanuvchi xabarini o'chirib bo'lmadi: %s", e)

            first_name = message.from_user.first_name or "Foydalanuvchi"
            safe_name = html.escape(first_name)
            user_link = f'<a href="tg://user?id={message.from_user.id}">{safe_name}</a>'

            warn_lines = [
                f"⚠️ {user_link}, guruhda yozish uchun quyidagi kanallarga a'zo bo'ling:\n"
            ]

            kb_buttons = []
            for i, ch in enumerate(missing, start=1):
                title = ch["channel_title"] or "Kanal"
                username = ch["channel_username"] or ch["channel_id"]

                if username.startswith("@"):
                    clean_user = username[1:]
                    url = f"https://t.me/{clean_user}"
                    display_tag = f"@{clean_user}"
                elif username.startswith("http"):
                    url = username
                    display_tag = title
                elif not username.startswith("-"):
                    url = f"https://t.me/{username}"
                    display_tag = f"@{username}"
                else:
                    url = f"https://t.me/{_bot_username}" if _bot_username else "https://t.me/"
                    display_tag = title

                warn_lines.append(f"{i}) {display_tag}")
                kb_buttons.append([InlineKeyboardButton(text=f"📢 {title}", url=url)])

            warn_lines.append("\nA'zo bo'lganingizdan so'ng 🔍 <b>Holatni tekshirish</b> tugmasini bosing!")
            kb_buttons.append([
                InlineKeyboardButton(
                    text="🔍 Holatni tekshirish",
                    callback_data=f"check_sub:{message.from_user.id}",
                )
            ])

            try:
                warn_msg = await message.answer(
                    "\n".join(warn_lines),
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_buttons),
                )
                # Guruh tozalanib turishi uchun ogohlantirishni 60 soniyada o'chiramiz
                asyncio.create_task(_auto_delete_msg(bot, message.chat.id, warn_msg.message_id, delay=60))
            except Exception as e:
                logger.error("Ogohlantirish xabarini yuborishda xatolik: %s", e)

            return  # Majburiy obunaga a'zo bo'lmaganlarga ball ham, 777 ham hisoblanmaydi!

    # ── 2. 777 JACKPOT (🎰 DICE) O'YIN TEKSHIRUVI ──
    if message.dice and message.dice.emoji == "🎰":
        logger.info(
            "🎰 Dice tashlandi: user=%s (%s), value=%s, chat=%s",
            message.from_user.id, message.from_user.first_name, message.dice.value, message.chat.id,
        )
        if message.dice.value == 64:  # 64 = 777 Jackpot
            reply_msg_id = message.message_id
            if message.reply_to_message:
                reply_msg_id = message.reply_to_message.message_id
            elif message.message_thread_id:
                reply_msg_id = message.message_thread_id

            # Bu post/mavzu ostida avval g'olib bo'lganmi?
            already_won = await check_777_winner_exists(message.chat.id, reply_msg_id)
            if not already_won:
                first_name = message.from_user.first_name or "Noma'lum"
                safe_name = html.escape(first_name)
                user_id = message.from_user.id

                try:
                    # Baraban aylanishi tugashini biroz kutamiz (1.5 soniya)
                    await asyncio.sleep(1.5)

                    await message.reply(
                        f"🎰🎰🎰 <b>JACKPOT! 777 TUSHDI!</b>\n\n"
                        f"🎉 Tabriklaymiz, "
                        f'<a href="tg://user?id={user_id}">{safe_name}</a>! '
                        f"Siz birinchi bo'lib <b>777</b> tushirdingiz va yutdingiz! 🏆\n\n"
                        f"Sovg'angizni olish uchun admin bilan bog'laning! 🎁",
                        parse_mode="HTML",
                    )

                    await save_777_winner(
                        chat_id=message.chat.id,
                        reply_to_message_id=reply_msg_id,
                        winner_user_id=user_id,
                        winner_first_name=first_name,
                    )
                    logger.info("777 Jackpot g'olib e'lon qilindi: user=%s, chat=%s", user_id, message.chat.id)
                except Exception as e:
                    logger.error("777 tabrik yuborishda xatolik: %s", e, exc_info=True)

    # ── 3. FAOLLIKNI BAZAGA YOZISH (FAQAT KANAL POSTI KOMMENTI BO'LSA) ──
    is_channel_post_comment = False
    if message.reply_to_message:
        reply = message.reply_to_message
        if reply.is_automatic_forward:
            is_channel_post_comment = True
        elif reply.sender_chat and reply.sender_chat.type == ChatType.CHANNEL:
            is_channel_post_comment = True
        elif reply.forward_from_chat and reply.forward_from_chat.type == ChatType.CHANNEL:
            is_channel_post_comment = True
        elif message.message_thread_id is not None:
            is_channel_post_comment = True
    elif message.message_thread_id is not None:
        is_channel_post_comment = True

    if is_channel_post_comment:
        await log_activity(
            user_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name or "Noma'lum",
            activity_type="comment",
            message_id=message.message_id,
            chat_id=message.chat.id,
        )
        logger.info("Komment faolligi yozildi: user=%s, chat=%s, msg=%s", message.from_user.id, message.chat.id, message.message_id)
    else:
        logger.debug("Oddiy chat xabari (post kamenti emas), ball yozilmadi. user=%s, chat=%s", message.from_user.id, message.chat.id)

