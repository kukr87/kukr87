import asyncio
import json
import os
import base64
import logging
import aiohttp
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import aiosqlite
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ====================== НАСТРОЙКИ ======================
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
BOT_USERNAME = os.getenv("BOT_USERNAME", "koefiibot")

YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID", "")
YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY", "")

# API-Football (https://www.api-football.com/) — бесплатный план: 100 запросов/день
API_FOOTBALL_KEY = os.getenv("API_FOOTBALL_KEY", "")
API_FOOTBALL_HOST = "v3.football.api-sports.io"

PREMIUM_PRICE = 300.0
TZ = ZoneInfo("Europe/Moscow")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("bot")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
admin_users = {str(ADMIN_ID)}

DB_PATH = "bot.db"

COUNTRY_FLAGS = {
    "Россия": "🇷🇺", "Англия": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "Испания": "🇪🇸", "Италия": "🇮🇹",
    "Германия": "🇩🇪", "Франция": "🇫🇷", "Португалия": "🇵🇹", "Турция": "🇹🇷",
    "Сербия": "🇷🇸", "Казахстан": "🇰🇿", "Украина": "🇺🇦", "Беларусь": "🇧🇾",
    "США": "🇺🇸", "Бразилия": "🇧🇷", "Аргентина": "🇦🇷", "Австрия": "🇦🇹",
    "Бельгия": "🇧🇪", "Болгария": "🇧🇬", "Венгрия": "🇭🇺", "Греция": "🇬🇷",
    "Дания": "🇩🇰", "Ирландия": "🇮🇪", "Нидерланды": "🇳🇱", "Норвегия": "🇳🇴",
    "Польша": "🇵🇱", "Хорватия": "🇭🇷", "Швеция": "🇸🇪", "Швейцария": "🇨🇭",
    "Шотландия": "🏴󠁧󠁢󠁳󠁣󠁴󠁿", "Чехия": "🇨🇿", "Румыния": "🇷🇴",
    "Spain": "🇪🇸", "England": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "Italy": "🇮🇹", "Germany": "🇩🇪",
    "France": "🇫🇷", "Portugal": "🇵🇹", "Turkey": "🇹🇷", "Brazil": "🇧🇷",
    "Argentina": "🇦🇷", "Netherlands": "🇳🇱", "Belgium": "🇧🇪", "Croatia": "🇭🇷",
    "Russia": "🇷🇺", "Ukraine": "🇺🇦", "Denmark": "🇩🇰", "Sweden": "🇸🇪",
    "Norway": "🇳🇴", "Poland": "🇵🇱", "Switzerland": "🇨🇭", "Austria": "🇦🇹",
    "Greece": "🇬🇷", "Romania": "🇷🇴", "Czech-Republic": "🇨🇿", "Hungary": "🇭🇺",
    "Bulgaria": "🇧🇬", "Serbia": "🇷🇸", "USA": "🇺🇸", "Ireland": "🇮🇪",
    "Scotland": "🏴󠁧󠁢󠁳󠁣󠁴󠁿", "Wales": "🏴󠁧󠁢󠁷󠁬󠁳󠁿",
}

def get_flag(country):
    return COUNTRY_FLAGS.get(country, "🏳️")


# ====================== БАЗА ДАННЫХ ======================

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT DEFAULT '',
                first_name TEXT DEFAULT '',
                subscription TEXT DEFAULT 'Free',
                end_date TEXT,
                reg_date TEXT,
                referred_by INTEGER,
                last_check_date TEXT,
                streak_days INTEGER DEFAULT 0,
                last_active_date TEXT,
                status TEXT DEFAULT 'active'
            );
            CREATE TABLE IF NOT EXISTS matches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                country TEXT,
                league TEXT,
                match_time TEXT,
                text TEXT,
                odds TEXT,
                api_prediction TEXT,
                api_fixture_id INTEGER,
                created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS viewed_matches (
                user_id INTEGER,
                match_id INTEGER,
                viewed_date TEXT,
                PRIMARY KEY (user_id, match_id)
            );
            CREATE TABLE IF NOT EXISTS favorites (
                user_id INTEGER,
                match_id INTEGER,
                added_at TEXT,
                PRIMARY KEY (user_id, match_id)
            );
            CREATE TABLE IF NOT EXISTS express_picks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT, country TEXT, league TEXT,
                prediction TEXT, coef TEXT, created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS support_threads (
                thread_id INTEGER PRIMARY KEY,
                category TEXT, user_name TEXT, created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS support_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                thread_id INTEGER,
                sender TEXT, text TEXT, created_at TEXT,
                FOREIGN KEY (thread_id) REFERENCES support_threads(thread_id)
            );
            CREATE TABLE IF NOT EXISTS pending_payments (
                payment_id TEXT PRIMARY KEY,
                user_id INTEGER,
                amount REAL,
                created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS admin_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER, action TEXT, created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS referrals (
                referrer_id INTEGER, referred_id INTEGER,
                created_at TEXT,
                PRIMARY KEY (referrer_id, referred_id)
            );
        """)
        await db.commit()


async def get_user(user_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = await cur.fetchone()
        if not row:
            now = datetime.now(TZ)
            await db.execute(
                "INSERT INTO users (user_id, subscription, reg_date, streak_days, last_active_date, status) "
                "VALUES (?, 'Free', ?, 0, ?, 'active')",
                (user_id, now.strftime("%Y-%m-%d"), now.strftime("%Y-%m-%d"))
            )
            await db.commit()
            return {
                "user_id": user_id, "subscription": "Free", "end_date": None,
                "reg_date": now.strftime("%Y-%m-%d"), "streak_days": 0, "status": "active"
            }
        return dict(row)


async def update_user(user_id: int, **kwargs):
    async with aiosqlite.connect(DB_PATH) as db:
        sets = ", ".join(f"{k} = ?" for k in kwargs)
        vals = list(kwargs.values()) + [user_id]
        await db.execute(f"UPDATE users SET {sets} WHERE user_id = ?", vals)
        await db.commit()


async def log_admin(admin_id: int, action: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO admin_log (admin_id, action, created_at) VALUES (?, ?, ?)",
            (admin_id, action, datetime.now(TZ).strftime("%Y-%m-%d %H:%M"))
        )
        await db.commit()


# ====================== API-FOOTBALL ======================

async def fetch_api_football(endpoint: str, params: dict = None):
    """Базовый запрос к API-Football v3."""
    if not API_FOOTBALL_KEY:
        logger.warning("API_FOOTBALL_KEY не задан — автопарсинг недоступен")
        return None

    url = f"https://{API_FOOTBALL_HOST}/{endpoint}"
    headers = {
        "x-apisports-key": API_FOOTBALL_KEY,
        "x-rapidapi-host": API_FOOTBALL_HOST,
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, params=params) as resp:
                if resp.status != 200:
                    logger.error(f"[API-Football] HTTP {resp.status}: {await resp.text()}")
                    return None
                data = await resp.json()
                return data.get("response", [])
    except Exception as e:
        logger.exception(f"[API-Football] Ошибка: {e}")
        return None


async def auto_parse_matches(target_date: str = None):
    """
    Получает матчи на указанную дату (по умолчанию сегодня) из API-Football.
    Для каждого матча получает прогнозы и коэффициенты.
    Возвращает количество добавленных матчей.
    """
    if not target_date:
        target_date = datetime.now(TZ).strftime("%Y-%m-%d")

    logger.info(f"[API-Football] Парсинг матчей на {target_date}")

    # 1. Получаем список матчей
    fixtures = await fetch_api_football("fixtures", {"date": target_date})
    if not fixtures:
        logger.warning("[API-Football] Матчи не найдены или ошибка API")
        return 0

    added = 0
    now_str = datetime.now(TZ).strftime("%Y-%m-%d %H:%M")

    async with aiosqlite.connect(DB_PATH) as db:
        for fx in fixtures:
            fixture = fx.get("fixture", {})
            teams = fx.get("teams", {})
            league = fx.get("league", {})

            fixture_id = fixture.get("id")
            home = teams.get("home", {}).get("name", "?")
            away = teams.get("away", {}).get("name", "?")
            match_name = f"{home} — {away}"
            country = league.get("country", "Unknown")
            league_name = league.get("name", "Unknown")

            # Время матча (UTC → Moscow)
            tz_str = fixture.get("timezone", "UTC")
            dt_str = fixture.get("date", "")
            match_time = "—"
            if dt_str:
                try:
                    dt_utc = datetime.strptime(dt_str[:19], "%Y-%m-%dT%H:%M:%S")
                    dt_msk = dt_utc.replace(tzinfo=ZoneInfo("UTC")).astimezone(TZ)
                    match_time = dt_msk.strftime("%H:%M")
                except Exception:
                    pass

            # Проверяем, есть ли уже такой матч в базе
            cur = await db.execute(
                "SELECT id FROM matches WHERE api_fixture_id = ? AND created_at LIKE ?",
                (fixture_id, target_date + "%")
            )
            exists = await cur.fetchone()
            if exists:
                continue

            # 2. Получаем прогноз API
            api_prediction = ""
            prediction_text = ""
            preds = await fetch_api_football("predictions", {"fixture": fixture_id})
            if preds:
                p = preds[0]
                winner = p.get("predictions", {}).get("winner", {})
                win_name = winner.get("name", "") if winner else ""
                win_pct = winner.get("percent", "") if winner else ""
                advice = p.get("predictions", {}).get("advice", "")
                under_over = p.get("predictions", {}).get("under_over", "")
                goals = p.get("predictions", {}).get("goals", {})
                home_goals = goals.get("home", "-")
                away_goals = goals.get("away", "-")

                pred_parts = []
                if win_name and win_pct:
                    pred_parts.append(f"Победитель: {win_name} ({win_pct})")
                if advice:
                    pred_parts.append(f"Совет: {advice}")
                if under_over:
                    pred_parts.append(f"Тотал: {under_over}")
                pred_parts.append(f"Ожидаемые голы: {home} {home_goals} — {away} {away_goals}")

                api_prediction = "\n".join(pred_parts)

                # Формируем текст для пользователя
                prediction_text = (
                    f"📊 <b>Прогноз API-Football</b>\n\n"
                    f"💡 {advice}\n\n"
                    f"🏆 Победитель: {win_name} ({win_pct})\n"
                    f"⚽ Тотал: {under_over}\n"
                    f"🥅 Ожидаемые голы: {home_goals} : {away_goals}\n\n"
                    f"📉 <i>Это автоматический прогноз на основе статистики. "
                    f"Админ добавит свой разбор позже.</i>"
                )

            # 3. Получаем коэффициенты (один запрос на матч)
            odds_text = ""
            odds_data = await fetch_api_football("odds", {"fixture": fixture_id})
            if odds_data:
                first = odds_data[0]
                values = first.get("values", [])
                for v in values:
                    val = v.get("value", "")
                    odd = v.get("odd", "")
                    if val and odd:
                        odds_text += f"{val}: {odd}  "
                odds_text = odds_text.strip()

            # Сохраняем в базу
            await db.execute(
                "INSERT INTO matches (name, country, league, match_time, text, odds, api_prediction, api_fixture_id, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (match_name, country, league_name, match_time,
                 prediction_text, odds_text, api_prediction, fixture_id, now_str)
            )
            added += 1

        await db.commit()

    logger.info(f"[API-Football] Добавлено {added} матчей")
    return added


# ====================== YOOKASSA ======================

async def create_yookassa_payment(user_id: int, amount: float = PREMIUM_PRICE):
    if not YOOKASSA_SHOP_ID or not YOOKASSA_SECRET_KEY:
        logger.error("YOOKASSA_SHOP_ID или YOOKASSA_SECRET_KEY не заданы")
        return None

    auth = base64.b64encode(f"{YOOKASSA_SHOP_ID}:{YOOKASSA_SECRET_KEY}".encode()).decode()
    url = "https://api.yookassa.ru/v3/payments"
    idemp_key = f"bot-{user_id}-{int(datetime.now(TZ).timestamp())}"

    payload = {
        "amount": {"value": str(amount), "currency": "RUB"},
        "confirmation": {
            "type": "redirect",
            "return_url": f"https://t.me/{BOT_USERNAME}"
        },
        "capture": True,
        "metadata": {"user_id": str(user_id)},
        "description": "Подписка Premium на 30 дней"
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Basic {auth}",
        "Idempotence-Key": idemp_key
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                data = await resp.json()
                logger.info(f"[YooKassa] HTTP {resp.status}")
                if resp.status in (200, 201):
                    pid = data.get("id")
                    curl = data.get("confirmation", {}).get("confirmation_url")
                    if curl:
                        async with aiosqlite.connect(DB_PATH) as db:
                            await db.execute(
                                "INSERT OR REPLACE INTO pending_payments (payment_id, user_id, amount, created_at) VALUES (?, ?, ?, ?)",
                                (pid, user_id, amount, datetime.now(TZ).strftime("%Y-%m-%d %H:%M"))
                            )
                            await db.commit()
                        return {"payment_id": pid, "confirmation_url": curl}
                else:
                    logger.error(f"[YooKassa] Ошибка: {data}")
                    return None
    except Exception as e:
        logger.exception(f"[YooKassa] {e}")
        return None


async def check_yookassa_payment(payment_id: str) -> str:
    auth = base64.b64encode(f"{YOOKASSA_SHOP_ID}:{YOOKASSA_SECRET_KEY}".encode()).decode()
    url = f"https://api.yookassa.ru/v3/payments/{payment_id}"
    headers = {"Authorization": f"Basic {auth}"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                data = await resp.json()
                return data.get("status", "unknown")
    except Exception:
        return "error"


async def give_premium(user_id: int, days: int = 30):
    user = await get_user(user_id)
    if user["subscription"] == "Premium" and user["end_date"]:
        try:
            cur_end = datetime.strptime(user["end_date"], "%Y-%m-%d")
            if cur_end > datetime.now(TZ):
                new_end = cur_end + timedelta(days=days)
            else:
                new_end = datetime.now(TZ) + timedelta(days=days)
        except Exception:
            new_end = datetime.now(TZ) + timedelta(days=days)
    else:
        new_end = datetime.now(TZ) + timedelta(days=days)

    await update_user(user_id, subscription="Premium", end_date=new_end.strftime("%Y-%m-%d"))

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM pending_payments WHERE user_id = ?", (user_id,))
        await db.commit()

    try:
        await bot.send_message(
            user_id,
            f"⭐ <b>Premium активирован!</b>\n\n"
            f"Действует до: {new_end.strftime('%Y-%m-%d')}\n"
            f"Спасибо за оплату! 🎉",
            parse_mode="HTML"
        )
    except Exception:
        pass


async def check_pending_payments_loop():
    while True:
        try:
            async with aiosqlite.connect(DB_PATH) as db:
                cur = await db.execute("SELECT payment_id, user_id FROM pending_payments")
                rows = await cur.fetchall()

            for pid, uid in rows:
                status = await check_yookassa_payment(pid)
                if status == "succeeded":
                    await give_premium(uid, 30)
                elif status in ("canceled", "error"):
                    async with aiosqlite.connect(DB_PATH) as db:
                        await db.execute("DELETE FROM pending_payments WHERE payment_id = ?", (pid,))
                        await db.commit()
        except Exception as e:
            logger.exception(f"[Payments loop] {e}")

        await asyncio.sleep(30)


async def check_premium_expiration_loop():
    while True:
        try:
            now = datetime.now(TZ).date()
            tomorrow = now + timedelta(days=1)

            async with aiosqlite.connect(DB_PATH) as db:
                db.row_factory = aiosqlite.Row
                cur = await db.execute(
                    "SELECT user_id, end_date FROM users WHERE subscription = 'Premium' AND status = 'active'"
                )
                rows = await cur.fetchall()

                for row in rows:
                    uid = row["user_id"]
                    ed = row["end_date"]
                    if not ed:
                        continue
                    try:
                        end_date = datetime.strptime(ed, "%Y-%m-%d").date()
                    except Exception:
                        continue

                    if end_date == tomorrow:
                        try:
                            await bot.send_message(
                                uid,
                                "⏰ <b>Подписка заканчивается завтра!</b>\n\n"
                                f"Дата окончания: {ed}\n"
                                "Не забудьте продлить, чтобы сохранить доступ к матчам и экспрессам!",
                                parse_mode="HTML"
                            )
                        except Exception:
                            await update_user(uid, status="blocked")

                    elif end_date < now:
                        await db.execute(
                            "UPDATE users SET subscription = 'Free', end_date = NULL WHERE user_id = ?",
                            (uid,)
                        )
                        try:
                            await bot.send_message(
                                uid,
                                "📋 Ваша подписка Premium закончилась.\n"
                                "Вы переведены на тариф Free."
                            )
                        except Exception:
                            await update_user(uid, status="blocked")

                await db.commit()
        except Exception as e:
            logger.exception(f"[Expiration loop] {e}")

        await asyncio.sleep(3600)


# ====================== КЛАВИАТУРЫ ======================

def main_keyboard(is_admin=False):
    kb = [
        [InlineKeyboardButton(text="📁 Аккаунт", callback_data="account")],
        [InlineKeyboardButton(text="⚽ Матчи", callback_data="matches"),
         InlineKeyboardButton(text="🚂 Экспресс дня", callback_data="express")],
        [InlineKeyboardButton(text="💬 Чат канала", url="https://t.me/koefchat"),
         InlineKeyboardButton(text="⭐ Premium", callback_data="premium")],
        [InlineKeyboardButton(text="🛠 Техподдержка", callback_data="support")],
    ]
    if is_admin:
        kb.append([InlineKeyboardButton(text="🔧 Админ-панель", callback_data="admin_panel")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


def account_keyboard(sub_type, fav_count=0, ref_count=0):
    kb = [
        [InlineKeyboardButton(text=f"⭐ Подписка: {sub_type}", callback_data="sub_info")],
        [InlineKeyboardButton(text=f"⭐ Избранное ({fav_count})", callback_data="favorites"),
         InlineKeyboardButton(text=f"🔗 Рефералы ({ref_count})", callback_data="ref_link")],
    ]
    if sub_type == "Free":
        kb.append([InlineKeyboardButton(text="Купить Premium (300 ₽)", callback_data="premium")])
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


def back_keyboard(cb="main_menu"):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data=cb)]
    ])


def support_categories_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🐛 Баг / ошибка", callback_data="supcat_bug")],
        [InlineKeyboardButton(text="💳 Оплата", callback_data="supcat_pay")],
        [InlineKeyboardButton(text="💡 Предложение", callback_data="supcat_idea")],
        [InlineKeyboardButton(text="❓ Вопрос", callback_data="supcat_q")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")],
    ])


def admin_panel_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить матч", callback_data="add_match_start")],
        [InlineKeyboardButton(text="🔄 Автопарсинг матчей", callback_data="autoparse_menu")],
        [InlineKeyboardButton(text="🗑 Удалить матч", callback_data="delete_match_menu")],
        [InlineKeyboardButton(text="🚂 Экспресс дня", callback_data="express_admin")],
        [InlineKeyboardButton(text="💰 Управление Premium", callback_data="premium_admin_menu")],
        [InlineKeyboardButton(text="🛠 Сообщения поддержки", callback_data="support_admin_menu")],
        [InlineKeyboardButton(text="📦 Бэкап БД", callback_data="backup_db")],
        [InlineKeyboardButton(text="📋 Логи админа", callback_data="admin_logs")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")],
    ])


# ====================== FSM STATES ======================

class SupportStates(StatesGroup):
    get_message = State()

class AdminStates(StatesGroup):
    add_match_time = State()
    add_match_name = State()
    add_country_league = State()
    add_text = State()
    delete_match_choice = State()
    reply_text = State()
    express_name = State()
    express_country_league = State()
    express_prediction = State()
    express_coef = State()


# ====================== ХЕНДЛЕРЫ ======================

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
    user = await get_user(uid)

    # Обновляем активность и streak
    today = datetime.now(TZ).strftime("%Y-%m-%d")
    yesterday = (datetime.now(TZ) - timedelta(days=1)).strftime("%Y-%m-%d")
    last_active = user.get("last_active_date")
    new_streak = user.get("streak_days", 0)
    if last_active == today:
        pass
    elif last_active == yesterday:
        new_streak += 1
    else:
        new_streak = 1
    await update_user(uid, last_active_date=today, streak_days=new_streak,
                      username=message.from_user.username or "",
                      first_name=message.from_user.first_name or "")

    # Рефералы
    if referrer and referrer != uid:
        if not user.get("referred_by"):
            await update_user(uid, referred_by=referrer)
            async with aiosqlite.connect(DB_PATH) as db:
                try:
                    await db.execute(
                        "INSERT INTO referrals (referrer_id, referred_id, created_at) VALUES (?, ?, ?)",
                        (referrer, uid, today)
                    )
                    await db.commit()
                    # Бонус пригласившему
                    ref_user = await get_user(referrer)
                    if ref_user["subscription"] == "Free":
                        end = (datetime.now(TZ) + timedelta(days=3)).strftime("%Y-%m-%d")
                        await update_user(referrer, subscription="Premium", end_date=end)
                    else:
                        if ref_user["end_date"]:
                            cur = datetime.strptime(ref_user["end_date"], "%Y-%m-%d")
                            end = (cur + timedelta(days=3)).strftime("%Y-%m-%d")
                        else:
                            end = (datetime.now(TZ) + timedelta(days=3)).strftime("%Y-%m-%d")
                        await update_user(referrer, end_date=end)
                    try:
                        await bot.send_message(referrer,
                            "🎉 По вашей реферальной ссылке зарегистрировался новый пользователь!\n"
                            "Вам начислено 3 дня Premium бесплатно!")
                    except Exception:
                        pass
                except Exception:
                    pass

    hour = datetime.now(TZ).hour
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
        f"{greeting}, {message.from_user.first_name}!\n\n"
        "Я твой помощник в мире футбола — собираю статистику, анализирую и предоставляю прогнозы.",
        reply_markup=main_keyboard(is_admin)
    )


@dp.callback_query(F.data == "main_menu")
async def to_main_menu(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    is_admin = str(callback.from_user.id) in admin_users
    await callback.message.edit_text("Главное меню:", reply_markup=main_keyboard(is_admin))
    await callback.answer()


# ---- АККАУНТ ----

@dp.callback_query(F.data == "account")
async def show_account(callback: types.CallbackQuery):
    uid = callback.from_user.id
    user = await get_user(uid)

    async with aiosqlite.connect(DB_PATH) as db:
        # Рефералы
        cur = await db.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id = ?", (uid,))
        ref_count = (await cur.fetchone())[0]
        # Избранное
        cur = await db.execute("SELECT COUNT(*) FROM favorites WHERE user_id = ?", (uid,))
        fav_count = (await cur.fetchone())[0]
        # Просмотрено сегодня
        today = datetime.now(TZ).strftime("%Y-%m-%d")
        cur = await db.execute("SELECT COUNT(*) FROM viewed_matches WHERE user_id = ? AND viewed_date = ?", (uid, today))
        viewed_today = (await cur.fetchone())[0]
        # Всего матчей
        cur = await db.execute("SELECT COUNT(*) FROM matches")
        total_matches = (await cur.fetchone())[0]
        # Всего пользователей
        cur = await db.execute("SELECT COUNT(*) FROM users")
        total_users = (await cur.fetchone())[0]
        cur = await db.execute("SELECT COUNT(*) FROM users WHERE subscription = 'Premium'")
        premium_users = (await cur.fetchone())[0]

    sub_type = user["subscription"]
    end_str = user["end_date"] if user["end_date"] else "бессрочно"

    matches_left = "∞" if sub_type == "Premium" else max(0, 3 - viewed_today)

    text = (
        f"👤 <b>Аккаунт</b>\n\n"
        f"🆔 ID: <code>{uid}</code>\n"
        f"👤 Имя: {callback.from_user.first_name}\n"
        f"💎 Тариф: {'⭐ Premium' if sub_type == 'Premium' else '🆓 Free'}\n"
        f"📅 Действует до: {end_str}\n"
        f"📅 С нами с: {user.get('reg_date', '—')}\n"
        f"🔥 Дней подряд: {user.get('streak_days', 0)}\n"
        f"⚽ Матчей осталось сегодня: {matches_left}\n"
        f"⭐ В избранном: {fav_count}\n"
        f"🏆 Матчей в базе: {total_matches}\n"
        f"👥 Пользователей: {total_users}\n"
        f"⭐ Premium-пользователей: {premium_users}"
    )
    await callback.message.edit_text(text, reply_markup=account_keyboard(sub_type, fav_count, ref_count), parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data == "sub_info")
async def sub_info(callback: types.CallbackQuery):
    user = await get_user(callback.from_user.id)
    end = user["end_date"] if user["end_date"] else "бессрочно"
    await callback.answer(f"Тариф: {user['subscription']}\nДействует до: {end}", show_alert=True)


@dp.callback_query(F.data == "ref_link")
async def show_ref_link(callback: types.CallbackQuery):
    uid = callback.from_user.id
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id = ?", (uid,))
        ref_count = (await cur.fetchone())[0]
    link = f"https://t.me/{BOT_USERNAME}?start=ref_{uid}"
    text = (
        f"🔗 <b>Ваша реферальная ссылка</b>\n\n"
        f"<code>{link}</code>\n\n"
        f"🎉 За каждого приглашённого — 3 дня Premium бесплатно!\n"
        f"Приглашено: {ref_count} чел."
    )
    await callback.message.edit_text(text, reply_markup=back_keyboard("account"), parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data == "favorites")
async def show_favorites(callback: types.CallbackQuery):
    uid = callback.from_user.id
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT m.id, m.name, m.match_time, m.country, m.league "
            "FROM favorites f JOIN matches m ON f.match_id = m.id "
            "WHERE f.user_id = ? ORDER BY f.added_at DESC", (uid,)
        )
        favs = await cur.fetchall()

    if not favs:
        await callback.message.edit_text("⭐ В избранном пусто.", reply_markup=back_keyboard("account"))
        await callback.answer()
        return

    kb = []
    for f in favs:
        flag = get_flag(f["country"])
        time_str = f"🕒 {f['match_time']} | " if f["match_time"] and f["match_time"] != "—" else ""
        kb.append([InlineKeyboardButton(text=f"{time_str}{f['name']}", callback_data=f"match_{f['id']}")])
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="account")])
    await callback.message.edit_text("⭐ <b>Избранное</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")
    await callback.answer()


# ---- МАТЧИ ----

@dp.callback_query(F.data == "matches")
async def show_leagues(callback: types.CallbackQuery):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT DISTINCT country, league, COUNT(*) as cnt FROM matches GROUP BY country, league")
        groups = await cur.fetchall()

    if not groups:
        await callback.message.edit_text("⚽ Матчей пока нет.", reply_markup=back_keyboard("main_menu"))
        await callback.answer()
        return

    kb = []
    for g in groups:
        flag = get_flag(g["country"])
        kb.append([InlineKeyboardButton(
            text=f"{flag} {g['country']} — {g['league']} ({g['cnt']})",
            callback_data=f"group_{g['country']}__{g['league']}"
        )])
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")])
    await callback.message.edit_text("📋 Выберите группу:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await callback.answer()


@dp.callback_query(F.data.startswith("group_"))
async def show_group_matches(callback: types.CallbackQuery):
    raw = callback.data.replace("group_", "", 1)
    parts = raw.split("__", 1)
    if len(parts) < 2:
        await callback.answer("Ошибка", show_alert=True)
        return
    country, league = parts

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT id, name, match_time FROM matches WHERE country = ? AND league = ? ORDER BY match_time",
            (country, league)
        )
        matches = await cur.fetchall()

    if not matches:
        await callback.message.edit_text("В этой группе матчей нет.", reply_markup=back_keyboard("matches"))
        await callback.answer()
        return

    flag = get_flag(country)
    text = f"🏟 {flag} {country} — {league}\n\n"
    kb = []
    for m in matches:
        time_str = f"🕒 {m['match_time']} | " if m["match_time"] and m["match_time"] != "—" else ""
        kb.append([InlineKeyboardButton(text=f"{time_str}{m['name']}", callback_data=f"match_{m['id']}")])
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="matches")])
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await callback.answer()


@dp.callback_query(F.data.startswith("match_"))
async def show_match_details(callback: types.CallbackQuery):
    match_id = int(callback.data.replace("match_", ""))
    uid = callback.from_user.id

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM matches WHERE id = ?", (match_id,))
        match = await cur.fetchone()

    if not match:
        await callback.answer("Матч не найден", show_alert=True)
        return

    user = await get_user(uid)

    # Лимит для Free
    if user["subscription"] != "Premium":
        today = datetime.now(TZ).strftime("%Y-%m-%d")
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute(
                "SELECT 1 FROM viewed_matches WHERE user_id = ? AND match_id = ?",
                (uid, match_id)
            )
            already = await cur.fetchone()
            if not already:
                cur = await db.execute(
                    "SELECT COUNT(*) FROM viewed_matches WHERE user_id = ? AND viewed_date = ?",
                    (uid, today)
                )
                count = (await cur.fetchone())[0]
                if count >= 3:
                    await callback.answer("❌ Лимит матчей исчерпан (3 в день). Купите Premium.", show_alert=True)
                    return
                await db.execute(
                    "INSERT OR IGNORE INTO viewed_matches (user_id, match_id, viewed_date) VALUES (?, ?, ?)",
                    (uid, match_id, today)
                )
                await db.commit()

    flag = get_flag(match["country"])
    time_str = f"🕒 Время: {match['match_time']}\n" if match["match_time"] and match["match_time"] != "—" else ""
    odds_str = f"📈 Коэффициенты: {match['odds']}\n\n" if match["odds"] else ""

    text = (
        f"⚽ <b>{match['name']}</b>\n"
        f"🌍 {flag} Страна: {match['country']}\n"
        f"🏆 Лига: {match['league']}\n"
        f"{time_str}"
        f"{odds_str}"
        f"{match['text'] or 'Текст прогноза появится позже.'}"
    )

    kb = [
        [InlineKeyboardButton(text="⭐ В избранное", callback_data=f"fav_{match_id}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="matches")],
    ]
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data.startswith("fav_"))
async def toggle_favorite(callback: types.CallbackQuery):
    match_id = int(callback.data.replace("fav_", ""))
    uid = callback.from_user.id
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT 1 FROM favorites WHERE user_id = ? AND match_id = ?", (uid, match_id))
        exists = await cur.fetchone()
        if exists:
            await db.execute("DELETE FROM favorites WHERE user_id = ? AND match_id = ?", (uid, match_id))
            await db.commit()
            await callback.answer("Удалено из избранного", show_alert=True)
        else:
            await db.execute(
                "INSERT OR IGNORE INTO favorites (user_id, match_id, added_at) VALUES (?, ?, ?)",
                (uid, match_id, datetime.now(TZ).strftime("%Y-%m-%d %H:%M"))
            )
            await db.commit()
            await callback.answer("Добавлено в избранное ⭐", show_alert=True)


# ---- ЭКСПРЕСС ----

@dp.callback_query(F.data == "express")
async def show_express(callback: types.CallbackQuery):
    user = await get_user(callback.from_user.id)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM express_picks")
        picks = await cur.fetchall()

    if not picks:
        await callback.message.edit_text("🚂 Экспресс дня пока не сформирован.", reply_markup=back_keyboard("main_menu"))
        await callback.answer()
        return

    if user["subscription"] != "Premium":
        await callback.message.edit_text(
            "🚂 <b>Экспресс дня</b>\n\n🔒 Полный экспресс доступен только по Premium!\n\n"
            "⭐ Купите Premium — и получите доступ ко всем экспрессам и матчам без ограничений.",
            reply_markup=back_keyboard("main_menu"), parse_mode="HTML"
        )
        await callback.answer()
        return

    total_coef = 1.0
    lines = []
    for p in picks:
        flag = get_flag(p["country"])
        lines.append(
            f"⚽ {p['name']}\n{flag} {p['country']} — {p['league']}\n"
            f"💡 Прогноз: {p['prediction']}\n💰 Коэффициент: {p['coef']}"
        )
        try:
            total_coef *= float(p["coef"])
        except Exception:
            pass

    text = "🚂 <b>Экспресс дня</b>\n\n"
    text += "\n\n────────────\n\n".join(lines)
    text += f"\n\n────────────\n👑 <b>Общий коэффициент: {total_coef:.2f}</b>"

    await callback.message.edit_text(text, reply_markup=back_keyboard("main_menu"), parse_mode="HTML")
    await callback.answer()


# ---- PREMIUM / ОПЛАТА ----

@dp.callback_query(F.data == "premium")
async def buy_premium(callback: types.CallbackQuery):
    uid = callback.from_user.id
    result = await create_yookassa_payment(uid)

    if result and result.get("confirmation_url"):
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💳 Оплатить 300 ₽", url=result["confirmation_url"])],
            [InlineKeyboardButton(text="✅ Я оплатил — проверить", callback_data=f"checkpay_{result['payment_id']}")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")]
        ])
        await callback.message.edit_text(
            "⭐ <b>Premium — 300 ₽/месяц</b>\n\n"
            "Полный доступ к матчам, аналитике и экспрессам без ограничений.\n\n"
            "Нажмите кнопку ниже для оплаты. После оплаты нажмите «Я оплатил».",
            reply_markup=kb, parse_mode="HTML"
        )
    else:
        await callback.answer("❌ Не удалось создать платёж. Попробуйте позже.", show_alert=True)
    await callback.answer()


@dp.callback_query(F.data.startswith("checkpay_"))
async def check_payment(callback: types.CallbackQuery):
    pid = callback.data.replace("checkpay_", "")
    status = await check_yookassa_payment(pid)
    if status == "succeeded":
        await give_premium(callback.from_user.id, 30)
        await callback.message.edit_text(
            "⭐ Premium активирован на 30 дней! 🎉",
            reply_markup=main_keyboard(str(callback.from_user.id) in admin_users)
        )
    elif status == "pending":
        await callback.answer("⏳ Платёж ещё обрабатывается. Подождите немного.", show_alert=True)
    elif status == "canceled":
        await callback.answer("❌ Платёж отменён.", show_alert=True)
    else:
        await callback.answer("⏳ Платёж ещё обрабатывается. Попробуйте через минуту.", show_alert=True)
    await callback.answer()


# ---- ТЕХПОДДЕРЖКА ----

@dp.callback_query(F.data == "support")
async def support_start(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "🛠 <b>Техподдержка</b>\n\nВыберите категорию:",
        reply_markup=support_categories_kb(), parse_mode="HTML"
    )
    await callback.answer()


SUPCAT_MAP = {"bug": "🐛 Баг", "pay": "💳 Оплата", "idea": "💡 Предложение", "q": "❓ Вопрос"}


@dp.callback_query(F.data.startswith("supcat_"))
async def support_choose_cat(callback: types.CallbackQuery, state: FSMContext):
    cat = callback.data.replace("supcat_", "")
    await state.update_data(sup_cat=cat)
    await callback.message.edit_text(
        f"{SUPCAT_MAP.get(cat, 'Вопрос')}\n\nНапишите ваше сообщение:",
        reply_markup=back_keyboard("support")
    )
    await state.set_state(SupportStates.get_message)
    await callback.answer()


@dp.message(SupportStates.get_message)
async def handle_support_message(message: types.Message, state: FSMContext):
    data = await state.get_data()
    cat = data.get("sup_cat", "q")
    uid = message.chat.id
    now = datetime.now(TZ).strftime("%Y-%m-%d %H:%M")

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT 1 FROM support_threads WHERE thread_id = ?", (uid,))
        exists = await cur.fetchone()
        if not exists:
            await db.execute(
                "INSERT INTO support_threads (thread_id, category, user_name, created_at) VALUES (?, ?, ?, ?)",
                (uid, cat, message.from_user.full_name, now)
            )
        await db.execute(
            "INSERT INTO support_messages (thread_id, sender, text, created_at) VALUES (?, ?, ?, ?)",
            (uid, "user", message.text, now)
        )
        await db.commit()

    cat_text = SUPCAT_MAP.get(cat, "Вопрос")
    try:
        await bot.send_message(
            ADMIN_ID,
            f"📨 <b>Новое сообщение в техподдержку!</b>\n\n"
            f"🏷 Категория: {cat_text}\n"
            f"👤 От: {message.from_user.full_name}\n"
            f"ID: <code>{uid}</code>\n"
            f"📝 Текст:\n{message.text}",
            parse_mode="HTML"
        )
    except Exception:
        pass

    await message.answer("✅ Ваше сообщение отправлено администрации!", reply_markup=main_keyboard(str(uid) in admin_users))
    await state.clear()


# ====================== АДМИН-ПАНЕЛЬ ======================

def check_admin(user_id):
    return str(user_id) in admin_users


@dp.message(Command("admin"))
async def cmd_admin(message: types.Message, state: FSMContext):
    if not check_admin(message.from_user.id):
        await message.answer("❌ Нет доступа!")
        return
    await state.clear()
    await message.answer("🔧 Админ-панель", reply_markup=admin_panel_kb())


@dp.callback_query(F.data == "admin_panel")
async def admin_panel_cb(callback: types.CallbackQuery, state: FSMContext):
    if not check_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await state.clear()
    await callback.message.edit_text("🔧 Админ-панель", reply_markup=admin_panel_kb())
    await callback.answer()


# ---- АВТОПАРСИНГ ----

@dp.callback_query(F.data == "autoparse_menu")
async def autoparse_menu(callback: types.CallbackQuery):
    if not check_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    today = datetime.now(TZ).strftime("%Y-%m-%d")
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT COUNT(*) FROM matches WHERE created_at LIKE ?", (today + "%",))
        today_count = (await cur.fetchone())[0]

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Спарсить сегодняшние матчи", callback_data="autoparse_today")],
        [InlineKeyboardButton(text="🔄 Спарсить на завтра", callback_data="autoparse_tomorrow")],
        [InlineKeyboardButton(text="🔄 Спарсить на дату (ввести)", callback_data="autoparse_date")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")],
    ])
    text = (
        f"🔄 <b>Автопарсинг матчей</b>\n\n"
        f"Источник: API-Football v3\n"
        f"Сегодня в базе: {today_count} матчей\n\n"
        f"Бесплатный лимит API: 100 запросов/день\n"
        f"Каждый матч = 3 запроса (матч + прогноз + коэффициенты)\n"
        f"⚠️ Не более ~30 матчей за один парсинг!"
    )
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data == "autoparse_today")
async def autoparse_today(callback: types.CallbackQuery):
    if not check_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    if not API_FOOTBALL_KEY:
        await callback.answer("❌ API_FOOTBALL_KEY не задан в переменных окружения!", show_alert=True)
        return
    await callback.answer("⏳ Парсим...")
    count = await auto_parse_matches()
    await log_admin(callback.from_user.id, f"Автопарсинг сегодня: добавлено {count} матчей")
    await callback.message.edit_text(
        f"✅ Готово! Добавлено {count} матчей.",
        reply_markup=back_keyboard("autoparse_menu")
    )


@dp.callback_query(F.data == "autoparse_tomorrow")
async def autoparse_tomorrow(callback: types.CallbackQuery):
    if not check_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    if not API_FOOTBALL_KEY:
        await callback.answer("❌ API_FOOTBALL_KEY не задан!", show_alert=True)
        return
    await callback.answer("⏳ Парсим...")
    tomorrow = (datetime.now(TZ) + timedelta(days=1)).strftime("%Y-%m-%d")
    count = await auto_parse_matches(tomorrow)
    await log_admin(callback.from_user.id, f"Автопарсинг завтра: добавлено {count} матчей")
    await callback.message.edit_text(
        f"✅ Готово! Добавлено {count} матчей на {tomorrow}.",
        reply_markup=back_keyboard("autoparse_menu")
    )


# ---- ДОБАВЛЕНИЕ МАТЧА ВРУЧНУЮ ----

@dp.callback_query(F.data == "add_match_start")
async def add_match_start(callback: types.CallbackQuery, state: FSMContext):
    if not check_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await callback.message.edit_text(
        "Шаг 1/4: Введите время матча в формате ЧЧ:ММ (например: 18:30):\n\n"
        "Или напишите «—» если время неизвестно.",
        reply_markup=back_keyboard("admin_panel")
    )
    await state.set_state(AdminStates.add_match_time)
    await callback.answer()


@dp.message(AdminStates.add_match_time)
async def add_match_time(message: types.Message, state: FSMContext):
    t = message.text.strip()
    if t != "—":
        try:
            parts = t.split(":")
            h, m = int(parts[0]), int(parts[1])
            if not (0 <= h <= 23 and 0 <= m <= 59):
                raise ValueError
        except (ValueError, IndexError):
            await message.answer("Неверный формат. Введите ЧЧ:ММ (например: 18:30) или «—»:")
            return
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
    await state.update_data(country=parts[0], league=parts[1])
    await message.answer("Шаг 4/4: Введите полный текст прогноза (одним сообщением):", reply_markup=back_keyboard("admin_panel"))
    await state.set_state(AdminStates.add_text)


@dp.message(AdminStates.add_text)
async def add_match_text(message: types.Message, state: FSMContext):
    data = await state.get_data()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO matches (name, country, league, match_time, text, odds, api_prediction, api_fixture_id, created_at) "
            "VALUES (?, ?, ?, ?, ?, '', '', NULL, ?)",
            (data["name"], data["country"], data["league"], data["match_time"],
             message.text, datetime.now(TZ).strftime("%Y-%m-%d %H:%M"))
        )
        await db.commit()
    await log_admin(message.from_user.id, f"Добавлен матч: {data['name']}")
    await message.answer(f"✅ Матч добавлен: {data['name']}", reply_markup=main_keyboard(True))
    await state.clear()


# ---- УДАЛЕНИЕ МАТЧЕЙ ----

@dp.callback_query(F.data == "delete_match_menu")
async def delete_match_menu(callback: types.CallbackQuery):
    if not check_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT id, name, country, match_time FROM matches ORDER BY id DESC")
        matches = await cur.fetchall()

    if not matches:
        await callback.message.edit_text("Матчей нет.", reply_markup=back_keyboard("admin_panel"))
        await callback.answer()
        return

    kb = []
    for m in matches:
        time_str = f"🕒{m['match_time']} " if m["match_time"] and m["match_time"] != "—" else ""
        kb.append([InlineKeyboardButton(text=f"🗑 {time_str}{m['name']} ({m['country']})", callback_data=f"delmatch_{m['id']}")])
    kb.append([InlineKeyboardButton(text="🗑 Очистить все", callback_data="delall_matches")])
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")])
    await callback.message.edit_text("Выберите матч для удаления:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await callback.answer()


@dp.callback_query(F.data.startswith("delmatch_"))
async def delete_one_match(callback: types.CallbackQuery):
    if not check_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    mid = int(callback.data.replace("delmatch_", ""))
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT name FROM matches WHERE id = ?", (mid,))
        row = await cur.fetchone()
        if row:
            await db.execute("DELETE FROM matches WHERE id = ?", (mid,))
            await db.execute("DELETE FROM favorites WHERE match_id = ?", (mid,))
            await db.commit()
            await log_admin(callback.from_user.id, f"Удалён матч: {row[0]}")
            await callback.message.edit_text(f"✅ Удалён: {row[0]}", reply_markup=back_keyboard("admin_panel"))
        else:
            await callback.answer("Не найден", show_alert=True)
    await callback.answer()


@dp.callback_query(F.data == "delall_matches")
async def delete_all_matches(callback: types.CallbackQuery):
    if not check_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM matches")
        await db.execute("DELETE FROM favorites")
        await db.commit()
    await log_admin(callback.from_user.id, "Удалены все матчи")
    await callback.message.edit_text("✅ Все матчи удалены.", reply_markup=back_keyboard("admin_panel"))
    await callback.answer()


# ---- PREMIUM АДМИНКА ----

@dp.callback_query(F.data == "premium_admin_menu")
async def premium_admin_menu(callback: types.CallbackQuery):
    if not check_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ Выдать Premium по ID", callback_data="give_premium")],
        [InlineKeyboardButton(text="🚫 Снять Premium по ID", callback_data="remove_premium")],
        [InlineKeyboardButton(text="⭐⭐ Premium всем Free (выбор срока)", callback_data="give_all_menu")],
        [InlineKeyboardButton(text="🚫🚫 Снять Premium со всех", callback_data="remove_all_premium")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")],
    ])
    await callback.message.edit_text("💰 Управление Premium:", reply_markup=kb)
    await callback.answer()


@dp.callback_query(F.data == "give_premium")
async def give_premium_start(callback: types.CallbackQuery, state: FSMContext):
    if not check_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await callback.message.edit_text("Введите ID пользователя для выдачи Premium:", reply_markup=back_keyboard("premium_admin_menu"))
    await state.set_state(AdminStates.reply_text)
    await state.update_data(action="give_premium_id")
    await callback.answer()


@dp.callback_query(F.data == "remove_premium")
async def remove_premium_start(callback: types.CallbackQuery, state: FSMContext):
    if not check_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await callback.message.edit_text("Введите ID пользователя для снятия Premium:", reply_markup=back_keyboard("premium_admin_menu"))
    await state.set_state(AdminStates.reply_text)
    await state.update_data(action="remove_premium_id")
    await callback.answer()


@dp.callback_query(F.data == "give_all_menu")
async def give_all_menu(callback: types.CallbackQuery):
    if not check_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="1 месяц (30 дней)", callback_data="giveall_30")],
        [InlineKeyboardButton(text="3 месяца (90 дней)", callback_data="giveall_90")],
        [InlineKeyboardButton(text="6 месяцев (180 дней)", callback_data="giveall_180")],
        [InlineKeyboardButton(text="1 год (365 дней)", callback_data="giveall_365")],
        [InlineKeyboardButton(text="♾ Навсегда", callback_data="giveall_forever")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="premium_admin_menu")],
    ])
    await callback.message.edit_text("⭐ Выдать Premium всем Free-пользователям:\n\nВыберите срок:", reply_markup=kb)
    await callback.answer()


@dp.callback_query(F.data.startswith("giveall_"))
async def give_all_premium(callback: types.CallbackQuery):
    if not check_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    period = callback.data.replace("giveall_", "")
    days_map = {"30": 30, "90": 90, "180": 180, "365": 365, "forever": None}

    if period not in days_map:
        await callback.answer("Ошибка", show_alert=True)
        return

    days = days_map[period]
    end_str = "9999-12-31" if days is None else (datetime.now(TZ) + timedelta(days=days)).strftime("%Y-%m-%d")

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT COUNT(*) FROM users WHERE subscription = 'Free'")
        count = (await cur.fetchone())[0]
        await db.execute("UPDATE users SET subscription = 'Premium', end_date = ? WHERE subscription = 'Free'", (end_str,))
        await db.commit()

    label = "навсегда" if days is None else f"на {days} дней"
    await log_admin(callback.from_user.id, f"Выдан Premium всем Free ({label}), кол-во: {count}")
    await callback.message.edit_text(f"✅ Premium выдан {count} Free-пользователям {label}.", reply_markup=back_keyboard("admin_panel"))
    await callback.answer()


@dp.callback_query(F.data == "remove_all_premium")
async def remove_all_premium(callback: types.CallbackQuery):
    if not check_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT COUNT(*) FROM users WHERE subscription = 'Premium'")
        count = (await cur.fetchone())[0]
        await db.execute("UPDATE users SET subscription = 'Free', end_date = NULL WHERE subscription = 'Premium'")
        await db.commit()
    await log_admin(callback.from_user.id, f"Снят Premium со всех, кол-во: {count}")
    await callback.message.edit_text(f"✅ Premium снят с {count} пользователей.", reply_markup=back_keyboard("admin_panel"))
    await callback.answer()


@dp.message(AdminStates.reply_text)
async def admin_text_handler(message: types.Message, state: FSMContext):
    data = await state.get_data()
    action = data.get("action")
    text = message.text.strip()

    try:
        uid = int(text)
    except ValueError:
        await message.answer("Нужно ввести числовой ID. Попробуйте ещё раз:")
        return

    if action == "give_premium_id":
        end = (datetime.now(TZ) + timedelta(days=30)).strftime("%Y-%m-%d")
        await update_user(uid, subscription="Premium", end_date=end)
        await log_admin(message.from_user.id, f"Выдан Premium пользователю {uid}")
        await message.answer(f"✅ Premium выдан пользователю {uid} на 30 дней.", reply_markup=main_keyboard(True))
    elif action == "remove_premium_id":
        await update_user(uid, subscription="Free", end_date=None)
        await log_admin(message.from_user.id, f"Снят Premium с пользователя {uid}")
        await message.answer(f"✅ Premium снят с пользователя {uid}.", reply_markup=main_keyboard(True))

    await state.clear()


# ---- ПОДДЕРЖКА АДМИН ----

@dp.callback_query(F.data == "support_admin_menu")
async def support_admin_menu(callback: types.CallbackQuery):
    if not check_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM support_threads ORDER BY created_at DESC")
        threads = await cur.fetchall()

    if not threads:
        await callback.message.edit_text("Сообщений поддержки нет.", reply_markup=back_keyboard("admin_panel"))
        await callback.answer()
        return

    kb = []
    for t in threads:
        cur_msgs = await db.execute("SELECT COUNT(*) FROM support_messages WHERE thread_id = ?", (t["thread_id"],))
        count = (await cur_msgs.fetchone())[0]
        cat = SUPCAT_MAP.get(t["category"], "❓ Вопрос")
        kb.append([InlineKeyboardButton(text=f"{cat} | {t['user_name']} ({count} сообщ.)", callback_data=f"thread_{t['thread_id']}")])
    kb.append([InlineKeyboardButton(text="🗑 Очистить все", callback_data="clear_all_support")])
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")])
    await callback.message.edit_text("🛠 Сообщения поддержки:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await callback.answer()


@dp.callback_query(F.data.startswith("thread_"))
async def view_thread(callback: types.CallbackQuery):
    if not check_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    tid = int(callback.data.replace("thread_", ""))
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM support_messages WHERE thread_id = ? ORDER BY id", (tid,))
        msgs = await cur.fetchall()

    if not msgs:
        await callback.answer("Тред пуст", show_alert=True)
        return

    text = ""
    for m in msgs:
        sender = "👤 Пользователь" if m["sender"] == "user" else "🏢 Админ"
        text += f"[{m['created_at']}] {sender}\n{m['text']}\n\n"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Ответить", callback_data=f"reply_{tid}")],
        [InlineKeyboardButton(text="🗑 Очистить", callback_data=f"clear_thread_{tid}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="support_admin_menu")],
    ])
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


@dp.callback_query(F.data.startswith("reply_"))
async def reply_start(callback: types.CallbackQuery, state: FSMContext):
    if not check_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    tid = int(callback.data.replace("reply_", ""))
    await state.update_data(reply_tid=tid)
    await callback.message.edit_text("Введите текст ответа пользователю:", reply_markup=back_keyboard("support_admin_menu"))
    await state.set_state(AdminStates.reply_text)
    await state.update_data(reply_tid=tid, action="reply")
    await callback.answer()


@dp.message(AdminStates.reply_text)
async def do_reply(message: types.Message, state: FSMContext):
    data = await state.get_data()
    if data.get("action") != "reply":
        return  # Это для give/remove premium, обрабатывается в другом хендлере

    tid = data.get("reply_tid")
    now = datetime.now(TZ).strftime("%Y-%m-%d %H:%M")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO support_messages (thread_id, sender, text, created_at) VALUES (?, ?, ?, ?)",
            (tid, "admin", message.text, now)
        )
        await db.commit()

    try:
        await bot.send_message(int(tid), f"💬 <b>Ответ техподдержки:</b>\n\n{message.text}", parse_mode="HTML")
    except Exception:
        pass

    await log_admin(message.from_user.id, f"Ответ в поддержку {tid}")
    await message.answer("✅ Ответ отправлен.", reply_markup=main_keyboard(True))
    await state.clear()


@dp.callback_query(F.data.startswith("clear_thread_"))
async def clear_thread(callback: types.CallbackQuery):
    if not check_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    tid = int(callback.data.replace("clear_thread_", ""))
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM support_messages WHERE thread_id = ?", (tid,))
        await db.execute("DELETE FROM support_threads WHERE thread_id = ?", (tid,))
        await db.commit()
    await callback.message.edit_text("✅ Переписка очищена.", reply_markup=back_keyboard("support_admin_menu"))
    await callback.answer()


@dp.callback_query(F.data == "clear_all_support")
async def clear_all_support(callback: types.CallbackQuery):
    if not check_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM support_messages")
        await db.execute("DELETE FROM support_threads")
        await db.commit()
    await callback.message.edit_text("✅ Все переписки очищены.", reply_markup=back_keyboard("admin_panel"))
    await callback.answer()


# ---- ЭКСПРЕСС АДМИНКА ----

@dp.callback_query(F.data == "express_admin")
async def express_admin(callback: types.CallbackQuery):
    if not check_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM express_picks")
        picks = await cur.fetchall()

    text = "🚂 <b>Управление экспрессом дня</b>\n\n"
    if picks:
        total = 1.0
        for p in picks:
            text += f"⚽ {p['name']} — {p['prediction']} (кф {p['coef']})\n"
            try:
                total *= float(p["coef"])
            except Exception:
                pass
        text += f"\n👑 Общий коэффициент: {total:.2f}\n"
    else:
        text += "Экспресс пуст.\n"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить матч в экспресс", callback_data="express_add")],
        [InlineKeyboardButton(text="🗑 Очистить экспресс", callback_data="express_clear")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")],
    ])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data == "express_add")
async def express_add(callback: types.CallbackQuery, state: FSMContext):
    if not check_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await callback.message.edit_text("Шаг 1/4: Название команд:", reply_markup=back_keyboard("express_admin"))
    await state.set_state(AdminStates.express_name)
    await callback.answer()


@dp.message(AdminStates.express_name)
async def express_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await message.answer("Шаг 2/4: Страна и лига через пробел:", reply_markup=back_keyboard("express_admin"))
    await state.set_state(AdminStates.express_country_league)


@dp.message(AdminStates.express_country_league)
async def express_country_league(message: types.Message, state: FSMContext):
    parts = message.text.strip().split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Нужно страну и лигу через пробел:")
        return
    await state.update_data(country=parts[0], league=parts[1])
    await message.answer("Шаг 3/4: Прогноз (например: П1 или ТБ 2.5):", reply_markup=back_keyboard("express_admin"))
    await state.set_state(AdminStates.express_prediction)


@dp.message(AdminStates.express_prediction)
async def express_prediction(message: types.Message, state: FSMContext):
    await state.update_data(prediction=message.text.strip())
    await message.answer("Шаг 4/4: Коэффициент (например: 1.85):", reply_markup=back_keyboard("express_admin"))
    await state.set_state(AdminStates.express_coef)


@dp.message(AdminStates.express_coef)
async def express_coef(message: types.Message, state: FSMContext):
    data = await state.get_data()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO express_picks (name, country, league, prediction, coef, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (data["name"], data["country"], data["league"], data["prediction"],
             message.text.strip(), datetime.now(TZ).strftime("%Y-%m-%d %H:%M"))
        )
        await db.commit()
    await log_admin(message.from_user.id, f"Добавлен матч в экспресс: {data['name']}")
    await message.answer(f"✅ Добавлен: {data['name']} (кф. {message.text.strip()})", reply_markup=main_keyboard(True))
    await state.clear()


@dp.callback_query(F.data == "express_clear")
async def express_clear(callback: types.CallbackQuery):
    if not check_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM express_picks")
        await db.commit()
    await log_admin(callback.from_user.id, "Экспресс очищен")
    await callback.message.edit_text("✅ Экспресс очищен.", reply_markup=back_keyboard("express_admin"))
    await callback.answer()


# ---- БЭКАП И ЛОГИ ----

@dp.callback_query(F.data == "backup_db")
async def backup_db(callback: types.CallbackQuery):
    if not check_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    backup_name = f"backup_{datetime.now(TZ).strftime('%Y%m%d_%H%M')}.db"
    import shutil
    shutil.copy2(DB_PATH, backup_name)
    from aiogram.types import FSInputFile
    await callback.message.answer_document(FSInputFile(backup_name), caption=f"📦 Бэкап БД от {datetime.now(TZ).strftime('%Y-%m-%d %H:%M')}")
    os.remove(backup_name)
    await log_admin(callback.from_user.id, "Создан бэкап БД")
    await callback.answer()


@dp.callback_query(F.data == "admin_logs")
async def admin_logs(callback: types.CallbackQuery):
    if not check_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM admin_log ORDER BY id DESC LIMIT 20")
        logs = await cur.fetchall()

    if not logs:
        text = "📋 Логов пока нет."
    else:
        text = "📋 <b>Последние 20 действий:</b>\n\n"
        for l in logs:
            text += f"[{l['created_at']}] Admin {l['admin_id']}: {l['action']}\n"

    await callback.message.edit_text(text, reply_markup=back_keyboard("admin_panel"), parse_mode="HTML")
    await callback.answer()


# ====================== ЗАПУСК ======================

async def main():
    await init_db()
    asyncio.create_task(check_pending_payments_loop())
    asyncio.create_task(check_premium_expiration_loop())
    logger.info("Бот запущен")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
