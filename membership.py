"""
membership.py — Foydalanuvchining kanal va guruhga a'zoligini tekshirish.
Bot API get_chat_member() orqali ikki joyda ham a'zoligini tasdiqlaydi.
"""

import logging
from aiogram import Bot
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramBadRequest

from config import CHANNEL_ID, CHAT_ID

logger = logging.getLogger(__name__)

# A'zo hisoblanmaydigan statuslar
_NOT_MEMBER_STATUSES = {ChatMemberStatus.LEFT, ChatMemberStatus.KICKED}


async def check_membership(bot: Bot, user_id: int) -> bool:
    """
    Foydalanuvchi ham kanalga, ham muhokama guruhiga a'zo ekanligini tekshiradi.
    Ikkalasiga ham a'zo bo'lsa True, aks holda False qaytaradi.
    """
    try:
        # 1. Kanalga a'zolikni tekshirish
        channel_member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        if channel_member.status in _NOT_MEMBER_STATUSES:
            logger.info("User %s kanalda a'zo EMAS (status: %s)", user_id, channel_member.status)
            return False

        # 2. Muhokama guruhiga a'zolikni tekshirish
        chat_member = await bot.get_chat_member(chat_id=CHAT_ID, user_id=user_id)
        if chat_member.status in _NOT_MEMBER_STATUSES:
            logger.info("User %s guruhda a'zo EMAS (status: %s)", user_id, chat_member.status)
            return False

        logger.info("User %s — eligible (ikkalasiga ham a'zo).", user_id)
        return True

    except TelegramBadRequest as e:
        # "user not found" yoki shunga o'xshash xatolik
        if "user not found" in str(e).lower():
            logger.warning("User %s topilmadi (get_chat_member xatosi), eligible EMAS.", user_id)
        else:
            logger.error("Telegram API xatosi (user %s): %s", user_id, e)
        return False

    except Exception as e:
        logger.error("Kutilmagan xato check_membership (user %s): %s", user_id, e)
        return False
