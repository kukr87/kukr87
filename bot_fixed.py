import asyncio
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import os

# ====================== КОНФИГ ======================

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID", "0")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Множество строковых ID админов
admin_users = {str(ADMIN_ID)} if ADMIN_ID != "0" else set()

matches_file = "matches.json"
users_file = "users.json"
support_file = "support.json"

tz = ZoneInfo("Europe/Moscow")


# ====================== JSON УТИЛИТЫ ======================

def load_json(file):
    if os.path.exists(file):
        with open(file, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_json(file, data):
    with open(file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# Загрузка данных
matches_data = load_json(matches_file)
users = load_json(users_file)
support = load_json(support_file)

# Гарантируем, что есть список матчей
if "matches" not in matches_data or not isinstance(matches_data["matches"], list):
    matches_data["matches"] = []


# ====================== FSM СОСТОЯНИЯ ======================

class AdminStates(StatesGroup):
    add_match_country = State()
    add_match_league = State()
    add_match_name = State()
    add_analitica = State()
    add_stats = State()
    add_time = State()
    add_injuries = State()
    add_forecast = State()
    premium_user_id = State()
    delete_match_idx = State()


class SupportStates(StatesGroup):
    get_message = State()


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
    kb = [
        [InlineKeyboardButton(text=f"Подписка: {sub['subscription']}", callback_data="sub_info")]
    ]
    if sub.get("subscription") == "Free":
        kb.append([InlineKeyboardButton(text="Купить Premium (300 ₽)", callback_data="premium")])
    kb.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


def matches_keyboard():
    mlist = matches_data.get("matches", [])
    if not mlist:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Матчей пока нет", callback_data="no_matches")]
        ])

    # Группируем по стране и лиге
    seen = []
    for i, m in enumerate(mlist):
        key = (m.get("country", "?"), m.get("league", "?"))
        if key not in seen:
            seen.append(key)

    kb = []
    for country, league in seen:
        kb.append([InlineKeyboardButton(
            text=f"🏳️ {country} — {league}",
            callback_data=f"league_{country}_{league}"
        )])
    kb.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


def match_list_keyboard(country, league):
    mlist = matches_data.get("matches", [])
    items = [
        (i, m) for i, m in enumerate(mlist)
        if m.get("country") == country and m.get("league") == league
    ]
    kb = []
    for idx, m in items:
        kb.append([InlineKeyboardButton(text=m.get("name", "?"), callback_data=f"match_{idx}")])
    kb.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="matches")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


def match_detail_keyboard(idx):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Аналитика", callback_data=f"tab_analitica_{idx}"),
         InlineKeyboardButton(text="📈 Статистика", callback_data=f"tab_stats_{idx}")],
        [InlineKeyboardButton(text="⏱ Таймы", callback_data=f"tab_times_{idx}"),
         InlineKeyboardButton(text="🚑 Травмы", callback_data=f"tab_injuries_{idx}")],
        [InlineKeyboardButton(text="🔮 Прогноз", callback_data=f"tab_forecast_{idx}")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="matches")]
    ])


def admin_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить матч", callback_data="add_match_start")],
        [InlineKeyboardButton(text="💰 Управление Premium", callback_data="premium_admin")],
        [InlineKeyboardButton(text="❌ Удалить матч", callback_data="delete_match_start")],
        [InlineKeyboardButton(text="📨 Сообщения поддержки", callback_data="support_messages")]
    ])


def admin_back_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")]
    ])


# ====================== ПОДПИСКИ И ЛИМИТЫ ======================

async def get_user_subscription(user_id: int) -> dict:
    uid = str(user_id)
    if uid not in users:
        users[uid] = {"subscription": "Free", "end_date": "2026-01-01"}
        save_json(users_file, users)
    return users[uid]


async def check_match_limit(user_id: int) -> bool:
    sub = await get_user_subscription(user_id)
    if sub.get("subscription") == "Premium":
        return True

    today = datetime.now(tz).date()
    uid = str(user_id)

    if "last_match_date" not in users[uid]:
        users[uid]["last_match_date"] = str(today)
        users[uid]["daily_matches"] = 0

    last = datetime.strptime(users[uid]["last_match_date"], "%Y-%m-%d").date()
    if last != today:
        users[uid]["last_match_date"] = str(today)
        users[uid]["daily_matches"] = 0

    if users[uid]["daily_matches"] >= 3:
        return False

    users[uid]["daily_matches"] += 1
    save_json(users_file, users)
    return True


# ====================== ОБРАБОТЧИКИ ПОЛЬЗОВАТЕЛЕЙ ======================

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await get_user_subscription(message.from_user.id)
    await message.answer(
        "Доброго времени суток!\n\n"
        "Я твой помощник в мире футбола, собираю полную статистику команд (травмы, результаты, "
        "положение в турнирной таблице, xG, статистика по таймам, тренды и много другое), "
        "анализирую и предоставляю наиболее вероятные исходы на событие.",
        reply_markup=main_keyboard()
    )


@dp.callback_query(F.data == "back_to_main")
async def back_to_main(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "Главное меню:",
        reply_markup=main_keyboard()
    )
    await callback.answer()


@dp.callback_query(F.data == "account")
async def account(callback: types.CallbackQuery):
    sub = await get_user_subscription(callback.from_user.id)
    await callback.message.edit_text(
        f"👤 Твой аккаунт\n\n"
        f"ID: <code>{callback.from_user.id}</code>\n"
        f"Имя: {callback.from_user.first_name}\n"
        f"Подписка: <b>{sub.get('subscription', 'Free')}</b>\n"
        f"Действует до: {sub.get('end_date', '—')}\n\n"
        "Бесплатно: 3 матча в сутки\n"
        "Premium: безлимит матчей каждый день",
        reply_markup=account_keyboard(sub)
    )
    await callback.answer()


@dp.callback_query(F.data == "sub_info")
async def sub_info(callback: types.CallbackQuery):
    sub = await get_user_subscription(callback.from_user.id)
    await callback.answer(
        f"Подписка: {sub.get('subscription', 'Free')} до {sub.get('end_date', '—')}",
        show_alert=True
    )


@dp.callback_query(F.data == "no_matches")
async def no_matches(callback: types.CallbackQuery):
    await callback.answer("Матчей пока нет. Загляните позже!")


@dp.callback_query(F.data == "matches")
async def show_leagues(callback: types.CallbackQuery):
    await callback.message.edit_text("📋 Выберите лигу:", reply_markup=matches_keyboard())
    await callback.answer()


@dp.callback_query(F.data.startswith("league_"))
async def show_matches_in_league(callback: types.CallbackQuery):
    parts = callback.data.split("_", 2)
    if len(parts) < 3:
        await callback.answer("Ошибка данных")
        return
    country = parts[1]
    league = parts[2]

    mlist = matches_data.get("matches", [])
    items = [
        (i, m) for i, m in enumerate(mlist)
        if m.get("country") == country and m.get("league") == league
    ]
    if not items:
        await callback.message.edit_text(
            f"В лиге {league} нет матчей пока.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="matches")]
            ])
        )
        await callback.answer()
        return

    text = f"🏟 {country} — {league}\n\nВыберите матч:\n"
    for i, (idx, m) in enumerate(items, 1):
        text += f"{i}. {m.get('name', '?')}\n"

    await callback.message.edit_text(text, reply_markup=match_list_keyboard(country, league))
    await callback.answer()


@dp.callback_query(F.data.startswith("match_"))
async def show_match_details(callback: types.CallbackQuery):
    try:
        idx = int(callback.data.split("_")[1])
    except (ValueError, IndexError):
        await callback.answer("Ошибка: неверный индекс")
        return

    mlist = matches_data.get("matches", [])
    if idx < 0 or idx >= len(mlist):
        await callback.message.edit_text("Матч не найден.")
        await callback.answer()
        return

    match = mlist[idx]

    # Проверяем лимит
    allowed = await check_match_limit(callback.from_user.id)
    if not allowed:
        await callback.message.edit_text(
            "🚫 Дневной лимит матчей (3) исчерпан.\n\n"
            "Купите Premium для безлимитного доступа!",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⭐ Купить Premium (300 ₽)", callback_data="premium")],
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="matches")]
            ])
        )
        await callback.answer()
        return

    await callback.message.edit_text(
        f"⚽ <b>{match.get('name', '?')}</b>\n\n"
        f"🏳️ {match.get('country', '?')} — {match.get('league', '?')}\n\n"
        "Выберите вкладку:",
        reply_markup=match_detail_keyboard(idx)
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("tab_"))
async def show_tab(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    if len(parts) < 3:
        await callback.answer("Ошибка данных")
        return

    tab = parts[1]
    try:
        idx = int(parts[2])
    except ValueError:
        await callback.answer("Ошибка индекса")
        return

    mlist = matches_data.get("matches", [])
    if idx < 0 or idx >= len(mlist):
        await callback.answer("Матч не найден")
        return

    match = mlist[idx]
    labels = {
        "analitica": "🔬 Аналитика",
        "stats": "📈 Статистика",
        "times": "⏱ Таймы",
        "injuries": "🚑 Травмы",
        "forecast": "🔮 Прогноз",
    }
    label = labels.get(tab, "Нет данных")
    content = match.get(tab, "Данные не заполнены.")

    await callback.message.answer(
        f"<b>{label}</b>\n\n{content}",
        parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query(F.data == "premium")
async def premium(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "⭐ Premium — полный доступ к матчам, аналитике, статистике и прогнозам.\n\n"
        "Цена: 300 ₽ в месяц\n\n"
        "Оплата через ЮKassa",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="Оплатить 300 ₽",
                url="https://yoomoney.ru/quickpay/confirm.xml?receiver=your_kassa@mail.ru&sum=300&label=koefbot&formcomment=true"
            )],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")]
        ])
    )
    await callback.answer()


@dp.callback_query(F.data == "support")
async def support(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "🛠 Техподдержка\n\n"
        "Напишите ваше сообщение — оно будет отправлено Администрации.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")]
        ])
    )
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
    await message.answer(
        "✅ Ваше сообщение успешно отправлено Администрации!",
        reply_markup=main_keyboard()
    )
    await state.clear()


# ====================== АДМИН ПАНЕЛЬ ======================

@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    if str(message.from_user.id) not in admin_users:
        await message.answer("❌ Нет доступа!")
        return

    await message.answer("Админ-панель:", reply_markup=admin_keyboard())


@dp.callback_query(F.data == "admin_back")
async def admin_back(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа")
        return
    await callback.message.edit_text("Админ-панель:", reply_markup=admin_keyboard())
    await callback.answer()


@dp.callback_query(F.data == "add_match_start")
async def add_match_start(callback: types.CallbackQuery, state: FSMContext):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа")
        return
    await callback.message.edit_text(
        "➕ Добавление матча\n\nШаг 1/7: Введите страну:",
        reply_markup=admin_back_keyboard()
    )
    await state.set_state(AdminStates.add_match_country)
    await callback.answer()


@dp.message(AdminStates.add_match_country)
async def add_match_country(message: types.Message, state: FSMContext):
    await state.update_data(country=message.text.strip())
    await message.answer("Шаг 2/7: Введите лигу:", reply_markup=admin_back_keyboard())
    await state.set_state(AdminStates.add_match_league)


@dp.message(AdminStates.add_match_league)
async def add_match_league(message: types.Message, state: FSMContext):
    await state.update_data(league=message.text.strip())
    await message.answer("Шаг 3/7: Введите название матча:", reply_markup=admin_back_keyboard())
    await state.set_state(AdminStates.add_match_name)


@dp.message(AdminStates.add_match_name)
async def add_match_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await message.answer("Шаг 4/7: Введите аналитику:", reply_markup=admin_back_keyboard())
    await state.set_state(AdminStates.add_analitica)


@dp.message(AdminStates.add_analitica)
async def add_analitica(message: types.Message, state: FSMContext):
    await state.update_data(analitica=message.text)
    await message.answer("Шаг 5/7: Введите статистику:", reply_markup=admin_back_keyboard())
    await state.set_state(AdminStates.add_stats)


@dp.message(AdminStates.add_stats)
async def add_stats(message: types.Message, state: FSMContext):
    await state.update_data(stats=message.text)
    await message.answer("Шаг 6/7: Введите таймы:", reply_markup=admin_back_keyboard())
    await state.set_state(AdminStates.add_time)


@dp.message(AdminStates.add_time)
async def add_time(message: types.Message, state: FSMContext):
    await state.update_data(times=message.text)
    await message.answer("Шаг 7/7: Введите травмы:", reply_markup=admin_back_keyboard())
    await state.set_state(AdminStates.add_injuries)


@dp.message(AdminStates.add_injuries)
async def add_injuries(message: types.Message, state: FSMContext):
    await state.update_data(injuries=message.text)
    await message.answer("Финальный шаг: Введите прогноз:", reply_markup=admin_back_keyboard())
    await state.set_state(AdminStates.add_forecast)


@dp.message(AdminStates.add_forecast)
async def add_forecast(message: types.Message, state: FSMContext):
    data = await state.get_data()
    new_match = {
        "country": data.get("country", ""),
        "league": data.get("league", ""),
        "name": data.get("name", ""),
        "analitica": data.get("analitica", ""),
        "stats": data.get("stats", ""),
        "times": data.get("times", ""),
        "injuries": data.get("injuries", ""),
        "forecast": message.text,
    }
    matches_data.setdefault("matches", []).append(new_match)
    save_json(matches_file, matches_data)
    await message.answer(
        "✅ Матч успешно добавлен!",
        reply_markup=admin_keyboard()
    )
    await state.clear()


@dp.callback_query(F.data == "premium_admin")
async def premium_admin(callback: types.CallbackQuery, state: FSMContext):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа")
        return
    await callback.message.edit_text(
        "💰 Управление Premium\n\nВведите ID пользователя:",
        reply_markup=admin_back_keyboard()
    )
    await state.set_state(AdminStates.premium_user_id)
    await callback.answer()


@dp.message(AdminStates.premium_user_id)
async def premium_set(message: types.Message, state: FSMContext):
    uid = message.text.strip()
    if uid not in users:
        await message.answer("Пользователь не найден.", reply_markup=admin_keyboard())
        await state.clear()
        return

    current = users[uid].get("subscription", "Free")
    if current == "Premium":
        users[uid]["subscription"] = "Free"
        users[uid]["end_date"] = "2026-01-01"
        save_json(users_file, users)
        await message.answer(f"Premium снят с пользователя {uid}.", reply_markup=admin_keyboard())
    else:
        end = (datetime.now(tz) + timedelta(days=30)).strftime("%Y-%m-%d")
        users[uid]["subscription"] = "Premium"
        users[uid]["end_date"] = end
        save_json(users_file, users)
        await message.answer(
            f"Premium выдан пользователю {uid} до {end}.",
            reply_markup=admin_keyboard()
        )
    await state.clear()


@dp.callback_query(F.data == "delete_match_start")
async def delete_match_start(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа")
        return

    mlist = matches_data.get("matches", [])
    if not mlist:
        await callback.message.edit_text(
            "Матчей нет.",
            reply_markup=admin_back_keyboard()
        )
        await callback.answer()
        return

    kb = []
    for i, m in enumerate(mlist):
        kb.append([InlineKeyboardButton(
            text=f"🗑 {i+1}. {m.get('name', '?')}",
            callback_data=f"del_{i}"
        )])
    kb.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")])

    await callback.message.edit_text(
        "Выберите матч для удаления:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb)
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("del_"))
async def delete_match(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа")
        return

    try:
        idx = int(callback.data.split("_")[1])
    except ValueError:
        await callback.answer("Ошибка индекса")
        return

    mlist = matches_data.get("matches", [])
    if 0 <= idx < len(mlist):
        removed = mlist.pop(idx)
        save_json(matches_file, matches_data)
        await callback.message.edit_text(
            f"✅ Удалён: {removed.get('name', '?')}",
            reply_markup=admin_keyboard()
        )
    else:
        await callback.message.edit_text("Матч не найден.", reply_markup=admin_keyboard())
    await callback.answer()


@dp.callback_query(F.data == "support_messages")
async def support_messages(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа")
        return

    if not support:
        await callback.message.edit_text(
            "Сообщений поддержки нет.",
            reply_markup=admin_back_keyboard()
        )
        await callback.answer()
        return

    text = "📨 Сообщения поддержки:\n\n"
    for uid, msgs in support.items():
        for m in msgs[-5:]:  # последние 5 от каждого
            text += (
                f"👤 {m['name']} (ID: {m['id']})\n"
                f"📅 {m['date']}\n"
                f"💬 {m['text']}\n\n"
            )

    # Если текст слишком длинный — обрезаем
    if len(text) > 4000:
        text = text[:4000] + "\n... (обрезано)"

    await callback.message.edit_text(text, reply_markup=admin_back_keyboard())
    await callback.answer()


# ====================== ЗАПУСК ======================

async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
