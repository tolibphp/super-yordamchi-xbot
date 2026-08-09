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
    find_user_by_id_or_username,
    manual_add_user_referrals,
    manual_add_user_points,
    spin_lucky_wheel,
    get_user_wheel_status,
    get_weekly_top_referrers,
    record_group_chat_activity,
    update_group_member,
    get_group_members,
    create_contest,
    get_active_contests,
    get_contest,
    register_user_for_contest,
    get_contest_participants,
    get_contest_participants_count,
    save_contest_channel_post,
    get_contest_channel_posts,
    end_contest,
    get_all_bot_user_ids,
    get_bot_setting,
    set_bot_setting,
    set_user_birthday,
    get_user_birthday,
    get_birthday_insights,
    parse_birthday_string,
    calculate_days_until_birthday,
)
from membership import check_membership, check_all_mandatory_subs
from winner import pick_winner
from contest import (
    build_share_data,
    build_contest_post_content,
    build_contest_results_channel_post,
    get_contest_results_view,
    draw_contest_winners,
    update_contest_channel_posts,
)
from birthday import build_daily_birthday_group_post, broadcast_daily_birthdays

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
    promo_type = State()
    promo_points = State()
    promo_max_uses = State()
    promo_post_channel = State()
    promo_post_text = State()
    daily_post_url = State()
    broadcast_text = State()
    draw_custom_count = State()
    manual_action_type = State()
    manual_user_target = State()
    manual_reward_amount = State()


class UserStates(StatesGroup):
    """Foydalanuvchi holatlari."""
    waiting_promo_code = State()
    waiting_birthday_input = State()


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
        f"1️⃣ «🚀 Do'stlarga Ulashish» orqali do'stlaringizni taklif qiling (+1 ball)\n"
        f"2️⃣ 🎡 Kunlik «Omad G'ildiragi»ni bepul aylantiring\n"
        f"3️⃣ Guruhda faol gaplashing (+1 ball chat mining)\n"
        f"4️⃣ Kanaldagi postlarni ko'ring va yashirin promokodlarni tering!\n\n"
        f"🎁 <b>Qimmatbaho konkurslarimizda qatnashing va Telegram Premium yuting!</b>"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🚀 Do'stlarga Ulashish", callback_data="user:share"),
            InlineKeyboardButton(text="🎁 Faol Konkurslar", callback_data="user:contests"),
        ],
        [
            InlineKeyboardButton(text="🎡 Omad G'ildiragi", callback_data="user:wheel"),
            InlineKeyboardButton(text="👤 Profilim", callback_data="user:profile"),
        ],
        [
            InlineKeyboardButton(text="🏆 Reyting (Top)", callback_data="user:top"),
            InlineKeyboardButton(text="🏁 Haftalik Top-5 (⭐️ Stars)", callback_data="user:weekly_top"),
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
    results_contest_id = 0

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
    elif payload.startswith("results_"):
        r_str = payload.replace("results_", "")
        if r_str.isdigit():
            results_contest_id = int(r_str)

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
        awarded, total_pts, milestone, tier2_info = await process_referral_reward(
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

            # 2-Pog'onali (Tier 2) bildirishnoma
            if tier2_info:
                g_id = tier2_info["grand_referrer_id"]
                try:
                    t2_text = (
                        "🌟 <b>2-POG'ONALI PASSIV REFERAL BONUSI!</b>\n\n"
                        "Siz taklif qilgan do'stingiz yangi a'zo taklif qildi. "
                        "Sizga passiv <b>+1 bonus ball</b> taqdim etildi! 🚀"
                    )
                    await bot.send_message(g_id, t2_text, parse_mode="HTML")
                except Exception as e:
                    logger.warning("Grand referrer %s ga xabar yuborib bo'lmadi: %s", g_id, e)

    # 4. Agar foydalanuvchi natijalarni tekshirish uchun kirgan bo'lsa
    if results_contest_id > 0:
        res_text, res_kb = await get_contest_results_view(results_contest_id)
        await message.answer(res_text, parse_mode="HTML", reply_markup=res_kb)
        return

    # 5. Agar foydalanuvchi ma'lum bir konkursga kirgan bo'lsa
    if contest_id > 0:
        success, reg_msg, t_num = await register_user_for_contest(contest_id, user_id)
        if success:
            await update_contest_channel_posts(bot, contest_id)
        reg_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎁 Barcha Konkurslar", callback_data="user:contests")],
            [InlineKeyboardButton(text="👤 Mening Profilim", callback_data="user:profile")],
        ])
        await message.answer(reg_msg, parse_mode="HTML", reply_markup=reg_kb)
        return

    # 6. Tug'ilgan kunni kiritish uchun kelgan bo'lsa
    if payload == "birthday":
        await state.set_state(UserStates.waiting_birthday_input)
        bday_prompt = (
            "🎂 <b>TUG'ILGAN KUNINGIZNI KIRITING</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Tug'ilgan kuningiz sanasini yuboring. Har yili ushbu sanada sizni guruhimizda qizg'in tabriklaymiz "
            "va kuningizgacha qolgan vaqtni hisoblab boramiz! 🎉\n\n"
            "✍️ <b>Namuna:</b> <code>15.08</code> yoki <code>15-avgust</code> yoki <code>15.08.2002</code>"
        )
        bday_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👤 Profilim", callback_data="user:profile")],
            [InlineKeyboardButton(text="⬅️ Bosh Menyu", callback_data="user:menu")],
        ])
        await message.answer(bday_prompt, parse_mode="HTML", reply_markup=bday_kb)
        return

        await message.answer(bday_prompt, parse_mode="HTML", reply_markup=bday_kb)
        return

    # 7. Promokod olish uchun kirgan bo'lsa (Deep-link orqali)
    if payload.startswith("promo_"):
        code_str = payload.replace("promo_", "")
        success, msg, _pts, _p_type = await claim_promo_code(user_id, code_str)
        if success:
            await update_promo_channel_posts(bot, code_str)
            msg = "🎉 <b>TABRIKLAYMIZ!</b>\n" + msg
            
        bday_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👤 Profilim", callback_data="user:profile")],
            [InlineKeyboardButton(text="⬅️ Bosh Menyu", callback_data="user:menu")],
        ])
        await message.answer(msg, parse_mode="HTML", reply_markup=bday_kb)
        return

    # 8. Oddiy holat: Asosiy dashboardni chiqarish
    dash_text, dash_kb = _build_user_dashboard(user_dict, _bot_username)
    await message.answer(dash_text, parse_mode="HTML", reply_markup=dash_kb)
# ─────────────────────────────────────────────
# GATEKEEPER OBUNA TEKSHIRISH CALLBACK
# ─────────────────────────────────────────────

@router.callback_query(F.data.startswith("user:verify_sub:"))
async def cb_user_verify_sub(query: CallbackQuery, bot: Bot, state: FSMContext) -> None:
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
    results_contest_id = 0
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
    elif payload.startswith("results_"):
        r_str = payload.replace("results_", "")
        if r_str.isdigit():
            results_contest_id = int(r_str)

    user_dict, is_new = await get_or_create_user(user_id, username, first_name, referred_by=referrer_id)

    if is_new and referrer_id > 0 and referrer_id != user_id:
        awarded, total_pts, milestone, tier2_info = await process_referral_reward(
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

            if tier2_info:
                g_id = tier2_info["grand_referrer_id"]
                try:
                    t2_text = (
                        "🌟 <b>2-POG'ONALI PASSIV REFERAL BONUSI!</b>\n\n"
                        "Siz taklif qilgan do'stingiz yangi a'zo taklif qildi. "
                        "Sizga passiv <b>+1 bonus ball</b> taqdim etildi! 🚀"
                    )
                    await bot.send_message(g_id, t2_text, parse_mode="HTML")
                except Exception:
                    pass

    if results_contest_id > 0:
        res_text, res_kb = await get_contest_results_view(results_contest_id)
        if query.message:
            await query.message.edit_text(res_text, parse_mode="HTML", reply_markup=res_kb)
        return

    if contest_id > 0:
        success, reg_msg, t_num = await register_user_for_contest(contest_id, user_id)
        if success:
            await update_contest_channel_posts(bot, contest_id)
        reg_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎁 Barcha Konkurslar", callback_data="user:contests")],
            [InlineKeyboardButton(text="👤 Mening Profilim", callback_data="user:profile")],
        ])
        if query.message:
            await query.message.edit_text(reg_msg, parse_mode="HTML", reply_markup=reg_kb)
        return

    if payload == "birthday":
        await state.set_state(UserStates.waiting_birthday_input)
        bday_prompt = (
            "🎂 <b>TUG'ILGAN KUNINGIZNI KIRITING</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Tug'ilgan kuningiz sanasini yuboring. Har yili ushbu sanada sizni guruhimizda qizg'in tabriklaymiz "
            "va kuningizgacha qolgan vaqtni hisoblab boramiz! 🎉\n\n"
            "✍️ <b>Namuna:</b> <code>15.08</code> yoki <code>15-avgust</code> yoki <code>15.08.2002</code>"
        )
        bday_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👤 Profilim", callback_data="user:profile")],
            [InlineKeyboardButton(text="⬅️ Bosh Menyu", callback_data="user:menu")],
        ])
        if query.message:
            await query.message.edit_text(bday_prompt, parse_mode="HTML", reply_markup=bday_kb)
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
    vip_label = "👑 VIP Foydalanuvchi" if is_vip else "Oddiy A'zo"

    # Tug'ilgan kun hisob-kitobi
    birthday = user.get("birthday")
    if birthday:
        parsed_bday = parse_birthday_string(birthday)
        if parsed_bday:
            bd_d, bd_m, bd_fmt = parsed_bday
            days_left = calculate_days_until_birthday(bd_d, bd_m)
            if days_left == 0:
                bday_display = f"🎂 <b>{bd_fmt}</b> (Bugun tavallud ayyomingiz! 🥳)"
            elif days_left == 1:
                bday_display = f"🎂 <b>{bd_fmt}</b> (Ertaga! ⏳)"
            else:
                bday_display = f"🎂 <b>{bd_fmt}</b> ({days_left} kun qoldi ⏳)"
            bday_btn_text = "🎂 Tug'ilgan kunni o'zgartirish"
        else:
            bday_display = f"🎂 <b>{birthday}</b>"
            bday_btn_text = "🎂 Tug'ilgan kunni o'zgartirish"
    else:
        bday_display = "<i>Belgilanmagan</i>"
        bday_btn_text = "🎂 Tug'ilgan kunimni kiritish"

    text = (
        f"👤 <b>SIZNING SHAXSIY PROFILINGIZ</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🆔 <b>ID:</b> <code>{user_id}</code>\n"
        f"👤 <b>Ism:</b> {name}\n"
        f"👑 <b>Status:</b> {vip_label}\n"
        f"📅 <b>Qo'shilgan sana:</b> {joined}\n"
        f"🎂 <b>Tug'ilgan kun:</b> {bday_display}\n\n"
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
            InlineKeyboardButton(text=bday_btn_text, callback_data="user:set_birthday"),
        ],
        [
            InlineKeyboardButton(text="🎁 Konkurslarga o'tish", callback_data="user:contests"),
            InlineKeyboardButton(text="⬅️ Bosh Menyu", callback_data="user:menu"),
        ],
    ])

    if query.message:
        await query.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await query.answer()


@router.callback_query(F.data == "user:set_birthday")
async def cb_user_set_birthday(query: CallbackQuery, state: FSMContext) -> None:
    """Tug'ilgan kunni kiritish holatini yoqish."""
    await state.set_state(UserStates.waiting_birthday_input)
    text = (
        "🎂 <b>TUG'ILGAN KUNINGIZNI KIRITING</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Tug'ilgan kuningiz sanasini yuboring. Har yili ushbu sanada sizni guruhimizda qizg'in tabriklaymiz "
        "va kuningizgacha qolgan vaqtni hisoblab boramiz! 🎉\n\n"
        "✍️ <b>Masalan:</b> <code>15.08</code> yoki <code>15-avgust</code> yoki <code>15.08.2002</code>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="user:profile")],
    ])
    if query.message:
        await query.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await query.answer()


@router.message(UserStates.waiting_birthday_input)
async def user_enter_birthday(message: Message, state: FSMContext) -> None:
    """Foydalanuvchi tug'ilgan kun sanasini yuborganda."""
    if not message.from_user or not message.text:
        return

    parsed = parse_birthday_string(message.text)
    if not parsed:
        err_text = (
            "❌ <b>Sana formati noto'g'ri!</b>\n\n"
            "Iltimos, namunadagidek yozing:\n"
            "• <code>15.08</code>\n"
            "• <code>15-avgust</code>\n"
            "• <code>15.08.2002</code>"
        )
        await message.reply(err_text, parse_mode="HTML")
        return

    d, m, fmt_date = parsed
    days_left = calculate_days_until_birthday(d, m)
    user_id = message.from_user.id

    # Bazaga saqlash
    await set_user_birthday(user_id, fmt_date)
    await state.clear()

    if days_left == 0:
        status_line = "🥳 <b>Bugun sizning tavallud ayyomingiz! Chin dildan tabriklaymiz! 🎉🎂</b>"
    elif days_left == 1:
        status_line = "⏳ <b>Tug'ilgan kuningizga atigi 1 kun (ertaga!) qoldi! 🎉</b>"
    else:
        status_line = f"⏳ Tug'ilgan kuningizga <b>{days_left} kun</b> qoldi!"

    success_text = (
        f"🎉 <b>Tug'ilgan kuningiz muvaffaqiyatli saqlandi!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📅 <b>Belgilangan sana:</b> <b>{fmt_date}</b>\n"
        f"{status_line}\n\n"
        f"<i>Ushbu sanada sizni guruhimizda barcha a'zolar bilan birgalikda maxsus tabriklaymiz! 🎁✨</i>"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Profilim", callback_data="user:profile")],
        [InlineKeyboardButton(text="⬅️ Bosh Menyu", callback_data="user:menu")],
    ])

    await message.reply(success_text, parse_mode="HTML", reply_markup=kb)


@router.message(Command("tugilgan_kun", "birthday"))
async def cmd_user_birthday(message: Message, state: FSMContext) -> None:
    """/tugilgan_kun yoki /birthday buyrug'i."""
    if message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
        # Guruhda buyruq berilsa, botga o'tish tugmasini beramiz
        b_text = (
            "🎂 <b>Tug'ilgan kuningizni bot orqali belgilang!</b>\n\n"
            "Har kuni guruhimizda eng yaqin tug'ilgan kunlar hisoblab boriladi va "
            "tavallud ayyomingizda barchamiz sizni tabriklaymiz! 🎉"
        )
        b_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎂 Sanani kiritish ↗️", url=f"https://t.me/{_bot_username}?start=birthday")],
        ])
        await message.reply(b_text, parse_mode="HTML", reply_markup=b_kb)
        return

    # Shaxsiy chatda
    await state.set_state(UserStates.waiting_birthday_input)
    prompt_text = (
        "🎂 <b>TUG'ILGAN KUNINGIZNI KIRITING</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Tug'ilgan kuningiz sanasini yuboring. Har yili ushbu sanada sizni guruhimizda qizg'in tabriklaymiz "
        "va kuningizgacha qolgan vaqtni hisoblab boramiz! 🎉\n\n"
        "✍️ <b>Masalan:</b> <code>15.08</code> yoki <code>15-avgust</code> yoki <code>15.08.2002</code>"
    )
    b_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Profilim", callback_data="user:profile")],
        [InlineKeyboardButton(text="⬅️ Bosh Menyu", callback_data="user:menu")],
    ])
    await message.answer(prompt_text, parse_mode="HTML", reply_markup=b_kb)


@router.message(Command("tugilgan_kunlar"))
async def cmd_group_birthdays(message: Message, bot: Bot) -> None:
    """Guruhda /tugilgan_kunlar bosilganda hisoblagich va tabriklarni ko'rsatish."""
    if not _bot_username:
        await set_bot_username(bot)

    today_list, upcoming_list = await get_birthday_insights(limit=5)
    post_text, kb = build_daily_birthday_group_post(_bot_username, today_list, upcoming_list)
    await message.reply(post_text, parse_mode="HTML", reply_markup=kb, disable_web_page_preview=True)


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
async def cb_user_join_contest(query: CallbackQuery, bot: Bot) -> None:
    """Foydalanuvchi konkursda qatnashish tugmasini bosganda."""
    contest_id = int(query.data.split(":")[2])
    user_id = query.from_user.id

    success, msg, ticket_num = await register_user_for_contest(contest_id, user_id)
    if success:
        await update_contest_channel_posts(bot, contest_id)

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
        "qo'shimcha ballar yoki <b>bepul referallarni</b> qo'lga kiriting!\n\n"
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

    success, msg, pts, reward_type = await claim_promo_code(user_id, code_text)
    await state.clear()

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Profilim", callback_data="user:profile")],
        [InlineKeyboardButton(text="⬅️ Bosh Menyu", callback_data="user:menu")],
    ])

    await message.reply(f"{msg}", parse_mode="HTML", reply_markup=kb)


# ── OMAD G'ILDIRAGI (LUCKY WHEEL) ──

@router.callback_query(F.data == "user:wheel")
async def cb_user_wheel(query: CallbackQuery) -> None:
    """Kunlik Omad G'ildiragi ekrani."""
    user_id = query.from_user.id
    can_spin = await get_user_wheel_status(user_id)

    status_text = "🟢 <b>Bugungi bepul imkoniyat mavjud!</b>" if can_spin else "⏳ <b>Bugungi imkoniyatdan foydalangansiz! (Ertaga ochiladi)</b>"

    text = (
        "🎡 <b>KUNLIK OMAD G'ILDIRAGI</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Har kuni botga kirib omad g'ildiragini bepul aylantiring va quyidagi sovg'alarni yutib oling:\n\n"
        "🎯 <b>+1 Ball</b>\n"
        "🚀 <b>+2 Ball</b>\n"
        "👥 <b>+1 Bepul Referal (Do'st)</b>\n"
        "🌟 <b>+3 Ball</b>\n"
        "🎟 <b>Omadli Chipta (+5 Ball)</b>\n\n"
        f"📌 <b>Holat:</b> {status_text}\n"
    )

    buttons = []
    if can_spin:
        buttons.append([InlineKeyboardButton(text="🎡 G'ildirakni Aylantirish!", callback_data="user:spin_wheel")])
    buttons.append([InlineKeyboardButton(text="⬅️ Bosh Menyu", callback_data="user:menu")])

    if query.message:
        await query.message.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await query.answer()


@router.callback_query(F.data == "user:spin_wheel")
async def cb_user_spin_wheel(query: CallbackQuery, bot: Bot) -> None:
    """G'ildirakni aylantirish jarayoni va natijasi."""
    user_id = query.from_user.id
    success, msg, r_type, r_val = await spin_lucky_wheel(user_id)

    if not success:
        await query.answer(msg, show_alert=True)
        return

    # Animatsiya hissi berish
    if query.message:
        try:
            await query.message.edit_text("🎡 <i>G'ildirak aylanmoqda... ⏳</i>", parse_mode="HTML")
            await asyncio.sleep(1.2)
        except Exception:
            pass

    text = (
        "🎡 <b>OMAD G'ILDIRAGI NATIJASI!</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{msg}\n\n"
        "💡 <i>Ertaga yana kiring va yangi bepul yutuqlarni qo'lga kiriting!</i>"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Profilim", callback_data="user:profile")],
        [InlineKeyboardButton(text="⬅️ Bosh Menyu", callback_data="user:menu")],
    ])

    if query.message:
        await query.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await query.answer()


# ── HAFTALIK LIDERLAR REYTINGI ──

@router.callback_query(F.data == "user:weekly_top")
async def cb_user_weekly_top(query: CallbackQuery) -> None:
    """Haftalik eng ko'p referal to'plagan Top-5 liderlar va Telegram Stars yutuqlari."""
    leaders = await get_weekly_top_referrers(limit=5)
    lines = [
        "🏁 <b>HAFTALIK TOP-5 LIDERLAR (STARS YUTUQLARI)</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "<i>Oxirgi 7 kun ichida eng ko'p do'st taklif qilgan Top-5 ishtirokchi har hafta Telegram Stars bilan taqdirlanadi!</i>\n\n"
        "🎁 <b>Haftalik Sovg'alar Jamg'armasi:</b>\n"
        "🥇 <b>1-o'rin:</b> ⭐️ <b>2 ta Stars</b>\n"
        "🥈 <b>2-o'rin:</b> ⭐️ <b>1 ta Stars</b>\n"
        "🥉 <b>3-o'rin:</b> ⭐️ <b>1 ta Stars</b>\n"
        "4️⃣ <b>4-o'rin:</b> ⭐️ <b>1 ta Stars</b>\n"
        "5️⃣ <b>5-o'rin:</b> ⭐️ <b>1 ta Stars</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "📊 <b>Hozirgi yetakchilar holati:</b>\n\n",
    ]

    if not leaders:
        lines.append("⚠️ Hozircha bu haftada faoliyat qayd etilmadi. Birinchi bo'lib do'stlaringizni taklif qiling va Stars yuting!\n")
    else:
        medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
        stars_rewards = ["⭐️ 2 Stars", "⭐️ 1 Star", "⭐️ 1 Star", "⭐️ 1 Star", "⭐️ 1 Star"]
        for i, u in enumerate(leaders, start=1):
            medal = medals[i - 1]
            prize = stars_rewards[i - 1]
            name = html.escape(u.get("first_name", "Noma'lum"))
            refs = u.get("weekly_refs", 0)
            pts = u.get("points", 0)
            vip = " 👑" if u.get("vip_status") == 1 else ""
            lines.append(f"{medal} <b>{name}</b>{vip} — <b>{refs}</b> ta do'st (Sovg'a: <b>{prize}</b>)\n")

    lines.append("\n💡 <i>Har hafta yakunida g'oliblarga Stars taqdim etiladi! Siz ham do'stlaringizni taklif qiling va yetakchiga aylaning!</i>")

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Do'stlarni taklif qilish", callback_data="user:share")],
        [InlineKeyboardButton(text="⬅️ Bosh Menyu", callback_data="user:menu")],
    ])

    if query.message:
        await query.message.edit_text("".join(lines), parse_mode="HTML", reply_markup=kb)
    await query.answer()


@router.callback_query(F.data == "user:top")
async def cb_user_top(query: CallbackQuery) -> None:
    """Eng ko'p do'st taklif qilgan liderlar reytingi (Umumiy)."""
    leaders = await get_top_referrers(limit=10)
    lines = [
        "🏆 <b>ENG KO'P DO'ST TAKLIF QILGAN LIDERLAR (UMUMIY)</b>\n"
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
    sub_status_label = "YONIQ" if is_sub_on else "O'CHIQ"

    text = (
        "👑 <b>ADMIN BOSHQARUV PANELI (SUPER ENGINE)</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "Bu yerdan barcha konkurslarni yaratish, g'oliblarni aniqlash, "
        "promokodlar va majburiy kanallarni boshqarishingiz mumkin.\n\n"
        f"⚙️ <b>Majburiy obuna:</b> {sub_icon} {sub_status_label}\n"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🎁 Yangi Konkurs Yaratish", callback_data="admin:new_contest"),
            InlineKeyboardButton(text="🎲 G'oliblarni Aniqlash (/draw)", callback_data="admin:draw_list"),
        ],
        [
            InlineKeyboardButton(text="🔑 Promokod Yaratish", callback_data="admin:new_promo"),
            InlineKeyboardButton(text="👤 Referal / Ball Qo'shish", callback_data="admin:manual_reward_menu"),
        ],
        [
            InlineKeyboardButton(text="⚡ Kunlik Post Linki", callback_data="admin:set_daily_post"),
            InlineKeyboardButton(text="📢 Barchaga Xabar (Broadcast)", callback_data="admin:broadcast"),
        ],
        [
            InlineKeyboardButton(text="➕ Majburiy Kanal Qo'shish", callback_data="admin:add_channel"),
            InlineKeyboardButton(text="🗑 Kanal O'chirish", callback_data="admin:del_channel_list"),
        ],
        [
            InlineKeyboardButton(text="📊 Bot Statistikasi", callback_data="admin:stats"),
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
        "⚡ <b>Tezkor Konkurs</b> — Shartsiz (0 referal), hamma obuna bo'lib 1-bosishda qatnashadi.\n"
        "🎁 <b>Gift / Yulduzlar Konkursi</b> — Kamida <b>30 ta do'st</b> taklif qilganlar qatnashadi.\n"
        "💎 <b>Telegram Premium Konkurs</b> — Kamida <b>50 ta do'st</b> taklif qilganlar qatnashadi.\n"
        "🎯 <b>Maxsus Konkurs</b> — O'zingiz istalgan minimal do'stlar sonini belgilaysiz."
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⚡ Tezkor Konkurs (Shartsiz — 0 ref)", callback_data="admin:c_type:instant"),
        ],
        [
            InlineKeyboardButton(text="🎁 Gift / Yulduzlar Konkursi (min 30 ref)", callback_data="admin:c_type:gift"),
        ],
        [
            InlineKeyboardButton(text="💎 Premium Konkurs (min 50 ref)", callback_data="admin:c_type:premium"),
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

    if c_type == "instant":
        await state.update_data(min_referrals=0)
        await state.set_state(AdminStates.contest_title)
        prompt = "✍️ <b>Konkurs nomini kiriting:</b>\n(Masalan: <i>Telegram Stars Konkursi</i>)"
    elif c_type == "premium":
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

    channels = await _get_all_target_channels()
    p_count = await get_contest_participants_count(contest_id)
    post_text, post_kb = build_contest_post_content(_bot_username, contest_dict, channels=channels, participant_count=p_count)

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


async def _get_all_target_channels() -> list[dict]:
    """Konkurs postlarini yuborish uchun barcha kanallarni (majburiy + ulangan) yig'adi."""
    target_map = {}
    # 1. Majburiy kanallar
    m_channels = await get_mandatory_channels()
    for mc in m_channels:
        cid = mc.get("channel_id")
        if not cid:
            continue
        try:
            num_cid = int(cid)
        except ValueError:
            num_cid = cid
        target_map[str(cid)] = {
            "chat_id": num_cid,
            "title": mc.get("channel_title") or "Kanal",
            "channel_username": mc.get("channel_username"),
        }
    # 2. Ulangan chatlar
    linked = await get_all_linked_chats()
    for lc in linked:
        if lc.get("chat_type") == "channel":
            cid = str(lc["chat_id"])
            if cid not in target_map:
                target_map[cid] = {
                    "chat_id": lc["chat_id"],
                    "title": lc.get("chat_title") or "Kanal",
                    "channel_username": None,
                }
    return list(target_map.values())


@router.callback_query(F.data.startswith("admin:post_contest:"))
async def cb_admin_post_contest_to_channel(query: CallbackQuery, bot: Bot) -> None:
    """Yaratilgan konkursni ulangan / majburiy kanallarga post qilish va live counter uchun saqlash."""
    contest_id = int(query.data.split(":")[2])
    contest = await get_contest(contest_id)
    if not contest:
        await query.answer("Konkurs topilmadi.", show_alert=True)
        return

    if not _bot_username:
        await set_bot_username(bot)

    channels = await _get_all_target_channels()
    if not channels:
        await query.answer(
            "⚠️ Hozircha qo'shilgan kanallar topilmadi.\n"
            "Admin paneldan «➕ Majburiy Kanal Qo'shish» orqali kanalingizni qo'shing va botni kanalga admin qiling.",
            show_alert=True,
        )
        return

    p_count = await get_contest_participants_count(contest_id)
    post_text, post_kb = build_contest_post_content(_bot_username, contest, channels=channels, participant_count=p_count)

    posted = 0
    errors = []
    for ch in channels:
        try:
            sent_msg = await bot.send_message(
                chat_id=ch["chat_id"],
                text=post_text,
                parse_mode="HTML",
                reply_markup=post_kb,
            )
            await save_contest_channel_post(contest_id, ch["chat_id"], sent_msg.message_id)
            posted += 1
        except Exception as e:
            logger.error("Kanalga post yuborishda xato (%s): %s", ch["chat_id"], e)
            errors.append(f"{ch['title']}: {e}")

    if posted > 0:
        await query.answer(f"✅ Konkurs {posted} ta kanalga muvaffaqiyatli joylandi!", show_alert=True)
    else:
        err_detail = "\n".join(errors[:2])
        await query.answer(
            f"⚠️ Kanalga post yuborib bo'lmadi:\n{err_detail}\n\n"
            "Bot kanalda admin ekanligi va 'Xabarlar yuborish' huquqi borligini tekshiring.",
            show_alert=True,
        )


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
                    callback_data=f"admin:draw_choose:{c['id']}",
                )
            ])
        buttons.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data="admin:menu")])
        kb = InlineKeyboardMarkup(inline_keyboard=buttons)

    if query.message:
        await query.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await query.answer()


@router.callback_query(F.data.startswith("admin:draw_choose:"))
async def cb_admin_draw_choose(query: CallbackQuery, state: FSMContext) -> None:
    """G'oliblar sonini tanlash menyusi."""
    await state.clear()
    contest_id = int(query.data.split(":")[2])
    contest = await get_contest(contest_id)
    if not contest:
        await query.answer("Konkurs topilmadi.", show_alert=True)
        return

    count = await get_contest_participants_count(contest_id)

    text = (
        f"🎲 <b>G'OLIBLAR SONINI TANLASH</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🏆 <b>Konkurs:</b> {contest['title']}\n"
        f"🎁 <b>Sovg'a:</b> {contest.get('prize_description') or 'Telegram Premium'}\n"
        f"👥 <b>Jami ishtirokchilar:</b> {count} ta\n\n"
        f"Ushbu konkursdan nechta g'olib aniqlansin?"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🥇 1 ta g'olib", callback_data=f"admin:draw_calc:{contest_id}:1"),
            InlineKeyboardButton(text="👥 2 ta g'olib", callback_data=f"admin:draw_calc:{contest_id}:2"),
        ],
        [
            InlineKeyboardButton(text="👥 3 ta g'olib", callback_data=f"admin:draw_calc:{contest_id}:3"),
            InlineKeyboardButton(text="👥 5 ta g'olib", callback_data=f"admin:draw_calc:{contest_id}:5"),
        ],
        [
            InlineKeyboardButton(text="👥 10 ta g'olib", callback_data=f"admin:draw_calc:{contest_id}:10"),
            InlineKeyboardButton(text="✍️ Boshqa son kiritish", callback_data=f"admin:draw_custom:{contest_id}"),
        ],
        [
            InlineKeyboardButton(text="⬅️ Orqaga", callback_data="admin:draw_list"),
        ],
    ])

    if query.message:
        await query.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await query.answer()


@router.callback_query(F.data.startswith("admin:draw_custom:"))
async def cb_admin_draw_custom(query: CallbackQuery, state: FSMContext) -> None:
    """G'oliblar sonini qo'lda kiritish."""
    contest_id = int(query.data.split(":")[2])
    await state.set_state(AdminStates.draw_custom_count)
    await state.update_data(draw_contest_id=contest_id)

    text = (
        "✍️ <b>Nechta g'olib aniqlansin?</b>\n\n"
        "Iltimos, g'oliblar sonini raqamda yozib yuboring (masalan: <code>4</code> yoki <code>7</code>):"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Bekor qilish", callback_data=f"admin:draw_choose:{contest_id}")]
    ])
    if query.message:
        await query.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await query.answer()


async def _render_draw_preview(
    bot: Bot,
    target: Message | CallbackQuery,
    contest_id: int,
    winner_count: int,
) -> None:
    """G'oliblarni hisoblash, xabarni chiqarish va qayta aniqlash (re-roll) imkonini beruvchi yordamchi funksiya."""
    res = await draw_contest_winners(bot, contest_id, winner_count=winner_count, save_to_db=True)
    if not res["success"]:
        raw_err = res.get("error") or "G'oliblarni aniqlab bo'lmadi"
        err_msg = f"❌ Xato: {raw_err}"
        if isinstance(target, CallbackQuery):
            await target.answer(err_msg, show_alert=True)
        else:
            await target.reply(err_msg)
        return

    contest = res["contest"]
    winners = res["winners"]

    text = (
        f"🎉 <b>G'OLIBLAR ANIQLANDI!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🏆 <b>Konkurs:</b> {contest['title']}\n"
        f"👥 <b>G'oliblar soni:</b> {len(winners)} ta\n\n"
        f"📢 <b>Kanalga chiqadigan qisqa post ko'rinishi:</b>\n\n"
        f"{res['channel_post_text']}\n\n"
        f"<i>(Agar ushbu natijalar yoqmasa, «🔄 Qayta aniqlash» tugmasini bosib yangi g'oliblarni tanlashingiz mumkin)</i>"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="📢 Natijalarni Kanalga Joylash",
                callback_data=f"admin:publish_winners:{contest_id}",
            )
        ],
        [
            InlineKeyboardButton(
                text="🔄 Qayta aniqlash (Re-roll)",
                callback_data=f"admin:draw_calc:{contest_id}:{winner_count}",
            )
        ],
        [
            InlineKeyboardButton(
                text="⚙️ G'oliblar sonini o'zgartirish",
                callback_data=f"admin:draw_choose:{contest_id}",
            )
        ],
        [
            InlineKeyboardButton(text="⬅️ Admin Menyu", callback_data="admin:menu"),
        ],
    ])

    if isinstance(target, CallbackQuery):
        if target.message:
            await target.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
        await target.answer()
    else:
        await target.answer(text, parse_mode="HTML", reply_markup=kb)


@router.message(AdminStates.draw_custom_count)
async def msg_admin_draw_custom_count(message: Message, state: FSMContext, bot: Bot) -> None:
    """Admin tomonidan yuborilgan g'oliblar sonini qabul qilish."""
    text_val = (message.text or "").strip()
    if not text_val.isdigit() or int(text_val) <= 0:
        await message.reply("⚠️ Iltimos, faqat musbat butun son kiriting (masalan: <code>3</code>):", parse_mode="HTML")
        return

    winner_count = int(text_val)
    data = await state.get_data()
    contest_id = data.get("draw_contest_id")
    await state.clear()

    if not contest_id:
        await message.reply("⚠️ Konkurs ma'lumoti topilmadi.")
        return

    await _render_draw_preview(bot, message, contest_id, winner_count)


@router.callback_query(F.data.startswith("admin:draw_calc:"))
async def cb_admin_draw_calc(query: CallbackQuery, bot: Bot) -> None:
    """Belgilangan g'oliblar soni bo'yicha hisoblash yoki qayta aniqlash (Re-roll)."""
    parts = query.data.split(":")
    contest_id = int(parts[2])
    winner_count = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 1
    await _render_draw_preview(bot, query, contest_id, winner_count)


@router.callback_query(F.data.startswith("admin:draw_exec:"))
async def cb_admin_draw_exec(query: CallbackQuery, bot: Bot) -> None:
    """Eski draw_exec chaqiruvlari uchun yo'naltirish."""
    contest_id = int(query.data.split(":")[2])
    await _render_draw_preview(bot, query, contest_id, 1)


@router.callback_query(F.data.startswith("admin:publish_winners:"))
async def cb_admin_publish_winners(query: CallbackQuery, bot: Bot) -> None:
    """G'oliblar e'lonini (tugmasi bilan) barcha kanallarga chiqarish."""
    import json
    contest_id = int(query.data.split(":")[2])
    contest = await get_contest(contest_id)
    if not contest:
        await query.answer("Konkurs topilmadi.", show_alert=True)
        return

    if not _bot_username:
        await set_bot_username(bot)

    raw_w = contest.get("winners_data")
    try:
        winners = json.loads(raw_w) if isinstance(raw_w, str) else (raw_w or [])
    except Exception:
        winners = []

    post_text, post_kb = build_contest_results_channel_post(
        bot_username=_bot_username,
        contest=contest,
        winners=winners,
    )

    channels = await _get_all_target_channels()
    if not channels:
        await query.answer("⚠️ Kanallar topilmadi.", show_alert=True)
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
            logger.error("Kanalga g'oliblarni yuborishda xato: %s", e)

    await query.answer(f"✅ G'oliblar e'loni {posted} ta kanalga chiqarildi!", show_alert=True)


async def update_promo_channel_posts(bot: Bot, code: str) -> None:
    """Promokod ishlatilganda kanaldagi post statistikasini jonli yangilaydi."""
    promo = await get_promo_by_code(code)
    if not promo:
        return
        
    chat_id = promo.get("post_chat_id", 0)
    msg_id = promo.get("post_msg_id", 0)
    html_text = promo.get("post_html")
    
    if not chat_id or not msg_id or not html_text:
        return
        
    pts = promo.get("reward_points", 2)
    p_type = promo.get("reward_type", "points")
    max_uses = promo.get("max_uses", 50)
    used_count = promo.get("used_count", 0)
    
    unit = "ta do'st" if p_type == "referrals" else "ball"
    remain = max_uses - used_count
    if remain < 0:
        remain = 0
        
    stats_html = (
        f"\n\n━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔑 <b>Promokod:</b> <code>{code}</code>\n"
        f"🎁 <b>Yutuq:</b> +{pts} {unit}\n"
        f"👥 <b>Limit:</b> {max_uses} ta odam\n"
        f"⏳ <b>Qoldi:</b> {remain} ta\n"
        f"✅ <b>Olingan:</b> {used_count} ta"
    )
    
    full_html = html_text + stats_html
    
    bot_info = await bot.get_me()
    deep_link = f"https://t.me/{bot_info.username}?start=promo_{code}"
    
    kb = None
    if remain > 0:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎉 Promokod olish", url=deep_link)]
        ])
    else:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Promokod tugadi", callback_data="none")]
        ])
        
    try:
        await bot.edit_message_caption(
            chat_id=chat_id,
            message_id=msg_id,
            caption=full_html,
            parse_mode="HTML",
            reply_markup=kb
        )
    except Exception:
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=msg_id,
                text=full_html,
                parse_mode="HTML",
                reply_markup=kb
            )
        except Exception as e:
            logger.error("Promokod postini yangilashda xato: %s", e)


# ── PROMOKOD YARATISH WIZARDI ──

@router.callback_query(F.data == "admin:new_promo")
async def cb_admin_new_promo_step1(query: CallbackQuery, state: FSMContext) -> None:
    """Promokod yaratish: 1-qadam — Kod nomini so'rash."""
    await state.set_state(AdminStates.promo_code)
    text = (
        "🔑 <b>YANGI PROMOKOD YARATISH (1/4)</b>\n"
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
    """Promokod turini tanlash (Ball yoki Referal)."""
    code = message.text.strip().upper() if message.text else ""
    await state.update_data(promo_code=code)
    await state.set_state(AdminStates.promo_type)

    text = (
        f"✅ Promokod: <b>{code}</b>\n\n"
        "🎁 <b>Promokod turini tanlang:</b>\n\n"
        "⭐️ <b>Ball beruvchi:</b> Foydalanuvchiga to'g'ridan-to'g'ri ball qo'shadi.\n"
        "👥 <b>Referal beruvchi:</b> Foydalanuvchining referallar sonini ko'paytiradi (konkurslarga kirish osonlashadi)."
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⭐️ Ball beruvchi", callback_data="admin:p_type:points"),
            InlineKeyboardButton(text="👥 Referal beruvchi", callback_data="admin:p_type:referrals"),
        ],
        [
            InlineKeyboardButton(text="⬅️ Bekor qilish", callback_data="admin:menu"),
        ],
    ])
    await message.reply(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data.startswith("admin:p_type:"))
async def cb_admin_promo_type_selected(query: CallbackQuery, state: FSMContext) -> None:
    """Promokod turi tanlandi, miqdorni so'rash."""
    p_type = query.data.split(":")[2]
    await state.update_data(promo_type=p_type)
    await state.set_state(AdminStates.promo_points)

    label = "nechta referal (do'st)" if p_type == "referrals" else "necha ball"
    text = (
        f"✍️ Ushbu promokodni faollashtirganga <b>{label}</b> berilsin?\n"
        f"(Masalan: <code>2</code> yoki <code>5</code>)"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Bekor qilish", callback_data="admin:menu")],
    ])
    if query.message:
        await query.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await query.answer()


@router.message(AdminStates.promo_points)
async def admin_promo_code_step3(message: Message, state: FSMContext) -> None:
    """Promokod nechta kishiga mo'ljallanganligini so'rash."""
    pts_str = message.text.strip() if message.text else "2"
    pts = int(pts_str) if pts_str.isdigit() else 2
    await state.update_data(promo_points=pts)
    await state.set_state(AdminStates.promo_max_uses)

    data = await state.get_data()
    p_type = data.get("promo_type", "points")
    unit = "referal" if p_type == "referrals" else "ball"

    await message.reply(
        f"✅ Mukofot: <b>+{pts} {unit}</b>\n\n"
        f"✍️ Ushbu promokoddan <b>maksimal nechta kishi</b> foydalana olsin?\n"
        f"(Masalan: <code>50</code> yoki <code>100</code>)",
        parse_mode="HTML",
    )


@router.message(AdminStates.promo_max_uses)
async def admin_promo_code_finish(message: Message, state: FSMContext) -> None:
    """Promokodni saqlash."""
    max_uses_str = message.text.strip() if message.text else "50"
    max_uses = int(max_uses_str) if max_uses_str.isdigit() else 50
    await state.update_data(promo_max_uses=max_uses)

    data = await state.get_data()
    code = data.get("promo_code", "BONUS")
    p_type = data.get("promo_type", "points")
    pts = data.get("promo_points", 2)

    await create_promo_code(code=code, reward_type=p_type, reward_points=pts, max_uses=max_uses)

    type_label = "👥 Referal qo'shuvchi" if p_type == "referrals" else "⭐️ Ball qo'shuvchi"
    unit = "ta do'st (referal)" if p_type == "referrals" else "ball"

    text = (
        f"🎉 <b>YANGI PROMOKOD TAYYOR!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔑 <b>Kod:</b> <code>{code}</code>\n"
        f"🏷 <b>Turi:</b> {type_label}\n"
        f"🎁 <b>Mukofot:</b> +{pts} {unit}\n"
        f"👥 <b>Foydalanishlar limiti:</b> {max_uses} ta odam\n\n"
        f"💡 Ushbu promokodni <b>avtomatik knopkali post</b> qilib kanalga e'lon qilamizmi?"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Kanalga e'lon qilish", callback_data="admin:promo_post")],
        [InlineKeyboardButton(text="⏭ O'tkazib yuborish (Faqat saqlash)", callback_data="admin:menu")],
    ])
    await message.reply(text, parse_mode="HTML", reply_markup=kb)

@router.callback_query(F.data == "admin:promo_post")
async def cb_admin_promo_post(query: CallbackQuery, state: FSMContext) -> None:
    """Kanalni so'rash."""
    await state.set_state(AdminStates.promo_post_channel)
    text = (
        "✍️ <b>Qaysi kanalga e'lon qilamiz?</b>\n\n"
        "Kanalning username'ini (@bilan) yoki ID raqamini yuboring."
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Bekor qilish", callback_data="admin:menu")],
    ])
    await query.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await query.answer()

@router.message(AdminStates.promo_post_channel)
async def admin_promo_post_channel(message: Message, bot: Bot, state: FSMContext) -> None:
    """Kanal qabul qilindi, postni zudlik bilan e'lon qilish."""
    channel_id = message.text.strip() if message.text else ""
    
    data = await state.get_data()
    code = data.get("promo_code")
    
    await state.clear()
    
    html_text = f"🎉 <b>YANGI PROMOKOD TAYYOR!</b>"
    
    try:
        sent_msg = await bot.send_message(chat_id=channel_id, text="Yuklanmoqda...", parse_mode="HTML")
        await update_promo_post_info(code=code, chat_id=sent_msg.chat.id, msg_id=sent_msg.message_id, html_text=html_text)
        await update_promo_channel_posts(bot, code)
        
        await message.reply(f"✅ Post muvaffaqiyatli {channel_id} kanaliga e'lon qilindi va jonli rejimga o'tkazildi!", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Bosh menyu", callback_data="admin:menu")]]))
    except Exception as e:
        logger.error(f"Promo post yuborishda xato: {e}")
        await message.reply(f"❌ Kanalga yuborishda xatolik yuz berdi. Kanal ID to'g'riligini va bot kanalda admin ekanligini tekshiring.\nXato: {e}")



# ── ADMIN TO'G'RIDAN-TO'G'RI REFERAL / BALL QO'SHISH ──

@router.message(Command("addref"))
async def cmd_admin_addref(message: Message, bot: Bot) -> None:
    """Tezkor komanda: /addref @username 5 yoki /addref 123456789 5"""
    if not ADMIN_ID or not message.from_user or message.from_user.id != ADMIN_ID:
        return

    parts = message.text.split() if message.text else []
    if len(parts) < 3:
        await message.reply(
            "✍️ <b>Foydalanish:</b> <code>/addref [user_id yoki @username] [soni]</code>\n"
            "Masalan: <code>/addref @Tolibjon 5</code> yoki <code>/addref 123456789 10</code>",
            parse_mode="HTML",
        )
        return

    target = parts[1]
    amount_str = parts[2]
    try:
        amount = int(amount_str)
    except ValueError:
        await message.reply("❌ Miqdor butun son bo'lishi kerak (masalan: 5 yoki 10).")
        return

    success, msg, u_dict = await manual_add_user_referrals(target, amount)
    if not success:
        await message.reply(msg, parse_mode="HTML")
        return

    uid = u_dict["user_id"]
    try:
        sign = "+" if amount > 0 else ""
        await bot.send_message(
            uid,
            f"🎁 <b>ADMIN BONUST!</b>\n\n"
            f"Admin tomonidan sizning profilingizga <b>{sign}{amount} ta referal</b> va ball qo'shildi! 🚀\n"
            f"📊 Sizning jami referallaringiz: <b>{u_dict['referral_count']}</b> ta\n"
            f"⭐️ Sizning jami balingiz: <b>{u_dict['points']}</b> ball",
            parse_mode="HTML",
        )
    except Exception:
        pass

    await message.reply(msg, parse_mode="HTML")


@router.message(Command("addball"))
async def cmd_admin_addball(message: Message, bot: Bot) -> None:
    """Tezkor komanda: /addball @username 10 yoki /addball 123456789 10"""
    if not ADMIN_ID or not message.from_user or message.from_user.id != ADMIN_ID:
        return

    parts = message.text.split() if message.text else []
    if len(parts) < 3:
        await message.reply(
            "✍️ <b>Foydalanish:</b> <code>/addball [user_id yoki @username] [soni]</code>\n"
            "Masalan: <code>/addball @Tolibjon 15</code> yoki <code>/addball 123456789 20</code>",
            parse_mode="HTML",
        )
        return

    target = parts[1]
    amount_str = parts[2]
    try:
        amount = int(amount_str)
    except ValueError:
        await message.reply("❌ Miqdor butun son bo'lishi kerak.")
        return

    success, msg, u_dict = await manual_add_user_points(target, amount)
    if not success:
        await message.reply(msg, parse_mode="HTML")
        return

    uid = u_dict["user_id"]
    try:
        sign = "+" if amount > 0 else ""
        await bot.send_message(
            uid,
            f"🎁 <b>ADMIN BONUST!</b>\n\n"
            f"Admin tomonidan sizning profilingizga <b>{sign}{amount} ball</b> taqdim etildi! 🌟\n"
            f"⭐️ Sizning jami balingiz: <b>{u_dict['points']}</b> ball",
            parse_mode="HTML",
        )
    except Exception:
        pass

    await message.reply(msg, parse_mode="HTML")


@router.callback_query(F.data == "admin:manual_reward_menu")
async def cb_admin_manual_reward_menu(query: CallbackQuery, state: FSMContext) -> None:
    """Admin panel orqali qo'lda referal yoki ball qo'shish menyusi."""
    await state.clear()
    text = (
        "👤 <b>FOYDALANUVCHIGA REFERAL YOKI BALL QO'SHISH</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Qaysi amalni bajarmoqchisiz?\n\n"
        "👥 <b>Referal qo'shish:</b> Foydalanuvchining referallar soni va balini oshiradi.\n"
        "⭐️ <b>Ball qo'shish:</b> Foydalanuvchiga faqat ball qo'shadi.\n\n"
        "💡 <i>Shuningdek, tezkor ravishda <code>/addref @username 5</code> yoki <code>/addball @username 10</code> buyruqlaridan ham foydalanishingiz mumkin.</i>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="👥 Referal qo'shish", callback_data="admin:man:referrals"),
            InlineKeyboardButton(text="⭐️ Ball qo'shish", callback_data="admin:man:points"),
        ],
        [
            InlineKeyboardButton(text="⬅️ Admin Menyu", callback_data="admin:menu"),
        ],
    ])
    if query.message:
        await query.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await query.answer()


@router.callback_query(F.data.startswith("admin:man:"))
async def cb_admin_manual_action_chosen(query: CallbackQuery, state: FSMContext) -> None:
    """Amal turi tanlandi, foydalanuvchi ID yoki username so'rash."""
    action = query.data.split(":")[2]
    await state.update_data(manual_action_type=action)
    await state.set_state(AdminStates.manual_user_target)

    label = "Referal" if action == "referrals" else "Ball"
    text = (
        f"✍️ <b>{label} qo'shmoqchi bo'lgan foydalanuvchining ID yoki @username'ini yozing:</b>\n\n"
        f"(Masalan: <code>@Tolibjon</code> yoki <code>123456789</code>)"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Bekor qilish", callback_data="admin:manual_reward_menu")],
    ])
    if query.message:
        await query.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await query.answer()


@router.message(AdminStates.manual_user_target)
async def admin_manual_user_target_entered(message: Message, state: FSMContext) -> None:
    """Foydalanuvchi tekshiriladi va miqdor so'raladi."""
    target = message.text.strip() if message.text else ""
    user = await find_user_by_id_or_username(target)
    if not user:
        await message.reply(
            f"❌ Foydalanuvchi topilmadi (<code>{target}</code>).\n"
            f"Iltimos, to'g'ri ID yoki @username kiriting:",
            parse_mode="HTML",
        )
        return

    await state.update_data(manual_user_target=target)
    await state.set_state(AdminStates.manual_reward_amount)

    data = await state.get_data()
    action = data.get("manual_action_type", "referrals")
    unit = "ta referal" if action == "referrals" else "ball"

    first_name = html.escape(user.get("first_name", "Foydalanuvchi"))
    await message.reply(
        f"✅ Foydalanuvchi topildi: <b>{first_name}</b> (ID: <code>{user['user_id']}</code>)\n"
        f"👥 Hozirgi referallari: <b>{user.get('referral_count', 0)}</b> ta\n"
        f"⭐️ Hozirgi bali: <b>{user.get('points', 0)}</b> ball\n\n"
        f"✍️ Nechta <b>{unit}</b> qo'shmoqchisiz?\n"
        f"(Masalan: <code>5</code> yoki <code>10</code>)",
        parse_mode="HTML",
    )


@router.message(AdminStates.manual_reward_amount)
async def admin_manual_reward_amount_finish(message: Message, state: FSMContext, bot: Bot) -> None:
    """Miqdorni qo'llash va bildirishnoma yuborish."""
    amt_str = message.text.strip() if message.text else "0"
    try:
        amount = int(amt_str)
    except ValueError:
        await message.reply("❌ Miqdor butun son bo'lishi kerak. Qaytadan kiriting:")
        return

    data = await state.get_data()
    await state.clear()

    target = data.get("manual_user_target", "")
    action = data.get("manual_action_type", "referrals")

    if action == "referrals":
        success, msg, u_dict = await manual_add_user_referrals(target, amount)
        if success and u_dict:
            try:
                sign = "+" if amount > 0 else ""
                await bot.send_message(
                    u_dict["user_id"],
                    f"🎁 <b>ADMIN BONUST!</b>\n\n"
                    f"Admin tomonidan sizning profilingizga <b>{sign}{amount} ta referal</b> va ball qo'shildi! 🚀\n"
                    f"📊 Sizning jami referallaringiz: <b>{u_dict['referral_count']}</b> ta\n"
                    f"⭐️ Sizning jami balingiz: <b>{u_dict['points']}</b> ball",
                    parse_mode="HTML",
                )
            except Exception:
                pass
    else:
        success, msg, u_dict = await manual_add_user_points(target, amount)
        if success and u_dict:
            try:
                sign = "+" if amount > 0 else ""
                await bot.send_message(
                    u_dict["user_id"],
                    f"🎁 <b>ADMIN BONUST!</b>\n\n"
                    f"Admin tomonidan sizning profilingizga <b>{sign}{amount} ball</b> taqdim etildi! 🌟\n"
                    f"⭐️ Sizning jami balingiz: <b>{u_dict['points']}</b> ball",
                    parse_mode="HTML",
                )
            except Exception:
                pass

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Admin Menyu", callback_data="admin:menu")],
    ])
    await message.reply(f"{msg}", parse_mode="HTML", reply_markup=kb)


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
    """Majburiy kanal qo'shish so'rovi (Bitta yoki birdaniga bir nechta)."""
    await state.set_state(AdminStates.waiting_for_channel_input)
    text = (
        "📢 <b>Yangi majburiy kanal(lar) qo'shish:</b>\n\n"
        "Kanal username'ini yoki ID sini yuboring.\n"
        "<i>Bir nechta kanal bo'lsa, ularni probel yoki yangi qatorda yozishingiz mumkin:</i>\n\n"
        "Misol: <code>@tolibjon_life</code> yoki <code>-1001234567890</code>\n\n"
        "<i>Eslatma: Bot ushbu kanallarning barchasida admin bo'lishi shart!</i>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Bekor qilish", callback_data="admin:menu")],
    ])
    if query.message:
        await query.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await query.answer()


@router.message(AdminStates.waiting_for_channel_input)
async def admin_save_mandatory_channel(message: Message, state: FSMContext, bot: Bot) -> None:
    """Admin kanal(lar) kiritganda tekshirish va barchasini saqlash."""
    raw_input = message.text.strip() if message.text else ""
    if not raw_input:
        await message.reply("⚠️ Iltimos, kanal username yoki ID sini yuboring.")
        return

    # Probel, vergul yoki yangi qator bo'yicha ajratish
    tokens = [t.strip(", \t\r\n") for t in raw_input.replace(",", " ").split() if t.strip(", \t\r\n")]
    if not tokens:
        await message.reply("⚠️ Hech qanday kanal aniqlanmadi.")
        return

    added_list = []
    failed_list = []

    for token in tokens:
        try:
            chat_info = await bot.get_chat(token)
            cid_str = str(chat_info.id)
            title = chat_info.title or token
            uname = f"@{chat_info.username}" if chat_info.username else None

            await add_mandatory_channel(
                channel_id=cid_str,
                channel_title=title,
                channel_username=uname,
            )
            try:
                await add_linked_chat(
                    owner_id=message.from_user.id if message.from_user else 0,
                    chat_id=int(cid_str),
                    chat_type="channel",
                    chat_title=title,
                )
            except Exception:
                pass

            display_name = uname if uname else title
            added_list.append(f"• <b>{title}</b> ({display_name})")
        except Exception as e:
            failed_list.append(f"• <code>{token}</code>: {e}")

    await state.clear()
    text_menu, kb_menu = await _build_admin_menu_text_and_kb()

    resp_lines = []
    if added_list:
        resp_lines.append(f"✅ <b>Qo'shilgan kanallar ({len(added_list)} ta):</b>")
        resp_lines.extend(added_list)
        resp_lines.append("")

    if failed_list:
        resp_lines.append(f"⚠️ <b>Qo'shib bo'lmagan kanallar ({len(failed_list)} ta):</b>")
        resp_lines.extend(failed_list)
        resp_lines.append("<i>(Bot kanalda admin ekanligini va username to'g'riligini tekshiring)</i>\n")

    resp_text = "\n".join(resp_lines)
    await message.reply(resp_text, parse_mode="HTML", reply_markup=kb_menu)


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

    m_channels = await get_mandatory_channels()
    if m_channels:
        lines.append(f"\n🔒 <b>Majburiy kanallar ({len(m_channels)} ta):</b>")
        for mc in m_channels:
            uname = f" ({mc['channel_username']})" if mc.get("channel_username") else ""
            lines.append(f"  • {mc['channel_title']}{uname} (<code>{mc['channel_id']}</code>)")

    all_chats = await get_all_linked_chats()
    if all_chats:
        channels = [c for c in all_chats if c["chat_type"] == "channel"]
        groups = [c for c in all_chats if c["chat_type"] == "group"]

        lines.append(f"\n📊 <b>Jami ulangan chatlar: {len(all_chats)} ta</b>")
        if channels:
            lines.append(f"\n📢 <b>Kanal e'lonlari uchun ({len(channels)} ta):</b>")
            for c in channels:
                lines.append(f"  • {c['chat_title'] or 'Nomsiz'} (<code>{c['chat_id']}</code>)")

        if groups:
            lines.append(f"\n💬 <b>Guruhlar ({len(groups)} ta):</b>")
            for g in groups:
                lines.append(f"  • {g['chat_title'] or 'Nomsiz'} (<code>{g['chat_id']}</code>)")
    elif not m_channels:
        lines.append("\n⚠️ Hozircha hech qanday kanal yoki guruh ulanmagan.")

    await message.reply("\n".join(lines), parse_mode="HTML")


async def _is_group_admin(message: Message, bot: Bot) -> bool:
    """Foydalanuvchi guruh admini, kanal egasi yoki tizim xabari ekanligini tekshiradi."""
    # 1. Avtomatik kanal posti
    if getattr(message, "is_automatic_forward", False):
        return True
    # 2. Kanal nomidan yuborilgan xabar
    if message.sender_chat is not None:
        return True
    # 3. Foydalanuvchi ma'lumoti yo'q yoki Telegram tizim akkauntlari
    if not message.from_user:
        return True
    if message.from_user.id in (777000, 1087968824):
        return True
    # 4. Bot egasi (ADMIN_ID)
    if ADMIN_ID and message.from_user.id == ADMIN_ID:
        return True
    # 5. Guruh admini yoki egasi
    try:
        member = await bot.get_chat_member(message.chat.id, message.from_user.id)
        if member.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR):
            return True
    except Exception as e:
        logger.debug("Chat member statusini aniqlashda xato: %s", e)
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


@router.message(Command(commands=["all", "hamma", "sall"]))
async def cmd_tag_all(message: Message, bot: Bot) -> None:
    """Guruhdagi barcha a'zolarni chaqirish (faqat adminlar uchun)."""
    if message.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        await message.reply("⚠️ Bu buyruq faqat guruhlarda ishlaydi!")
        return

    # Adminligini tekshirish
    is_admin = False
    if message.from_user.id == ADMIN_ID:
        is_admin = True
    else:
        try:
            member = await bot.get_chat_member(message.chat.id, message.from_user.id)
            if member.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR):
                is_admin = True
        except Exception:
            pass

    if not is_admin:
        await message.reply("❌ Bu buyruqdan faqat guruh adminlari foydalana oladi.")
        return

    # Xabar matnini ajratib olish (agar mavjud bo'lsa)
    is_silent = False
    if message.text and message.text.startswith("/sall"):
        is_silent = True
        
    text_parts = message.text.split(maxsplit=1)
    tag_text = text_parts[1] if len(text_parts) > 1 else "📣 Diqqat! Barchangizni chaqirishmoqda!"

    members = await get_group_members(message.chat.id)
    if not members:
        await message.reply("⚠️ Hozircha bu guruhda a'zolar bazaga saqlanmagan (faqat guruhda yozganlar belgilanadi).")
        return

    # Asosiy xabarni yuboramiz
    main_msg = await message.reply(f"📢 <b>ADMIN XABARI:</b>\n\n{html.escape(tag_text)}", parse_mode="HTML")

    # A'zolarni 10 tadan bo'lib jo'natamiz
    chunk_size = 10
    chunks = [members[i:i + chunk_size] for i in range(0, len(members), chunk_size)]
    
    for chunk in chunks:
        mentions = []
        for user in chunk:
            name = user['first_name'] or "A'zo"
            if is_silent:
                # Ko'rinmas tag
                mentions.append(f'<a href="tg://user?id={user["user_id"]}">&#8203;</a>')
            else:
                mentions.append(f'<a href="tg://user?id={user["user_id"]}">{html.escape(name)}</a>')
        
        if is_silent:
            chunk_text = "📣" + "".join(mentions)
        else:
            chunk_text = ", ".join(mentions)
            
        try:
            await main_msg.reply(chunk_text, parse_mode="HTML")
            await asyncio.sleep(2.5)  # Spam/Flood limitdan qochish
        except Exception as e:
            logger.error("Tagging error: %s", e)


@router.message(F.new_chat_members)
async def on_new_chat_members(message: Message, bot: Bot) -> None:
    """Yangi a'zolarni kutib olish."""
    if message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
        bot_info = await bot.get_me()
        for member in message.new_chat_members:
            if member.id == bot_info.id:
                continue
            
            # Guruh a'zosi sifatida saqlab qo'yamiz (Tag All uchun)
            try:
                await update_group_member(
                    chat_id=message.chat.id,
                    user_id=member.id,
                    first_name=member.first_name,
                    username=member.username
                )
            except Exception:
                pass

            text = (
                f"👋 <b>Xush kelibsiz, {html.escape(member.first_name)}!</b>\n\n"
                f"Guruhimizga qo'shilganingizdan xursandmiz. Konkurslarimizda qatnashib ⭐️ Telegram Stars va qimmatbaho yutuqlarni yutib olish uchun botimizga kiring!\n"
                f"👉 @{bot_info.username}"
            )
            try:
                welcome_msg = await message.reply(text, parse_mode="HTML")
                asyncio.create_task(_auto_delete_msg(bot, message.chat.id, welcome_msg.message_id, delay=60))
            except Exception as e:
                logger.error("Welcome yuborishda xato: %s", e)


@router.message(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))
async def on_group_message(message: Message, bot: Bot) -> None:
    """Guruhdagi xabarlar (majburiy obuna tekshiruvi, 777 o'yini, post kamentlari)."""
    # 1. Avtomatik kanal forvardlari yoki kanal nomidan yuborilgan xabarlarni zudlik bilan o'tkazib yuborish
    if getattr(message, "is_automatic_forward", False) or message.sender_chat is not None:
        return

    if message.from_user is None or message.from_user.is_bot:
        return

    # Telegram tizim akkauntlari (Anonymous Admin va Telegram Service)
    if message.from_user.id in (777000, 1087968824):
        return

    if message.text and message.text.startswith("/"):
        return

    # Anti-Spam (Linklar va Forwardlar) tekshiruvi
    is_admin = await _is_group_admin(message, bot)
    if not is_admin:
        has_link = False
        if message.entities:
            for ent in message.entities:
                if ent.type in ("url", "text_link"):
                    has_link = True
                    break
        
        if has_link or message.forward_from_chat:
            try:
                await message.delete()
                warning = await message.answer(f"⚠️ <b>{html.escape(message.from_user.first_name)}</b>, guruhda link yoki reklama tarqatish taqiqlangan!")
                asyncio.create_task(_auto_delete_msg(bot, message.chat.id, warning.message_id, delay=10))
            except Exception:
                pass
            return

    if not await is_linked_chat(message.chat.id):
        await add_linked_chat(
            owner_id=ADMIN_ID or 0,
            chat_id=message.chat.id,
            chat_type="group",
            chat_title=message.chat.title,
        )

    # 2. Majburiy obuna tekshiruvi (oddiy a'zolar uchun)
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

    # 4. Guruh faolligi (Chat Mining: har 15 ta xabarda +1 ball)
    try:
        user_mined, current_count, total_mined = await record_group_chat_activity(
            user_id=message.from_user.id,
            chat_id=message.chat.id,
        )
        if user_mined:
            first_name = message.from_user.first_name or "Foydalanuvchi"
            safe_name = html.escape(first_name)
            user_tag = f'<a href="tg://user?id={message.from_user.id}">{safe_name}</a>'
            bonus_msg = await message.reply(
                f"🔥 <b>CHAT FAOLLIK BONUST!</b>\n\n"
                f"🎉 {user_tag}, guruhdagi 15 ta faol xabaringiz uchun profilingizga <b>+1 ball</b> qo'shildi! 🚀\n"
                f"<i>(Jami chatdan ishlangan: {total_mined} ball)</i>",
                parse_mode="HTML",
            )
            asyncio.create_task(_auto_delete_msg(bot, message.chat.id, bonus_msg.message_id, delay=30))
    except Exception as e:
        logger.warning("Chat mining xatosi: %s", e)

