"""
membership.py — Foydalanuvchining kanal va guruhga a'zoligini tekshirish.
Bot API get_chat_member() orqali dinamik kanal/guruhda a'zoligini tasdiqlaydi.
"""

import logging
from aiogram import Bot
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramBadRequest

logger = logging.getLogger(__name__)

# A'zo hisoblanmaydigan statuslar
_NOT_MEMBER_STATUSES = {ChatMemberStatus.LEFT, ChatMemberStatus.KICKED}


async def check_membership(
    bot: Bot,
    user_id: int,
    channel_id: int | None = None,
    chat_id: int | None = None,
) -> bool:
    """
    Foydalanuvchi berilgan kanal va/yoki guruhga a'zo ekanligini tekshiradi.
    Berilgan barcha chatlarda a'zo bo'lsa True, aks holda False qaytaradi.
    """
    chats_to_check: list[tuple[int, str]] = []
    if channel_id:
        chats_to_check.append((channel_id, "kanal"))
    if chat_id:
        chats_to_check.append((chat_id, "guruh"))

    if not chats_to_check:
        # Hech qanday chat berilmagan — tekshiruvsiz eligible
        return True

    for cid, label in chats_to_check:
        try:
            member = await bot.get_chat_member(chat_id=cid, user_id=user_id)
            if member.status in _NOT_MEMBER_STATUSES:
                logger.info("User %s %sda a'zo EMAS (status: %s)", user_id, label, member.status)
                return False
        except TelegramBadRequest as e:
            if "user not found" in str(e).lower():
                logger.warning("User %s topilmadi (%s), eligible EMAS.", user_id, label)
            else:
                logger.error("Telegram API xatosi (user %s, %s): %s", user_id, label, e)
            return False
        except Exception as e:
            logger.error("Kutilmagan xato check_membership (user %s, %s): %s", user_id, label, e)
            return False

    logger.info("User %s — eligible (barcha chatlarga a'zo).", user_id)
    return True
