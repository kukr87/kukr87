import asyncio
import json
import os
import base64
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

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
BOT_USERNAME = os.getenv("BOT_USERNAME", "koefiibot")

YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID", "1192478")
YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY", "390540012:LIVE:103363")
YOOKASSA_RETURN_URL = os.getenv("YOOKASSA_RETURN_URL", f"https://t.me/{BOT_USERNAME}")

PREMIUM_PRICE = "300.00"
PREMIUM_DAYS = 30

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

admin_users = {str(ADMIN_ID)}

matches_file = "matches.json"
users_file = "users.json"
support_file = "support.json"
express_file = "express.json"

tz = ZoneInfo("Europe/Moscow")

# Хранилище ожидающих платежей: {payment_id: {"user_id": int, "created": datetime}}
pending_payments = {}

COUNTRY_FLAGS = {
    "Россия": "🇷🇺",
    "Англия": "🇬🇧",
    "Испания": "🇪🇸",
    "Италия": "🇮🇹",
    "Германия": "🇩🇪",
    "Франция": "🇫🇷",
    "Португалия": "🇵🇹",
    "Турция": "🇹🇷",
    "Сербия": "🇷🇸",
    "Казахстан": "🇰🇿",
    "Украина": "🇺🇦",
    "Беларусь": "🇧🇾",
    "США": "🇺🇸",
    "Бразилия": "🇧🇷",
    "Аргентина": "🇦🇷",
    "Австрия": "🇦🇹",
    "Бельгия": "🇧🇪",
    "Болгария": "🇧🇬",
    "Венгрия": "🇭🇺",
    "Греция": "🇬🇷",
    "Дания": "🇩🇰",
    "Ирландия": "🇮🇪",
    "Нидерланды": "🇳🇱",
    "Норвегия": "🇳🇴",
    "Польша": "🇵🇱",
    "Хорватия": "🇭🇷",
    "Швеция": "🇸🇪",
    "Швейцария": "🇨🇭",
    "Шотландия": "🏴󠁧󠁢󠁳󠁣󠁴󠁿",
    "Чехия": "🇨🇿",
    "Румыния": "🇷🇴",
}

def get_flag(country: str) -> str:
    return COUNTRY_FLAGS.get(country, "🏳️")

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

SUPPORT_CATEGORIES = {
    "bug": "🐛 Баг / ошибка",
    "pay": "💳 Оплата",
    "idea": "💡 Предложение",
    "q": "❓ Вопрос",
}

# ====================== YOOKASSA ======================

def yookassa_auth_header():
    credentials = f"{YOOKASSA_SHOP_ID}:{YOOKASSA_SECRET_KEY}"
    encoded = base64.b64encode(credentials.encode()).decode()
    return f"Basic {encoded}"

async def create_yookassa_payment(user_id: int) -> dict | None:
    idempotence_key = str(uuid.uuid4())
    headers = {
        "Authorization": yookassa_auth_header(),
        "Idempotence-Key": idempotence_key,
        "Content-Type": "application/json",
    }
    payload = {
        "amount": {"value": PREMIUM_PRICE, "currency": "RUB"},
        "capture": True,
        "confirmation": {"type": "redirect", "return_url": YOOKASSA_RETURN_URL},
        "description": "Premium-подписка на 30 дней",
        "metadata": {"user_id": str(user_id)},
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.yookassa.ru/v3/payments",
                headers=headers,
                json=payload,
            ) as resp:
                data = await resp.json()
                return data
    except Exception as e:
        print(f"YooKassa create payment error: {e}")
        return None

async def check_yookassa_payment(payment_id: str) -> dict | None:
    headers = {
        "Authorization": yookassa_auth_header(),
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"https://api.yookassa.ru/v3/payments/{payment_id}",
                headers=headers,
            ) as resp:
                data = await resp.json()
                return data
    except Exception as e:
        print(f"YooKassa check payment error: {e}")
        return None

async def give_premium_to_user(user_id: int, days: int = PREMIUM_DAYS):
    uid = str(user_id)
    if uid not in users:
        await get_user_subscription(user_id)

    if users[uid].get("subscription") == "Premium":
        cur_str = users[uid].get("end_date", "")
        try:
            cur = datetime.strptime(cur_str, "%Y-%m-%d")
        except ValueError:
            cur = datetime.now(tz)
        new_end = (cur + timedelta(days=days)).strftime("%Y-%m-%d")
    else:
        new_end = (datetime.now(tz) + timedelta(days=days)).strftime("%Y-%m-%d")

    users[uid]["subscription"] = "Premium"
    users[uid]["end_date"] = new_end
    save_json(users_file, users)

async def process_payment_success(payment_id: str, user_id: int):
    if payment_id in pending_payments:
        del pending_payments[payment_id]

    await give_premium_to_user(user_id, PREMIUM_DAYS)

    try:
        await bot.send_message(
            user_id,
            "🎉 <b>Оплата прошла успешно!</b>\n\n"
            f"Вам выдан Premium на {PREMIUM_DAYS} дней.\n"
            "Спасибо за поддержку!",
            parse_mode="HTML",
        )
    except Exception as e:
        print(f"Failed to send payment success message to {user_id}: {e}")

async def check_pending_payments_task():
    while True:
        await asyncio.sleep(30)
        if not pending_payments:
            continue
        for payment_id in list(pending_payments.keys()):
            info = pending_payments[payment_id]
            payment_data = await check_yookassa_payment(payment_id)
            if not payment_data:
                continue
            status = payment_data.get("status", "")
            user_id = info.get("user_id")
            if status == "succeeded":
                await process_payment_success(payment_id, user_id)
            elif status in ("canceled",):
                if payment_id in pending_payments:
                    del pending_payments[payment_id]
                try:
                    await bot.send_message(user_id, "❌ Платёж отменён.")
                except Exception:
                    pass

# ====================== ФОНОВЫЕ УВЕДОМЛЕНИЯ ======================

async def check_premium_expiration_task():
    while True:
        try:
            current_users = load_json(users_file)
            now = datetime.now(tz).date()
            tomorrow = now + timedelta(days=1)

            for uid, data in current_users.items():
                if data.get("subscription") != "Premium":
                    continue

                end_date_str = data.get("end_date", "")
                if not end_date_str:
                    continue

                try:
                    end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
                except ValueError:
                    continue

                already_notified = data.get("notified_expire", False)

                if end_date == tomorrow and not already_notified:
                    message_text = (
                        "⏰ <b>Внимание!</b>\n"
                        f"Ваша подписка Premium заканчивается завтра ({end_date}).\n\n"
                        "Не забудьте продлить, чтобы сохранить доступ к матчам и экспрессам!"
                    )
                    try:
                        await bot.send_message(int(uid), message_text, parse_mode="HTML")
                        data["notified_expire"] = True
                        save_json(users_file, current_users)
                    except Exception as e:
                        print(f"Failed to send expiration notification to {uid}: {e}")

                if end_date > tomorrow and already_notified:
                    data["notified_expire"] = False
                    save_json(users_file, current_users)

                if end_date < now:
                    data["subscription"] = "Free"
                    data["end_date"] = (now + timedelta(days=30)).strftime("%Y-%m-%d")
                    data["notified_expire"] = False
                    save_json(users_file, current_users)
                    try:
                        await bot.send_message(
                            int(uid),
                            "⏳ Ваша подписка Premium истекла.\n"
                            "Вы переведены на тариф Free.",
                        )
                    except Exception:
                        pass

        except Exception as e:
            print(f"Error in expiration check task: {e}")

        await asyncio.sleep(3600)

# ====================== КЛАВИАТУРЫ ======================

def main_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📂 Аккаунт", callback_data="account")],
        [InlineKeyboardButton(text="⚽ Матчи", callback_data="matches")],
        [InlineKeyboardButton(text="🚆 Экспресс дня", callback_data="express")],
        [InlineKeyboardButton(text="💬 Чат канала", url="https://t.me/koefchat")],
        [InlineKeyboardButton(text="⭐ Premium", callback_data="premium")],
        [InlineKeyboardButton(text="🛠 Техподдержка", callback_data="support")],
    ])

def account_keyboard(sub, ref_count=0):
    kb = [
        [InlineKeyboardButton(text=f"Подписка: {sub['subscription']}", callback_data="sub_info")],
        [InlineKeyboardButton(text=f"🔗 Реферальная ссылка (приглашено: {ref_count})", callback_data="ref_link")],
    ]
    if sub["subscription"] == "Free":
        kb.append([InlineKeyboardButton(text="Купить Premium (300 ₽)", callback_data="premium")])
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def matches_keyboard():
    groups = {}
    for m in matches_data.get("matches", []):
        key = f"{m['country']} — {m['league']}"
        groups.setdefault(key, []).append(m)

    kb = []
    for group_name, group_matches in groups.items():
        country, league = group_name.split(" — ", 1)
        flag = get_flag(country)
        count = len(group_matches)
        kb.append([
            InlineKeyboardButton(
                text=f"{flag} {country} — {league} ({count})",
                callback_data=f"group_{group_name}"
            )
        ])

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

# ====================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ======================

async def get_user_subscription(user_id: int) -> dict:
    uid = str(user_id)
    if uid not in users:
        users[uid] = {
            "subscription": "Free",
            "end_date": (datetime.now(tz) + timedelta(days=30)).strftime("%Y-%m-%d"),
            "viewed_matches": [],
            "referrals": [],
            "referred_by": None,
            "reg_date": datetime.now(tz).strftime("%Y-%m-%d"),
        }
        save_json(users_file, users)
    return users[uid]

async def check_match_limit(user_id: int, match_index: int) -> bool:
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
    cat_text = SUPPORT_CATEGORIES.get(category, "Вопрос")
    try:
        await bot.send_message(
            ADMIN_ID,
            f"📨 <b>Новое сообщение в техподдержку!</b>\n\n"
            f"🏷 Категория: {cat_text}\n"
            f"👤 От: {user_name}\n"
            f"ID: <code>{user_id}</code>\n"
            f"📝 Текст:\n{text}",
            parse_mode="HTML"
        )
    except Exception:
        pass

def get_ref_link(user_id):
    return f"https://t.me/{BOT_USERNAME}?start=ref_{user_id}"

async def add_referral_bonus(referrer_id):
    uid = str(referrer_id)
    if uid not in users:
        return
    if users[uid]["subscription"] == "Free":
        users[uid]["subscription"] = "Premium"
        users[uid]["end_date"] = (datetime.now(tz) + timedelta(days=3)).strftime("%Y-%m-%d")
    else:
        cur = datetime.strptime(users[uid]["end_date"], "%Y-%m-%d")
        users[uid]["end_date"] = (cur + timedelta(days=3)).strftime("%Y-%m-%d")
    save_json(users_file, users)
    try:
        await bot.send_message(
            int(uid),
            "🎉 По вашей реферальной ссылке зарегистрировался новый пользователь!\n"
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
            f"⚽ {p['name']}\n"
            f"{flag} {p.get('country', '')} — {p.get('league', '')}\n"
            f"💡 Прогноз: {p.get('prediction', '')}\n"
            f"💰 Коэффициент: {p.get('coef', '')}"
        )
        lines.append(line)
        try:
            total_coef *= float(p.get("coef", 1))
        except (ValueError, TypeError):
            pass
    text = "🚆 <b>Экспресс дня</b>\n\n"
    text += "\n\n─────────────\n\n".join(lines)
    text += f"\n\n─────────────\n"
    text += f"👑 <b>Общий коэффициент: {total_coef:.2f}</b>"
    return text

# ====================== STATES ======================

class SupportStates(StatesGroup):
    waiting_category = State()
    get_message = State()

class AdminStates(StatesGroup):
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

class PaymentStates(StatesGroup):
    waiting_payment = State()

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

    uid = str(message.from_user.id)
    await get_user_subscription(message.from_user.id)

    if referrer and referrer != message.from_user.id:
        if uid not in users:
            await get_user_subscription(message.from_user.id)
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
        greeting = "☀️ Доброе утро"
    elif 12 <= hour < 18:
        greeting = "🌇 Привет"
    elif 18 <= hour < 23:
        greeting = "🌙 Вечер добрый"
    else:
        greeting = "🌙 Доброй ночи"

    await message.answer(
        f"{greeting}, {message.from_user.first_name}!\n\n"
        "Я твой помощник в мире футбола — собираю статистику, анализирую и предоставляю прогнозы.",
        reply_markup=main_keyboard()
    )

@dp.callback_query(F.data == "main_menu")
async def to_main_menu(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Главное меню:", reply_markup=main_keyboard())
    await callback.answer()

@dp.callback_query(F.data == "account")
async def account(callback: types.CallbackQuery):
    sub = await get_user_subscription(callback.from_user.id)
    uid = str(callback.from_user.id)
    ref_count = len(users[uid].get("referrals", []))
    total_matches = len(matches_data.get("matches", []))
    total_users = len(users)
    premium_users = sum(1 for u in users.values() if u.get("subscription") == "Premium")

    viewed = users[uid].get("viewed_matches", [])
    if sub["subscription"] == "Premium":
        matches_left = "∞"
    else:
        matches_left = max(0, 3 - len(viewed))

    sub_emoji = "⭐ Premium" if sub["subscription"] == "Premium" else "🆓 Free"

    text = (
        "👤 <b>Аккаунт</b>\n\n"
        f"🆔 ID: <code>{callback.from_user.id}</code>\n"
        f"👤 Имя: {callback.from_user.first_name}\n"
        f"💎 Тариф: {sub_emoji}\n"
        f"📅 С нами с: {users[uid].get('reg_date', '—')}\n"
        f"⚽ Матчей осталось сегодня: {matches_left}\n"
        f"🏆 Всего матчей в базе: {total_matches}\n"
        f"👥 Всего пользователей: {total_users}\n"
        f"⭐ Premium-пользователей: {premium_users}"
    )
    await callback.message.edit_text(text, reply_markup=account_keyboard(sub, ref_count), parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "ref_link")
async def show_ref_link(callback: types.CallbackQuery):
    uid = str(callback.from_user.id)
    ref_count = len(users[uid].get("referrals", []))
    link = get_ref_link(callback.from_user.id)
    text = (
        "🔗 <b>Ваша реферальная ссылка</b>\n\n"
        f"<code>{link}</code>\n\n"
        f"🎉 За каждого приглашённого — 3 дня Premium бесплатно!\n"
        f"Приглашено: {ref_count} чел."
    )
    await callback.message.edit_text(text, reply_markup=back_keyboard("account"), parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "matches")
async def show_leagues(callback: types.CallbackQuery):
    await callback.message.edit_text("📋 Выберите группу (страна — лига):", reply_markup=matches_keyboard())
    await callback.answer()

@dp.callback_query(F.data.startswith("group_"))
async def show_group_matches(callback: types.CallbackQuery):
    group_name = callback.data.replace("group_", "", 1)
    parts = group_name.split(" — ", 1)
    if len(parts) < 2:
        await callback.answer("Ошибка", show_alert=True)
        return
    country, league = parts

    group_matches = [
        m for m in matches_data.get("matches", [])
        if m["country"] == country and m["league"] == league
    ]

    if not group_matches:
        await callback.message.edit_text("В этой группе матчей нет.", reply_markup=back_keyboard("matches"))
        await callback.answer()
        return

    flag = get_flag(country)
    text = f"🏟 {flag} {country} — {league}\n\n"

    kb_buttons = []
    for i, m in enumerate(group_matches):
        kb_buttons.append([InlineKeyboardButton(text=m["name"], callback_data=f"match_{i}")])

    kb_buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="matches")])
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_buttons))
    await callback.answer()

@dp.callback_query(F.data.startswith("match_"))
async def show_match_details(callback: types.CallbackQuery):
    idx = int(callback.data.split("_")[1])
    all_matches = matches_data.get("matches", [])

    if idx >= len(all_matches):
        await callback.answer("Матч не найден", show_alert=True)
        return

    match = all_matches[idx]

    allowed = await check_match_limit(callback.from_user.id, idx)
    if not allowed:
        await callback.answer("❌ Лимит матчей исчерпан (3 в день). Купите Premium.", show_alert=True)
        return

    flag = get_flag(match["country"])
    text = (
        f"⚽ <b>{match['name']}</b>\n"
        f"🌍 {flag} Страна: {match['country']}\n"
        f"🏆 Лига: {match['league']}\n\n"
        f"{match['text']}"
    )
    await callback.message.edit_text(text, reply_markup=back_keyboard("matches"), parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "express")
async def show_express(callback: types.CallbackQuery):
    sub = await get_user_subscription(callback.from_user.id)
    picks = express_data.get("picks", [])

    if not picks:
        await callback.message.edit_text(
            "🚆 Экспресс дня пока не сформирован. Загляните позже!",
            reply_markup=back_keyboard("main_menu")
        )
        await callback.answer()
        return

    if sub["subscription"] != "Premium":
        text = "🚆 <b>Экспресс дня</b>\n\n"
        text += "🔒 Полный экспресс доступен только по Premium!\n\n"
        text += "⭐ Купите Premium и получите доступ ко всем экспрессам и матчам без ограничений."
        await callback.message.edit_text(text, reply_markup=back_keyboard("main_menu"), parse_mode="HTML")
        await callback.answer()
        return

    text = format_express(picks)
    await callback.message.edit_text(text, reply_markup=back_keyboard("main_menu"), parse_mode="HTML")
    await callback.answer()

# ====================== ОПЛАТА PREMIUM ======================

@dp.callback_query(F.data == "premium")
async def premium(callback: types.CallbackQuery, state: FSMContext):
    sub = await get_user_subscription(callback.from_user.id)

    if sub["subscription"] == "Premium":
        end_date = sub.get("end_date", "—")
        await callback.message.edit_text(
            f"⭐ У вас уже активна подписка Premium!\n\n"
            f"Действует до: {end_date}\n\n"
            "Хотите продлить?",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💳 Продлить Premium (300 ₽)", callback_data="pay_premium")],
                [InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")]
            ])
        )
        await callback.answer()
        return

    await callback.message.edit_text(
        "⭐ <b>Premium — полный доступ</b>\n\n"
        "• Безлимитные матчи и аналитика\n"
        "• Доступ к экспрессам дня\n"
        "• Без ограничений\n\n"
        f"Цена: {PREMIUM_PRICE} ₽ на {PREMIUM_DAYS} дней\n\n"
        "Оплата через ЮKassa (банковская карта, ЮMoney, СБП)",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💳 Оплатить 300 ₽", callback_data="pay_premium")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")]
        ]),
        parse_mode="HTML"
    )
    await callback.answer()

@dp.callback_query(F.data == "pay_premium")
async def pay_premium(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id

    payment_data = await create_yookassa_payment(user_id)
    if not payment_data or "id" not in payment_data:
        await callback.answer("Ошибка создания платежа. Попробуйте позже.", show_alert=True)
        return

    payment_id = payment_data["id"]
    confirmation = payment_data.get("confirmation", {})
    payment_url = confirmation.get("confirmation_url", "")

    if not payment_url:
        await callback.answer("Не удалось получить ссылку на оплату.", show_alert=True)
        return

    pending_payments[payment_id] = {
        "user_id": user_id,
        "created": datetime.now(tz),
    }

    await callback.message.edit_text(
        "💳 <b>Оплата Premium</b>\n\n"
        f"Сумма: {PREMIUM_PRICE} ₽\n\n"
        "1. Нажмите кнопку «Перейти к оплате»\n"
        "2. Оплатите на странице ЮKassa\n"
        "3. Нажмите «Я оплатил» — бот проверит платёж",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔗 Перейти к оплате", url=payment_url)],
            [InlineKeyboardButton(text="✅ Я оплатил — проверить", callback_data=f"checkpay_{payment_id}")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="premium")]
        ]),
        parse_mode="HTML"
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("checkpay_"))
async def check_payment(callback: types.CallbackQuery):
    payment_id = callback.data.replace("checkpay_", "", 1)

    if payment_id not in pending_payments:
        await callback.answer("Платёж не найден или уже обработан.", show_alert=True)
        return

    payment_data = await check_yookassa_payment(payment_id)
    if not payment_data:
        await callback.answer("Ошибка проверки. Попробуйте через минуту.", show_alert=True)
        return

    status = payment_data.get("status", "")

    if status == "succeeded":
        user_id = pending_payments[payment_id].get("user_id")
        await process_payment_success(payment_id, user_id)
        await callback.message.edit_text(
            "🎉 <b>Оплата прошла успешно!</b>\n\n"
            f"Вам выдан Premium на {PREMIUM_DAYS} дней.\n"
            "Спасибо за поддержку!",
            reply_markup=main_keyboard(),
            parse_mode="HTML"
        )
    elif status == "pending" or status == "waiting_for_capture":
        await callback.answer("Платёж ещё обрабатывается. Подождите немного.", show_alert=True)
    elif status == "canceled":
        if payment_id in pending_payments:
            del pending_payments[payment_id]
        await callback.message.edit_text(
            "❌ Платёж отменён.\n\n"
            "Вы можете попробовать оплатить снова.",
            reply_markup=back_keyboard("premium")
        )
    else:
        await callback.answer(f"Статус платежа: {status}", show_alert=True)

    await callback.answer()

# ====================== ТЕХПОДДЕРЖКА ======================

@dp.callback_query(F.data == "support")
async def support_start(callback: types.CallbackQuery, state: FSMContext):
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
        f"{cat_text}\n\nНапишите ваше сообщение (одним сообщением):",
        reply_markup=back_keyboard("support")
    )
    await state.set_state(SupportStates.get_message)
    await callback.answer()

@dp.message(SupportStates.get_message)
async def handle_support(message: types.Message, state: FSMContext):
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

    await message.answer("✅ Ваше сообщение успешно отправлено Администрации!", reply_markup=main_keyboard())
    await state.clear()

# ====================== АДМИН ПАНЕЛЬ ======================

@dp.message(Command("admin"))
async def admin_panel(message: types.Message, state: FSMContext):
    if str(message.from_user.id) not in admin_users:
        await message.answer("❌ Нет доступа!")
        return
    await state.clear()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить матч", callback_data="add_match_start")],
        [InlineKeyboardButton(text="🗑 Удалить матч / Очистить все", callback_data="delete_match_menu")],
        [InlineKeyboardButton(text="🚆 Экспресс дня", callback_data="express_admin")],
        [InlineKeyboardButton(text="💰 Управление Premium", callback_data="premium_admin_menu")],
        [InlineKeyboardButton(text="🛠 Сообщения поддержки", callback_data="support_admin_menu")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")]
    ])
    await message.answer("Админ-панель", reply_markup=kb)

@dp.callback_query(F.data == "add_match_start")
async def add_match_start(callback: types.CallbackQuery, state: FSMContext):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    await callback.message.edit_text("Шаг 1/3: Введите название команд (например: Спартак — Зенит):", reply_markup=back_keyboard("admin_panel"))
    await state.set_state(AdminStates.add_match_name)
    await callback.answer()

@dp.message(AdminStates.add_match_name)
async def add_match_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await message.answer("Шаг 2/3: Страна и лига (через пробел, например: Россия РПЛ):", reply_markup=back_keyboard("admin_panel"))
    await state.set_state(AdminStates.add_country_league)

@dp.message(AdminStates.add_country_league)
async def add_country_league(message: types.Message, state: FSMContext):
    parts = message.text.strip().split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Нужно ввести страну и лигу через пробел. Попробуйте ещё раз:")
        return
    country, league = parts[0], parts[1]
    await state.update_data(country=country, league=league)
    await message.answer("Шаг 3/3: Введите полный текст матча (одним сообщением):", reply_markup=back_keyboard("admin_panel"))
    await state.set_state(AdminStates.add_text)

@dp.message(AdminStates.add_text)
async def add_text(message: types.Message, state: FSMContext):
    data = await state.get_data()
    new_match = {
        "name": data["name"],
        "country": data["country"],
        "league": data["league"],
        "text": message.text
    }
    matches_data.setdefault("matches", []).append(new_match)
    save_json(matches_file, matches_data)
    await message.answer(f"✅ Матч добавлен: {new_match['name']}", reply_markup=main_keyboard())
    await state.clear()

@dp.callback_query(F.data == "delete_match_menu")
async def delete_match_menu(callback: types.CallbackQuery):
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
        kb.append([InlineKeyboardButton(text=f"🗑 {m['name']} ({m['country']})", callback_data=f"delmatch_{i}")])
    kb.append([InlineKeyboardButton(text="🗑 Очистить все", callback_data="delall_matches")])
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")])
    await callback.message.edit_text("Выберите матч для удаления:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await callback.answer()

@dp.callback_query(F.data.startswith("delmatch_"))
async def delete_one_match(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    idx = int(callback.data.replace("delmatch_", ""))
    all_matches = matches_data.get("matches", [])
    if idx < len(all_matches):
        removed = all_matches.pop(idx)
        save_json(matches_file, matches_data)
        await callback.message.edit_text(f"✅ Удалён: {removed['name']}", reply_markup=back_keyboard("admin_panel"))
    else:
        await callback.answer("Не найден", show_alert=True)
    await callback.answer()

@dp.callback_query(F.data == "delall_matches")
async def delete_all_matches(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    matches_data["matches"] = []
    save_json(matches_file, matches_data)
    await callback.message.edit_text("✅ Все матчи удалены.", reply_markup=back_keyboard("admin_panel"))
    await callback.answer()

@dp.callback_query(F.data == "premium_admin_menu")
async def premium_admin_menu(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ Выдать Premium по ID", callback_data="give_premium")],
        [InlineKeyboardButton(text="🚫 Снять Premium по ID", callback_data="remove_premium")],
        [InlineKeyboardButton(text="⭐ Premium всем Free", callback_data="give_all_premium")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")]
    ])
    await callback.message.edit_text("💰 Управление Premium:", reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data == "give_premium")
async def give_premium(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Введите ID пользователя для выдачи Premium:", reply_markup=back_keyboard("premium_admin_menu"))
    await state.set_state(AdminStates.premium_give_id)
    await callback.answer()

@dp.message(AdminStates.premium_give_id)
async def do_give_premium(message: types.Message, state: FSMContext):
    try:
        uid = message.text.strip()
        if uid not in users:
            await message.answer("Пользователь не найден.")
            return
        users[uid]["subscription"] = "Premium"
        users[uid]["end_date"] = (datetime.now(tz) + timedelta(days=30)).strftime("%Y-%m-%d")
        save_json(users_file, users)
        await message.answer(f"✅ Premium выдан пользователю {uid} на 30 дней.", reply_markup=main_keyboard())
    except Exception:
        await message.answer("Ошибка. Проверьте ID.")
    await state.clear()

@dp.callback_query(F.data == "remove_premium")
async def remove_premium(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Введите ID пользователя для снятия Premium:", reply_markup=back_keyboard("premium_admin_menu"))
    await state.set_state(AdminStates.premium_remove_id)
    await callback.answer()

@dp.message(AdminStates.premium_remove_id)
async def do_remove_premium(message: types.Message, state: FSMContext):
    try:
        uid = message.text.strip()
        if uid not in users:
            await message.answer("Пользователь не найден.")
            return
        users[uid]["subscription"] = "Free"
        users[uid]["end_date"] = (datetime.now(tz) + timedelta(days=30)).strftime("%Y-%m-%d")
        save_json(users_file, users)
        await message.answer(f"✅ Premium снят с пользователя {uid}.", reply_markup=main_keyboard())
    except Exception:
        await message.answer("Ошибка. Проверьте ID.")
    await state.clear()

@dp.callback_query(F.data == "give_all_premium")
async def give_all_premium(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    count = 0
    for uid, u in users.items():
        if u.get("subscription") == "Free":
            u["subscription"] = "Premium"
            u["end_date"] = (datetime.now(tz) + timedelta(days=30)).strftime("%Y-%m-%d")
            count += 1
    save_json(users_file, users)
    await callback.message.edit_text(f"✅ Premium выдан {count} Free-пользователям на 30 дней.", reply_markup=back_keyboard("admin_panel"))
    await callback.answer()

@dp.callback_query(F.data == "support_admin_menu")
async def support_admin_menu(callback: types.CallbackQuery):
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
        cat_emoji = SUPPORT_CATEGORIES.get(cat, "❓ Вопрос")
        name = last_msg.get("name", "Без имени")
        count = len(msgs)
        date = last_msg.get("date", "")
        kb.append([InlineKeyboardButton(
            text=f"{cat_emoji} | {name} ({count} сообщ.) [{date}]",
            callback_data=f"thread_{tid}"
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
        sender = "👤 Пользователь" if m.get("from") == "user" else "🏢 Админ"
        text += f"[{m.get('date', '')}] {sender} ({cat_text})\n{m.get('text', '')}\n\n"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Ответить", callback_data=f"reply_{tid}")],
        [InlineKeyboardButton(text="🗑 Очистить", callback_data=f"clear_thread_{tid}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="support_admin_menu")]
    ])
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data.startswith("reply_"))
async def reply_start(callback: types.CallbackQuery, state: FSMContext):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    tid = callback.data.replace("reply_", "", 1)
    await state.update_data(reply_tid=tid)
    await callback.message.edit_text("Введите текст ответа пользователю:", reply_markup=back_keyboard("support_admin_menu"))
    await state.set_state(AdminStates.reply_support_text)
    await callback.answer()

@dp.message(AdminStates.reply_support_text)
async def do_reply(message: types.Message, state: FSMContext):
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
        await bot.send_message(int(tid), f"💬 <b>Ответ техподдержки:</b>\n\n{message.text}", parse_mode="HTML")
    except Exception:
        pass
    await message.answer("✅ Ответ отправлен пользователю.", reply_markup=main_keyboard())
    await state.clear()

@dp.callback_query(F.data.startswith("clear_thread_"))
async def clear_thread(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    tid = callback.data.replace("clear_thread_", "", 1)
    threads = support.get("threads", {})
    if tid in threads:
        del threads[tid]
        save_json(support_file, support)
    await callback.message.edit_text("✅ Переписка очищена.", reply_markup=back_keyboard("support_admin_menu"))
    await callback.answer()

@dp.callback_query(F.data == "clear_all_support")
async def clear_all_support(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    support["threads"] = {}
    save_json(support_file, support)
    await callback.message.edit_text("✅ Все переписки очищены.", reply_markup=back_keyboard("admin_panel"))
    await callback.answer()

# ====================== ЭКСПРЕСС — АДМИНКА ======================

@dp.callback_query(F.data == "express_admin")
async def express_admin(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    picks = express_data.get("picks", [])
    text = "🚆 <b>Управление экспрессом дня</b>\n\n"
    if picks:
        text += format_express(picks) + "\n"
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
    pick = {
        "name": data["name"],
        "country": data["country"],
        "league": data["league"],
        "prediction": data["prediction"],
        "coef": message.text.strip()
    }
    express_data.setdefault("picks", []).append(pick)
    save_json(express_file, express_data)
    await message.answer(f"✅ Матч добавлен в экспресс: {pick['name']} (кф. {pick['coef']})", reply_markup=main_keyboard())
    await state.clear()

@dp.callback_query(F.data == "express_clear")
async def express_clear(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    express_data["picks"] = []
    save_json(express_file, express_data)
    await callback.message.edit_text("✅ Экспресс очищен.", reply_markup=back_keyboard("express_admin"))
    await callback.answer()

@dp.callback_query(F.data == "admin_panel")
async def admin_panel_cb(callback: types.CallbackQuery, state: FSMContext):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    await state.clear()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить матч", callback_data="add_match_start")],
        [InlineKeyboardButton(text="🗑 Удалить матч / Очистить все", callback_data="delete_match_menu")],
        [InlineKeyboardButton(text="🚆 Экспресс дня", callback_data="express_admin")],
        [InlineKeyboardButton(text="💰 Управление Premium", callback_data="premium_admin_menu")],
        [InlineKeyboardButton(text="🛠 Сообщения поддержки", callback_data="support_admin_menu")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")]
    ])
    await callback.message.edit_text("Админ-панель", reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data == "no_matches")
async def no_matches(callback: types.CallbackQuery):
    await callback.answer("Матчей пока нет", show_alert=True)

@dp.callback_query(F.data == "sub_info")
async def sub_info(callback: types.CallbackQuery):
    sub = await get_user_subscription(callback.from_user.id)
    text = f"Тариф: {sub['subscription']}\nДействует до: {sub['end_date']}"
    await callback.answer(text, show_alert=True)

# ====================== ЗАПУСК ======================

async def main():
    asyncio.create_task(check_premium_expiration_task())
    asyncio.create_task(check_pending_payments_task())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
