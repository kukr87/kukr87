import asyncio
import json
from datetime import datetime, timedelta
import pytz
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import aiohttp
from dotenv import load_dotenv
import os

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
admin_users = {ADMIN_ID}

matches_file = "matches.json"
users_file = "users.json"
support_file = "support.json"

def load_json(file):
    if os.path.exists(file):
        with open(file, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_json(file, data):
    with open(file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

matches = load_json(matches_file)
users = load_json(users_file)
support = load_json(support_file)

if "matches" not in matches:
    matches["matches"] = {}

if "mathes" not in matches:
    matches["mathes"] = {}

tz = pytz.timezone("Europe/Moscow")

user_matches = {u: 0 for u in users}
if not users:
    users = {"default": {}}

class AdminStates(StatesGroup):
    add_match_name = State()
    add_analitica = State()
    add_stats = State()
    add_time = State()
    add_injuries = State()
    add_forecast = State()

class SupportStates(StatesGroup):
    get_message = State()

def main_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📂 Аккаунт", callback_data="account")],
        [InlineKeyboardButton(text="⚽ Матчи", callback_data="matches")],
        [InlineKeyboardButton(text="💬 Чат канала", url="https://t.me/koefchat")],
        [InlineKeyboardButton(text="⭐ Premium", callback_data="premium")],
        [InlineKeyboardButton(text="🛠 Техподдержка", callback_data="support")]
    ])

def account_keyboard(sub):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"Подписка: {sub['subscription']}", callback_data="sub_info")]
    ])
    if sub["subscription"] == "Free":
        kb.inline_keyboard.append([InlineKeyboardButton(text="Купить Premium (300 ₽)", callback_data="premium")])
    return kb

def matches_keyboard():
    kb = []
    for country, leagues in matches.get("mathes", {}).items():
        for league in leagues:
            kb.append([InlineKeyboardButton(text=f"🏳️ {country} — {league}", callback_data=f"league_{country}_{league}")])
    return InlineKeyboardMarkup(inline_keyboard=kb or [[InlineKeyboardButton(text="Матчей пока нет", callback_data="no_matches")]])

def match_detail_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Аналитика", callback_data="analitica"),
         InlineKeyboardButton(text="📈 Статистика", callback_data="stats")],
        [InlineKeyboardButton(text="⏱ Таймы", callback_data="times"),
         InlineKeyboardButton(text="🚑 Травмы", callback_data="injuries")],
        [InlineKeyboardButton(text="🔮 Прогноз", callback_data="forecast")]
    ])

def preview_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Аналитика", callback_data="spoiler_analitica"),
         InlineKeyboardButton(text="Статистика", callback_data="spoiler_stats")],
        [InlineKeyboardButton(text="Таймы", callback_data="spoiler_times"),
         InlineKeyboardButton(text="Травмы", callback_data="spoiler_injuries")],
        [InlineKeyboardButton(text="Прогноз", callback_data="spoiler_forecast")]
    ])

async def get_user_subscription(user_id: int) -> dict:
    uid = str(user_id)
    if uid not in users:
        users[uid] = {"subscription": "Free", "end_date": "2026-01-01"}
        save_json(users_file, users)
    return users[uid]

async def check_match_limit(user_id: int):
    sub = await get_user_subscription(user_id)
    if sub["subscription"] == "Premium":
        return True
    today = datetime.now(tz).date()
    uid = str(user_id)
    if "last_match_date" not in users[uid]:
        users[uid]["last_match_date"] = str(today)
        users[uid]["daily_matches"] = 0
        save_json(users_file, users)
    last = datetime.strptime(users[uid]["last_match_date"], "%Y-%m-%d").date()
    if last != today:
        users[uid]["last_match_date"] = str(today)
        users[uid]["daily_matches"] = 0
        save_json(users_file, users)
    if users[uid]["daily_matches"] >= 3:
        return False
    users[uid]["daily_matches"] += 1
    save_json(users_file, users)
    return True

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    sub = await get_user_subscription(message.from_user.id)
    await message.answer(
        "Доброго времени суток!\n\n"
        "Я твой помощник в мире футбола, собираю полную статистику команд (травмы, результаты, положение в турнирной таблице, xG, "
        "статистику по таймам, тренды и много другое), анализирую и предоставляю наиболее вероятные исходы на событие.",
        reply_markup=main_keyboard()
    )

@dp.callback_query(F.data == "account")
async def account(callback: types.CallbackQuery):
    sub = await get_user_subscription(callback.from_user.id)
    await callback.message.edit_text(
        f"👤 Твой аккаунт\n\n"
        f"ID: <code>{callback.from_user.id}</code>\n"
        f"Имя: {callback.from_user.first_name}\n"
        f"Подписка: <b>{sub['subscription']}</b>\n"
        f"Действует до: {sub.get('end_date', '—')}\n\n"
        "Бесплатно: 3 матча в сутки\n"
        "Premium: безлимит матчей каждый день",
        reply_markup=account_keyboard(sub)
    )
    await callback.answer()

@dp.callback_query(F.data == "matches")
async def show_leagues(callback: types.CallbackQuery):
    await callback.message.edit_text("📋 Выберите лигу:", reply_markup=matches_keyboard())
    await callback.answer()

@dp.callback_query(F.data.startswith("league_"))
async def show_matches(callback: types.CallbackQuery):
    _, country, league = callback.data.split("_")
    matches_list = matches.get("mathes", {}).get(country, {}).get(league, [])
    if not matches_list:
        await callback.message.edit_text(f"В лиге {league} нет матчей пока.")
        return
    text = f"🏟 {country} — {league}\n\n"
    for i, m in enumerate(matches_list, 1):
        text += f"{i}. {m}\n"
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{i+1}. {m}", callback_data=f"match_{i}") for i, m in enumerate(matches_list[:3])]
    ]))
    await callback.answer()

@dp.callback_query(F.data.startswith("match_"))
async def show_match_details(callback: types.CallbackQuery):
    idx = int(callback.data.split("_")[1]) - 1
    matches_list = list(matches.get("mathes", {}).values())[0][0] if matches.get("mathes", {}) else []
    match = matches_list[idx] if idx < len(matches_list) else "Матч не найден"
    await callback.message.edit_text(
        f"⚽ <b>{match}</b>\n\n"
        "Выберите вкладку:",
        reply_markup=match_detail_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("spoiler_"))
async def show_spoiler(callback: types.CallbackQuery):
    tab = callback.data.split("_")[1]
    texts = {
        "analitica": "🔬 Аналитика:\n... (полный текст матча из админки)",
        "stats": "📊 Статистика:\n... (xG, результаты, таблица и т.д.)",
        "times": "⏱ Таймы:\n...",
        "injuries": "🚑 Травмы:\n...",
        "forecast": "🔮 Прогноз:\n..."
    }
    await callback.message.answer(f"<tg-spoiler>{texts.get(tab, 'Нет данных')}</tg-spoiler>", parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "premium")
async def premium(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "⭐ Premium — полный доступ к матчам, аналитике, статистике и прогнозам.\n\n"
        "Цена: 300 ₽ в месяц\n\n"
        "Оплата через ЮKassa",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Оплатить 300 ₽", url="https://yoomoney.ru/quickpay/confirm.xml?receiver=your_kassa@mail.ru&sum=300&label=koefbot&formcomment=true")]
        ])
    )
    await callback.answer()

@dp.callback_query(F.data == "support")
async def support(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("🛠 Техподдержка — напишите сообщение (ID + имя + текст)")
    await state.set_state(SupportStates.get_message)
    await callback.answer()

@dp.message(SupportStates.get_message)
async def handle_support(message: types.Message, state: FSMContext):
    uid = str(message.chat.id)
    support.setdefault(uid, []).append({
        "id": message.from_user.id,
        "name": message.from_user.full_name,
        "text": message.text,
        "date": datetime.now(tz).strftime("%Y-%m-%d %H:%M")
    })
    save_json(support_file, support)
    await message.answer("Сообщение отправлено в техподдержку!")
    await state.clear()

@dp.callback_query(F.data == "admin")
async def admin_panel(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Нет доступа")
        return
    await callback.message.edit_text("Админ-панель /goal", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить матч", callback_data="add_match_start")],
        [InlineKeyboardButton(text="💰 Управление Premium", callback_data="premium_admin")],
        [InlineKeyboardButton(text="❌ Удалить матч", callback_data="delete_match")]
    ]))

@dp.callback_query(F.data == "add_match_start")
async def add_match_start(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    await callback.message.edit_text("Введите название матча:")
    await state.set_state(AdminStates.add_match_name)

@dp.message(AdminStates.add_match_name)
async def add_match_name(message: types.Message, state: FSMContext):
    match_name = message.text.strip()
    matches["matches"].setdefault("temp", {})["name"] = match_name
    save_json(matches_file, matches)
    await message.answer("Название сохранено. Теперь аналитика:")
    await state.set_state(AdminStates.add_analitica)

@dp.message(AdminStates.add_analitica)
async def add_analitica(message: types.Message, state: FSMContext):
    matches["matches"]["temp"]["analitica"] = message.text
    save_json(matches_file, matches)
    await message.answer("Аналитика сохранена. Статистика:")
    await state.set_state(AdminStates.add_stats)

@dp.message(AdminStates.add_stats)
async def add_stats(message: types.Message, state: FSMContext):
    matches["matches"]["temp"]["stats"] = message.text
    save_json(matches_file, matches)
    await message.answer("Статистика сохранена. Таймы:")
    await state.set_state(AdminStates.add_time)

@dp.message(AdminStates.add_time)
async def add_time(message: types.Message, state: FSMContext):
    matches["matches"]["temp"]["times"] = message.text
    save_json(matches_file, matches)
    await message.answer("Таймы сохранены. Травмы:")
    await state.set_state(AdminStates.add_injuries)

@dp.message(AdminStates.add_injuries)
async def add_injuries(message: types.Message, state: FSMContext):
    matches["matches"]["temp"]["injuries"] = message.text
    save_json(matches_file, matches)
    await message.answer("Травмы сохранены. Прогноз:")
    await state.set_state(AdminStates.add_forecast)

@dp.message(AdminStates.add_forecast)
async def add_forecast(message: types.Message, state: FSMContext):
    matches["matches"]["temp"]["forecast"] = message.text
    save_json(matches_file, matches)
    await message.answer("Прогноз сохранён!")
    await state.clear()

# ================== ЗАПУСК ==================
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
