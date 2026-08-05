"""
config.py — Loyiha sozlamalari.
.env faylidan BOT_TOKEN, ADMIN_ID, CHANNEL_ID, CHAT_ID ni o'qiydi.
"""

import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
ADMIN_ID: int = int(os.getenv("ADMIN_ID", "0"))
CHANNEL_ID: int = int(os.getenv("CHANNEL_ID", "0"))
CHAT_ID: int = int(os.getenv("CHAT_ID", "0"))

# Sozlamalar to'g'ri to'ldirilganini tekshirish
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN .env faylida ko'rsatilmagan!")
if not ADMIN_ID:
    raise ValueError("ADMIN_ID .env faylida ko'rsatilmagan!")
if not CHANNEL_ID:
    raise ValueError("CHANNEL_ID .env faylida ko'rsatilmagan!")
if not CHAT_ID:
    raise ValueError("CHAT_ID .env faylida ko'rsatilmagan!")
