# 🤖 Telegram Faollik va G'olib Aniqlash Boti

Telegram kanal va muhokama guruhidagi foydalanuvchilar faolligini (reaksiyalar va kommentariyalar) kuzatib boruvchi va tasodifiy g'olib aniqlaydigan bot.

## ✨ Imkoniyatlar

- 📊 Kanal postlariga bosilgan **reaksiyalarni** avtomatik kuzatish
- 💬 Muhokama guruhidagi **kommentariyalarni** avtomatik kuzatish
- 🏆 Haftalik va oylik **tasodifiy g'olib** tanlash
- ✅ G'olib tanlanishidan oldin **kanal + guruhga a'zolikni** tekshirish
- 📈 Faollik **statistikasi** (top 5 foydalanuvchi)
- 📝 Barcha faolliklarni **SQLite bazasiga** yozish

## ⚠️ MUHIM: Botni admin qilish

> **Telegram Bot API reaksiyalarni faqat bot kanal/guruhda ADMIN qilib qo'yilgandan KEYINGI vaqtdan boshlab ko'ra oladi.**
>
> Botni ishga tushirishdan **OLDIN** quyidagilarni bajaring:
> 1. Botni **kanalingizga admin** qilib qo'shing
> 2. Botni **muhokama guruhingizga admin** qilib qo'shing
> 3. Bot adminligida kamida quyidagi ruxsatlarni bering:
>    - Xabarlarni o'qish (Read Messages)
>    - Xabar yuborish (Post Messages) — g'olib e'lonini yuborish uchun

## 📁 Loyiha tuzilmasi

```
telegram-activity-bot/
├── main.py              # Botning kirish nuqtasi (polling, logging)
├── config.py            # .env dan sozlamalarni o'qish
├── database.py          # SQLite bazasi bilan ishlash (async)
├── handlers.py          # Reaction/comment kuzatish va admin buyruqlari
├── membership.py        # Kanal+guruh a'zoligini tekshirish
├── winner.py            # G'olib tanlash va e'lon qilish
├── .env.example         # Muhit o'zgaruvchilari namunasi
├── .gitignore           # Git ignore
├── requirements.txt     # Python kutubxonalar
├── Procfile             # Railway worker buyrug'i
├── railway.json         # Railway deploy sozlamalari
├── runtime.txt          # Python versiyasi (3.11)
├── telegram-activity-bot.service  # Systemd service fayli (VPS uchun)
└── README.md            # Hujjat (shu fayl)
```

## 🚀 O'rnatish va ishga tushirish (Lokal)

### 1. Repozitoriyani klonlash

```bash
git clone <repo-url>
cd telegram-activity-bot
```

### 2. Virtual muhit yaratish

```bash
python3.11 -m venv venv
source venv/bin/activate   # Linux/macOS
# yoki
venv\Scripts\activate      # Windows
```

### 3. Kutubxonalarni o'rnatish

```bash
pip install -r requirements.txt
```

### 4. `.env` faylini sozlash

```bash
cp .env.example .env
nano .env   # yoki boshqa muharrir bilan oching
```

Quyidagi qiymatlarni to'ldiring:

| O'zgaruvchi   | Tavsif                                     | Misol                   |
| ------------- | ------------------------------------------ | ----------------------- |
| `BOT_TOKEN`   | @BotFather dan olingan bot token           | `123456:ABC-DEF...`     |
| `ADMIN_ID`    | Sizning Telegram raqamli ID'ngiz           | `123456789`             |
| `CHANNEL_ID`  | Kanalning raqamli ID'si                    | `-1001234567890`        |
| `CHAT_ID`     | Muhokama guruhining (discussion group) raqamli ID'si | `-1001234567891` |

> **Telegram ID'larni qanday bilish mumkin?**
> - **Shaxsiy ID:** @userinfobot ga `/start` yuboring
> - **Kanal/Guruh ID:** @getmyid_bot ni kanal/guruhga qo'shib, ID'ni oling.

### 5. Botni ishga tushirish

```bash
python main.py
```

---

## ☁️ Railway'ga deploy qilish (24/7)

### 1-qadam: GitHub'ga yuklash

```bash
cd telegram-activity-bot
git init
git add .
git commit -m "Initial commit: Telegram activity bot"
git branch -M main
git remote add origin https://github.com/SIZNING_USERNAME/telegram-activity-bot.git
git push -u origin main
```

### 2-qadam: Railway'da loyiha yaratish

1. [railway.app](https://railway.app) ga kiring (GitHub akkaunt bilan)
2. **New Project** → **Deploy from GitHub Repo** ni tanlang
3. `telegram-activity-bot` reponi tanlang
4. Railway avtomatik build qiladi

### 3-qadam: Environment Variables sozlash

Railway dashboardda loyihangizni oching:

**Settings** → **Variables** → quyidagilarni qo'shing:

| Nomi          | Qiymati                          |
| ------------- | -------------------------------- |
| `BOT_TOKEN`   | BotFather'dan olingan token      |
| `ADMIN_ID`    | Sizning Telegram ID'ngiz         |
| `CHANNEL_ID`  | Kanal ID'si (`-100...`)          |
| `CHAT_ID`     | Muhokama guruhi ID'si (`-100...`)|
| `DB_PATH`     | `/data/activity.db`              |

### 4-qadam: Volume ulash (baza saqlanishi uchun)

> ⚠️ **Muhim:** Railway'da fayl tizimi vaqtinchalik (ephemeral). Volume ulamasangiz, har deploy'da baza yo'qoladi!

1. Loyiha ichida **+ New** → **Volume** ni bosing
2. **Mount Path:** `/data` deb yozing
3. **Service**'ga ulang

Shundan keyin SQLite baza `/data/activity.db` da saqlanadi va deploy'larda yo'qolmaydi.

### 5-qadam: Tekshirish

- Railway dashboardda **Deployments** tabidan loglarni ko'ring
- Bot ishga tushganini Telegramda `/statistika` buyrug'i bilan tekshiring

> 💡 **Eslatma:** Railway free tier'da oyiga ~500 soat bepul beriladi. 24/7 uchun bu yetarli (~720 soat/oy), lekin limitga yaqinlashsa, Developer plan ($5/oy) ga o'tish mumkin.

## 🛠 Admin buyruqlari

Buyruqlar faqat `.env` da ko'rsatilgan `ADMIN_ID` uchun ishlaydi.

| Buyruq              | Tavsif                                                        |
| ------------------- | ------------------------------------------------------------- |
| `/haftalik_golib`   | Oxirgi 7 kunda faol va eligible a'zolardan g'olib tanlaydi    |
| `/oylik_golib`      | Oxirgi 30 kunda faol va eligible a'zolardan g'olib tanlaydi   |
| `/statistika`       | Haftalik eng faol 5 kishini ko'rsatadi                        |

## 📊 Ma'lumotlar bazasi

Bot `activity.db` nomli SQLite faylini avtomatik yaratadi.

**`activity` jadvali:**

| Ustun           | Turi     | Tavsif                              |
| --------------- | -------- | ----------------------------------- |
| `id`            | INTEGER  | Primary key, autoincrement          |
| `user_id`       | INTEGER  | Foydalanuvchi Telegram ID'si        |
| `username`      | TEXT     | @username (bo'lmasligi mumkin)      |
| `first_name`    | TEXT     | Foydalanuvchi ismi                  |
| `activity_type` | TEXT     | `reaction` yoki `comment`           |
| `message_id`    | INTEGER  | Qaysi xabarga tegishli              |
| `created_at`    | DATETIME | Faollik vaqti (UTC)                 |

## 🖥 VPS'ga joylashtirish (Deployment)

### 1. Fayllarni VPS'ga ko'chirish

```bash
scp -r telegram-activity-bot/ user@your-vps:/opt/
```

### 2. VPS'da sozlash

```bash
ssh user@your-vps
cd /opt/telegram-activity-bot

# Virtual muhit va kutubxonalar
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# .env faylini sozlash
cp .env.example .env
nano .env
```

### 3. Systemd service sifatida ishga tushirish

```bash
# Bot uchun alohida foydalanuvchi (xavfsizlik uchun)
sudo useradd -r -s /bin/false botuser
sudo chown -R botuser:botuser /opt/telegram-activity-bot

# Service faylini nusxalash
sudo cp /opt/telegram-activity-bot/telegram-activity-bot.service /etc/systemd/system/

# Systemd'ni yangilash va botni ishga tushirish
sudo systemctl daemon-reload
sudo systemctl enable telegram-activity-bot   # Avtomatik start
sudo systemctl start telegram-activity-bot    # Hozir ishga tushirish
```

### 4. Holatni tekshirish

```bash
# Service holati
sudo systemctl status telegram-activity-bot

# Loglarni ko'rish
sudo journalctl -u telegram-activity-bot -f

# Yoki bot.log faylini ko'rish
tail -f /opt/telegram-activity-bot/bot.log
```

### 5. Botni qayta ishga tushirish

```bash
sudo systemctl restart telegram-activity-bot
```

## 📋 G'olib tanlash jarayoni

```
1. Admin /haftalik_golib (yoki /oylik_golib) buyrug'ini beradi
2. Bot bazadan oxirgi 7 (yoki 30) kunda faol bo'lgan user_id'larni oladi
3. Har bir foydalanuvchining kanal + guruhga a'zoligini tekshiradi
4. Faqat ikkalasiga ham a'zo bo'lganlarni saralaydi
5. random.choice() bilan 1 tasodifiy g'olib tanlaydi
6. Natijani chiroyli HTML formatda muhokama guruhiga yuboradi
```

## 🔧 Texnik talablar

- Python 3.11+
- Telegram Bot API 7.0+ (reaksiyalar uchun)
- Bot kanal va guruhda admin bo'lishi shart

## 📄 Litsenziya

MIT License
