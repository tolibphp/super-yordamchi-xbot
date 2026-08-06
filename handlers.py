"""
handlers.py — Telegram update handlerlar.
Smart Viral Contest, Referal tizimi, Anti-drop penalty, Majburiy obuna,
777 o'yini va Admin boshqaruv paneli.
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
from aiogram.filters import (
    Command,
    CommandStart,
    ChatMemberUpdatedFilter,
    IS_NOT_MEMBER,
    MEMBER,
    ADMINISTRATOR,
    KICKED,
    LEFT,
)
from aiogram.enums import ChatType, ChatMemberStatus
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
    get_or_create_user,
    process_referral_reward,
    process_referral_drop,
    get_user_profile,
    get_top_referrers,
    claim_daily_post_reward,
    create_promo_code,
    claim_promo_code,
    create_contest,
    get_active_contests,
    get_contest,
    register_user_for_contest,
    get_contest_participants,
    end_contest,
    get_all_bot_user_ids,
    get_bot_setting,
    set_bot_setting,
)
from membership import check_membership, check_all_mandatory_subs
from winner import pick_winner
from contest import (
    build_share_data,
    build_contest_post_content,
    draw_contest_winners,
)

logger = logging.getLogger(__name__)
router = Router()

# Bot username'ini saqlash uchun
_bot_username: str = ""


class AdminStates(StatesGroup):
    """Admin panel uchun FSM holatlari."""
    waiting_for_channel_input = State()
    contest_title = State()
    contest_min_refs = State()
    contest_prize = State()
    promo_code = State()
    promo_points = State()
    promo_max_uses = State()
    daily_post_url = State()
    broadcast_text = State()


class UserStates(StatesGroup):
    """Foydalanuvchi holatlari."""
    waiting_promo_code = State()


async def set_bot_username(bot: Bot) -> None:
    """Bot username'ini olish va saqlash."""
    global _bot_username
    me = await bot.get_me()
    _bot_username = me.username or ""


# ─────────────────────────────────────────────
# FOYDALANUVCHI INTERFEYSI VA MENYULAR
# ─────────────────────────────────────────────

def _build_user_dashboard(user: dict, bot_user_name: str) -> tuple[str, InlineKeyboardMarkup]:
    """Foydalanuvchi asosiy boshqaruv kabineti matni va tugmalari."""
    name = html.escape(user.get("first_name", "Do'stim"))
    points = user.get("points", 0)
    refs = user.get("referral_count", 0)
    is_vip = user.get("vip_status", 0) == 1
    vip_badge = " 👑 VIP" if is_vip else ""

    text = (
        f"👋 <b>Xush kelibsiz, {name}!</b>{vip_badge}\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 <b>Sizning balingiz:</b> <code>{points}</code> ball\n"
        f"👥 <b>Faol referallaringiz:</b> <code>{refs}</code> ta do'st\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🔥 <b>Qanday qilib ball to'plash mumkin?</b>\n"
        f"1️⃣ «🚀 Do'stlarga Ulashish» tugmasi orqali do'stlaringizni taklif qiling (+1 ball)\n"
        f"2️⃣ Kanaldagi kunlik postlarni ko'ring (+1 ball)\n"
        f"3️⃣ Yashirin promokodlarni kiriting (+2 ball)\n\n"
        f"🎁 <b>Qimmatbaho konkurslarimizda qatnashing va Telegram Premium yuting!</b>"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🚀 Do'stlarga Ulashish", callback_data="user:share"),
            InlineKeyboardButton(text="🎁 Faol Konkurslar", callback_data="user:contests"),
        ],
        [
            InlineKeyboardButton(text="👤 Profilim", callback_data="user:profile"),
            InlineKeyboardButton(text="🏆 Reyting (Top)", callback_data="user:top"),
        ],
        [
            InlineKeyboardButton(text="⚡ Bugungi post (+1 ball)", callback_data="user:daily_post"),
            InlineKeyboardButton(text="🔑 Promokod kiritish", callback_data="user:promo"),
        ],
        [
            InlineKeyboardButton(text="ℹ️ Qo'llanma", callback_data="user:help"),
        ],
    ])

    return text, kb


def _build_sub_gatekeeper(missing: list[dict], bot_user_name: str, payload: str = "") -> tuple[str, InlineKeyboardMarkup]:
    """Majburiy obuna ekrani (Gatekeeper)."""
    text_lines = [
        "🔒 <b>BOTDAN FOYDALANISH UCHUN KANALGA A'ZO BO'LING!</b>\n",
        "Konkurslarda qatnashish, ballar to'plash va sovg'alarni yutib olish uchun avval quyidagi rasmiy kanalimizga a'zo bo'lishingiz shart:\n",
    ]

    buttons = []
    for i, ch in enumerate(missing, start=1):
        title = ch.get("channel_title") or "Rasmiy Kanal"
        uname = ch.get("channel_username") or ch.get("channel_id")
        if uname.startswith("@"):
            url = f"https://t.me/{uname[1:]}"
            display_tag = uname
        elif uname.startswith("http"):
            url = uname
            display_tag = title
        elif not uname.startswith("-"):
            url = f"https://t.me/{uname}"
            display_tag = f"@{uname}"
        else:
            url = f"https://t.me/{bot_user_name}" if bot_user_name else "https://t.me/"
            display_tag = title

        text_lines.append(f"{i}) <b>{title}</b> ({display_tag})")
        buttons.append([InlineKeyboardButton(text=f"📢 {title} ga A'zo bo'lish", url=url)])

    text_lines.append("\n✅ A'zo bo'lgach, pastdagi <b>«Tekshirish & Davom etish»</b> tugmasini bosing:")
    buttons.append([
        InlineKeyboardButton(
            text="✅ Tekshirish & Davom etish",
            callback_data=f"user:verify_sub:{payload}",
        )
    ])

    return "\n".join(text_lines), InlineKeyboardMarkup(inline_keyboard=buttons)


# ─────────────────────────────────────────────
# /START VA PAYLOAD HANDLER
# ─────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(message: Message, bot: Bot, state: FSMContext) -> None:
    """Botga start berilganda: referal, konkurs yoki oddiy kirishni qayta ishlaydi."""
    await state.clear()
    if not _bot_username:
        await set_bot_username(bot)

    if not message.from_user:
        return

    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name or "Foydalanuvchi"

    # Start argumentini tahlil qilish
    args = message.text.split(maxsplit=1)
    payload = args[1].strip() if len(args) > 1 else ""

    referrer_id = 0
    contest_id = 0

    if payload.startswith("ref_"):
        ref_str = payload.replace("ref_", "")
        if ref_str.isdigit():
            referrer_id = int(ref_str)
    elif payload.isdigit():
        referrer_id = int(payload)
    elif payload.startswith("contest_"):
        c_str = payload.replace("contest_", "")
        if c_str.isdigit():
            contest_id = int(c_str)

    # 1. Majburiy obunani tekshirish (Gatekeeper)
    is_subbed, missing = await check_all_mandatory_subs(bot, user_id)
    if not is_subbed and missing:
        gate_text, gate_kb = _build_sub_gatekeeper(missing, _bot_username, payload=payload)
        await message.answer(gate_text, parse_mode="HTML", reply_markup=gate_kb)
        return

    # 2. Foydalanuvchini bazaga yozish / olish
    user_dict, is_new = await get_or_create_user(user_id, username, first_name, referred_by=referrer_id)

    # 3. Agar yangi referal bo'lsa — taklif qiluvchiga mukofot berish va bildirishnoma yuborish
    if is_new and referrer_id > 0 and referrer_id != user_id:
        awarded, total_pts, milestone = await process_referral_reward(
            referrer_id=referrer_id,
            new_user_id=user_id,
            new_user_name=username,
            new_user_first_name=first_name,
        )
        if awarded:
            safe_new_name = html.escape(first_name)
            new_user_tag = f"@{username}" if username else f'<a href="tg://user?id={user_id}">{safe_new_name}</a>'
            try:
                notif_text = (
                    f"🎉 <b>Yangi do'stingiz {new_user_tag} kanalga a'zo bo'ldi!</b>\n\n"
                    f"🎁 Sizga <b>+1 ball</b> qo'shildi!\n"
                    f"📊 Sizning jami balingiz: <b>{total_pts} ball</b>"
                )
                if milestone:
                    notif_text += f"\n\n🏆 <b>Yutuq:</b> {milestone['title']}"

                await bot.send_message(referrer_id, notif_text, parse_mode="HTML")
            except Exception as e:
                logger.warning("Referrer %s ga xabar yuborib bo'lmadi: %s", referrer_id, e)

    # 4. Agar foydalanuvchi ma'lum bir konkursga kirgan bo'lsa
    if contest_id > 0:
        success, reg_msg, t_num = await register_user_for_contest(contest_id, user_id)
        dash_text, dash_kb = _build_user_dashboard(user_dict, _bot_username)
        await message.answer(f"{reg_msg}\n\n━━━━━━━━━━━━━━━━━━━━━\n{dash_text}", parse_mode="HTML", reply_markup=dash_kb)
        return

    # 5. Oddiy holat: Asosiy dashboardni chiqarish
    dash_text, dash_kb = _build_user_dashboard(user_dict, _bot_username)
    await message.answer(dash_text, parse_mode="HTML", reply_markup=dash_kb)


# ─────────────────────────────────────────────
# GATEKEEPER OBUNA TEKSHIRISH CALLBACK
# ─────────────────────────────────────────────

@router.callback_query(F.data.startswith("user:verify_sub:"))
async def cb_user_verify_sub(query: CallbackQuery, bot: Bot) -> None:
    """Foydalanuvchi Gatekeeperda obunani tasdiqlaganda."""
    if not _bot_username:
        await set_bot_username(bot)

    payload = query.data.replace("user:verify_sub:", "").strip()
    user_id = query.from_user.id
    username = query.from_user.username
    first_name = query.from_user.first_name or "Foydalanuvchi"

    is_subbed, missing = await check_all_mandatory_subs(bot, user_id)
    if not is_subbed and missing:
        await query.answer("❌ Siz hali barcha kanallarga a'zo bo'lmadingiz! Iltimos, a'zo bo'ling.", show_alert=True)
        return

    await query.answer("✅ Obuna tasdiqlandi! Xush kelibsiz!", show_alert=False)

    referrer_id = 0
    contest_id = 0
    if payload.startswith("ref_"):
        ref_str = payload.replace("ref_", "")
        if ref_str.isdigit():
            referrer_id = int(ref_str)
    elif payload.isdigit():
        referrer_id = int(payload)
    elif payload.startswith("contest_"):
        c_str = payload.replace("contest_", "")
        if c_str.isdigit():
            contest_id = int(c_str)

    user_dict, is_new = await get_or_create_user(user_id, username, first_name, referred_by=referrer_id)

    if is_new and referrer_id > 0 and referrer_id != user_id:
        awarded, total_pts, milestone = await process_referral_reward(
            referrer_id=referrer_id,
            new_user_id=user_id,
            new_user_name=username,
            new_user_first_name=first_name,
        )
        if awarded:
            safe_new_name = html.escape(first_name)
            new_user_tag = f"@{username}" if username else f'<a href="tg://user?id={user_id}">{safe_new_name}</a>'
            try:
                notif_text = (
                    f"🎉 <b>Yangi do'stingiz {new_user_tag} kanalga a'zo bo'ldi!</b>\n\n"
                    f"🎁 Sizga <b>+1 ball</b> qo'shildi!\n"
                    f"📊 Sizning jami balingiz: <b>{total_pts} ball</b>"
                )
                if milestone:
                    notif_text += f"\n\n🏆 <b>Yutuq:</b> {milestone['title']}"

                await bot.send_message(referrer_id, notif_text, parse_mode="HTML")
            except Exception:
                pass

    if contest_id > 0:
        success, reg_msg, t_num = await register_user_for_contest(contest_id, user_id)
        dash_text, dash_kb = _build_user_dashboard(user_dict, _bot_username)
        if query.message:
            await query.message.edit_text(f"{reg_msg}\n\n━━━━━━━━━━━━━━━━━━━━━\n{dash_text}", parse_mode="HTML", reply_markup=dash_kb)
        return

    dash_text, dash_kb = _build_user_dashboard(user_dict, _bot_username)
    if query.message:
        await query.message.edit_text(dash_text, parse_mode="HTML", reply_markup=dash_kb)


# ─────────────────────────────────────────────
# FOYDALANUVCHI MENYU CALLBACKLARI
# ─────────────────────────────────────────────

@router.callback_query(F.data == "user:menu")
async def cb_user_menu(query: CallbackQuery, bot: Bot, state: FSMContext) -> None:
    """Asosiy menyuga qaytish."""
    await state.clear()
    if not _bot_username:
        await set_bot_username(bot)

    user_dict = await get_user_profile(query.from_user.id)
    if not user_dict:
        user_dict, _ = await get_or_create_user(
            query.from_user.id,
            query.from_user.username,
            query.from_user.first_name or "Foydalanuvchi",
        )

    text, kb = _build_user_dashboard(user_dict, _bot_username)
    if query.message:
        try:
            await query.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
        except Exception:
            pass
    await query.answer()


@router.callback_query(F.data == "user:share")
async def cb_user_share(query: CallbackQuery, bot: Bot) -> None:
    """Do'stlarga ulashish (1-bosishda share)."""
    if not _bot_username:
        await set_bot_username(bot)

    user_id = query.from_user.id
    share_url, post_text = build_share_data(_bot_username, user_id)
    ref_link = f"https://t.me/{_bot_username}?start=ref_{user_id}"

    text = (
        f"🚀 <b>DO'STLARNI TAKLIF QILISH VA 1-BOSISHDA ULASHISH</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🔗 <b>Sizning shaxsiy referal havolangiz:</b>\n"
        f"<code>{ref_link}</code>\n\n"
        f"💡 <i>Ushbu havolani do'stlaringizga, guruhlarga yoki kanallarga tarqating. "
        f"Har bir yangi obuna bo'lgan do'stingiz uchun sizga <b>+1 ball</b> beriladi!</i>\n\n"
        f"🎁 <b>Bonuslar:</b>\n"
        f"• 3 ta do'st — Omadli chipta statusi\n"
        f"• 10 ta do'st — +5 qo'shimcha bonus ball\n"
        f"• 25 ta do'st — 👑 VIP Status va +15 bonus ball!\n"
        f"• 30 ta do'st — Gift Konkursida qatnashish huquqi\n"
        f"• 50 ta do'st — Telegram Premium Konkursida qatnashish huquqi!\n\n"
        f"👇 <b>Hoziroq quyidagi tugmani bosib do'stlaringizga yuboring:</b>"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🚀 Do'stlarga Yuborish (1-bosishda)", url=share_url),
        ],
        [
            InlineKeyboardButton(text="⬅️ Bosh Menyu", callback_data="user:menu"),
        ],
    ])

    if query.message:
        await query.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await query.answer()


@router.callback_query(F.data == "user:profile")
async def cb_user_profile(query: CallbackQuery, bot: Bot) -> None:
    """Foydalanuvchi shaxsiy profili."""
    if not _bot_username:
        await set_bot_username(bot)

    user = await get_user_profile(query.from_user.id)
    if not user:
        user, _ = await get_or_create_user(
            query.from_user.id,
            query.from_user.username,
            query.from_user.first_name or "Foydalanuvchi",
        )

    name = html.escape(user.get("first_name", "Foydalanuvchi"))
    user_id = user["user_id"]
    pts = user.get("points", 0)
    refs = user.get("referral_count", 0)
    bonus = user.get("bonus_points", 0)
    is_vip = user.get("vip_status", 0) == 1
    joined = user.get("joined_at", "Noma'lum")
    ref_link = f"https://t.me/{_bot_username}?start=ref_{user_id}"

    # Konkurslarga loyiqlik (Eligibility)
    gift_status = "✅ Tayyor (Qatnasha olasiz)" if refs >= 30 else f"⏳ Yana {30 - refs} ta do'st kerak"
    prem_status = "✅ Tayyor (Qatnasha olasiz)" if refs >= 50 else f"⏳ Yana {50 - refs} ta do'st kerak"

    text = (
        f"👤 <b>SIZNING SHAXSIY PROFILINGIZ</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🆔 <b>ID:</b> <code>{user_id}</code>\n"
        f"👤 <b>Ism:</b> {name}\n"
        f"👑 <b>Status:</b> {'👑 VIP Foydalanuvchi' if is_vip else 'Oddiy A\'zo'}\n"
        f"📅 <b>Qo'shilgan sana:</b> {joined}\n\n"
        f"📊 <b>HISOB STATISTIKASI:</b>\n"
        f"💰 <b>Jami ballar:</b> <b>{pts}</b> ball\n"
        f"👥 <b>Chaqirilgan do'stlar:</b> <b>{refs}</b> ta\n"
        f"🎁 <b>Olingan bonuslar:</b> <b>{bonus}</b> ball\n\n"
        f"🏆 <b>KONKURSLARGA STATUSINGIZ:</b>\n"
        f"🎁 <b>Gift Konkurs (min 30 ref):</b> {gift_status}\n"
        f"💎 <b>Premium Konkurs (min 50 ref):</b> {prem_status}\n\n"
        f"🔗 <b>Sizning taklif havolangiz:</b>\n<code>{ref_link}</code>"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🚀 Do'stlarni taklif qilish", callback_data="user:share"),
        ],
        [
            InlineKeyboardButton(text="🎁 Konkurslarga o'tish", callback_data="user:contests"),
            InlineKeyboardButton(text="⬅️ Bosh Menyu", callback_data="user:menu"),
        ],
    ])

    if query.message:
        await query.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await query.answer()


@router.callback_query(F.data == "user:contests")
async def cb_user_contests(query: CallbackQuery) -> None:
    """Faol konkurslar ro'yxati va ularga qatnashish imkoniyati."""
    contests = await get_active_contests()
    user = await get_user_profile(query.from_user.id)
    user_refs = user.get("referral_count", 0) if user else 0

    if not contests:
        text = (
            "🎁 <b>FAOL KONKURSLAR</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            "⚠️ Hozirda faol konkurslar mavjud emas.\n"
            "Tez orada yangi qimmatbaho konkurslar e'lon qilinadi! Kanalimizni kuzatib boring."
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Bosh Menyu", callback_data="user:menu")],
        ])
    else:
        lines = [
            "🎁 <b>HOZIRGI FAOL KONKURSLAR</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━\n",
            f"📊 Sizning hozirgi referallaringiz: <b>{user_refs} ta</b>\n",
        ]

        buttons = []
        for c in contests:
            c_type = c["contest_type"]
            badge = "💎 Telegram Premium" if c_type == "premium" else ("🎁 Telegram Gift" if c_type == "gift" else "🎯 Maxsus")
            min_r = c["min_referrals"]
            title = c["title"]
            prize = c["prize_description"] or "Sovg'alar"

            lines.append(f"🏆 <b>{title}</b> ({badge})")
            lines.append(f"🎁 <b>Sovg'a:</b> {prize}")
            lines.append(f"📌 <b>Talab:</b> Kamida <b>{min_r} ta</b> faol referal")
            lines.append("──────────────────────")

            buttons.append([
                InlineKeyboardButton(
                    text=f"🎁 Qatnashish: {title[:20]}",
                    callback_data=f"user:join:{c['id']}",
                )
            ])

        buttons.append([InlineKeyboardButton(text="⬅️ Bosh Menyu", callback_data="user:menu")])
        text = "\n".join(lines)
        kb = InlineKeyboardMarkup(inline_keyboard=buttons)

    if query.message:
        await query.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await query.answer()


@router.callback_query(F.data.startswith("user:join:"))
async def cb_user_join_contest(query: CallbackQuery) -> None:
    """Foydalanuvchi konkursda qatnashish tugmasini bosganda."""
    contest_id = int(query.data.split(":")[2])
    user_id = query.from_user.id

    success, msg, ticket_num = await register_user_for_contest(contest_id, user_id)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🚀 Do'stlarni taklif qilish", callback_data="user:share"),
        ],
        [
            InlineKeyboardButton(text="🎁 Barcha Konkurslar", callback_data="user:contests"),
            InlineKeyboardButton(text="⬅️ Bosh Menyu", callback_data="user:menu"),
        ],
    ])

    if query.message:
        await query.message.edit_text(msg, parse_mode="HTML", reply_markup=kb)
    await query.answer()


@router.callback_query(F.data == "user:daily_post")
async def cb_user_daily_post(query: CallbackQuery) -> None:
    """Kunlik post o'qish uchun +1 ball olish."""
    user_id = query.from_user.id
    success, msg = await claim_daily_post_reward(user_id)
    daily_url = await get_bot_setting("daily_post_url", "")

    lines = [
        "⚡ <b>KUNLIK POST MUKOFOSTI</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n",
        msg,
    ]

    buttons = []
    if daily_url:
        buttons.append([InlineKeyboardButton(text="📢 Bugungi Postni Ko'rish", url=daily_url)])

    buttons.append([InlineKeyboardButton(text="⬅️ Bosh Menyu", callback_data="user:menu")])

    if query.message:
        await query.message.edit_text("\n".join(lines), parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await query.answer()


@router.callback_query(F.data == "user:promo")
async def cb_user_promo_prompt(query: CallbackQuery, state: FSMContext) -> None:
    """Promokod kiritishni so'rash."""
    await state.set_state(UserStates.waiting_promo_code)
    text = (
        "🔑 <b>YASHIRIN PROMOKOD KIRITISH</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Kanaldagi postlarga yashirilgan maxsus promokodlarni (masalan: <code>#AI_PRO</code>) kiritib, "
        "qo'shimcha ballarni qo'lga kiriting!\n\n"
        "✍️ <b>Promokodni yuboring:</b>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="user:menu")],
    ])
    if query.message:
        await query.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await query.answer()


@router.message(UserStates.waiting_promo_code)
async def user_enter_promo_code(message: Message, state: FSMContext) -> None:
    """Foydalanuvchi promokod yozganda."""
    code_text = message.text.strip() if message.text else ""
    user_id = message.from_user.id if message.from_user else 0

    success, msg, pts = await claim_promo_code(user_id, code_text)
    await state.clear()

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Profilim", callback_data="user:profile")],
        [InlineKeyboardButton(text="⬅️ Bosh Menyu", callback_data="user:menu")],
    ])

    await message.reply(f"{msg}", parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data == "user:top")
async def cb_user_top(query: CallbackQuery) -> None:
    """Eng ko'p do'st taklif qilgan liderlar reytingi."""
    leaders = await get_top_referrers(limit=10)
    lines = [
        "🏆 <b>ENG KO'P DO'ST TAKLIF QILGAN LIDERLAR</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n",
    ]

    if not leaders:
        lines.append("⚠️ Hozircha referal taklif qilganlar yo'q. Birinchi bo'ling!")
    else:
        for i, u in enumerate(leaders, start=1):
            medal = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"][i - 1]
            name = html.escape(u.get("first_name", "Noma'lum"))
            refs = u.get("referral_count", 0)
            pts = u.get("points", 0)
            vip = " 👑" if u.get("vip_status") == 1 else ""
            lines.append(f"{medal} <b>{name}</b>{vip} — <b>{refs}</b> ta do'st ({pts} ball)")

    lines.append("\n💡 <i>Liderlar ro'yxatiga kirish uchun ko'proq do'stlaringizni taklif qiling!</i>")

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Do'stlarni taklif qilish", callback_data="user:share")],
        [InlineKeyboardButton(text="⬅️ Bosh Menyu", callback_data="user:menu")],
    ])

    if query.message:
        await query.message.edit_text("\n".join(lines), parse_mode="HTML", reply_markup=kb)
    await query.answer()


@router.callback_query(F.data == "user:help")
async def cb_user_help(query: CallbackQuery) -> None:
    """Foydalanuvchi uchun yo'riqnoma."""
    text = (
        "📖 <b>BOT VA KONKURSLAR BO'YICHA QO'LLANMA</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "🎯 <b>Konkursda qanday qatnashish mumkin?</b>\n"
        "1. «🎁 Faol Konkurslar» bo'limiga kiring.\n"
        "2. Konkurs shartini (masalan: min 30 yoki 50 ta referal) bajaring.\n"
        "3. «🎁 Qatnashish» tugmasini bosing va o'z omadli chiptangizni oling!\n\n"
        "🛡️ <b>Anti-Drop (Jarima) tizimi qanday ishlaydi?</b>\n"
        "Siz taklif qilgan do'st kanaldan chiqib ketmasligi kerak. "
        "Agar u kanaldan chiqsa, sizdan avtomatik <b>-1 ball</b> olinadi.\n\n"
        "🎰 <b>777 Jackpot o'yini:</b>\n"
        "Kanal postlari ostidagi muhokama guruhida 🎰 stikerini yuborib, "
        "birinchi 777 tushirgan ishtirokchi kutilmagan sovg'ani yutadi!"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Bosh Menyu", callback_data="user:menu")],
    ])
    if query.message:
        await query.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await query.answer()


# ─────────────────────────────────────────────
# ANTI-DROP & PENALTY HODISASI (CHAT MEMBER)
# ─────────────────────────────────────────────

@router.chat_member()
async def on_chat_member_updated(event: ChatMemberUpdated, bot: Bot) -> None:
    """
    Kanal yoki guruhdan kimdir chiqib ketganda (MEMBER >> LEFT/KICKED):
    Anti-Drop himoyasi ishga tushadi, taklif qilgandan -1 ball olinadi va ogohlantirish beriladi.
    """
    old_status = event.old_chat_member.status
    new_status = event.new_chat_member.status

    # Chiqib ketish holati
    is_leaving = (
        old_status in (ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.RESTRICTED)
        and new_status in (ChatMemberStatus.LEFT, ChatMemberStatus.KICKED)
    )

    if not is_leaving:
        return

    leaving_user = event.new_chat_member.user
    if leaving_user.is_bot:
        return

    logger.info("Foydalanuvchi chatdan chiqdi: user_id=%s, chat_id=%s", leaving_user.id, event.chat.id)

    referrer_id, user_name, rem_pts = await process_referral_drop(leaving_user.id)
    if referrer_id:
        safe_name = html.escape(user_name or "Foydalanuvchi")
        try:
            warn_msg = (
                f"⚠️ <b>DIQQAT: Referal balingiz kamaydi!</b>\n\n"
                f"Siz taklif qilgan <b>{safe_name}</b> rasmiy kanalimizdan chiqib ketdi.\n"
                f"🔻 Sizdan <b>-1 ball</b> olindi.\n"
                f"📊 Hozirgi balingiz: <b>{rem_pts} ball</b>"
            )
            await bot.send_message(referrer_id, warn_msg, parse_mode="HTML")
            logger.info("Anti-Drop jarimasi referrer %s ga yuborildi.", referrer_id)
        except Exception as e:
            logger.warning("Anti-Drop xabarini referrer %s ga yuborib bo'lmadi: %s", referrer_id, e)


# ─────────────────────────────────────────────
# ADMIN BOSHQARUV PANELİ (/admin)
# ─────────────────────────────────────────────

async def _build_admin_menu_text_and_kb() -> tuple[str, InlineKeyboardMarkup]:
    """Admin boshqaruv panelining bosh menyusi."""
    is_sub_on = await is_mandatory_sub_enabled()
    sub_icon = "🟢" if is_sub_on else "🔴"
    sub_action_text = "Majburiy obunani o'chirish" if is_sub_on else "Majburiy obunani yoqish"

    text = (
        "👑 <b>ADMIN BOSHQARUV PANELI (SUPER ENGINE)</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "Bu yerdan barcha konkurslarni yaratish, g'oliblarni aniqlash, "
        "promokodlar va majburiy kanallarni boshqarishingiz mumkin.\n\n"
        f"⚙️ <b>Majburiy obuna:</b> {sub_icon} {'YONIQ' if is_sub_on else 'O\'CHIQ'}\n"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🎁 Yangi Konkurs Yaratish", callback_data="admin:new_contest"),
            InlineKeyboardButton(text="🎲 G'oliblarni Aniqlash (/draw)", callback_data="admin:draw_list"),
        ],
        [
            InlineKeyboardButton(text="🔑 Promokod Yaratish", callback_data="admin:new_promo"),
            InlineKeyboardButton(text="⚡ Kunlik Post Linki", callback_data="admin:set_daily_post"),
        ],
        [
            InlineKeyboardButton(text="📢 Barchaga Xabar (Broadcast)", callback_data="admin:broadcast"),
            InlineKeyboardButton(text="📊 Bot Statistikasi", callback_data="admin:stats"),
        ],
        [
            InlineKeyboardButton(text="➕ Majburiy Kanal Qo'shish", callback_data="admin:add_channel"),
            InlineKeyboardButton(text="🗑 Kanal O'chirish", callback_data="admin:del_channel_list"),
        ],
        [
            InlineKeyboardButton(text=f"{sub_icon} {sub_action_text}", callback_data="admin:toggle_sub"),
        ],
        [
            InlineKeyboardButton(text="❌ Yopish", callback_data="admin:close"),
        ],
    ])

    return text, kb


@router.message(Command("admin"))
async def cmd_admin(message: Message, bot: Bot, state: FSMContext) -> None:
    """Admin panelni ochadi."""
    await state.clear()
    if not ADMIN_ID or not message.from_user or message.from_user.id != ADMIN_ID:
        return

    text, kb = await _build_admin_menu_text_and_kb()
    await message.reply(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data == "admin:menu")
async def cb_admin_menu(query: CallbackQuery, state: FSMContext) -> None:
    """Admin menyusiga qaytish."""
    await state.clear()
    text, kb = await _build_admin_menu_text_and_kb()
    if query.message:
        try:
            await query.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
        except Exception:
            pass
    await query.answer()


# ── KONKURS YARATISH WIZARDI ──

@router.callback_query(F.data == "admin:new_contest")
async def cb_admin_new_contest_step1(query: CallbackQuery, state: FSMContext) -> None:
    """Konkurs yaratish: 1-qadam — Konkurs turi."""
    await state.clear()
    text = (
        "🎁 <b>YANGI KONKURS YARATISH (1/3)</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Qanday turdagi konkurs yaratmoqchisiz?\n\n"
        "💎 <b>Telegram Premium Konkurs</b> — Kamida <b>50 ta do'st</b> taklif qilganlar qatnashadi.\n"
        "🎁 <b>Telegram Gift / Yulduzlar Konkursi</b> — Kamida <b>30 ta do'st</b> taklif qilganlar qatnashadi.\n"
        "🎯 <b>Maxsus Konkurs</b> — O'zingiz istalgan minimal do'stlar sonini belgilaysiz."
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="💎 Premium Konkurs (min 50 ref)", callback_data="admin:c_type:premium"),
        ],
        [
            InlineKeyboardButton(text="🎁 Gift Konkurs (min 30 ref)", callback_data="admin:c_type:gift"),
        ],
        [
            InlineKeyboardButton(text="🎯 Maxsus Konkurs (O'zim kiritaman)", callback_data="admin:c_type:custom"),
        ],
        [
            InlineKeyboardButton(text="⬅️ Bekor qilish", callback_data="admin:menu"),
        ],
    ])
    if query.message:
        await query.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await query.answer()


@router.callback_query(F.data.startswith("admin:c_type:"))
async def cb_admin_new_contest_step2(query: CallbackQuery, state: FSMContext) -> None:
    """Konkurs turi tanlandi, nomini va shartlarini so'rash."""
    c_type = query.data.split(":")[2]
    await state.update_data(contest_type=c_type)

    if c_type == "premium":
        await state.update_data(min_referrals=50)
        await state.set_state(AdminStates.contest_title)
        prompt = "✍️ <b>Konkurs nomini kiriting:</b>\n(Masalan: <i>Telegram Premium 3 Oylik Konkurs</i>)"
    elif c_type == "gift":
        await state.update_data(min_referrals=30)
        await state.set_state(AdminStates.contest_title)
        prompt = "✍️ <b>Konkurs nomini kiriting:</b>\n(Masalan: <i>1000 Telegram Yulduzlar Konkursi</i>)"
    else:
        await state.set_state(AdminStates.contest_min_refs)
        prompt = "✍️ Ushbu maxsus konkursda qatnashish uchun <b>minimal nechta do'st</b> chaqirish shart bo'lsin?\n(Masalan: <code>15</code> yoki <code>20</code>)"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Bekor qilish", callback_data="admin:menu")],
    ])
    if query.message:
        await query.message.edit_text(prompt, parse_mode="HTML", reply_markup=kb)
    await query.answer()


@router.message(AdminStates.contest_min_refs)
async def admin_contest_custom_min_refs(message: Message, state: FSMContext) -> None:
    """Maxsus konkurs uchun min referal kiritildi."""
    val = message.text.strip() if message.text else ""
    if not val.isdigit() or int(val) <= 0:
        await message.reply("⚠️ Iltimos, faqat musbat raqam kiriting (masalan: 15):")
        return

    await state.update_data(min_referrals=int(val))
    await state.set_state(AdminStates.contest_title)
    await message.reply(
        "✅ Minimal referal: <b>" + val + " ta</b> deb belgilandi.\n\n"
        "✍️ Endi <b>Konkurs nomini</b> kiriting:\n(Masalan: <i>Yozgi Maxsus Sovg'alar Konkursi</i>)",
        parse_mode="HTML",
    )


@router.message(AdminStates.contest_title)
async def admin_contest_get_title(message: Message, state: FSMContext) -> None:
    """Konkurs nomi kiritildi, sovg'a tavsifini so'rash."""
    title = message.text.strip() if message.text else "Yangi Konkurs"
    await state.update_data(contest_title=title)
    await state.set_state(AdminStates.contest_prize)

    await message.reply(
        f"✅ Konkurs nomi: <b>{title}</b>\n\n"
        f"✍️ Endi <b>Sovg'a tavsifini</b> kiriting:\n"
        f"(Masalan: <i>3 oylik Telegram Premium obunasi yoki 500 yulduz!</i>)",
        parse_mode="HTML",
    )


@router.message(AdminStates.contest_prize)
async def admin_contest_finish(message: Message, state: FSMContext, bot: Bot) -> None:
    """Konkurs yaratildi — bazaga yozish va e'lon qilish imkoniyatini berish."""
    prize = message.text.strip() if message.text else "Sovrin"
    data = await state.get_data()
    await state.clear()

    c_type = data.get("contest_type", "gift")
    min_refs = data.get("min_referrals", 30)
    title = data.get("contest_title", "Konkurs")

    contest_id = await create_contest(
        title=title,
        contest_type=c_type,
        min_referrals=min_refs,
        prize_description=prize,
    )

    contest_dict = {
        "id": contest_id,
        "title": title,
        "contest_type": c_type,
        "min_referrals": min_refs,
        "prize_description": prize,
    }

    if not _bot_username:
        await set_bot_username(bot)

    post_text, post_kb = build_contest_post_content(_bot_username, contest_dict)

    text = (
        f"🎉 <b>KONKURS MUVAFFAQIYATLI YARATILDI!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🆔 <b>ID:</b> #{contest_id}\n"
        f"🏆 <b>Nomi:</b> {title}\n"
        f"🎖 <b>Turi:</b> {c_type}\n"
        f"👥 <b>Min referal:</b> {min_refs} ta\n"
        f"🎁 <b>Sovg'a:</b> {prize}\n\n"
        f"📢 <b>Kanalga chiqariladigan e'lon ko'rinishi:</b>\n\n"
        f"{post_text}"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📢 Kanalga e'lon qilish", callback_data=f"admin:post_contest:{contest_id}"),
        ],
        [
            InlineKeyboardButton(text="⬅️ Admin Menyu", callback_data="admin:menu"),
        ],
    ])

    await message.reply(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data.startswith("admin:post_contest:"))
async def cb_admin_post_contest_to_channel(query: CallbackQuery, bot: Bot) -> None:
    """Yaratilgan konkursni ulangan kanallarga post qilish."""
    contest_id = int(query.data.split(":")[2])
    contest = await get_contest(contest_id)
    if not contest:
        await query.answer("Konkurs topilmadi.", show_alert=True)
        return

    if not _bot_username:
        await set_bot_username(bot)

    post_text, post_kb = build_contest_post_content(_bot_username, contest)
    all_chats = await get_all_linked_chats()
    channels = [c for c in all_chats if c["chat_type"] == "channel"]

    if not channels:
        await query.answer("⚠️ Hozircha ulangan kanallar topilmadi. Botni kanalga admin qiling.", show_alert=True)
        return

    posted = 0
    for ch in channels:
        try:
            await bot.send_message(
                chat_id=ch["chat_id"],
                text=post_text,
                parse_mode="HTML",
                reply_markup=post_kb,
            )
            posted += 1
        except Exception as e:
            logger.error("Kanalga post yuborishda xato (%s): %s", ch["chat_id"], e)

    await query.answer(f"✅ Konkurs {posted} ta kanalga joylandi!", show_alert=True)


# ── G'OLIBLARNI ANIQLASH (/draw) ──

@router.callback_query(F.data == "admin:draw_list")
async def cb_admin_draw_list(query: CallbackQuery) -> None:
    """G'oliblarni aniqlash uchun faol konkurslar ro'yxati."""
    contests = await get_active_contests()
    if not contests:
        text = "🎲 <b>G'OLIBLARNI ANIQLASH (/draw)</b>\n\n⚠️ Hozirda faol konkurslar yo'q."
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="admin:menu")],
        ])
    else:
        text = "🎲 <b>G'oliblarni aniqlash uchun konkursni tanlang:</b>"
        buttons = []
        for c in contests:
            buttons.append([
                InlineKeyboardButton(
                    text=f"🏆 {c['title'][:25]}",
                    callback_data=f"admin:draw_exec:{c['id']}",
                )
            ])
        buttons.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data="admin:menu")])
        kb = InlineKeyboardMarkup(inline_keyboard=buttons)

    if query.message:
        await query.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await query.answer()


@router.callback_query(F.data.startswith("admin:draw_exec:"))
async def cb_admin_draw_exec(query: CallbackQuery, bot: Bot) -> None:
    """Tanlangan konkurs bo'yicha g'oliblarni aniqlash."""
    contest_id = int(query.data.split(":")[2])
    res = await draw_contest_winners(bot, contest_id)

    if not res["success"]:
        await query.answer(f"Xato: {res.get('error')}", show_alert=True)
        return

    text = (
        f"{res['announcement_text']}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"✅ <i>Konkurs muvaffaqiyatli yakunlandi!</i>"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="📢 Natijalarni Kanalga Joylash",
                callback_data=f"admin:publish_winners:{contest_id}",
            )
        ],
        [
            InlineKeyboardButton(text="⬅️ Admin Menyu", callback_data="admin:menu"),
        ],
    ])

    if query.message:
        await query.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await query.answer()


@router.callback_query(F.data.startswith("admin:publish_winners:"))
async def cb_admin_publish_winners(query: CallbackQuery, bot: Bot) -> None:
    """G'oliblar e'lonini barcha kanallarga chiqarish."""
    text_to_post = query.message.text if query.message else ""
    # "✅ Konkurs muvaffaqiyatli yakunlandi!" qismini olib tashlaymiz
    if "━━━━━━━━━━━━━━━━━━━━━\n✅ Konkurs" in text_to_post:
        text_to_post = text_to_post.split("━━━━━━━━━━━━━━━━━━━━━\n✅ Konkurs")[0].strip()

    all_chats = await get_all_linked_chats()
    channels = [c for c in all_chats if c["chat_type"] == "channel"]

    posted = 0
    for ch in channels:
        try:
            await bot.send_message(ch["chat_id"], text_to_post, parse_mode="HTML")
            posted += 1
        except Exception as e:
            logger.error("Kanalga g'oliblarni yuborishda xato: %s", e)

    await query.answer(f"✅ G'oliblar e'loni {posted} ta kanalga chiqarildi!", show_alert=True)


# ── PROMOKOD YARATISH ──

@router.callback_query(F.data == "admin:new_promo")
async def cb_admin_new_promo_step1(query: CallbackQuery, state: FSMContext) -> None:
    """Promokod yaratish: kod nomini so'rash."""
    await state.set_state(AdminStates.promo_code)
    text = (
        "🔑 <b>YANGI PROMOKOD YARATISH (1/3)</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "✍️ <b>Promokod matnini kiriting:</b>\n"
        "(Masalan: <code>#AI_PRO</code> yoki <code>TOLIBJON_GIFT</code>)"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Bekor qilish", callback_data="admin:menu")],
    ])
    if query.message:
        await query.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await query.answer()


@router.message(AdminStates.promo_code)
async def admin_promo_code_step2(message: Message, state: FSMContext) -> None:
    """Promokod ballini so'rash."""
    code = message.text.strip().upper() if message.text else ""
    await state.update_data(promo_code=code)
    await state.set_state(AdminStates.promo_points)
    await message.reply(
        f"✅ Promokod: <b>{code}</b>\n\n"
        f"✍️ Ushbu kodni kiritgan foydalanuvchiga <b>necha ball</b> berilsin?\n"
        f"(Masalan: <code>2</code> yoki <code>5</code>)",
        parse_mode="HTML",
    )


@router.message(AdminStates.promo_points)
async def admin_promo_code_step3(message: Message, state: FSMContext) -> None:
    """Promokod nechta kishiga mo'ljallanganligini so'rash."""
    pts_str = message.text.strip() if message.text else "2"
    pts = int(pts_str) if pts_str.isdigit() else 2
    await state.update_data(promo_points=pts)
    await state.set_state(AdminStates.promo_max_uses)
    await message.reply(
        f"✅ Ball: <b>+{pts} ball</b>\n\n"
        f"✍️ Ushbu promokoddan <b>maksimal nechta kishi</b> foydalana olsin?\n"
        f"(Masalan: <code>50</code> yoki <code>100</code>)",
        parse_mode="HTML",
    )


@router.message(AdminStates.promo_max_uses)
async def admin_promo_code_finish(message: Message, state: FSMContext) -> None:
    """Promokodni saqlash."""
    max_uses_str = message.text.strip() if message.text else "50"
    max_uses = int(max_uses_str) if max_uses_str.isdigit() else 50
    data = await state.get_data()
    await state.clear()

    code = data.get("promo_code", "BONUS")
    pts = data.get("promo_points", 2)

    await create_promo_code(code, pts, max_uses)

    text = (
        f"🎉 <b>YANGI PROMOKOD TAYYOR!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔑 <b>Kod:</b> <code>{code}</code>\n"
        f"🎁 <b>Mukofot:</b> +{pts} ball\n"
        f"👥 <b>Foydalanishlar limiti:</b> {max_uses} ta odam\n\n"
        f"💡 <i>Ushbu promokodni kanaldagi postingizga yashirib qo'yishingiz mumkin!</i>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Admin Menyu", callback_data="admin:menu")],
    ])
    await message.reply(text, parse_mode="HTML", reply_markup=kb)


# ── KUNLIK POST SOZLASH ──

@router.callback_query(F.data == "admin:set_daily_post")
async def cb_admin_set_daily_post(query: CallbackQuery, state: FSMContext) -> None:
    """Kunlik post URL sini sozlash."""
    await state.set_state(AdminStates.daily_post_url)
    current_url = await get_bot_setting("daily_post_url", "Belgilanmagan")
    text = (
        "⚡ <b>KUNLIK POST LINKINI BELGILASH</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📌 Hozirgi post linki: {current_url}\n\n"
        "✍️ Kanaldagi bugungi yangi post havolasini (linkini) yuboring:\n"
        "(Masalan: <code>https://t.me/Tolibjon_Life/123</code>)"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Bekor qilish", callback_data="admin:menu")],
    ])
    if query.message:
        await query.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await query.answer()


@router.message(AdminStates.daily_post_url)
async def admin_save_daily_post_url(message: Message, state: FSMContext) -> None:
    """Kunlik post URL sini saqlash."""
    url = message.text.strip() if message.text else ""
    await set_bot_setting("daily_post_url", url)
    await state.clear()

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Admin Menyu", callback_data="admin:menu")],
    ])
    await message.reply(f"✅ Kunlik post havolasi saqlandi:\n<code>{url}</code>", parse_mode="HTML", reply_markup=kb)


# ── BROADCAST (BARCHAGA XABAR YUBORISH) ──

@router.callback_query(F.data == "admin:broadcast")
async def cb_admin_broadcast_prompt(query: CallbackQuery, state: FSMContext) -> None:
    """Broadcast xabarni so'rash."""
    await state.set_state(AdminStates.broadcast_text)
    text = (
        "📢 <b>BARCHA BOT FOYDALANUVCHILARIGA XABAR YUBORISH</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "✍️ Barchaga yubormoqchi bo'lgan xabaringizni yozing (rasm, video yoki matn):"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Bekor qilish", callback_data="admin:menu")],
    ])
    if query.message:
        await query.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await query.answer()


@router.message(AdminStates.broadcast_text)
async def admin_broadcast_execute(message: Message, state: FSMContext, bot: Bot) -> None:
    """Xabarni barcha bot foydalanuvchilariga tarqatish."""
    await state.clear()
    user_ids = await get_all_bot_user_ids()
    if not user_ids:
        await message.reply("⚠️ Hozircha botda foydalanuvchilar yo'q.")
        return

    progress_msg = await message.reply(f"⏳ Xabar {len(user_ids)} ta foydalanuvchiga yuborilmoqda...")

    sent = 0
    failed = 0
    for uid in user_ids:
        try:
            await message.copy_to(chat_id=uid)
            sent += 1
            await asyncio.sleep(0.05)  # Telegram limits
        except Exception:
            failed += 1

    await progress_msg.edit_text(
        f"✅ <b>Broadcast yakunlandi!</b>\n\n"
        f"📤 Yuborildi: <b>{sent} ta</b>\n"
        f"❌ Yetib bormadi (bloklagan): <b>{failed} ta</b>",
        parse_mode="HTML",
    )


# ── MAJBURIY KANALLAR SOZLAMALARI ──

@router.callback_query(F.data == "admin:add_channel")
async def cb_admin_add_channel(query: CallbackQuery, state: FSMContext) -> None:
    """Majburiy kanal qo'shish so'rovi."""
    await state.set_state(AdminStates.waiting_for_channel_input)
    text = (
        "📢 <b>Yangi majburiy kanal qo'shish:</b>\n\n"
        "Kanal username'ini yoki ID sini yuboring:\n"
        "Misol: <code>@Tolibjon_Life</code> yoki <code>-1001234567890</code>\n\n"
        "<i>Eslatma: Bot ushbu kanalda admin bo'lishi shart!</i>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Bekor qilish", callback_data="admin:menu")],
    ])
    if query.message:
        await query.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await query.answer()


@router.message(AdminStates.waiting_for_channel_input)
async def admin_save_mandatory_channel(message: Message, state: FSMContext, bot: Bot) -> None:
    """Admin kanal kiritganda tekshirish va saqlash."""
    raw_input = message.text.strip() if message.text else ""
    try:
        chat_info = await bot.get_chat(raw_input)
        cid_str = str(chat_info.id)
        title = chat_info.title or raw_input
        uname = f"@{chat_info.username}" if chat_info.username else None

        await add_mandatory_channel(
            channel_id=cid_str,
            channel_title=title,
            channel_username=uname,
        )
        await state.clear()

        text, kb = await _build_admin_menu_text_and_kb()
        await message.reply(
            f"✅ <b>Kanal muvaffaqiyatli qo'shildi!</b>\n\n"
            f"📢 Nomi: <b>{title}</b>\n"
            f"🆔 ID: <code>{cid_str}</code>\n"
            f"🔗 Username: {uname or 'Mavjud emas'}",
            parse_mode="HTML",
            reply_markup=kb,
        )
    except Exception as e:
        await message.reply(
            f"❌ Kanalni topib bo'lmadi yoki bot kanalda admin emas: {e}\n\n"
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
        try:
            await query.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
        except Exception:
            pass


@router.callback_query(F.data == "admin:stats")
async def cb_admin_stats(query: CallbackQuery) -> None:
    """To'liq statistikani ko'rsatish."""
    stats = await get_admin_stats()
    all_chats = await get_all_linked_chats()
    is_sub_on = await is_mandatory_sub_enabled()
    sub_text = "🟢 Yoniq" if is_sub_on else "🔴 O'chiq"

    lines = [
        "📊 <b>BOT TO'LIQ STATISTIKASI</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n",
        f"⚙️ <b>Majburiy obuna:</b> {sub_text}",
        f"📢 <b>Majburiy kanallar:</b> {stats['total_mandatory']} ta",
        f"👥 <b>Jami bot foydalanuvchilari:</b> {stats['total_users']} ta",
        f"🔗 <b>Faol referallar:</b> {stats['total_active_referrals']} ta",
        f"🎁 <b>Faol konkurslar:</b> {stats['active_contests']} ta",
        f"💬 <b>Ulangan guruhlar:</b> {stats['total_groups']} ta",
        f"📢 <b>Ulangan kanallar:</b> {stats['total_channels']} ta",
        f"📝 <b>Jami faolliklar:</b> {stats['total_activities']} ta",
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
    """Guruhdagi ogohlantirishda 'Holatni tekshirish' bosilganda."""
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

    await message.reply("\n".join(lines), parse_mode="HTML")


async def _is_group_admin(message: Message, bot: Bot) -> bool:
    """Foydalanuvchi guruh admini yoki bot egasi ekanligini tekshiradi."""
    if not message.from_user:
        return False
    if ADMIN_ID and message.from_user.id == ADMIN_ID:
        return True
    try:
        member = await bot.get_chat_member(message.chat.id, message.from_user.id)
        return member.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR)
    except Exception:
        return False


# ─────────────────────────────────────────────
# GURUH VA KANAL FAOLLIKLARI, 777 JACKPOT
# ─────────────────────────────────────────────

@router.message(Command("haftalik_golib"))
async def cmd_haftalik_golib(message: Message, bot: Bot) -> None:
    """Guruhda haftalik g'olib tanlash."""
    if message.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        await message.reply("⚠️ Bu buyruq faqat guruhlarda ishlaydi.")
        return

    if not await _is_group_admin(message, bot):
        return

    await message.reply("⏳ Haftalik g'olib aniqlanmoqda...")
    try:
        await pick_winner(bot=bot, days=7, period="haftalik", chat_id=message.chat.id, admin_id=message.from_user.id)
    except Exception as e:
        logger.error("Haftalik g'olib xatosi: %s", e)
        await message.reply(f"❌ Xatolik: {e}")


@router.message(Command("oylik_golib"))
async def cmd_oylik_golib(message: Message, bot: Bot) -> None:
    """Guruhda oylik g'olib tanlash."""
    if message.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        await message.reply("⚠️ Bu buyruq faqat guruhlarda ishlaydi.")
        return

    if not await _is_group_admin(message, bot):
        return

    await message.reply("⏳ Oylik g'olib aniqlanmoqda...")
    try:
        await pick_winner(bot=bot, days=30, period="oylik", chat_id=message.chat.id, admin_id=message.from_user.id)
    except Exception as e:
        logger.error("Oylik g'olib xatosi: %s", e)
        await message.reply(f"❌ Xatolik: {e}")


@router.message(Command("statistika"))
async def cmd_statistika(message: Message, bot: Bot) -> None:
    """Guruhda haftalik faollik statistikasi."""
    if message.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        await message.reply("⚠️ Bu buyruq faqat guruhlarda ishlaydi.")
        return

    if not await _is_group_admin(message, bot):
        return

    try:
        top_users = await get_top_users(days=7, chat_id=message.chat.id, limit=5)
        if not top_users:
            await message.reply("📊 Bu hafta hali hech qanday faollik qayd etilmadi.")
            return

        lines = ["📊 <b>Haftalik faollik statistikasi (Top 5)</b>\n"]
        for i, user in enumerate(top_users, start=1):
            medal = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"][i - 1]
            name = html.escape(user["first_name"])
            username = f" (@{user['username']})" if user["username"] else ""
            total = user["total"]
            lines.append(f"{medal} <b>{name}</b>{username} — {total} ta faollik")

        await message.reply("\n".join(lines), parse_mode="HTML")
    except Exception as e:
        logger.error("Statistika xatosi: %s", e)
        await message.reply(f"❌ Xatolik: {e}")


@router.message_reaction()
async def on_reaction(event: MessageReactionUpdated) -> None:
    """Reaksiyalarni kuzatadi va bazaga yozadi."""
    if not event.new_reaction:
        return

    user = event.user
    if user is None:
        return

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


@router.message(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))
async def on_group_message(message: Message, bot: Bot) -> None:
    """Guruhdagi xabarlar (majburiy obuna tekshiruvi, 777 o'yini, post kamentlari)."""
    if message.from_user is None or message.from_user.is_bot:
        return

    if message.text and message.text.startswith("/"):
        return

    if not await is_linked_chat(message.chat.id):
        await add_linked_chat(
            owner_id=ADMIN_ID or 0,
            chat_id=message.chat.id,
            chat_type="group",
            chat_title=message.chat.title,
        )

    # 1. Majburiy obuna tekshiruvi
    is_admin = await _is_group_admin(message, bot)
    if not is_admin:
        is_subbed, missing = await check_all_mandatory_subs(bot, message.from_user.id)
        if not is_subbed and missing:
            try:
                await message.delete()
            except Exception:
                pass

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
                    url = f"https://t.me/{username[1:]}"
                    display_tag = username
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
                asyncio.create_task(_auto_delete_msg(bot, message.chat.id, warn_msg.message_id, delay=60))
            except Exception as e:
                logger.error("Ogohlantirish yuborishda xato: %s", e)

            return

    # 2. 777 Jackpot Dice
    if message.dice and message.dice.emoji == "🎰":
        if message.dice.value == 64:
            reply_msg_id = message.message_id
            if message.reply_to_message:
                reply_msg_id = message.reply_to_message.message_id
            elif message.message_thread_id:
                reply_msg_id = message.message_thread_id

            already_won = await check_777_winner_exists(message.chat.id, reply_msg_id)
            if not already_won:
                first_name = message.from_user.first_name or "Noma'lum"
                safe_name = html.escape(first_name)
                user_id = message.from_user.id

                try:
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
                except Exception as e:
                    logger.error("777 tabrik xatosi: %s", e)

    # 3. Faollikni bazaga yozish (faqat kanal posti kommenti bo'lsa)
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
