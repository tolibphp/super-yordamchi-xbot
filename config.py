"""
config.py — Loyiha sozlamalari.
.env faylidan BOT_TOKEN va ADMIN_ID ni o'qiydi.
CHANNEL_ID va CHAT_ID endi bazadan boshqariladi (multi-user rejim).
"""

import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
ADMIN_ID: int = int(os.getenv("ADMIN_ID", "0"))

# Sozlamalar to'g'ri to'ldirilganini tekshirish
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN .env faylida ko'rsatilmagan!")
if not ADMIN_ID:
    raise ValueError("ADMIN_ID .env faylida ko'rsatilmagan!")
