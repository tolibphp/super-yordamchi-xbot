"""
main.py — Botning kirish nuqtasi.
Barcha handlerlarni ulaydi, bazani ishga tushiradi va pollingni boshlaydi.
"""

import asyncio
import logging
import sys
from datetime import datetime

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.types import FSInputFile
import os

from config import BOT_TOKEN, ADMIN_ID, get_uzb_now
from database import init_db
from handlers import router, set_bot_username
from birthday import broadcast_daily_birthdays


def setup_logging() -> None:
    """Logging sozlamalari: konsol + fayl."""
    log_format = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

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


async def daily_birthday_scheduler(bot: Bot) -> None:
    """
    O'zbekiston vaqti (UTC+5) bo'yicha har kuni ertalab soat 09:00 da
    barcha ulangan guruhlarga kunlik tug'ilgan kun postini e'lon qiluvchi fon vazifasi.
    """
    scheduler_logger = logging.getLogger("birthday_scheduler")
    last_sent_date: str = ""
    me = await bot.get_me()
    bot_uname = me.username or ""

    while True:
        try:
            now_uzb = get_uzb_now()
            today_str = now_uzb.strftime("%Y-%m-%d")

            # Har kuni soat 09:00 da (va faqat bir marta)
            if now_uzb.hour == 9 and last_sent_date != today_str:
                scheduler_logger.info("Guruhlarga kunlik tug'ilgan kun xabarnomasi yuborilmoqda (%s)", today_str)
                await broadcast_daily_birthdays(bot, bot_uname)
                last_sent_date = today_str
                
            # Avtomatik Baza Zaxirasi (Har kuni soat 23:55 da adminga tashlaydi)
            auto_backup_key = f"backup_{today_str}"
            if now_uzb.hour == 23 and now_uzb.minute >= 55 and auto_backup_key not in last_sent_date:
                scheduler_logger.info("Adminga avtomatik baza zaxirasi yuborilmoqda...")
                db_path = "data/bot.db"
                if os.path.exists(db_path) and ADMIN_ID:
                    try:
                        file = FSInputFile(db_path, filename=f"auto_backup_{today_str}.db")
                        await bot.send_document(
                            chat_id=ADMIN_ID,
                            document=file,
                            caption=f"🛡 <b>Avtomatik Baza Zaxirasi</b> ({today_str})\n\n"
                                    f"Bu botingizning kunlik avtomatik saqlangan bazasi. "
                                    f"Agar baza o'chib ketsa, shu faylni botga yuborsangiz o'rnatib olaman.",
                            parse_mode="HTML"
                        )
                        # Avoid triggering again today by saving the key in last_sent_date or just adding to it
                        last_sent_date += auto_backup_key
                    except Exception as e:
                        scheduler_logger.error(f"Avtomatik backup yuborishda xato: {e}")

            await asyncio.sleep(45)
        except asyncio.CancelledError:
            break
        except Exception as e:
            scheduler_logger.error("Kunlik tug'ilgan kun schedulerida xato: %s", e)
            await asyncio.sleep(60)


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

    # Bot username'ini olish (inline knopkalar uchun)
    await set_bot_username(bot)

    # Dispatcher va routerlarni ulash
    dp = Dispatcher()
    dp.include_router(router)

    # Kunlik tug'ilgan kun hisoblagichi fon vazifasini ishga tushirish
    scheduler_task = asyncio.create_task(daily_birthday_scheduler(bot))

    logger.info("Polling boshlandi. Botni to'xtatish uchun Ctrl+C bosing.")

    try:
        # Adminga bot ishga tushganini xabar berish (agar ADMIN_ID ko'rsatilgan bo'lsa)
        if ADMIN_ID:
            try:
                uzb_time = get_uzb_now().strftime("%Y-%m-%d %H:%M:%S")
                await bot.send_message(
                    ADMIN_ID,
                    f"✅ Bot muvaffaqiyatli ishga tushdi!\n"
                    f"⏰ Toshkent vaqti: {uzb_time}"
                )
            except Exception as e:
                logger.warning("Adminga xabar yuborib bo'lmadi: %s", e)

        # Barcha kerakli update turlarini qabul qilish
        await dp.start_polling(
            bot,
            allowed_updates=[
                "message",
                "edited_message",
                "callback_query",
                "message_reaction",
                "chat_member",
                "my_chat_member",
            ],
            drop_pending_updates=True,
        )
    finally:
        scheduler_task.cancel()
        await bot.session.close()
        logger.info("Bot to'xtatildi.")


if __name__ == "__main__":
    asyncio.run(main())

