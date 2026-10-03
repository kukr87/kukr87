import asyncio
import json
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))  # Telegram ID админа (число)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

admin_users = {str(ADMIN_ID)}  # храним как строку для корректного сравнения

matches_file = "matches.json"
users_file = "users.json"
support_file = "support.json"

tz = ZoneInfo("Europe/Moscow")

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

# Загрузка данных
matches_data = load_json(matches_file)
users = load_json(users_file)
support = load_json(support_file)

if "matches" not in matches_data:
    matches_data["matches"] = []

def get_all_users():
    return users

# ====================== КЛАВИАТУРЫ ======================

def main_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📂 Аккаунт", callback_data="account")],
        [InlineKeyboardButton(text="⚽ Матчи", callback_data="matches")],
        [InlineKeyboardButton(text="💬 Чат канала", url="https://t.me/koefchat")],
        [InlineKeyboardButton(text="⭐ Premium", callback_data="premium")],
        [InlineKeyboardButton(text="🛠 Техподдержка", callback_data="support")]
    ])

def account_keyboard(sub):
    kb = [[InlineKeyboardButton(text=f"Подписка: {sub['subscription']}", callback_data="sub_info")]]
    if sub["subscription"] == "Free":
        kb.append([InlineKeyboardButton(text="Купить Premium (300 ₽)", callback_data="premium")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def matches_keyboard():
    # Группировка по стране и лиге
    groups = {}
    for m in matches_data.get("matches", []):
        key = f"{m['country']} — {m['league']}"
        groups.setdefault(key, []).append(m)

    kb = []
    for group_name, group_matches in groups.items():
        count = len(group_matches)
        kb.append([InlineKeyboardButton(text=f"🏳️ {group_name} ({count})", callback_data=f"group_{group_name}")])

    if not kb:
        kb = [[InlineKeyboardButton(text="Матчей пока нет", callback_data="no_matches")]]

    return InlineKeyboardMarkup(inline_keyboard=kb)

def back_keyboard(callback_data="matches"):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data=callback_data)]
    ])

# ====================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ======================

async def get_user_subscription(user_id: int) -> dict:
    uid = str(user_id)
    if uid not in users:
        users[uid] = {
            "subscription": "Free",
            "end_date": (datetime.now(tz) + timedelta(days=30)).strftime("%Y-%m-%d"),
            "viewed_matches": []  # список индексов просмотренных матчей
        }
        save_json(users_file, users)
    return users[uid]

async def check_match_limit(user_id: int, match_index: int) -> bool:
    sub = await get_user_subscription(user_id)
    if sub["subscription"] == "Premium":
        return True

    today = datetime.now(tz).date()
    uid = str(user_id)

    # Сброс лимита, если новый день
    last_date_str = users[uid].get("last_check_date", "")
    if last_date_str != str(today):
        users[uid]["last_check_date"] = str(today)
        users[uid]["viewed_matches"] = []
        save_json(users_file, users)

    viewed = users[uid].get("viewed_matches", [])
    if match_index in viewed:
        # Уже смотрели этот матч — лимит не тратим
        return True

    if len(viewed) >= 3:
        return False

    users[uid]["viewed_matches"].append(match_index)
    save_json(users_file, users)
    return True

async def notify_admin_support(user_id, user_name, text):
    try:
        await bot.send_message(
            ADMIN_ID,
            f"📩 <b>Новое сообщение в техподдержку!</b>\n\n"
            f"👤 От: {user_name}\n"
            f"ID: <code>{user_id}</code>\n"
            f"📝 Текст:\n{text}",
            parse_mode="HTML"
        )
    except Exception:
        pass  # Если админ заблокировал бота, просто игнорируем

# ====================== ОБРАБОТЧИКИ ПОЛЬЗОВАТЕЛЯ ======================

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await get_user_subscription(message.from_user.id)
    await message.answer(
        "Доброго времени суток!\n\n"
        "Я твой помощник в мире футбола, собираю статистику, анализирую и предоставляю прогнозы.",
        reply_markup=main_keyboard()
    )

@dp.callback_query(F.data == "account")
async def account(callback: types.CallbackQuery):
    sub = await get_user_subscription(callback.from_user.id)
    text = (
        f"👤 Аккаунт\n\n"
        f"ID: <code>{callback.from_user.id}</code>\n"
        f"Имя: {callback.from_user.first_name}\n"
        f"Тариф: {'⭐ Premium' if sub['subscription'] == 'Premium' else '🆓 Free'}"
    )
    await callback.message.edit_text(text, reply_markup=account_keyboard(sub), parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "matches")
async def show_leagues(callback: types.CallbackQuery):
    await callback.message.edit_text("📋 Выберите группу (страна — лига):", reply_markup=matches_keyboard())
    await callback.answer()

@dp.callback_query(F.data.startswith("group_"))
async def show_group_matches(callback: types.CallbackQuery):
    group_name = callback.data.replace("group_", "")
    country, league = group_name.split(" — ")
    
    group_matches = [
        m for m in matches_data.get("matches", [])
        if m["country"] == country and m["league"] == league
    ]

    if not group_matches:
        await callback.message.edit_text("В этой группе матчей нет.", reply_markup=back_keyboard("matches"))
        await callback.answer()
        return

    text = f"🏟 {group_name}\n\n"
    kb_buttons = []
    for i, m in enumerate(group_matches):
        text += f"{i+1}. {m['name']}\n"
        kb_buttons.append(InlineKeyboardButton(text=f"{i+1}. {m['name']}", callback_data=f"match_{i}"))

    # Разбиваем кнопки по 2 в ряд
    kb_rows = [kb_buttons[i:i+2] for i in range(0, len(kb_buttons), 2)]
    kb_rows.append([InlineKeyboardButton(text="🔙 Назад", callback_data="matches")])

    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows))
    await callback.answer()

@dp.callback_query(F.data.startswith("match_"))
async def show_match_details(callback: types.CallbackQuery):
    idx = int(callback.data.split("_")[1])
    all_matches = matches_data.get("matches", [])

    if idx >= len(all_matches):
        await callback.answer("Матч не найден", show_alert=True)
        return

    match = all_matches[idx]

    # Проверка лимита
    allowed = await check_match_limit(callback.from_user.id, idx)
    if not allowed:
        await callback.answer("❌ Лимит матчей исчерпан (3 в день). Купите Premium.", show_alert=True)
        return

    text = (
        f"⚽ <b>{match['name']}</b>\n"
        f"🌍 Страна: {match['country']}\n"
        f"🏆 Лига: {match['league']}\n\n"
        f"{match['text']}"
    )

    await callback.message.edit_text(text, reply_markup=back_keyboard("matches"), parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "premium")
async def premium(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "⭐ Premium — полный доступ к матчам и аналитике.\n\n"
        "Цена: 300 ₽ в месяц\n\n"
        "Оплата через ЮKassa",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Оплатить 300 ₽", url="https://yoomoney.ru/quickpay/confirm.xml?receiver=your_kassa@mail.ru&sum=300&label=koefbot&formcomment=true")]
        ])
    )
    await callback.answer()

@dp.callback_query(F.data == "support")
async def support(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("🛠 Техподдержка — напишите сообщение (кратко суть):")
    await state.set_state(SupportStates.get_message)
    await callback.answer()

class SupportStates(StatesGroup):
    get_message = State()

@dp.message(SupportStates.get_message)
async def handle_support(message: types.Message, state: FSMContext):
    uid = str(message.chat.id)
    user_name = message.from_user.full_name or "Без имени"
    text_msg = message.text

    support.setdefault(uid, []).append({
        "id": message.from_user.id,
        "name": user_name,
        "text": text_msg,
        "date": datetime.now(tz).strftime("%Y-%m-%d %H:%M")
    })
    save_json(support_file, support)

    # Уведомление админу
    await notify_admin_support(message.from_user.id, user_name, text_msg)

    await message.answer("✅ Ваше сообщение успешно отправлено Администрации!", reply_markup=main_keyboard())
    await state.clear()

# ====================== АДМИН ПАНЕЛЬ ======================

class AdminStates(StatesGroup):
    add_match_name = State()
    add_country_league = State()
    add_text = State()

    premium_give_id = State()
    premium_remove_id = State()

    reply_support_user_id = State()
    reply_support_text = State()

@dp.message(Command("admin"))
async def admin_panel(message: types.Message, state: FSMContext):
    if str(message.from_user.id) not in admin_users:
        await message.answer("❌ Нет доступа!")
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить матч", callback_data="add_match_start")],
        [InlineKeyboardButton(text="🗑 Удалить матч / Очистить все", callback_data="delete_match_menu")],
        [InlineKeyboardButton(text="💰 Управление Premium", callback_data="premium_admin_menu")],
        [InlineKeyboardButton(text="🛠 Сообщения поддержки", callback_data="support_admin_menu")]
    ])
    await message.answer("Админ-панель", reply_markup=kb)

@dp.callback_query(F.data == "add_match_start")
async def add_match_start(callback: types.CallbackQuery, state: FSMContext):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    await callback.message.edit_text("Шаг 1/3: Введите название команд (например: Спартак — Зенит):")
    await state.set_state(AdminStates.add_match_name)
    await callback.answer()

@dp.message(AdminStates.add_match_name)
async def add_match_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await message.answer("Шаг 2/3: Страна и лига (через пробел, например: Россия РПЛ):")
    await state.set_state(AdminStates.add_country_league)

@dp.message(AdminStates.add_country_league)
async def add_country_league(message: types.Message, state: FSMContext):
    parts = message.text.strip().split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Пожалуйста, введите страну и лигу через пробел (например: Россия РПЛ).")
        return
    country, league = parts[0], parts[1]
    await state.update_data(country=country, league=league)
    await message.answer("Шаг 3/3: Введите полный текст матча (одним сообщением):")
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
    matches_data["matches"].append(new_match)
    save_json(matches_file, matches_data)

    await message.answer(
        f"✅ Матч добавлен!\n\n"
        f"Название: {new_match['name']}\n"
        f"Группа: {new_match['country']} — {new_match['league']}\n"
        f"Текст сохранён целиком."
    )
