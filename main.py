import asyncio
import json
import os
import base64
import logging
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import aiohttp
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
BOT_USERNAME = os.getenv("BOT_USERNAME", "koefiibot")
YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID", "")
YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY", "")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

admin_users = {str(ADMIN_ID)}

matches_file = "matches.json"
users_file = "users.json"
support_file = "support.json"
express_file = "express.json"

tz = ZoneInfo("Europe/Moscow")

COUNTRY_FLAGS = {
    "Россия": "\U0001f1f7\U0001f1fa",
    "Англия": "\U0001f1ec\U0001f1e7",
    "Испания": "\U0001f1ea\U0001f1f8",
    "Италия": "\U0001f1ee\U0001f1f9",
    "Германия": "\U0001f1e9\U0001f1ea",
    "Франция": "\U0001f1eb\U0001f1f7",
    "Португалия": "\U0001f1f5\U0001f1f9",
    "Турция": "\U0001f1f9\U0001f1f7",
    "Сербия": "\U0001f1f7\U0001f1f8",
    "Казахстан": "\U0001f1f0\U0001f1ff",
    "Украина": "\U0001f1fa\U0001f1e6",
    "Беларусь": "\U0001f1e7\U0001f1fe",
    "США": "\U0001f1fa\U0001f1f8",
    "Бразилия": "\U0001f1e7\U0001f1f7",
    "Аргентина": "\U0001f1e6\U0001f1f7",
    "Австрия": "\U0001f1e6\U0001f1f9",
    "Бельгия": "\U0001f1e7\U0001f1ea",
    "Болгария": "\U0001f1e7\U0001f1ec",
    "Венгрия": "\U0001f1ed\U0001f1fa",
    "Греция": "\U0001f1ec\U0001f1f7",
    "Дания": "\U0001f1e9\U0001f1f0",
    "Ирландия": "\U0001f1ee\U0001f1ea",
    "Нидерланды": "\U0001f1f3\U0001f1f1",
    "Норвегия": "\U0001f1f3\U0001f1f4",
    "Польша": "\U0001f1f5\U0001f1f1",
    "Хорватия": "\U0001f1ed\U0001f1f7",
    "Швеция": "\U0001f1f8\U0001f1ea",
    "Швейцария": "\U0001f1e8\U0001f1ed",
    "Чехия": "\U0001f1e8\U0001f1ff",
    "Румыния": "\U0001f1f7\U0001f1f4",
}

SUPPORT_CATEGORIES = {
    "bug": "\U0001f41b Баг / ошибка",
    "pay": "\U0001f4b3 Оплата",
    "idea": "\U0001f4a1 Предложение",
    "q": "\u2753 Вопрос",
}

def get_flag(country):
    return COUNTRY_FLAGS.get(country, "\U0001f3f3")

def load_json(file):
    if os.path.exists(file):
        with open(file, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}

def save_json(file, data):
    with open(file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

matches_data = load_json(matches_file)
users = load_json(users_file)
support = load_json(support_file)
express_data = load_json(express_file)

if "matches" not in matches_data:
    matches_data["matches"] = []
if "picks" not in express_data:
    express_data["picks"] = []

# Cleanup: Free users don't have end_date
for uid_u in list(users.items()):
    uid, u = uid_u
    if u.get("subscription") == "Free":
        u["end_date"] = None
save_json(users_file, users)


# ====================== HELPER FUNCTIONS ======================

def is_user_admin(user_id):
    return str(user_id) in admin_users

async def get_user_subscription(user_id):
    uid = str(user_id)
    if uid not in users:
        users[uid] = {
            "subscription": "Free",
            "end_date": None,
            "viewed_matches": [],
            "referrals": [],
            "referred_by": None,
            "reg_date": datetime.now(tz).strftime("%Y-%m-%d"),
        }
        save_json(users_file, users)
    return users[uid]

async def check_match_limit(user_id, match_index):
    sub = await get_user_subscription(user_id)
    if sub["subscription"] == "Premium":
        return True
    today = datetime.now(tz).date()
    uid = str(user_id)
    last_date_str = users[uid].get("last_check_date", "")
    if last_date_str != str(today):
        users[uid]["last_check_date"] = str(today)
        users[uid]["viewed_matches"] = []
        save_json(users_file, users)
    viewed = users[uid].get("viewed_matches", [])
    if match_index in viewed:
        return True
    if len(viewed) >= 3:
        return False
    users[uid]["viewed_matches"].append(match_index)
    save_json(users_file, users)
    return True

async def notify_admin_support(user_id, user_name, text, category):
    cat_text = SUPPORT_CATEGORIES.get(category, "\u2753 Вопрос")
    try:
        await bot.send_message(
            ADMIN_ID,
            "\U0001f4e9 <b>Новое сообщение в техподдержку!</b>\n\n"
            "\U0001f3f7 Категория: " + cat_text + "\n"
            "\U0001f464 От: " + user_name + "\n"
            "ID: <code>" + str(user_id) + "</code>\n"
            "\U0001f4dd Текст:\n" + text,
            parse_mode="HTML"
        )
    except Exception:
        pass

def get_ref_link(user_id):
    return "https://t.me/" + BOT_USERNAME + "?start=ref_" + str(user_id)

async def add_referral_bonus(referrer_id):
    uid = str(referrer_id)
    if uid not in users:
        return
    if users[uid]["subscription"] == "Free":
        users[uid]["subscription"] = "Premium"
        users[uid]["end_date"] = (datetime.now(tz) + timedelta(days=3)).strftime("%Y-%m-%d")
        users[uid]["notified_expire"] = False
    else:
        end_str = users[uid].get("end_date", "")
        if end_str and end_str != "9999-12-31":
            cur = datetime.strptime(end_str, "%Y-%m-%d")
            users[uid]["end_date"] = (cur + timedelta(days=3)).strftime("%Y-%m-%d")
            users[uid]["notified_expire"] = False
    save_json(users_file, users)
    try:
        await bot.send_message(
            int(uid),
            "\U0001f389 По вашей реферальной ссылке зарегистрировался новый пользователь!\n"
            "Вам начислено 3 дня Premium бесплатно!"
        )
    except Exception:
        pass

def format_express(picks):
    if not picks:
        return None
    total_coef = 1.0
    lines = []
    for p in picks:
        flag = get_flag(p.get("country", ""))
        line = (
            "\u26bd " + p["name"] + "\n"
            + flag + " " + p.get("country", "") + " — " + p.get("league", "") + "\n"
            + "\U0001f4a1 Прогноз: " + p.get("prediction", "") + "\n"
            + "\U0001f4b0 Коэффициент: " + p.get("coef", "")
        )
        lines.append(line)
        try:
            total_coef *= float(p.get("coef", 1))
        except (ValueError, TypeError):
            pass
    separator = "\n\n\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n\n"
    text = "\U0001f686 <b>Экспресс дня</b>\n\n"
    text += separator.join(lines)
    text += "\n\n\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n"
    text += "\U0001f451 <b>Общий коэффициент: " + str(round(total_coef, 2)) + "</b>"
    return text


# ====================== YOOKASSA PAYMENTS ======================

async def create_yookassa_payment(user_id, amount=300.0):
    shop_id = YOOKASSA_SHOP_ID
    secret_key = YOOKASSA_SECRET_KEY
    if not shop_id or not secret_key:
        logger.error("YOOKASSA_SHOP_ID or YOOKASSA_SECRET_KEY not set")
        return None
    auth_string = shop_id + ":" + secret_key
    auth_header = base64.b64encode(auth_string.encode("utf-8")).decode("utf-8")
    url = "https://api.yookassa.ru/v3/payments"
    idem_key = str(uuid.uuid4())
    payload = {
        "amount": {
            "value": str(round(amount, 2)),
            "currency": "RUB"
        },
        "confirmation": {
            "type": "redirect",
            "return_url": "https://t.me/" + BOT_USERNAME
        },
        "capture": True,
        "metadata": {
            "user_id": str(user_id),
            "bot_name": BOT_USERNAME
        },
        "description": "Оплата подписки Premium на 30 дней"
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Basic " + auth_header,
        "Idempotence-Key": idem_key
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                data = await resp.json()
                logger.info("YooKassa create payment: HTTP " + str(resp.status))
                if resp.status in (200, 201):
                    payment_id = data.get("id")
                    confirmation_url = data.get("confirmation", {}).get("confirmation_url")
                    if confirmation_url:
                        return {"payment_id": payment_id, "confirmation_url": confirmation_url}
                    logger.warning("No confirmation_url in response")
                    return None
                else:
                    logger.error("YooKassa error: " + str(resp.status) + " | " + str(data))
                    return None
    except Exception as e:
        logger.error("YooKassa exception: " + str(e))
        return None

async def check_yookassa_payment_status(payment_id):
    shop_id = YOOKASSA_SHOP_ID
    secret_key = YOOKASSA_SECRET_KEY
    if not shop_id or not secret_key:
        return None
    auth_string = shop_id + ":" + secret_key
    auth_header = base64.b64encode(auth_string.encode("utf-8")).decode("utf-8")
    url = "https://api.yookassa.ru/v3/payments/" + payment_id
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Basic " + auth_header
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("status")
                logger.error("YooKassa check status error: " + str(resp.status))
                return None
    except Exception as e:
        logger.error("YooKassa check status exception: " + str(e))
        return None


# ====================== BACKGROUND TASKS ======================

async def check_pending_payments_loop():
    while True:
        try:
            for uid, data in list(users.items()):
                payment_id = data.get("pending_payment")
                if not payment_id:
                    continue
                status = await check_yookassa_payment_status(payment_id)
                if status == "succeeded":
                    sub = data.get("subscription", "Free")
                    end_str = data.get("end_date")
                    if sub == "Premium" and end_str and end_str != "9999-12-31":
                        cur = datetime.strptime(end_str, "%Y-%m-%d")
                        new_end = cur + timedelta(days=30)
                    else:
                        new_end = datetime.now(tz) + timedelta(days=30)
                    users[uid]["subscription"] = "Premium"
                    users[uid]["end_date"] = new_end.strftime("%Y-%m-%d")
                    users[uid]["pending_payment"] = None
                    users[uid]["notified_expire"] = False
                    save_json(users_file, users)
                    try:
                        await bot.send_message(int(uid), "\u2705 Оплата получена! Premium активирован на 30 дней.")
                    except Exception as e:
                        logger.error("Cannot send payment confirmation to " + uid + ": " + str(e))
                elif status == "canceled":
                    users[uid]["pending_payment"] = None
                    save_json(users_file, users)
        except Exception as e:
            logger.error("Error in check_pending_payments: " + str(e))
        await asyncio.sleep(30)

async def check_premium_expiration_loop():
    while True:
        try:
            now = datetime.now(tz).date()
            tomorrow = now + timedelta(days=1)
            changed = False
            for uid, data in list(users.items()):
                if data.get("subscription") != "Premium":
                    continue
                end_str = data.get("end_date")
                if not end_str:
                    continue
                if end_str == "9999-12-31":
                    continue
                try:
                    end_date = datetime.strptime(end_str, "%Y-%m-%d").date()
                except ValueError:
                    continue
                notified = data.get("notified_expire", False)
                # Notification 1 day before
                if end_date == tomorrow and not notified:
                    try:
                        msg = (
                            "\u23f0 <b>Внимание!</b>\n"
                            "Ваша подписка Premium заканчивается завтра (" + end_str + ").\n\n"
                            "Не забудьте продлить, чтобы сохранить доступ к матчам и экспрессам!"
                        )
                        await bot.send_message(int(uid), msg, parse_mode="HTML")
                        users[uid]["notified_expire"] = True
                        changed = True
                    except Exception as e:
                        logger.error("Cannot send expiry notification to " + uid + ": " + str(e))
                # Downgrade if expired
                if end_date < now:
                    users[uid]["subscription"] = "Free"
                    users[uid]["end_date"] = None
                    users[uid]["notified_expire"] = False
                    changed = True
                    try:
                        await bot.send_message(
                            int(uid),
                            "Ваша подписка Premium закончилась. Вы переведены на тариф Free.\n"
                            "Чтобы снова получить доступ ко всем функциям, оформите Premium."
                        )
                    except Exception as e:
                        logger.error("Cannot send downgrade notification to " + uid + ": " + str(e))
                # Reset notification flag if renewed
                if end_date != tomorrow and notified:
                    users[uid]["notified_expire"] = False
                    changed = True
            if changed:
                save_json(users_file, users)
        except Exception as e:
            logger.error("Error in check_premium_expiration: " + str(e))
        await asyncio.sleep(3600)


# ====================== KEYBOARDS ======================

def main_keyboard(user_id=None):
    is_admin = user_id is not None and str(user_id) in admin_users
    kb = [
        [InlineKeyboardButton(text="\U0001f4c2 Аккаунт", callback_data="account")],
        [InlineKeyboardButton(text="\u26bd Матчи", callback_data="matches")],
        [InlineKeyboardButton(text="\U0001f686 Экспресс дня", callback_data="express")],
        [InlineKeyboardButton(text="\U0001f4ac Чат канала", url="https://t.me/koefchat")],
        [InlineKeyboardButton(text="\u2b50 Premium", callback_data="premium")],
        [InlineKeyboardButton(text="\U0001f6e0 Техподдержка", callback_data="support")],
    ]
    if is_admin:
        kb.append([InlineKeyboardButton(text="\U0001f527 Админ-панель", callback_data="admin_panel")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def account_keyboard(sub, ref_count=0):
    kb = []
    if sub["subscription"] == "Premium":
        end_date = sub.get("end_date", "")
        if end_date == "9999-12-31":
            kb.append([InlineKeyboardButton(text="\u2b50 Premium (навсегда)", callback_data="sub_info")])
        else:
            kb.append([InlineKeyboardButton(text="\u2b50 Premium (до " + end_date + ")", callback_data="sub_info")])
    kb.append([InlineKeyboardButton(text="\U0001f517 Реферальная ссылка (приглашено: " + str(ref_count) + ")", callback_data="ref_link")])
    if sub["subscription"] == "Free":
        kb.append([InlineKeyboardButton(text="Купить Premium (300 \u20bd)", callback_data="premium")])
    kb.append([InlineKeyboardButton(text="\U0001f519 Назад", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def matches_keyboard():
    groups = {}
    for m in matches_data.get("matches", []):
        key = m["country"] + " — " + m["league"]
        groups.setdefault(key, []).append(m)
    kb = []
    for group_name, group_matches in groups.items():
        country, league = group_name.split(" — ", 1)
        flag = get_flag(country)
        count = len(group_matches)
        kb.append([
            InlineKeyboardButton(
                text=flag + " " + country + " — " + league + " (" + str(count) + ")",
                callback_data="group_" + group_name
            )
        ])
    if not kb:
        kb = [[InlineKeyboardButton(text="Матчей пока нет", callback_data="no_matches")]]
    kb.append([InlineKeyboardButton(text="\U0001f519 Назад", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def back_keyboard(callback_data="matches"):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="\U0001f519 Назад", callback_data=callback_data)]
    ])

def support_categories_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="\U0001f41b Баг / ошибка", callback_data="supcat_bug")],
        [InlineKeyboardButton(text="\U0001f4b3 Оплата", callback_data="supcat_pay")],
        [InlineKeyboardButton(text="\U0001f4a1 Предложение", callback_data="supcat_idea")],
        [InlineKeyboardButton(text="\u2753 Вопрос", callback_data="supcat_q")],
        [InlineKeyboardButton(text="\U0001f519 Назад", callback_data="main_menu")],
    ])

def admin_panel_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="\u2795 Добавить матч", callback_data="add_match_start")],
        [InlineKeyboardButton(text="\U0001f5d1 Удалить матч / Очистить все", callback_data="delete_match_menu")],
        [InlineKeyboardButton(text="\U0001f686 Экспресс дня", callback_data="express_admin")],
        [InlineKeyboardButton(text="\U0001f4b0 Управление Premium", callback_data="premium_admin_menu")],
        [InlineKeyboardButton(text="\U0001f6e0 Сообщения поддержки", callback_data="support_admin_menu")],
        [InlineKeyboardButton(text="\U0001f519 Назад", callback_data="main_menu")]
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
    reply_support_user_id = State()
    reply_support_text = State()
    express_name = State()
    express_country_league = State()
    express_prediction = State()
    express_coef = State()


# ====================== USER HANDLERS ======================

@dp.message(Command("start"))
async def cmd_start(message, state):
    await state.clear()
    args = message.text.split(maxsplit=1)
    referrer = None
    if len(args) > 1 and args[1].startswith("ref_"):
        try:
            referrer = int(args[1].replace("ref_", ""))
        except ValueError:
            pass
    uid = str(message.from_user.id)
    await get_user_subscription(message.from_user.id)
    if referrer and referrer != message.from_user.id:
        if not users[uid].get("referred_by"):
            users[uid]["referred_by"] = referrer
            ref_uid = str(referrer)
            if ref_uid in users:
                if uid not in users[ref_uid].get("referrals", []):
                    users[ref_uid].setdefault("referrals", []).append(uid)
                    save_json(users_file, users)
                    await add_referral_bonus(referrer)
    hour = datetime.now(tz).hour
    if 6 <= hour < 12:
        greeting = "\u2600\ufe0f Доброе утро"
    elif 12 <= hour < 18:
        greeting = "\U0001f306 Привет"
    elif 18 <= hour < 23:
        greeting = "\U0001f319 Вечер добрый"
    else:
        greeting = "\U0001f319 Доброй ночи"
    await message.answer(
        greeting + ", " + message.from_user.first_name + "!\n\n"
        "Я твой помощник в мире футбола — собираю статистику, анализирую и предоставляю прогнозы.",
        reply_markup=main_keyboard(message.from_user.id)
    )

@dp.callback_query(F.data == "main_menu")
async def to_main_menu(callback, state):
    await state.clear()
    await callback.message.edit_text("Главное меню:", reply_markup=main_keyboard(callback.from_user.id))
    await callback.answer()

@dp.callback_query(F.data == "account")
async def account(callback):
    sub = await get_user_subscription(callback.from_user.id)
    uid = str(callback.from_user.id)
    ref_count = len(users[uid].get("referrals", []))
    total_matches = len(matches_data.get("matches", []))
    total_users = len(users)
    premium_users = sum(1 for u in users.values() if u.get("subscription") == "Premium")
    viewed = users[uid].get("viewed_matches", [])
    if sub["subscription"] == "Premium":
        matches_left = "\u221e"
    else:
        matches_left = str(max(0, 3 - len(viewed)))
    if sub["subscription"] == "Free":
        sub_display = "\U0001f193 Free"
        end_display = "бессрочно"
    else:
        sub_display = "\u2b50 Premium"
        end_date = sub.get("end_date", "")
        if end_date == "9999-12-31":
            end_display = "навсегда"
        else:
            end_display = end_date or "—"
    text = (
        "\U0001f464 <b>Аккаунт</b>\n\n"
        "\U0001f194 ID: <code>" + str(callback.from_user.id) + "</code>\n"
        "\U0001f464 Имя: " + str(callback.from_user.first_name) + "\n"
        "\U0001f48e Тариф: " + sub_display + "\n"
        "\U0001f4c5 Действует до: " + end_display + "\n"
        "\u26bd Матчей осталось сегодня: " + str(matches_left) + "\n"
        "\U0001f3c6 Всего матчей в базе: " + str(total_matches) + "\n"
        "\U0001f465 Всего пользователей: " + str(total_users) + "\n"
        "\u2b50 Premium-пользователей: " + str(premium_users)
    )
    await callback.message.edit_text(text, reply_markup=account_keyboard(sub, ref_count), parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "ref_link")
async def show_ref_link(callback):
    uid = str(callback.from_user.id)
    ref_count = len(users[uid].get("referrals", []))
    link = get_ref_link(callback.from_user.id)
    text = (
        "\U0001f517 <b>Ваша реферальная ссылка</b>\n\n"
        "<code>" + link + "</code>\n\n"
        "\U0001f389 За каждого приглашённого — 3 дня Premium бесплатно!\n"
        "Приглашено: " + str(ref_count) + " чел."
    )
    await callback.message.edit_text(text, reply_markup=back_keyboard("account"), parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "sub_info")
async def sub_info(callback):
    sub = await get_user_subscription(callback.from_user.id)
    if sub["subscription"] == "Free":
        await callback.answer("Тариф: Free (бессрочно)", show_alert=True)
    else:
        end_date = sub.get("end_date", "—")
        if end_date == "9999-12-31":
            await callback.answer("Тариф: Premium (навсегда)", show_alert=True)
        else:
            await callback.answer("Тариф: Premium (до " + end_date + ")", show_alert=True)

@dp.callback_query(F.data == "matches")
async def show_leagues(callback):
    await callback.message.edit_text("\U0001f4cb Выберите группу (страна — лига):", reply_markup=matches_keyboard())
    await callback.answer()

@dp.callback_query(F.data.startswith("group_"))
async def show_group_matches(callback):
    group_name = callback.data.replace("group_", "", 1)
    parts = group_name.split(" — ", 1)
    if len(parts) < 2:
        await callback.answer("Ошибка", show_alert=True)
        return
    country, league = parts
    kb_buttons = []
    for i, m in enumerate(matches_data.get("matches", [])):
        if m["country"] == country and m["league"] == league:
            time_str = m.get("time", "")
            if time_str:
                btn_text = "\U0001f552 " + time_str + " | " + m["name"]
            else:
                btn_text = m["name"]
            kb_buttons.append([InlineKeyboardButton(text=btn_text, callback_data="match_" + str(i))])
    if not kb_buttons:
        await callback.message.edit_text("В этой группе матчей нет.", reply_markup=back_keyboard("matches"))
        await callback.answer()
        return
    flag = get_flag(country)
    text = "\U0001f3df " + flag + " " + country + " — " + league + "\n\n"
    kb_buttons.append([InlineKeyboardButton(text="\U0001f519 Назад", callback_data="matches")])
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_buttons))
    await callback.answer()

@dp.callback_query(F.data.startswith("match_"))
async def show_match_details(callback):
    idx = int(callback.data.split("_")[1])
    all_matches = matches_data.get("matches", [])
    if idx >= len(all_matches):
        await callback.answer("Матч не найден", show_alert=True)
        return
    match = all_matches[idx]
    allowed = await check_match_limit(callback.from_user.id, idx)
    if not allowed:
        await callback.answer("\u274c Лимит матчей исчерпан (3 в день). Купите Premium.", show_alert=True)
        return
    flag = get_flag(match["country"])
    time_str = match.get("time", "")
    text = "\u26bd <b>" + match["name"] + "</b>\n"
    if time_str:
        text += "\U0001f552 Время: " + time_str + "\n"
    text += "\U0001f30d " + flag + " Страна: " + match["country"] + "\n"
    text += "\U0001f3c6 Лига: " + match["league"] + "\n\n"
    text += match["text"]
    await callback.message.edit_text(text, reply_markup=back_keyboard("matches"), parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "express")
async def show_express(callback):
    sub = await get_user_subscription(callback.from_user.id)
    picks = express_data.get("picks", [])
    if not picks:
        await callback.message.edit_text(
            "\U0001f686 Экспресс дня пока не сформирован. Загляните позже!",
            reply_markup=back_keyboard("main_menu")
        )
        await callback.answer()
        return
    if sub["subscription"] != "Premium":
        text = "\U0001f686 <b>Экспресс дня</b>\n\n"
        text += "\U0001f512 Полный экспресс доступен только по Premium!\n\n"
        text += "\u2b50 Купите Premium и получите доступ ко всем экспрессам и матчам без ограничений."
        await callback.message.edit_text(text, reply_markup=back_keyboard("main_menu"), parse_mode="HTML")
        await callback.answer()
        return
    text = format_express(picks)
    await callback.message.edit_text(text, reply_markup=back_keyboard("main_menu"), parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "premium")
async def buy_premium(callback):
    user_id = callback.from_user.id
    uid = str(user_id)
    sub = await get_user_subscription(user_id)
    if sub["subscription"] == "Premium":
        end_date = sub.get("end_date", "")
        if end_date == "9999-12-31":
            msg = "\u2b50 У вас уже есть Premium (навсегда)!"
        else:
            msg = "\u2b50 У вас уже есть Premium (до " + end_date + ")!"
        await callback.message.edit_text(msg, reply_markup=back_keyboard("main_menu"))
        await callback.answer()
        return
    payment_result = await create_yookassa_payment(user_id)
    if payment_result and payment_result.get("confirmation_url"):
        url = payment_result["confirmation_url"]
        payment_id = payment_result["payment_id"]
        users[uid]["pending_payment"] = payment_id
        save_json(users_file, users)
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="\U0001f4b3 Оплатить Premium (300 \u20bd)", url=url)],
            [InlineKeyboardButton(text="\u2705 Я оплатил — проверить", callback_data="check_payment")],
            [InlineKeyboardButton(text="\U0001f519 Назад", callback_data="main_menu")]
        ])
        await callback.message.edit_text(
            "\u2b50 Premium — полный доступ к матчам, аналитике и экспрессам.\n\n"
            "Цена: 300 \u20bd в месяц\n\n"
            "Нажмите кнопку ниже, чтобы перейти к оплате. "
            "После оплаты нажмите «Я оплатил — проверить».",
            reply_markup=kb
        )
    else:
        await callback.answer("\u274c Не удалось создать платёж. Попробуйте позже.", show_alert=True)
    await callback.answer()

@dp.callback_query(F.data == "check_payment")
async def check_payment_status(callback):
    uid = str(callback.from_user.id)
    payment_id = users.get(uid, {}).get("pending_payment")
    if not payment_id:
        await callback.answer("Нет активного платежа.", show_alert=True)
        return
    status = await check_yookassa_payment_status(payment_id)
    if status == "succeeded":
        sub = await get_user_subscription(callback.from_user.id)
        if sub["subscription"] == "Premium" and sub.get("end_date") and sub["end_date"] != "9999-12-31":
            cur = datetime.strptime(sub["end_date"], "%Y-%m-%d")
            new_end = cur + timedelta(days=30)
        else:
            new_end = datetime.now(tz) + timedelta(days=30)
        users[uid]["subscription"] = "Premium"
        users[uid]["end_date"] = new_end.strftime("%Y-%m-%d")
        users[uid]["pending_payment"] = None
        users[uid]["notified_expire"] = False
        save_json(users_file, users)
        await callback.message.edit_text(
            "\u2705 Оплата получена! Premium активирован на 30 дней.",
            reply_markup=main_keyboard(callback.from_user.id)
        )
        await callback.answer()
    elif status == "canceled":
        users[uid]["pending_payment"] = None
        save_json(users_file, users)
        await callback.answer("\u274c Платёж отменён.", show_alert=True)
    elif status in ("pending", "waiting_for_capture"):
        await callback.answer("\u23f3 Платёж ещё обрабатывается. Подождите немного.", show_alert=True)
    else:
        await callback.answer("\u274c Не удалось проверить платёж. Попробуйте позже.", show_alert=True)

@dp.message(Command("testpay"))
async def cmd_testpay(message):
    if str(message.from_user.id) not in admin_users:
        return
    result = await create_yookassa_payment(message.from_user.id, 10.0)
    if result:
        await message.answer(
            "\u2705 Платёж создан!\n"
            "ID: <code>" + result["payment_id"] + "</code>\n"
            "Ссылка: " + result.get("confirmation_url", "нет"),
            parse_mode="HTML"
        )
    else:
        await message.answer("\u274c Не удалось создать платёж. Проверьте логи.")


# ====================== SUPPORT ======================

@dp.callback_query(F.data == "support")
async def support_start(callback, state):
    await callback.message.edit_text(
        "\U0001f6e0 <b>Техподдержка</b>\n\nВыберите категорию обращения:",
        reply_markup=support_categories_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("supcat_"))
async def support_choose_cat(callback, state):
    cat = callback.data.replace("supcat_", "")
    cat_text = SUPPORT_CATEGORIES.get(cat, "\u2753 Вопрос")
    await state.update_data(sup_cat=cat)
    await callback.message.edit_text(
        cat_text + "\n\nНапишите ваше сообщение (одним сообщением):",
        reply_markup=back_keyboard("support")
    )
    await state.set_state(SupportStates.get_message)
    await callback.answer()

@dp.message(SupportStates.get_message)
async def handle_support(message, state):
    data = await state.get_data()
    cat = data.get("sup_cat", "q")
    uid = str(message.chat.id)
    user_name = message.from_user.full_name or "Без имени"
    text_msg = message.text
    support.setdefault("threads", {})
    thread_id = uid
    support["threads"].setdefault(thread_id, []).append({
        "from": "user",
        "id": message.from_user.id,
        "name": user_name,
        "text": text_msg,
        "category": cat,
        "date": datetime.now(tz).strftime("%Y-%m-%d %H:%M")
    })
    save_json(support_file, support)
    await notify_admin_support(message.from_user.id, user_name, text_msg, cat)
    await message.answer("\u2705 Ваше сообщение успешно отправлено Администрации!", reply_markup=main_keyboard(message.from_user.id))
    await state.clear()


# ====================== ADMIN ======================

@dp.message(Command("admin"))
async def admin_panel_cmd(message, state):
    if str(message.from_user.id) not in admin_users:
        await message.answer("\u274c Нет доступа!")
        return
    await state.clear()
    await message.answer("Админ-панель", reply_markup=admin_panel_keyboard())

@dp.callback_query(F.data == "admin_panel")
async def admin_panel_cb(callback, state):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    await state.clear()
    await callback.message.edit_text("Админ-панель", reply_markup=admin_panel_keyboard())
    await callback.answer()

# --- ADD MATCH (with time) ---

@dp.callback_query(F.data == "add_match_start")
async def add_match_start(callback, state):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    await callback.message.edit_text(
        "Шаг 1/4: Введите время матча в формате ЧЧ:ММ (например: 18:30):",
        reply_markup=back_keyboard("admin_panel")
    )
    await state.set_state(AdminStates.add_match_time)
    await callback.answer()

@dp.message(AdminStates.add_match_time)
async def add_match_time(message, state):
    time_str = message.text.strip()
    try:
        parts = time_str.split(":")
        if len(parts) == 2:
            h, m = int(parts[0]), int(parts[1])
            if 0 <= h <= 23 and 0 <= m <= 59:
                await state.update_data(time=time_str)
                await message.answer(
                    "Шаг 2/4: Введите название команд (например: Спартак — Зенит):",
                    reply_markup=back_keyboard("admin_panel")
                )
                await state.set_state(AdminStates.add_match_name)
                return
    except ValueError:
        pass
    await message.answer("Неверный формат времени. Используйте ЧЧ:ММ (например: 18:30):")

@dp.message(AdminStates.add_match_name)
async def add_match_name(message, state):
    await state.update_data(name=message.text.strip())
    await message.answer(
        "Шаг 3/4: Страна и лига (через пробел, например: Россия РПЛ):",
        reply_markup=back_keyboard("admin_panel")
    )
    await state.set_state(AdminStates.add_country_league)

@dp.message(AdminStates.add_country_league)
async def add_country_league(message, state):
    parts = message.text.strip().split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Нужно ввести страну и лигу через пробел. Попробуйте ещё раз:")
        return
    country, league = parts[0], parts[1]
    await state.update_data(country=country, league=league)
    await message.answer(
        "Шаг 4/4: Введите полный текст матча (одним сообщением):",
        reply_markup=back_keyboard("admin_panel")
    )
    await state.set_state(AdminStates.add_text)

@dp.message(AdminStates.add_text)
async def add_text(message, state):
    data = await state.get_data()
    new_match = {
        "time": data.get("time", ""),
        "name": data["name"],
        "country": data["country"],
        "league": data["league"],
        "text": message.text
    }
    matches_data.setdefault("matches", []).append(new_match)
    save_json(matches_file, matches_data)
    await message.answer("\u2705 Матч добавлен: " + new_match["name"], reply_markup=main_keyboard(message.from_user.id))
    await state.clear()

# --- DELETE MATCH ---

@dp.callback_query(F.data == "delete_match_menu")
async def delete_match_menu(callback):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    all_matches = matches_data.get("matches", [])
    if not all_matches:
        await callback.message.edit_text("Матчей нет.", reply_markup=back_keyboard("admin_panel"))
        await callback.answer()
        return
    kb = []
    for i, m in enumerate(all_matches):
        time_str = m.get("time", "")
        if time_str:
            btn = "\U0001f5d1 " + time_str + " | " + m["name"] + " (" + m["country"] + ")"
        else:
            btn = "\U0001f5d1 " + m["name"] + " (" + m["country"] + ")"
        kb.append([InlineKeyboardButton(text=btn, callback_data="delmatch_" + str(i))])
    kb.append([InlineKeyboardButton(text="\U0001f5d1 Очистить все", callback_data="delall_matches")])
    kb.append([InlineKeyboardButton(text="\U0001f519 Назад", callback_data="admin_panel")])
    await callback.message.edit_text("Выберите матч для удаления:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await callback.answer()

@dp.callback_query(F.data.startswith("delmatch_"))
async def delete_one_match(callback):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    idx = int(callback.data.replace("delmatch_", ""))
    all_matches = matches_data.get("matches", [])
    if idx < len(all_matches):
        removed = all_matches.pop(idx)
        save_json(matches_file, matches_data)
        await callback.message.edit_text("\u2705 Удалён: " + removed["name"], reply_markup=back_keyboard("admin_panel"))
    else:
        await callback.answer("Не найден", show_alert=True)
    await callback.answer()

@dp.callback_query(F.data == "delall_matches")
async def delete_all_matches(callback):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    matches_data["matches"] = []
    save_json(matches_file, matches_data)
    await callback.message.edit_text("\u2705 Все матчи удалены.", reply_markup=back_keyboard("admin_panel"))
    await callback.answer()

# --- EXPRESS ADMIN ---

@dp.callback_query(F.data == "express_admin")
async def express_admin(callback):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    picks = express_data.get("picks", [])
    text = "\U0001f686 <b>Управление экспрессом дня</b>\n\n"
    if picks:
        text += format_express(picks) + "\n"
    else:
        text += "Экспресс пуст.\n"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="\u2795 Добавить матч в экспресс", callback_data="express_add")],
        [InlineKeyboardButton(text="\U0001f5d1 Очистить экспресс", callback_data="express_clear")],
        [InlineKeyboardButton(text="\U0001f519 Назад", callback_data="admin_panel")]
    ])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "express_add")
async def express_add(callback, state):
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
async def express_name(message, state):
    await state.update_data(name=message.text.strip())
    await message.answer("Шаг 2/4: Страна и лига (через пробел, например: Россия РПЛ):", reply_markup=back_keyboard("express_admin"))
    await state.set_state(AdminStates.express_country_league)

@dp.message(AdminStates.express_country_league)
async def express_country_league(message, state):
    parts = message.text.strip().split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Нужно страну и лигу через пробел. Попробуйте ещё раз:")
        return
    await state.update_data(country=parts[0], league=parts[1])
    await message.answer("Шаг 3/4: Введите прогноз (например: П1 или ТБ 2.5):", reply_markup=back_keyboard("express_admin"))
    await state.set_state(AdminStates.express_prediction)

@dp.message(AdminStates.express_prediction)
async def express_prediction(message, state):
    await state.update_data(prediction=message.text.strip())
    await message.answer("Шаг 4/4: Введите коэффициент (например: 1.85):", reply_markup=back_keyboard("express_admin"))
    await state.set_state(AdminStates.express_coef)

@dp.message(AdminStates.express_coef)
async def express_coef(message, state):
    data = await state.get_data()
    pick = {
        "name": data["name"],
        "country": data["country"],
        "league": data["league"],
        "prediction": data["prediction"],
        "coef": message.text.strip()
    }
    express_data.setdefault("picks", []).append(pick)
    save_json(express_file, express_data)
    await message.answer("\u2705 Матч добавлен в экспресс: " + pick["name"] + " (кф. " + pick["coef"] + ")", reply_markup=main_keyboard(message.from_user.id))
    await state.clear()

@dp.callback_query(F.data == "express_clear")
async def express_clear(callback):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    express_data["picks"] = []
    save_json(express_file, express_data)
    await callback.message.edit_text("\u2705 Экспресс очищен.", reply_markup=back_keyboard("express_admin"))
    await callback.answer()

# --- PREMIUM ADMIN ---

@dp.callback_query(F.data == "premium_admin_menu")
async def premium_admin_menu(callback):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="\u2b50 Выдать Premium по ID", callback_data="give_premium")],
        [InlineKeyboardButton(text="\U0001f6ab Снять Premium по ID", callback_data="remove_premium")],
        [InlineKeyboardButton(text="\u2b50 Premium всем Free", callback_data="give_all_premium_menu")],
        [InlineKeyboardButton(text="\U0001f6ab Снять со всех Premium", callback_data="remove_all_premium")],
        [InlineKeyboardButton(text="\U0001f519 Назад", callback_data="admin_panel")]
    ])
    await callback.message.edit_text("\U0001f4b0 Управление Premium:", reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data == "give_premium")
async def give_premium(callback, state):
    await callback.message.edit_text("Введите ID пользователя для выдачи Premium:", reply_markup=back_keyboard("premium_admin_menu"))
    await state.set_state(AdminStates.premium_give_id)
    await callback.answer()

@dp.message(AdminStates.premium_give_id)
async def do_give_premium(message, state):
    try:
        uid = message.text.strip()
        if uid not in users:
            await message.answer("Пользователь не найден.")
            await state.clear()
            return
        users[uid]["subscription"] = "Premium"
        users[uid]["end_date"] = (datetime.now(tz) + timedelta(days=30)).strftime("%Y-%m-%d")
        users[uid]["notified_expire"] = False
        save_json(users_file, users)
        await message.answer("\u2705 Premium выдан пользователю " + uid + " на 30 дней.", reply_markup=main_keyboard(message.from_user.id))
    except Exception:
        await message.answer("Ошибка. Проверьте ID.")
    await state.clear()

@dp.callback_query(F.data == "remove_premium")
async def remove_premium(callback, state):
    await callback.message.edit_text("Введите ID пользователя для снятия Premium:", reply_markup=back_keyboard("premium_admin_menu"))
    await state.set_state(AdminStates.premium_remove_id)
    await callback.answer()

@dp.message(AdminStates.premium_remove_id)
async def do_remove_premium(message, state):
    try:
        uid = message.text.strip()
        if uid not in users:
            await message.answer("Пользователь не найден.")
            await state.clear()
            return
        users[uid]["subscription"] = "Free"
        users[uid]["end_date"] = None
        users[uid]["notified_expire"] = False
        save_json(users_file, users)
        await message.answer("\u2705 Premium снят с пользователя " + uid + ".", reply_markup=main_keyboard(message.from_user.id))
    except Exception:
        await message.answer("Ошибка. Проверьте ID.")
    await state.clear()

@dp.callback_query(F.data == "give_all_premium_menu")
async def give_all_premium_menu(callback):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="1 месяц", callback_data="give_all_30")],
        [InlineKeyboardButton(text="3 месяца", callback_data="give_all_90")],
        [InlineKeyboardButton(text="6 месяцев", callback_data="give_all_180")],
        [InlineKeyboardButton(text="1 год", callback_data="give_all_365")],
        [InlineKeyboardButton(text="Навсегда", callback_data="give_all_forever")],
        [InlineKeyboardButton(text="\U0001f519 Назад", callback_data="premium_admin_menu")]
    ])
    await callback.message.edit_text("Выберите срок выдачи Premium всем Free-пользователям:", reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data.startswith("give_all_"))
async def give_all_premium_duration(callback):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    duration = callback.data.replace("give_all_", "")
    if duration == "forever":
        days = None
        duration_text = "навсегда"
    else:
        days_map = {"30": 30, "90": 90, "180": 180, "365": 365}
        days = days_map.get(duration)
        if days is None:
            await callback.answer("Неизвестный срок", show_alert=True)
            return
        duration_text = "на " + str(days) + " дней"
    count = 0
    for uid, u in users.items():
        if u.get("subscription") == "Free":
            u["subscription"] = "Premium"
            u["notified_expire"] = False
            if days is None:
                u["end_date"] = "9999-12-31"
            else:
                u["end_date"] = (datetime.now(tz) + timedelta(days=days)).strftime("%Y-%m-%d")
            count += 1
    save_json(users_file, users)
    await callback.message.edit_text(
        "\u2705 Premium выдан " + str(count) + " Free-пользователям " + duration_text + ".",
        reply_markup=back_keyboard("premium_admin_menu")
    )
    await callback.answer()

@dp.callback_query(F.data == "remove_all_premium")
async def remove_all_premium(callback):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    count = 0
    for uid, u in users.items():
        if u.get("subscription") == "Premium":
            u["subscription"] = "Free"
            u["end_date"] = None
            u["notified_expire"] = False
            count += 1
    save_json(users_file, users)
    await callback.message.edit_text(
        "\u2705 Premium снят с " + str(count) + " пользователей.",
        reply_markup=back_keyboard("premium_admin_menu")
    )
    await callback.answer()

# --- SUPPORT ADMIN ---

@dp.callback_query(F.data == "support_admin_menu")
async def support_admin_menu(callback):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    threads = support.get("threads", {})
    if not threads:
        await callback.message.edit_text("Сообщений поддержки нет.", reply_markup=back_keyboard("admin_panel"))
        await callback.answer()
        return
    kb = []
    for tid, msgs in threads.items():
        last_msg = msgs[-1] if msgs else {}
        cat = last_msg.get("category", "q")
        cat_emoji = SUPPORT_CATEGORIES.get(cat, "\u2753 Вопрос")
        name = last_msg.get("name", "Без имени")
        count = len(msgs)
        date = last_msg.get("date", "")
        kb.append([InlineKeyboardButton(
            text=cat_emoji + " | " + name + " (" + str(count) + " сообщ.) [" + date + "]",
            callback_data="thread_" + tid
        )])
    kb.append([InlineKeyboardButton(text="\U0001f5d1 Очистить все", callback_data="clear_all_support")])
    kb.append([InlineKeyboardButton(text="\U0001f519 Назад", callback_data="admin_panel")])
    await callback.message.edit_text("\U0001f6e0 Сообщения поддержки:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await callback.answer()

@dp.callback_query(F.data.startswith("thread_"))
async def view_thread(callback):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    tid = callback.data.replace("thread_", "", 1)
    threads = support.get("threads", {})
    if tid not in threads:
        await callback.answer("Тред не найден", show_alert=True)
        return
    msgs = threads[tid]
    text = ""
    for m in msgs:
        cat = m.get("category", "q")
        cat_text = SUPPORT_CATEGORIES.get(cat, "Вопрос")
        sender = "\U0001f464 Пользователь" if m.get("from") == "user" else "\U0001f3e2 Админ"
        text += "[" + m.get("date", "") + "] " + sender + " (" + cat_text + ")\n" + m.get("text", "") + "\n\n"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="\U0001f4ac Ответить", callback_data="reply_" + tid)],
        [InlineKeyboardButton(text="\U0001f5d1 Очистить", callback_data="clear_thread_" + tid)],
        [InlineKeyboardButton(text="\U0001f519 Назад", callback_data="support_admin_menu")]
    ])
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data.startswith("reply_"))
async def reply_start(callback, state):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    tid = callback.data.replace("reply_", "", 1)
    await state.update_data(reply_tid=tid)
    await callback.message.edit_text("Введите текст ответа пользователю:", reply_markup=back_keyboard("support_admin_menu"))
    await state.set_state(AdminStates.reply_support_text)
    await callback.answer()

@dp.message(AdminStates.reply_support_text)
async def do_reply(message, state):
    data = await state.get_data()
    tid = data.get("reply_tid")
    threads = support.get("threads", {})
    if tid not in threads:
        await message.answer("Тред не найден.")
        await state.clear()
        return
    threads[tid].append({
        "from": "admin",
        "id": message.from_user.id,
        "name": "Админ",
        "text": message.text,
        "category": threads[tid][-1].get("category", "q"),
        "date": datetime.now(tz).strftime("%Y-%m-%d %H:%M")
    })
    save_json(support_file, support)
    try:
        await bot.send_message(int(tid), "\U0001f4ac <b>Ответ техподдержки:</b>\n\n" + message.text, parse_mode="HTML")
    except Exception:
        pass
    await message.answer("\u2705 Ответ отправлен пользователю.", reply_markup=main_keyboard(message.from_user.id))
    await state.clear()

@dp.callback_query(F.data.startswith("clear_thread_"))
async def clear_thread(callback):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    tid = callback.data.replace("clear_thread_", "", 1)
    threads = support.get("threads", {})
    if tid in threads:
        del threads[tid]
        save_json(support_file, support)
    await callback.message.edit_text("\u2705 Переписка очищена.", reply_markup=back_keyboard("support_admin_menu"))
    await callback.answer()

@dp.callback_query(F.data == "clear_all_support")
async def clear_all_support(callback):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    support["threads"] = {}
    save_json(support_file, support)
    await callback.message.edit_text("\u2705 Все переписки очищены.", reply_markup=back_keyboard("admin_panel"))
    await callback.answer()

@dp.callback_query(F.data == "no_matches")
async def no_matches(callback):
    await callback.answer("Матчей пока нет", show_alert=True)


# ====================== MAIN ======================

async def main():
    asyncio.create_task(check_pending_payments_loop())
    asyncio.create_task(check_premium_expiration_loop())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
