"""
main.py — Botning kirish nuqtasi.
Barcha handlerlarni ulaydi, bazani ishga tushiradi va pollingni boshlaydi.
"""

import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties

from config import BOT_TOKEN
from database import init_db
from handlers import router


def setup_logging() -> None:
    """Logging sozlamalari: konsol + fayl."""
    log_format = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # Konsol handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter(log_format, datefmt=date_format))
    root_logger.addHandler(console_handler)

    # Fayl handler
    file_handler = logging.FileHandler("bot.log", encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter(log_format, datefmt=date_format))
    root_logger.addHandler(file_handler)

    # Aiogram ichki loglarini kamaytirish
    logging.getLogger("aiogram").setLevel(logging.WARNING)


async def main() -> None:
    """Asosiy funksiya: bot va dispatcherni ishga tushiradi."""
    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("Bot ishga tushmoqda...")

    # Ma'lumotlar bazasini tayyorlash
    await init_db()

    # Bot instansiya (HTML parse_mode default)
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode="HTML"),
    )

    # Dispatcher va routerlarni ulash
    dp = Dispatcher()
    dp.include_router(router)

    logger.info("Polling boshlandi. Botni to'xtatish uchun Ctrl+C bosing.")

    try:
        # Adminga bot ishga tushganini xabar berish
        try:
            from config import ADMIN_ID
            await bot.send_message(
                ADMIN_ID,
                "✅ Bot muvaffaqiyatli ishga tushdi!\n"
                f"⏰ {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
        except Exception as e:
            logger.warning("Adminga xabar yuborib bo'lmadi: %s", e)

        # message_reaction update turini ham qabul qilish uchun allowed_updates ro'yxati
        await dp.start_polling(
            bot,
            allowed_updates=[
                "message",
                "message_reaction",
                "chat_member",
            ],
            drop_pending_updates=True,  # Eski updatelarni tashlab yuborish
        )
    finally:
        await bot.session.close()
        logger.info("Bot to'xtatildi.")


if __name__ == "__main__":
    asyncio.run(main())
