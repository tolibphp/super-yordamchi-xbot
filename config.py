"""
config.py — Loyiha sozlamalari.
.env faylidan BOT_TOKEN va ADMIN_ID ni o'qiydi.
CHANNEL_ID va CHAT_ID endi bazadan boshqariladi (multi-user rejim).
"""

import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN: str = os.getenv("BOT_TOKEN", "").strip().strip('"').strip("'")
_raw_admin_id = os.getenv("ADMIN_ID", "0").strip().strip('"').strip("'")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN ko'rsatilmagan! Railway Variables yoki .env faylida BOT_TOKEN ni to'ldiring.")

# ADMIN_ID ixtiyoriy — agar raqam bo'lsa o'qiydi, bo'lmasa 0 bo'ladi
ADMIN_IDS = [int(x.strip()) for x in _raw_admin_id.split(",") if x.strip().isdigit()]
ADMIN_ID = ADMIN_IDS[0] if ADMIN_IDS else 0

# O'zbekiston vaqt mintaqasi (UTC+5, Tashkent)
from datetime import datetime, timezone, timedelta
UZB_TZ = timezone(timedelta(hours=5), name="Asia/Tashkent")

def get_uzb_now() -> datetime:
    """O'zbekiston vaqti bilan joriy vaqtni qaytaradi."""
    return datetime.now(UZB_TZ)
