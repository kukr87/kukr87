import asyncio
import json
import os
import base64
import logging
import sqlite3
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import aiohttp
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramForbiddenError

# ====================== НАСТРОЙКИ ======================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)
logger = logging.getLogger("koefiibot")

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
BOT_USERNAME = os.getenv("BOT_USERNAME", "koefiibot")

YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID", "")
YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY", "")

PREMIUM_PRICE = 300
tz = ZoneInfo("Europe/Moscow")
DB_FILE = "bot.db"

admin_users = {str(ADMIN_ID)}

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

COUNTRY_FLAGS = {
    "Россия": "🇷🇺", "Англия": "🇬🇧", "Испания": "🇪🇸", "Италия": "🇮🇹",
    "Германия": "🇩🇪", "Франция": "🇫🇷", "Португалия": "🇵🇹", "Турция": "🇹🇷",
    "Сербия": "🇷🇸", "Казахстан": "🇰🇿", "Украина": "🇺🇦", "Беларусь": "🇧🇾",
    "США": "🇺🇸", "Бразилия": "🇧🇷", "Аргентина": "🇦🇷", "Австрия": "🇦🇹",
    "Бельгия": "🇧🇪", "Болгария": "🇧🇬", "Венгрия": "🇭🇺", "Греция": "🇬🇷",
    "Дания": "🇩🇰", "Ирландия": "🇮🇪", "Нидерланды": "🇳🇱", "Норвегия": "🇳🇴",
    "Польша": "🇵🇱", "Хорватия": "🇭🇷", "Швеция": "🇸🇪", "Швейцария": "🇨🇭",
    "Чехия": "🇨🇿", "Румыния": "🇷🇴",
}

SUPPORT_CATEGORIES = {
    "bug": "🐛 Баг / ошибка",
    "pay": "💳 Оплата",
    "idea": "💡 Предложение",
    "q": "❓ Вопрос",
}

def get_flag(country: str) -> str:
    return COUNTRY_FLAGS.get(country, "🏳️")

# ====================== БАЗА ДАННЫХ ======================

db_pool: aiohttp.ClientSession = None  # для yookassa

def init_db():
    """Создаёт таблицы если их ещё нет."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    c.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id      INTEGER PRIMARY KEY,
        username     TEXT DEFAULT '',
        first_name   TEXT DEFAULT '',
        subscription TEXT DEFAULT 'Free',
        end_date     TEXT DEFAULT NULL,
        reg_date     TEXT,
        referred_by  INTEGER DEFAULT NULL,
        streak_days  INTEGER DEFAULT 0,
        last_visit   TEXT DEFAULT NULL,
        status       TEXT DEFAULT 'active',
        notified_expire INTEGER DEFAULT 0
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS matches (
        id        INTEGER PRIMARY KEY AUTOINCREMENT,
        name      TEXT,
        country   TEXT,
        league    TEXT,
        match_time TEXT DEFAULT '',
        text      TEXT,
        created_at TEXT
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS viewed_matches (
        user_id   INTEGER,
        match_id  INTEGER,
        viewed_date TEXT,
        PRIMARY KEY (user_id, match_id)
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS favorites (
        user_id  INTEGER,
        match_id INTEGER,
        added_at TEXT,
        PRIMARY KEY (user_id, match_id)
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS express_picks (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        name       TEXT,
        country    TEXT,
        league     TEXT,
        prediction TEXT,
        coef       TEXT,
        created_at TEXT
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS support_threads (
        thread_id INTEGER PRIMARY KEY,
        user_id   INTEGER,
        user_name TEXT,
        category  TEXT,
        created_at TEXT
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS support_messages (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        thread_id  INTEGER,
        sender     TEXT,
        text       TEXT,
        created_at TEXT
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS pending_payments (
        payment_id TEXT PRIMARY KEY,
        user_id    INTEGER,
        amount     REAL,
        status     TEXT DEFAULT 'pending',
        created_at TEXT
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS admin_log (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        admin_id   INTEGER,
        action     TEXT,
        details    TEXT,
        created_at TEXT
    )""")

    conn.commit()
    conn.close()
    logger.info("База данных инициализирована")

# --- Async DB helpers ---

async def db_execute(query: str, params: tuple = ()):
    loop = asyncio.get_event_loop()
    def _exec():
        conn = sqlite3.connect(DB_FILE, timeout=10)
        conn.execute(query, params)
        conn.commit()
        conn.close()
    await loop.run_in_executor(None, _exec)

async def db_execute_many(query: str, params_list: list):
    loop = asyncio.get_event_loop()
    def _exec():
        conn = sqlite3.connect(DB_FILE, timeout=10)
        conn.executemany(query, params_list)
        conn.commit()
        conn.close()
    await loop.run_in_executor(None, _exec)

async def db_fetchone(query: str, params: tuple = ()):
    loop = asyncio.get_event_loop()
    def _fetch():
        conn = sqlite3.connect(DB_FILE, timeout=10)
        c = conn.cursor()
        c.execute(query, params)
        row = c.fetchone()
        conn.close()
        return row
    return await loop.run_in_executor(None, _fetch)

async def db_fetchall(query: str, params: tuple = ()):
    loop = asyncio.get_event_loop()
    def _fetch():
        conn = sqlite3.connect(DB_FILE, timeout=10)
        c = conn.cursor()
        c.execute(query, params)
        rows = c.fetchall()
        conn.close()
        return rows
    return await loop.run_in_executor(None, _fetch)

# --- User helpers ---

async def get_or_create_user(user_id: int, first_name: str = "", username: str = "") -> dict:
    row = await db_fetchone("SELECT * FROM users WHERE user_id = ?", (user_id,))
    if row:
        return {
            "user_id": row[0], "username": row[1], "first_name": row[2],
            "subscription": row[3], "end_date": row[4], "reg_date": row[5],
            "referred_by": row[6], "streak_days": row[7], "last_visit": row[8],
            "status": row[9], "notified_expire": row[10],
        }
    now = datetime.now(tz).strftime("%Y-%m-%d")
    await db_execute(
        "INSERT INTO users (user_id, username, first_name, subscription, reg_date, status) "
        "VALUES (?, ?, ?, 'Free', ?, 'active')",
        (user_id, username, first_name, now)
    )
    return {
        "user_id": user_id, "username": username, "first_name": first_name,
        "subscription": "Free", "end_date": None, "reg_date": now,
        "referred_by": None, "streak_days": 0, "last_visit": None,
        "status": "active", "notified_expire": 0,
    }

async def update_user_subscription(user_id: int, sub: str, end_date: str = None):
    await db_execute(
        "UPDATE users SET subscription = ?, end_date = ?, notified_expire = 0 WHERE user_id = ?",
        (sub, end_date, user_id)
    )

async def check_match_limit(user_id: int, match_id: int) -> bool:
    user = await get_or_create_user(user_id)
    if user["subscription"] == "Premium":
        return True
    today = datetime.now(tz).date()
    viewed = await db_fetchall(
        "SELECT match_id FROM viewed_matches WHERE user_id = ? AND viewed_date = ?",
        (user_id, str(today))
    )
    viewed_ids = [r[0] for r in viewed]
    if match_id in viewed_ids:
        return True
    if len(viewed_ids) >= 3:
        return False
    await db_execute(
        "INSERT OR IGNORE INTO viewed_matches (user_id, match_id, viewed_date) VALUES (?, ?, ?)",
        (user_id, match_id, str(today))
    )
    return True

async def update_streak(user_id: int):
    user = await get_or_create_user(user_id)
    today = datetime.now(tz).date()
    last_visit = user.get("last_visit")
    if last_visit:
        try:
            last_date = datetime.strptime(last_visit, "%Y-%m-%d").date()
            if last_date == today:
                return
            diff = (today - last_date).days
            if diff == 1:
                new_streak = user.get("streak_days", 0) + 1
            elif diff > 1:
                new_streak = 1
            else:
                new_streak = user.get("streak_days", 0)
        except ValueError:
            new_streak = 1
    else:
        new_streak = 1
    await db_execute(
        "UPDATE users SET last_visit = ?, streak_days = ? WHERE user_id = ?",
        (str(today), new_streak, user_id)
    )

async def log_admin_action(admin_id: int, action: str, details: str = ""):
    now = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
    await db_execute(
        "INSERT INTO admin_log (admin_id, action, details, created_at) VALUES (?, ?, ?, ?)",
        (admin_id, action, details, now)
    )

# ====================== YOOKASSA ======================

async def create_yookassa_payment(user_id: int, amount: float = PREMIUM_PRICE):
    if not YOOKASSA_SHOP_ID or not YOOKASSA_SECRET_KEY:
        logger.error("YOOKASSA_SHOP_ID или YOOKASSA_SECRET_KEY не заданы")
        return None

    auth_string = "{}:{}".format(YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY)
    auth_header = base64.b64encode(auth_string.encode("utf-8")).decode("utf-8")

    url = "https://api.yookassa.ru/v3/payments"
    idempotence_key = "{}-{}".format(user_id, int(datetime.now(tz).timestamp()))

    payload = {
        "amount": {"value": "{:.2f}".format(amount), "currency": "RUB"},
        "confirmation": {
            "type": "redirect",
            "return_url": "https://t.me/{}".format(BOT_USERNAME)
        },
        "capture": True,
        "metadata": {"user_id": str(user_id)},
        "description": "Premium на 30 дней",
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": "Basic {}".format(auth_header),
        "Idempotence-Key": idempotence_key,
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                data = await resp.json()
                logger.info("[YooKassa] HTTP %s", resp.status)
                if resp.status in (200, 201):
                    pid = data.get("id")
                    curl = data.get("confirmation", {}).get("confirmation_url")
                    if pid and curl:
                        now = datetime.now(tz).strftime("%Y-%m-%d %H:%M")
                        await db_execute(
                            "INSERT OR REPLACE INTO pending_payments "
                            "(payment_id, user_id, amount, status, created_at) VALUES (?, ?, ?, 'pending', ?)",
                            (pid, user_id, amount, now)
                        )
                        return {"payment_id": pid, "confirmation_url": curl}
                    logger.warning("[YooKassa] Нет confirmation_url: %s", data)
                    return None
                else:
                    logger.error("[YooKassa] Ошибка: %s | %s", resp.status, data)
                    return None
    except Exception as e:
        logger.exception("[YooKassa] Исключение: %s", e)
        return None

async def check_yookassa_payment(payment_id: str) -> str:
    if not YOOKASSA_SHOP_ID or not YOOKASSA_SECRET_KEY:
        return "error"
    auth_string = "{}:{}".format(YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY)
    auth_header = base64.b64encode(auth_string.encode("utf-8")).decode("utf-8")
    url = "https://api.yookassa.ru/v3/payments/{}".format(payment_id)
    headers = {
        "Authorization": "Basic {}".format(auth_header),
        "Content-Type": "application/json",
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                data = await resp.json()
                if resp.status == 200:
                    return data.get("status", "unknown")
                logger.error("[YooKassa check] HTTP %s: %s", resp.status, data)
                return "error"
    except Exception as e:
        logger.exception("[YooKassa check] %s", e)
        return "error"

async def activate_premium(user_id: int, days: int = 30):
    user = await get_or_create_user(user_id)
    if user["subscription"] == "Premium" and user["end_date"]:
        try:
            cur_end = datetime.strptime(user["end_date"], "%Y-%m-%d")
            if cur_end.date() > datetime.now(tz).date():
                new_end = (cur_end + timedelta(days=days)).strftime("%Y-%m-%d")
            else:
                new_end = (datetime.now(tz) + timedelta(days=days)).strftime("%Y-%m-%d")
        except ValueError:
            new_end = (datetime.now(tz) + timedelta(days=days)).strftime("%Y-%m-%d")
    else:
        new_end = (datetime.now(tz) + timedelta(days=days)).strftime("%Y-%m-%d")
    await update_user_subscription(user_id, "Premium", new_end)
    return new_end

async def process_successful_payment(payment_id: str, user_id: int):
    row = await db_fetchone(
        "SELECT status FROM pending_payments WHERE payment_id = ?", (payment_id,)
    )
    if row and row[0] == "succeeded":
        return  # уже обработан
    end_date = await activate_premium(user_id, 30)
    await db_execute(
        "UPDATE pending_payments SET status = 'succeeded' WHERE payment_id = ?",
        (payment_id,)
    )
    try:
        await bot.send_message(
            user_id,
            "🎉 <b>Оплата прошла успешно!</b>\n\n"
            "Вам активирована подписка Premium на 30 дней.\n"
            "Действует до: {}".format(end_date),
            parse_mode="HTML"
        )
    except TelegramForbiddenError:
        await db_execute("UPDATE users SET status = 'blocked' WHERE user_id = ?", (user_id,))
    except Exception as e:
        logger.warning("Не отправить сообщение %s: %s", user_id, e)

# ====================== ФОНОВЫЕ ЗАДАЧИ ======================

async def check_pending_payments_loop():
    while True:
        try:
            rows = await db_fetchall(
                "SELECT payment_id, user_id FROM pending_payments WHERE status = 'pending'"
            )
            for pid, uid in rows:
                status = await check_yookassa_payment(pid)
                if status == "succeeded":
                    await process_successful_payment(pid, uid)
                elif status == "canceled":
                    await db_execute(
                        "UPDATE pending_payments SET status = 'canceled' WHERE payment_id = ?",
                        (pid,)
                    )
        except Exception as e:
            logger.exception("check_pending_payments: %s", e)
        await asyncio.sleep(30)

async def check_premium_expiration_loop():
    while True:
        try:
            today = datetime.now(tz).date()
            tomorrow = today + timedelta(days=1)
            rows = await db_fetchall(
                "SELECT user_id, end_date FROM users WHERE subscription = 'Premium'"
            )
            for uid, end_str in rows:
                if not end_str:
                    continue
                try:
                    end_date = datetime.strptime(end_str, "%Y-%m-%d").date()
                except ValueError:
                    continue
                if end_date == tomorrow:
                    row = await db_fetchone(
                        "SELECT notified_expire FROM users WHERE user_id = ?", (uid,)
                    )
                    if row and row[0] == 0:
                        try:
                            await bot.send_message(
                                uid,
                                "⏰ <b>Внимание!</b>\n\n"
                                "Ваша подписка Premium заканчивается завтра ({}).\n\n"
                                "Не забудьте продлить!".format(end_str),
                                parse_mode="HTML"
                            )
                            await db_execute(
                                "UPDATE users SET notified_expire = 1 WHERE user_id = ?", (uid,)
                            )
                        except TelegramForbiddenError:
                            await db_execute(
                                "UPDATE users SET status = 'blocked' WHERE user_id = ?", (uid,)
                            )
                        except Exception:
                            pass
                elif end_date < today:
                    await db_execute(
                        "UPDATE users SET subscription = 'Free', end_date = NULL, "
                        "notified_expire = 0 WHERE user_id = ?",
                        (uid,)
                    )
                    try:
                        await bot.send_message(
                            uid,
                            "Ваша подписка Premium истекла. Вы переведены на Free. "
                            "Оформите Premium снова, чтобы получить полный доступ."
                        )
                    except TelegramForbiddenError:
                        await db_execute(
                            "UPDATE users SET status = 'blocked' WHERE user_id = ?", (uid,)
                        )
                    except Exception:
                        pass
        except Exception as e:
            logger.exception("check_premium_expiration: %s", e)
        await asyncio.sleep(3600)

# ====================== КЛАВИАТУРЫ ======================

def main_keyboard(is_admin: bool = False):
    kb = [
        [InlineKeyboardButton(text="👤 Аккаунт", callback_data="account")],
        [InlineKeyboardButton(text="⚽ Матчи", callback_data="matches")],
        [InlineKeyboardButton(text="🚆 Экспресс дня", callback_data="express")],
        [InlineKeyboardButton(text="💬 Чат канала", url="https://t.me/koefchat")],
        [InlineKeyboardButton(text="⭐ Premium", callback_data="premium")],
        [InlineKeyboardButton(text="🛠 Техподдержка", callback_data="support")],
    ]
    if is_admin:
        kb.append([InlineKeyboardButton(text="🔧 Админ-панель", callback_data="admin_panel")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def account_keyboard(sub_type: str, ref_count: int = 0, fav_count: int = 0):
    kb = [
        [InlineKeyboardButton(text="⭐ Избранное ({})".format(fav_count), callback_data="favorites")],
        [InlineKeyboardButton(text="🔗 Реферальная ссылка (приглашено: {})".format(ref_count), callback_data="ref_link")],
    ]
    if sub_type == "Free":
        kb.append([InlineKeyboardButton(text="Купить Premium ({} ₽)".format(PREMIUM_PRICE), callback_data="premium")])
    elif sub_type == "Premium":
        kb.append([InlineKeyboardButton(text="📋 Информация о подписке", callback_data="sub_info")])
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def matches_keyboard(matches):
    groups = {}
    for m in matches:
        key = "{}|{}".format(m[2], m[3])  # country|league
        groups.setdefault(key, []).append(m)
    kb = []
    for key, group in groups.items():
        country, league = key.split("|", 1)
        flag = get_flag(country)
        count = len(group)
        kb.append([InlineKeyboardButton(
            text="{} {} — {} ({})".format(flag, country, league, count),
            callback_data="group_{}".format(key)
        )])
    if not kb:
        kb = [[InlineKeyboardButton(text="Матчей пока нет", callback_data="no_matches")]]
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def back_keyboard(callback_data="matches"):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data=callback_data)]
    ])

def support_categories_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🐛 Баг / ошибка", callback_data="supcat_bug")],
        [InlineKeyboardButton(text="💳 Оплата", callback_data="supcat_pay")],
        [InlineKeyboardButton(text="💡 Предложение", callback_data="supcat_idea")],
        [InlineKeyboardButton(text="❓ Вопрос", callback_data="supcat_q")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")],
    ])

# ====================== STATES ======================

class SupportStates(StatesGroup):
    waiting_category = State()
    get_message = State()

class AdminStates(StatesGroup):
    add_match_time = State()
    add_match_name = State()
    add_country_league = State()
    add_text = State()
    delete_match_choice = State()
    premium_give_id = State()
    premium_remove_id = State()
    reply_support_text = State()
    express_name = State()
    express_country_league = State()
    express_prediction = State()
    express_coef = State()

# ====================== ПОЛЬЗОВАТЕЛЬ ======================

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    args = message.text.split(maxsplit=1)
    referrer = None
    if len(args) > 1 and args[1].startswith("ref_"):
        try:
            referrer = int(args[1].replace("ref_", ""))
        except ValueError:
            pass

    uid = message.from_user.id
    await get_or_create_user(uid, message.from_user.first_name, message.from_user.username or "")

    if referrer and referrer != uid:
        user = await get_or_create_user(uid, message.from_user.first_name, message.from_user.username or "")
        if not user.get("referred_by"):
            await db_execute(
                "UPDATE users SET referred_by = ? WHERE user_id = ?", (referrer, uid)
            )
            # проверяем что у реферера есть запись
            ref_user = await get_or_create_user(referrer)
            if ref_user:
                await add_referral_bonus(referrer)

    await update_streak(uid)

    hour = datetime.now(tz).hour
    if 6 <= hour < 12:
        greeting = "☀️ Доброе утро"
    elif 12 <= hour < 18:
        greeting = "🏙 Привет"
    elif 18 <= hour < 23:
        greeting = "🌙 Вечер добрый"
    else:
        greeting = "🌙 Доброй ночи"

    is_admin = str(uid) in admin_users
    await message.answer(
        "{}, {}!\n\nЯ твой помощник в мире футбола — собираю статистику, "
        "анализирую и предоставляю прогнозы.".format(greeting, message.from_user.first_name),
        reply_markup=main_keyboard(is_admin)
    )

async def add_referral_bonus(referrer_id: int):
    user = await get_or_create_user(referrer_id)
    if not user:
        return
    if user["subscription"] == "Free":
        new_end = (datetime.now(tz) + timedelta(days=3)).strftime("%Y-%m-%d")
        await update_user_subscription(referrer_id, "Premium", new_end)
    else:
        if user["end_date"]:
            try:
                cur = datetime.strptime(user["end_date"], "%Y-%m-%d")
                new_end = (cur + timedelta(days=3)).strftime("%Y-%m-%d")
            except ValueError:
                new_end = (datetime.now(tz) + timedelta(days=3)).strftime("%Y-%m-%d")
        else:
            new_end = (datetime.now(tz) + timedelta(days=3)).strftime("%Y-%m-%d")
        await update_user_subscription(referrer_id, "Premium", new_end)
    try:
        await bot.send_message(
            referrer_id,
            "🎉 По вашей реферальной ссылке зарегистрировался новый пользователь!\n"
            "Вам начислено 3 дня Premium бесплатно!"
        )
    except Exception:
        pass

@dp.callback_query(F.data == "main_menu")
async def to_main_menu(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    is_admin = str(callback.from_user.id) in admin_users
    await callback.message.edit_text("Главное меню:", reply_markup=main_keyboard(is_admin))
    await callback.answer()

@dp.callback_query(F.data == "account")
async def account(callback: types.CallbackQuery):
    uid = callback.from_user.id
    user = await get_or_create_user(uid, callback.from_user.first_name, callback.from_user.username or "")
    await update_streak(uid)

    # считаем рефералов
    ref_rows = await db_fetchall("SELECT user_id FROM users WHERE referred_by = ?", (uid,))
    ref_count = len(ref_rows)

    # считаем избранное
    fav_rows = await db_fetchall("SELECT COUNT(*) FROM favorites WHERE user_id = ?", (uid,))
    fav_count = fav_rows[0][0] if fav_rows else 0

    # считаем просмотры сегодня
    today = datetime.now(tz).date()
    viewed_rows = await db_fetchall(
        "SELECT COUNT(*) FROM viewed_matches WHERE user_id = ? AND viewed_date = ?",
        (uid, str(today))
    )
    viewed_today = viewed_rows[0][0] if viewed_rows else 0

    # статистика
    total_users_row = await db_fetchone("SELECT COUNT(*) FROM users")
    total_users = total_users_row[0] if total_users_row else 0
    premium_row = await db_fetchone("SELECT COUNT(*) FROM users WHERE subscription = 'Premium'")
    premium_users = premium_row[0] if premium_row else 0
    matches_row = await db_fetchone("SELECT COUNT(*) FROM matches")
    total_matches = matches_row[0] if matches_row else 0

    if user["subscription"] == "Premium":
        matches_left = "∞"
        sub_emoji = "⭐"
        sub_text = "Premium"
        end_text = user.get("end_date") or "—"
    else:
        matches_left = max(0, 3 - viewed_today)
        sub_emoji = "🆓"
        sub_text = "Free (бессрочно)"
        end_text = "бессрочно"

    text = (
        "👤 <b>Аккаунт</b>\n\n"
        "🆔 ID: <code>{}</code>\n"
        "👤 Имя: {}\n"
        "💎 Тариф: {} {}\n"
        "📅 С нами с: {}\n"
        "⚽ Матчей осталось сегодня: {}\n"
        "🔥 Дней подряд: {}\n"
        "🏆 Всего матчей в базе: {}\n"
        "👥 Всего пользователей: {}\n"
        "⭐ Premium-пользователей: {}\n"
    )
    text = text.format(
        uid, callback.from_user.first_name, sub_emoji, sub_text,
        user.get("reg_date", "—"), matches_left, user.get("streak_days", 0),
        total_matches, total_users, premium_users
    )
    if user["subscription"] == "Premium":
        text += "📅 Premium до: {}".format(end_text)

    await callback.message.edit_text(
        text, reply_markup=account_keyboard(user["subscription"], ref_count, fav_count),
        parse_mode="HTML"
    )
    await callback.answer()

@dp.callback_query(F.data == "ref_link")
async def show_ref_link(callback: types.CallbackQuery):
    uid = callback.from_user.id
    ref_rows = await db_fetchall("SELECT user_id FROM users WHERE referred_by = ?", (uid,))
    ref_count = len(ref_rows)
    link = "https://t.me/{}?start=ref_{}".format(BOT_USERNAME, uid)
    text = (
        "🔗 <b>Ваша реферальная ссылка</b>\n\n"
        "<code>{}</code>\n\n"
        "🎉 За каждого приглашённого — 3 дня Premium бесплатно!\n"
        "Приглашено: {} чел."
    ).format(link, ref_count)
    await callback.message.edit_text(text, reply_markup=back_keyboard("account"), parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "favorites")
async def show_favorites(callback: types.CallbackQuery):
    uid = callback.from_user.id
    rows = await db_fetchall(
        "SELECT m.id, m.name, m.country, m.match_time FROM matches m "
        "INNER JOIN favorites f ON m.id = f.match_id WHERE f.user_id = ?",
        (uid,)
    )
    if not rows:
        await callback.message.edit_text(
            "⭐ У вас пока нет избранных матчей.",
            reply_markup=back_keyboard("account")
        )
        await callback.answer()
        return
    text = "⭐ <b>Избранные матчи</b>\n\n"
    kb = []
    for row in rows:
        mid, name, country, mtime = row
        flag = get_flag(country)
        label = name
        if mtime:
            label = "🕒 {} | {}".format(mtime, name)
        text += "{} {}\n".format(flag, label)
        kb.append([InlineKeyboardButton(text=label, callback_data="match_{}".format(mid))])
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="account")])
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "matches")
async def show_leagues(callback: types.CallbackQuery):
    matches = await db_fetchall("SELECT * FROM matches ORDER BY country, league")
    await callback.message.edit_text("📋 Выберите группу (страна — лига):", reply_markup=matches_keyboard(matches))
    await callback.answer()

@dp.callback_query(F.data.startswith("group_"))
async def show_group_matches(callback: types.CallbackQuery):
    key = callback.data.replace("group_", "", 1)
    parts = key.split("|", 1)
    if len(parts) < 2:
        await callback.answer("Ошибка", show_alert=True)
        return
    country, league = parts
    rows = await db_fetchall(
        "SELECT id, name, match_time FROM matches WHERE country = ? AND league = ? ORDER BY match_time",
        (country, league)
    )
    if not rows:
        await callback.message.edit_text("В этой группе матчей нет.", reply_markup=back_keyboard("matches"))
        await callback.answer()
        return
    flag = get_flag(country)
    text = "🏟 {} {} — {}\n\n".format(flag, country, league)
    kb = []
    for row in rows:
        mid, name, mtime = row
        label = name
        if mtime:
            label = "🕒 {} | {}".format(mtime, name)
        kb.append([InlineKeyboardButton(text=label, callback_data="match_{}".format(mid))])
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="matches")])
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await callback.answer()

@dp.callback_query(F.data.startswith("match_"))
async def show_match_details(callback: types.CallbackQuery):
    mid = int(callback.data.replace("match_", ""))
    row = await db_fetchone("SELECT id, name, country, league, match_time, text FROM matches WHERE id = ?", (mid,))
    if not row:
        await callback.answer("Матч не найден", show_alert=True)
        return

    allowed = await check_match_limit(callback.from_user.id, mid)
    if not allowed:
        await callback.answer("❌ Лимит матчей исчерпан (3 в день). Купите Premium.", show_alert=True)
        return

    _, name, country, league, mtime, mtext = row
    flag = get_flag(country)
    text = "⚽ <b>{}</b>\n".format(name)
    if mtime:
        text += "🕒 Время: {}\n".format(mtime)
    text += "🌍 {} Страна: {}\n".format(flag, country)
    text += "🏆 Лига: {}\n\n".format(league)
    text += mtext or ""

    # проверяем избранное
    fav_row = await db_fetchone("SELECT 1 FROM favorites WHERE user_id = ? AND match_id = ?", (callback.from_user.id, mid))
    fav_text = "💔 Убрать из избранного" if fav_row else "⭐ В избранное"
    fav_cb = "unfav_{}".format(mid) if fav_row else "fav_{}".format(mid)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=fav_text, callback_data=fav_cb)],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="matches")],
    ])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data.startswith("fav_"))
async def add_favorite(callback: types.CallbackQuery):
    mid = int(callback.data.replace("fav_", ""))
    uid = callback.from_user.id
    now = datetime.now(tz).strftime("%Y-%m-%d %H:%M")
    await db_execute(
        "INSERT OR IGNORE INTO favorites (user_id, match_id, added_at) VALUES (?, ?, ?)",
        (uid, mid, now)
    )
    await callback.answer("⭐ Добавлено в избранное!")
    # обновляем сообщение
    await show_match_details(callback)

@dp.callback_query(F.data.startswith("unfav_"))
async def remove_favorite(callback: types.CallbackQuery):
    mid = int(callback.data.replace("unfav_", ""))
    uid = callback.from_user.id
    await db_execute("DELETE FROM favorites WHERE user_id = ? AND match_id = ?", (uid, mid))
    await callback.answer("💔 Убрано из избранного")
    await show_match_details(callback)

@dp.callback_query(F.data == "express")
async def show_express(callback: types.CallbackQuery):
    user = await get_or_create_user(callback.from_user.id)
    picks = await db_fetchall("SELECT name, country, league, prediction, coef FROM express_picks ORDER BY id")
    if not picks:
        await callback.message.edit_text(
            "🚆 Экспресс дня пока не сформирован. Загляните позже!",
            reply_markup=back_keyboard("main_menu")
        )
        await callback.answer()
        return
    if user["subscription"] != "Premium":
        text = "🚆 <b>Экспресс дня</b>\n\n"
        text += "🔒 Полный экспресс доступен только по Premium!\n\n"
        text += "⭐ Купите Premium и получите доступ ко всем экспрессам и матчам без ограничений."
        await callback.message.edit_text(text, reply_markup=back_keyboard("main_menu"), parse_mode="HTML")
        await callback.answer()
        return

    total_coef = 1.0
    lines = []
    for p in picks:
        pname, pcountry, pleague, ppred, pcoef = p
        flag = get_flag(pcountry or "")
        line = "⚽ {}\n".format(pname)
        line += "{} {} — {}\n".format(flag, pcountry or "", pleague or "")
        line += "💡 Прогноз: {}\n".format(ppred or "")
        line += "💰 Коэффициент: {}".format(pcoef or "")
        lines.append(line)
        try:
            total_coef *= float(pcoef)
        except (ValueError, TypeError):
            pass

    text = "🚆 <b>Экспресс дня</b>\n\n"
    text += "\n\n───────────────\n\n".join(lines)
    text += "\n\n───────────────\n"
    text += "👑 <b>Общий коэффициент: {:.2f}</b>".format(total_coef)
    await callback.message.edit_text(text, reply_markup=back_keyboard("main_menu"), parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "premium")
async def premium(callback: types.CallbackQuery):
    uid = callback.from_user.id
    result = await create_yookassa_payment(uid, PREMIUM_PRICE)
    if result and result.get("confirmation_url"):
        url = result["confirmation_url"]
        pid = result["payment_id"]
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💳 Оплатить {} ₽".format(PREMIUM_PRICE), url=url)],
            [InlineKeyboardButton(text="✅ Я оплатил — проверить", callback_data="checkpay_{}".format(pid))],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="account")],
        ])
        await callback.message.edit_text(
            "⭐ <b>Premium — полный доступ</b>\n\n"
            "• Безлимитные матчи\n"
            "• Доступ к экспрессам\n"
            "• Без ограничений\n\n"
            "Цена: {} ₽ в месяц\n\n"
            "Нажмите кнопку ниже для оплаты.".format(PREMIUM_PRICE),
            reply_markup=kb,
            parse_mode="HTML"
        )
    else:
        await callback.message.edit_text(
            "❌ Не удалось создать платёж. Попробуйте позже или обратитесь в техподдержку.",
            reply_markup=back_keyboard("account")
        )
    await callback.answer()

@dp.callback_query(F.data.startswith("checkpay_"))
async def check_payment(callback: types.CallbackQuery):
    pid = callback.data.replace("checkpay_", "")
    status = await check_yookassa_payment(pid)
    if status == "succeeded":
        row = await db_fetchone("SELECT user_id FROM pending_payments WHERE payment_id = ?", (pid,))
        if row:
            await process_successful_payment(pid, row[0])
        await callback.message.edit_text(
            "✅ Оплата подтверждена! Premium активирован.",
            reply_markup=back_keyboard("main_menu")
        )
    elif status == "pending" or status == "waiting_for_capture":
        await callback.answer("⏳ Платёж ещё обрабатывается. Подождите немного.", show_alert=True)
    elif status == "canceled":
        await callback.answer("❌ Платёж отменён.", show_alert=True)
    else:
        await callback.answer("⚠️ Не удалось проверить статус. Попробуйте позже.", show_alert=True)

@dp.callback_query(F.data == "sub_info")
async def sub_info(callback: types.CallbackQuery):
    user = await get_or_create_user(callback.from_user.id)
    end_date = user.get("end_date", "—")
    text = "⭐ <b>Информация о подписке</b>\n\nТариф: Premium\nДействует до: {}".format(end_date)
    await callback.message.edit_text(text, reply_markup=back_keyboard("account"), parse_mode="HTML")
    await callback.answer()

# ====================== ТЕХПОДДЕРЖКА ======================

@dp.callback_query(F.data == "support")
async def support_start(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "🛠 <b>Техподдержка</b>\n\nВыберите категорию обращения:",
        reply_markup=support_categories_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("supcat_"))
async def support_choose_cat(callback: types.CallbackQuery, state: FSMContext):
    cat = callback.data.replace("supcat_", "")
    cat_text = SUPPORT_CATEGORIES.get(cat, "Вопрос")
    await state.update_data(sup_cat=cat)
    await callback.message.edit_text(
        "{}\n\nНапишите ваше сообщение (одним сообщением):".format(cat_text),
        reply_markup=back_keyboard("support")
    )
    await state.set_state(SupportStates.get_message)
    await callback.answer()

@dp.message(SupportStates.get_message)
async def handle_support(message: types.Message, state: FSMContext):
    data = await state.get_data()
    cat = data.get("sup_cat", "q")
    cat_text = SUPPORT_CATEGORIES.get(cat, "Вопрос")
    uid = message.chat.id
    user_name = message.from_user.full_name or "Без имени"
    text_msg = message.text
    now = datetime.now(tz).strftime("%Y-%m-%d %H:%M")

    # создаём тред если нет
    thread = await db_fetchone("SELECT thread_id FROM support_threads WHERE thread_id = ?", (uid,))
    if not thread:
        await db_execute(
            "INSERT INTO support_threads (thread_id, user_id, user_name, category, created_at) VALUES (?, ?, ?, ?, ?)",
            (uid, uid, user_name, cat, now)
        )

    await db_execute(
        "INSERT INTO support_messages (thread_id, sender, text, created_at) VALUES (?, 'user', ?, ?)",
        (uid, text_msg, now)
    )

    try:
        await bot.send_message(
            ADMIN_ID,
            "📩 <b>Новое сообщение в техподдержку!</b>\n\n"
            "🏷 Категория: {}\n"
            "👤 От: {}\n"
            "ID: <code>{}</code>\n"
            "📝 Текст:\n{}".format(cat_text, user_name, uid, text_msg),
            parse_mode="HTML"
        )
    except Exception:
        pass

    await message.answer("✅ Ваше сообщение отправлено Администрации!", reply_markup=main_keyboard(str(uid) in admin_users))
    await state.clear()

# ====================== АДМИН ПАНЕЛЬ ======================

@dp.message(Command("admin"))
async def admin_panel_cmd(message: types.Message, state: FSMContext):
    if str(message.from_user.id) not in admin_users:
        await message.answer("❌ Нет доступа!")
        return
    await state.clear()
    await message.answer("Админ-панель", reply_markup=admin_panel_keyboard())

def admin_panel_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить матч", callback_data="add_match_start")],
        [InlineKeyboardButton(text="🗑 Удалить матч / Очистить все", callback_data="delete_match_menu")],
        [InlineKeyboardButton(text="🚆 Экспресс дня", callback_data="express_admin")],
        [InlineKeyboardButton(text="💰 Управление Premium", callback_data="premium_admin_menu")],
        [InlineKeyboardButton(text="🛠 Сообщения поддержки", callback_data="support_admin_menu")],
        [InlineKeyboardButton(text="📦 Бэкап БД", callback_data="backup_db")],
        [InlineKeyboardButton(text="📋 Логи админа", callback_data="admin_logs")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")]
    ])

@dp.callback_query(F.data == "admin_panel")
async def admin_panel_cb(callback: types.CallbackQuery, state: FSMContext):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    await state.clear()
    await callback.message.edit_text("Админ-панель", reply_markup=admin_panel_keyboard())
    await callback.answer()

# --- Добавление матча ---

@dp.callback_query(F.data == "add_match_start")
async def add_match_start(callback: types.CallbackQuery, state: FSMContext):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    await callback.message.edit_text(
        "Шаг 1/4: Введите время матча в формате ЧЧ:ММ (например: 18:30).\n"
        "Если время неизвестно — введите «-»",
        reply_markup=back_keyboard("admin_panel")
    )
    await state.set_state(AdminStates.add_match_time)
    await callback.answer()

@dp.message(AdminStates.add_match_time)
async def add_match_time(message: types.Message, state: FSMContext):
    t = message.text.strip()
    if t != "-":
        parts = t.split(":")
        if len(parts) != 2:
            await message.answer("Нужно в формате ЧЧ:ММ (например: 18:30). Попробуйте ещё раз:")
            return
        try:
            h, m = int(parts[0]), int(parts[1])
            if not (0 <= h <= 23 and 0 <= m <= 59):
                raise ValueError
        except ValueError:
            await message.answer("Некорректное время. ЧЧ:ММ, например 18:30:")
            return
    else:
        t = ""
    await state.update_data(match_time=t)
    await message.answer("Шаг 2/4: Введите название команд (например: Спартак — Зенит):", reply_markup=back_keyboard("admin_panel"))
    await state.set_state(AdminStates.add_match_name)

@dp.message(AdminStates.add_match_name)
async def add_match_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await message.answer("Шаг 3/4: Страна и лига (через пробел, например: Россия РПЛ):", reply_markup=back_keyboard("admin_panel"))
    await state.set_state(AdminStates.add_country_league)

@dp.message(AdminStates.add_country_league)
async def add_country_league(message: types.Message, state: FSMContext):
    parts = message.text.strip().split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Нужно ввести страну и лигу через пробел. Попробуйте ещё раз:")
        return
    country, league = parts[0], parts[1]
    await state.update_data(country=country, league=league)
    await message.answer("Шаг 4/4: Введите полный текст матча (одним сообщением):", reply_markup=back_keyboard("admin_panel"))
    await state.set_state(AdminStates.add_text)

@dp.message(AdminStates.add_text)
async def add_text(message: types.Message, state: FSMContext):
    data = await state.get_data()
    now = datetime.now(tz).strftime("%Y-%m-%d %H:%M")
    await db_execute(
        "INSERT INTO matches (name, country, league, match_time, text, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (data["name"], data["country"], data["league"], data.get("match_time", ""), message.text, now)
    )
    await log_admin_action(message.from_user.id, "add_match", data["name"])
    await message.answer("✅ Матч добавлен: {}".format(data["name"]), reply_markup=main_keyboard(True))
    await state.clear()

# --- Удаление матча ---

@dp.callback_query(F.data == "delete_match_menu")
async def delete_match_menu(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    rows = await db_fetchall("SELECT id, name, country, match_time FROM matches ORDER BY id")
    if not rows:
        await callback.message.edit_text("Матчей нет.", reply_markup=back_keyboard("admin_panel"))
        await callback.answer()
        return
    kb = []
    for row in rows:
        mid, name, country, mtime = row
        label = name
        if mtime:
            label = "🕒 {} | {}".format(mtime, name)
        kb.append([InlineKeyboardButton(text="🗑 {} ({})".format(label, country), callback_data="delmatch_{}".format(mid))])
    kb.append([InlineKeyboardButton(text="🗑 Очистить все", callback_data="delall_matches")])
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")])
    await callback.message.edit_text("Выберите матч для удаления:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await callback.answer()

@dp.callback_query(F.data.startswith("delmatch_"))
async def delete_one_match(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    mid = int(callback.data.replace("delmatch_", ""))
    row = await db_fetchone("SELECT name FROM matches WHERE id = ?", (mid,))
    if row:
        await db_execute("DELETE FROM matches WHERE id = ?", (mid,))
        await db_execute("DELETE FROM viewed_matches WHERE match_id = ?", (mid,))
        await db_execute("DELETE FROM favorites WHERE match_id = ?", (mid,))
        await log_admin_action(callback.from_user.id, "delete_match", row[0])
        await callback.message.edit_text("✅ Удалён: {}".format(row[0]), reply_markup=back_keyboard("admin_panel"))
    else:
        await callback.answer("Не найден", show_alert=True)
    await callback.answer()

@dp.callback_query(F.data == "delall_matches")
async def delete_all_matches(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    await db_execute("DELETE FROM matches")
    await db_execute("DELETE FROM viewed_matches")
    await db_execute("DELETE FROM favorites")
    await log_admin_action(callback.from_user.id, "delete_all_matches", "")
    await callback.message.edit_text("✅ Все матчи удалены.", reply_markup=back_keyboard("admin_panel"))
    await callback.answer()

# --- Управление Premium ---

@dp.callback_query(F.data == "premium_admin_menu")
async def premium_admin_menu(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ Выдать Premium по ID", callback_data="give_premium")],
        [InlineKeyboardButton(text="🚫 Снять Premium по ID", callback_data="remove_premium")],
        [InlineKeyboardButton(text="⭐ Premium всем Free", callback_data="give_all_premium_menu")],
        [InlineKeyboardButton(text="🚫 Снять со всех Premium", callback_data="remove_all_premium")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")]
    ])
    await callback.message.edit_text("💰 Управление Premium:", reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data == "give_premium")
async def give_premium(callback: types.CallbackQuery, state: FSMContext):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    await callback.message.edit_text("Введите ID пользователя для выдачи Premium:", reply_markup=back_keyboard("premium_admin_menu"))
    await state.set_state(AdminStates.premium_give_id)
    await callback.answer()

@dp.message(AdminStates.premium_give_id)
async def do_give_premium(message: types.Message, state: FSMContext):
    try:
        uid = int(message.text.strip())
    except ValueError:
        await message.answer("Некорректный ID.")
        await state.clear()
        return
    row = await db_fetchone("SELECT user_id FROM users WHERE user_id = ?", (uid,))
    if not row:
        await message.answer("Пользователь не найден.")
        await state.clear()
        return
    end_date = (datetime.now(tz) + timedelta(days=30)).strftime("%Y-%m-%d")
    await update_user_subscription(uid, "Premium", end_date)
    await log_admin_action(message.from_user.id, "give_premium", str(uid))
    try:
        await bot.send_message(uid, "🎉 Вам выдан Premium на 30 дней!")
    except Exception:
        pass
    await message.answer("✅ Premium выдан пользователю {} на 30 дней.".format(uid), reply_markup=main_keyboard(True))
    await state.clear()

@dp.callback_query(F.data == "remove_premium")
async def remove_premium(callback: types.CallbackQuery, state: FSMContext):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    await callback.message.edit_text("Введите ID пользователя для снятия Premium:", reply_markup=back_keyboard("premium_admin_menu"))
    await state.set_state(AdminStates.premium_remove_id)
    await callback.answer()

@dp.message(AdminStates.premium_remove_id)
async def do_remove_premium(message: types.Message, state: FSMContext):
    try:
        uid = int(message.text.strip())
    except ValueError:
        await message.answer("Некорректный ID.")
        await state.clear()
        return
    row = await db_fetchone("SELECT user_id FROM users WHERE user_id = ?", (uid,))
    if not row:
        await message.answer("Пользователь не найден.")
        await state.clear()
        return
    await update_user_subscription(uid, "Free", None)
    await log_admin_action(message.from_user.id, "remove_premium", str(uid))
    try:
        await bot.send_message(uid, "Ваша подписка Premium снята. Вы переведены на Free.")
    except Exception:
        pass
    await message.answer("✅ Premium снят с пользователя {}.".format(uid), reply_markup=main_keyboard(True))
    await state.clear()

@dp.callback_query(F.data == "give_all_premium_menu")
async def give_all_premium_menu(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="1 месяц (30 дней)", callback_data="giveall_30")],
        [InlineKeyboardButton(text="3 месяца (90 дней)", callback_data="giveall_90")],
        [InlineKeyboardButton(text="6 месяцев (180 дней)", callback_data="giveall_180")],
        [InlineKeyboardButton(text="1 год (365 дней)", callback_data="giveall_365")],
        [InlineKeyboardButton(text="♾ Навсегда", callback_data="giveall_forever")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="premium_admin_menu")]
    ])
    await callback.message.edit_text("⭐ Выдать Premium всем Free-пользователям.\nВыберите срок:", reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data.startswith("giveall_"))
async def give_all_premium(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    param = callback.data.replace("giveall_", "")
    if param == "forever":
        end_date = "9999-12-31"
        days_text = "навсегда"
    else:
        days = int(param)
        end_date = (datetime.now(tz) + timedelta(days=days)).strftime("%Y-%m-%d")
        days_text = "{} дней".format(days)

    rows = await db_fetchall("SELECT user_id FROM users WHERE subscription = 'Free'")
    count = 0
    for row in rows:
        uid = row[0]
        await update_user_subscription(uid, "Premium", end_date)
        count += 1
        try:
            await bot.send_message(uid, "🎉 Вам выдан Premium ({})!".format(days_text))
        except TelegramForbiddenError:
            await db_execute("UPDATE users SET status = 'blocked' WHERE user_id = ?", (uid,))
        except Exception:
            pass

    await log_admin_action(callback.from_user.id, "give_all_premium", days_text)
    await callback.message.edit_text(
        "✅ Premium выдан {} Free-пользователям ({}).".format(count, days_text),
        reply_markup=back_keyboard("admin_panel")
    )
    await callback.answer()

@dp.callback_query(F.data == "remove_all_premium")
async def remove_all_premium(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    rows = await db_fetchall("SELECT user_id FROM users WHERE subscription = 'Premium'")
    count = len(rows)
    for row in rows:
        uid = row[0]
        await update_user_subscription(uid, "Free", None)
        try:
            await bot.send_message(uid, "Ваша подписка Premium снята. Вы переведены на Free.")
        except TelegramForbiddenError:
            await db_execute("UPDATE users SET status = 'blocked' WHERE user_id = ?", (uid,))
        except Exception:
            pass
    await log_admin_action(callback.from_user.id, "remove_all_premium", "")
    await callback.message.edit_text(
        "✅ Premium снят с {} пользователей.".format(count),
        reply_markup=back_keyboard("admin_panel")
    )
    await callback.answer()

# --- Техподдержка админка ---

@dp.callback_query(F.data == "support_admin_menu")
async def support_admin_menu(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    rows = await db_fetchall("SELECT thread_id, user_name, category, created_at FROM support_threads ORDER BY created_at DESC")
    if not rows:
        await callback.message.edit_text("Сообщений поддержки нет.", reply_markup=back_keyboard("admin_panel"))
        await callback.answer()
        return
    kb = []
    for row in rows:
        tid, uname, cat, created = row
        cat_emoji = SUPPORT_CATEGORIES.get(cat, "❓ Вопрос")
        kb.append([InlineKeyboardButton(
            text="{} | {} [{}]".format(cat_emoji, uname, created[:10]),
            callback_data="thread_{}".format(tid)
        )])
    kb.append([InlineKeyboardButton(text="🗑 Очистить все", callback_data="clear_all_support")])
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")])
    await callback.message.edit_text("🛠 Сообщения поддержки:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await callback.answer()

@dp.callback_query(F.data.startswith("thread_"))
async def view_thread(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    tid = int(callback.data.replace("thread_", ""))
    msgs = await db_fetchall(
        "SELECT sender, text, created_at FROM support_messages WHERE thread_id = ? ORDER BY id", (tid,)
    )
    if not msgs:
        await callback.answer("Тред не найден", show_alert=True)
        return
    text = ""
    for sender, mtext, created in msgs:
        sender_label = "👤 Пользователь" if sender == "user" else "🏢 Админ"
        text += "[{}] {}\n{}\n\n".format(created, sender_label, mtext)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Ответить", callback_data="reply_{}".format(tid))],
        [InlineKeyboardButton(text="🗑 Очистить", callback_data="clear_thread_{}".format(tid))],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="support_admin_menu")]
    ])
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data.startswith("reply_"))
async def reply_start(callback: types.CallbackQuery, state: FSMContext):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    tid = int(callback.data.replace("reply_", ""))
    await state.update_data(reply_tid=tid)
    await callback.message.edit_text("Введите текст ответа пользователю:", reply_markup=back_keyboard("support_admin_menu"))
    await state.set_state(AdminStates.reply_support_text)
    await callback.answer()

@dp.message(AdminStates.reply_support_text)
async def do_reply(message: types.Message, state: FSMContext):
    data = await state.get_data()
    tid = data.get("reply_tid")
    now = datetime.now(tz).strftime("%Y-%m-%d %H:%M")
    await db_execute(
        "INSERT INTO support_messages (thread_id, sender, text, created_at) VALUES (?, 'admin', ?, ?)",
        (tid, message.text, now)
    )
    try:
        await bot.send_message(tid, "💬 <b>Ответ техподдержки:</b>\n\n{}".format(message.text), parse_mode="HTML")
    except Exception:
        pass
    await log_admin_action(message.from_user.id, "reply_support", str(tid))
    await message.answer("✅ Ответ отправлен пользователю.", reply_markup=main_keyboard(True))
    await state.clear()

@dp.callback_query(F.data.startswith("clear_thread_"))
async def clear_thread(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    tid = int(callback.data.replace("clear_thread_", ""))
    await db_execute("DELETE FROM support_messages WHERE thread_id = ?", (tid,))
    await db_execute("DELETE FROM support_threads WHERE thread_id = ?", (tid,))
    await callback.message.edit_text("✅ Переписка очищена.", reply_markup=back_keyboard("support_admin_menu"))
    await callback.answer()

@dp.callback_query(F.data == "clear_all_support")
async def clear_all_support(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    await db_execute("DELETE FROM support_messages")
    await db_execute("DELETE FROM support_threads")
    await callback.message.edit_text("✅ Все переписки очищены.", reply_markup=back_keyboard("admin_panel"))
    await callback.answer()

# --- Экспресс админка ---

@dp.callback_query(F.data == "express_admin")
async def express_admin(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    picks = await db_fetchall("SELECT name, country, league, prediction, coef FROM express_picks ORDER BY id")
    text = "🚆 <b>Управление экспрессом дня</b>\n\n"
    if picks:
        total_coef = 1.0
        lines = []
        for p in picks:
            pname, pcountry, pleague, ppred, pcoef = p
            flag = get_flag(pcountry or "")
            line = "⚽ {}\n".format(pname)
            line += "{} {} — {}\n".format(flag, pcountry or "", pleague or "")
            line += "💡 Прогноз: {}\n".format(ppred or "")
            line += "💰 Коэффициент: {}".format(pcoef or "")
            lines.append(line)
            try:
                total_coef *= float(pcoef)
            except (ValueError, TypeError):
                pass
        text += "\n\n───────────────\n\n".join(lines)
        text += "\n\n───────────────\n"
        text += "👑 <b>Общий: {:.2f}</b>".format(total_coef)
    else:
        text += "Экспресс пуст.\n"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить матч в экспресс", callback_data="express_add")],
        [InlineKeyboardButton(text="🗑 Очистить экспресс", callback_data="express_clear")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")]
    ])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "express_add")
async def express_add(callback: types.CallbackQuery, state: FSMContext):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    await callback.message.edit_text(
        "Шаг 1/4: Введите название команд (например: Спартак — Зенит):",
        reply_markup=back_keyboard("express_admin")
    )
    await state.set_state(AdminStates.express_name)
    await callback.answer()

@dp.message(AdminStates.express_name)
async def express_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await message.answer("Шаг 2/4: Страна и лига (через пробел, например: Россия РПЛ):", reply_markup=back_keyboard("express_admin"))
    await state.set_state(AdminStates.express_country_league)

@dp.message(AdminStates.express_country_league)
async def express_country_league(message: types.Message, state: FSMContext):
    parts = message.text.strip().split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Нужно страну и лигу через пробел. Попробуйте ещё раз:")
        return
    await state.update_data(country=parts[0], league=parts[1])
    await message.answer("Шаг 3/4: Введите прогноз (например: П1 или ТБ 2.5):", reply_markup=back_keyboard("express_admin"))
    await state.set_state(AdminStates.express_prediction)

@dp.message(AdminStates.express_prediction)
async def express_prediction(message: types.Message, state: FSMContext):
    await state.update_data(prediction=message.text.strip())
    await message.answer("Шаг 4/4: Введите коэффициент (например: 1.85):", reply_markup=back_keyboard("express_admin"))
    await state.set_state(AdminStates.express_coef)

@dp.message(AdminStates.express_coef)
async def express_coef(message: types.Message, state: FSMContext):
    data = await state.get_data()
    now = datetime.now(tz).strftime("%Y-%m-%d %H:%M")
    await db_execute(
        "INSERT INTO express_picks (name, country, league, prediction, coef, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (data["name"], data["country"], data["league"], data["prediction"], message.text.strip(), now)
    )
    await log_admin_action(message.from_user.id, "add_express", data["name"])
    await message.answer(
        "✅ Матч добавлен в экспресс: {} (кф. {})".format(data["name"], message.text.strip()),
        reply_markup=main_keyboard(True)
    )
    await state.clear()

@dp.callback_query(F.data == "express_clear")
async def express_clear(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    await db_execute("DELETE FROM express_picks")
    await log_admin_action(callback.from_user.id, "clear_express", "")
    await callback.message.edit_text("✅ Экспресс очищен.", reply_markup=back_keyboard("express_admin"))
    await callback.answer()

# --- Бэкап БД ---

@dp.callback_query(F.data == "backup_db")
async def backup_db(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    import shutil
    backup_name = "bot_backup_{}.db".format(datetime.now(tz).strftime("%Y%m%d_%H%M%S"))
    shutil.copy2(DB_FILE, backup_name)
    from aiogram.types import FSInputFile
    doc = FSInputFile(backup_name)
    try:
        await callback.message.answer_document(doc, caption="📦 Бэкап базы данных: {}".format(backup_name))
    except Exception as e:
        await callback.message.answer("Ошибка бэкапа: {}".format(e))
    os.remove(backup_name)
    await callback.answer()

# --- Логи админа ---

@dp.callback_query(F.data == "admin_logs")
async def admin_logs(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    rows = await db_fetchall(
        "SELECT admin_id, action, details, created_at FROM admin_log ORDER BY id DESC LIMIT 20"
    )
    if not rows:
        await callback.message.edit_text("Логов пока нет.", reply_markup=back_keyboard("admin_panel"))
        await callback.answer()
        return
    text = "📋 <b>Последние действия админа</b>\n\n"
    for admin_id, action, details, created in rows:
        text += "[{}] {} ({}): {}\n".format(created, action, admin_id, details or "")
    if len(text) > 4000:
        text = text[:4000] + "\n... (обрезано)"
    await callback.message.edit_text(text, reply_markup=back_keyboard("admin_panel"), parse_mode="HTML")
    await callback.answer()

# --- Прочее ---

@dp.callback_query(F.data == "no_matches")
async def no_matches(callback: types.CallbackQuery):
    await callback.answer("Матчей пока нет", show_alert=True)

# --- Тест оплаты ---

@dp.message(Command("testpay"))
async def cmd_testpay(message: types.Message):
    if str(message.from_user.id) not in admin_users:
        return
    result = await create_yookassa_payment(message.from_user.id, 10.0)
    if result:
        await message.answer(
            "✅ Платёж создан!\nID: {}\nСсылка: {}".format(
                result["payment_id"], result.get("confirmation_url", "нет")
            )
        )
    else:
        await message.answer("❌ Не удалось создать платёж. Проверьте логи.")

# ====================== ЗАПУСК ======================

async def main():
    init_db()
    asyncio.create_task(check_pending_payments_loop())
    asyncio.create_task(check_premium_expiration_loop())
    logger.info("Бот запущен")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
