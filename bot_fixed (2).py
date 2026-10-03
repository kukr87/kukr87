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

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")

if not BOT_TOKEN or not ADMIN_ID:
    raise RuntimeError("Укажите BOT_TOKEN и ADMIN_ID в переменных окружения")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

admin_users = {str(ADMIN_ID)}  # строковые ID для корректного сравнения

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


# Структура matches_data:
# {
#   "matches": [
#     {"country": "Россия", "league": "РПЛ", "name": "Спартак — Зенит", "text": "текст матча"},
#     ...
#   ]
# }

matches_data = load_json(matches_file)
if "matches" not in matches_data or not isinstance(matches_data["matches"], list):
    matches_data["matches"] = []

users = load_json(users_file)
support = load_json(support_file)

tz = ZoneInfo("Europe/Moscow")


# ====================== FSM STATES ======================

class AdminStates(StatesGroup):
    add_match_name = State()
    add_match_league = State()
    add_match_text = State()
    remove_premium_id = State()
    add_premium_id = State()


class SupportStates(StatesGroup):
    get_message = State()


class AdminSupportStates(StatesGroup):
    reply_message = State()


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
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"Подписка: {sub['subscription']}", callback_data="sub_info")]
    ])
    if sub["subscription"] == "Free":
        kb.inline_keyboard.append([InlineKeyboardButton(text="Купить Premium (300 ₽)", callback_data="premium")])
    kb.inline_keyboard.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="main_menu")])
    return kb


def matches_keyboard():
    """Группировка матчей по 'Страна — Лига (кол-во)'"""
    groups = {}
    for m in matches_data["matches"]:
        key = f"{m['country']} — {m['league']}"
        groups[key] = groups.get(key, 0) + 1

    kb = []
    for key, count in groups.items():
        kb.append([InlineKeyboardButton(text=f"🏳️ {key} ({count})", callback_data=f"group_{key}")])

    if not kb:
        kb = [[InlineKeyboardButton(text="Матчей пока нет", callback_data="no_matches")]]

    kb.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


def group_matches_keyboard(country, league):
    """Список матчей внутри группы Страна+Лига"""
    kb = []
    for i, m in enumerate(matches_data["matches"]):
        if m["country"] == country and m["league"] == league:
            kb.append([InlineKeyboardButton(text=f"⚽ {m['name']}", callback_data=f"match_{i}")])

    if not kb:
        kb = [[InlineKeyboardButton(text="Матчей в этой группе нет", callback_data="no_matches")]]

    kb.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="matches")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


def match_detail_keyboard(match_idx):
    """Кнопки вкладок матча — несут индекс матча"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Аналитика", callback_data=f"tab_analitica_{match_idx}"),
         InlineKeyboardButton(text="📈 Статистика", callback_data=f"tab_stats_{match_idx}")],
        [InlineKeyboardButton(text="⏱ Таймы", callback_data=f"tab_times_{match_idx}"),
         InlineKeyboardButton(text="🚑 Травмы", callback_data=f"tab_injuries_{match_idx}")],
        [InlineKeyboardButton(text="🔮 Прогноз", callback_data=f"tab_forecast_{match_idx}")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="matches")]
    ])


def admin_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить матч", callback_data="add_match_start")],
        [InlineKeyboardButton(text="❌ Удалить матч", callback_data="delete_match")],
        [InlineKeyboardButton(text="🗑 Очистить все матчи", callback_data="clear_all_matches")],
        [InlineKeyboardButton(text="💰 Управление Premium", callback_data="premium_admin")],
        [InlineKeyboardButton(text="🛠 Сообщения поддержки", callback_data="admin_support")]
    ])


def premium_admin_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Список пользователей", callback_data="list_users")],
        [InlineKeyboardButton(text="➕ Выдать Premium по ID", callback_data="add_premium_start")],
        [InlineKeyboardButton(text="➕ Выдать Premium всем", callback_data="add_premium_all")],
        [InlineKeyboardButton(text="➖ Снять Premium по ID", callback_data="remove_premium_start")],
        [InlineKeyboardButton(text="➖ Снять Premium всем", callback_data="remove_premium_all")],
        [InlineKeyboardButton(text="⬅️ Назад в админ-панель", callback_data="admin_back")]
    ])


def delete_match_keyboard():
    """Список матчей с кнопками удаления"""
    kb = []
    for i, m in enumerate(matches_data["matches"]):
        kb.append([InlineKeyboardButton(
            text=f"🗑 {m['country']} — {m['league']} | {m['name']}",
            callback_data=f"del_{i}"
        )])
    if not kb:
        kb = [[InlineKeyboardButton(text="Матчей нет", callback_data="no_matches")]]
    kb.append([InlineKeyboardButton(text="⬅️ Назад в админ-панель", callback_data="admin_back")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


# ====================== ПОДПИСКИ И ЛИМИТЫ ======================

def get_user_subscription(user_id: int) -> dict:
    uid = str(user_id)
    if uid not in users:
        users[uid] = {"subscription": "Free", "end_date": "2026-01-01"}
        save_json(users_file, users)
    return users[uid]


async def check_match_limit(user_id: int, match_idx: int) -> bool:
    """
    Лимит: Free-пользователь может открыть 3 РАЗНЫХ матча в день.
    Повторное открытие того же матча — не тратит лимит.
    """
    sub = get_user_subscription(user_id)
    if sub["subscription"] == "Premium":
        return True

    today = datetime.now(tz).date()
    uid = str(user_id)

    # Инициализация на первый запуск
    if "last_match_date" not in users[uid]:
        users[uid]["last_match_date"] = str(today)
        users[uid]["viewed_matches"] = []
        save_json(users_file, users)

    last = datetime.strptime(users[uid]["last_match_date"], "%Y-%m-%d").date()
    if last != today:
        # Новый день — сбрасываем список просмотренных
        users[uid]["last_match_date"] = str(today)
        users[uid]["viewed_matches"] = []
        save_json(users_file, users)

    viewed = users[uid].get("viewed_matches", [])

    # Если матч уже просмотрен сегодня — не тратим лимит
    if match_idx in viewed:
        return True

    # Новый матч — проверяем лимит
    if len(viewed) >= 3:
        return False

    # Добавляем матч в просмотренные
    viewed.append(match_idx)
    users[uid]["viewed_matches"] = viewed
    save_json(users_file, users)
    return True


# ====================== ОБРАБОТЧИКИ ПОЛЬЗОВАТЕЛЯ ======================

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    get_user_subscription(message.from_user.id)
    await message.answer(
        "Доброго времени суток!\n\n"
        "Я твой помощник в мире футбола, собираю полную статистику команд (травмы, результаты, "
        "положение в турнирной таблице, xG, статистика по таймам, тренды и многое другое), "
        "анализирую и предоставляю наиболее вероятные исходы на событие.",
        reply_markup=main_keyboard()
    )


@dp.callback_query(F.data == "main_menu")
async def main_menu(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "Главное меню:",
        reply_markup=main_keyboard()
    )
    await callback.answer()


@dp.callback_query(F.data == "account")
async def account(callback: types.CallbackQuery):
    sub = get_user_subscription(callback.from_user.id)
    await callback.message.edit_text(
        f"👤 Твой аккаунт\n\n"
        f"ID: <code>{callback.from_user.id}</code>\n"
        f"Имя: {callback.from_user.first_name}\n"
        f"Подписка: <b>{sub['subscription']}</b>\n"
        f"Действует до: {sub.get('end_date', '—')}\n\n"
        "Бесплатно: 3 разных матча в сутки\n"
        "Premium: безлимит матчей каждый день",
        reply_markup=account_keyboard(sub)
    )
    await callback.answer()


@dp.callback_query(F.data == "sub_info")
async def sub_info(callback: types.CallbackQuery):
    await callback.answer("Информация о подписке — нажмите Купить Premium", show_alert=True)


@dp.callback_query(F.data == "no_matches")
async def no_matches(callback: types.CallbackQuery):
    await callback.answer("Нет данных", show_alert=True)


@dp.callback_query(F.data == "matches")
async def show_matches_groups(callback: types.CallbackQuery):
    await callback.message.edit_text("📋 Выберите лигу:", reply_markup=matches_keyboard())
    await callback.answer()


@dp.callback_query(F.data.startswith("group_"))
async def show_matches_in_group(callback: types.CallbackQuery):
    # group_Россия — РПЛ
    key = callback.data[len("group_"):]
    parts = key.split(" — ", 1)
    if len(parts) != 2:
        await callback.answer("Ошибка группировки", show_alert=True)
        return
    country, league = parts[0], parts[1]
    await callback.message.edit_text(
        f"🏟 {country} — {league}\n\nВыберите матч:",
        reply_markup=group_matches_keyboard(country, league)
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("match_"))
async def show_match_details(callback: types.CallbackQuery):
    idx = int(callback.data.split("_")[1])

    if idx < 0 or idx >= len(matches_data["matches"]):
        await callback.answer("Матч не найден", show_alert=True)
        return

    match = matches_data["matches"][idx]

    # Проверяем лимит — повторное открытие того же матча не тратит лимит
    allowed = await check_match_limit(callback.from_user.id, idx)
    if not allowed:
        await callback.answer(
            "Лимит бесплатных матчей исчерпан (3 разных матча в день). "
            "Оформите Premium для безлимита.",
            show_alert=True
        )
        return

    await callback.message.edit_text(
        f"⚽ <b>{match['name']}</b>\n"
        f"🏳️ {match['country']} — {match['league']}\n\n"
        f"Выберите вкладку:",
        reply_markup=match_detail_keyboard(idx)
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("tab_"))
async def show_tab(callback: types.CallbackQuery):
    """Показывает текст вкладки матча под спойлером"""
    parts = callback.data.split("_", 2)  # tab_analitica_0
    if len(parts) < 3:
        await callback.answer("Ошибка", show_alert=True)
        return

    tab_name = parts[1]
    match_idx = int(parts[2])

    if match_idx < 0 or match_idx >= len(matches_data["matches"]):
        await callback.answer("Матч не найден", show_alert=True)
        return

    match = matches_data["matches"][match_idx]
    text = match.get("text", "Нет данных")

    labels = {
        "analitica": "🔬 Аналитика",
        "stats": "📈 Статистика",
        "times": "⏱ Таймы",
        "injuries": "🚑 Травмы",
        "forecast": "🔮 Прогноз"
    }
    label = labels.get(tab_name, "📊")

    await callback.message.answer(
        f"<b>{label}</b>\n\n<tg-spoiler>{text}</tg-spoiler>",
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
            [InlineKeyboardButton(text="Оплатить 300 ₽", url="https://yoomoney.ru/quickpay/confirm.xml?receiver=your_kassa@mail.ru&sum=300&label=koefbot&formcomment=true")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="main_menu")]
        ])
    )
    await callback.answer()


@dp.callback_query(F.data == "support")
async def support(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "🛠 Техподдержка\n\nНапишите ваше сообщение — оно будет отправлено Администрации.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="main_menu")]
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

    await message.answer("Админ-панель /goal", reply_markup=admin_keyboard())


@dp.callback_query(F.data == "admin_back")
async def admin_back(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Админ-панель /goal", reply_markup=admin_keyboard())
    await callback.answer()


# --- ДОБАВЛЕНИЕ МАТЧА (3 шага) ---

@dp.callback_query(F.data == "add_match_start")
async def add_match_start(callback: types.CallbackQuery, state: FSMContext):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа")
        return
    await callback.message.edit_text("Введите название матча (например: Спартак — Зенит):")
    await state.set_state(AdminStates.add_match_name)
    await callback.answer()


@dp.message(AdminStates.add_match_name)
async def add_match_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await message.answer("Введите страну и лигу через пробел (например: Россия РПЛ):")
    await state.set_state(AdminStates.add_match_league)


@dp.message(AdminStates.add_match_league)
async def add_match_league(message: types.Message, state: FSMContext):
    parts = message.text.strip().split(maxsplit=1)
    if len(parts) != 2:
        await message.answer("Нужно ввести страну и лигу через пробел, например: Россия РПЛ\nПопробуйте ещё раз:")
        return
    await state.update_data(country=parts[0], league=parts[1])
    await message.answer("Введите текст матча (всё одним сообщением):")
    await state.set_state(AdminStates.add_match_text)


@dp.message(AdminStates.add_match_text)
async def add_match_text(message: types.Message, state: FSMContext):
    data = await state.get_data()
    new_match = {
        "country": data["country"],
        "league": data["league"],
        "name": data["name"],
        "text": message.text
    }
    matches_data["matches"].append(new_match)
    save_json(matches_file, matches_data)
    await message.answer(
        f"✅ Матч добавлен!\n\n"
        f"⚽ {new_match['name']}\n"
        f"🏳️ {new_match['country']} — {new_match['league']}\n\n"
        f"Текст: {new_match['text'][:100]}{'...' if len(new_match['text']) > 100 else ''}",
        reply_markup=admin_keyboard()
    )
    await state.clear()


# --- УДАЛЕНИЕ МАТЧА ---

@dp.callback_query(F.data == "delete_match")
async def delete_match_menu(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа")
        return
    await callback.message.edit_text("🗑 Выберите матч для удаления:", reply_markup=delete_match_keyboard())
    await callback.answer()


@dp.callback_query(F.data.startswith("del_"))
async def delete_match(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа")
        return
    idx = int(callback.data.split("_")[1])
    if 0 <= idx < len(matches_data["matches"]):
        removed = matches_data["matches"].pop(idx)
        save_json(matches_file, matches_data)
        await callback.message.edit_text(
            f"✅ Удалён: {removed['country']} — {removed['league']} | {removed['name']}",
            reply_markup=delete_match_keyboard()
        )
    await callback.answer()


@dp.callback_query(F.data == "clear_all_matches")
async def clear_all_matches(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа")
        return
    matches_data["matches"] = []
    save_json(matches_file, matches_data)
    await callback.message.edit_text("✅ Все матчи очищены!", reply_markup=admin_keyboard())
    await callback.answer()


# --- УПРАВЛЕНИЕ PREMIUM ---

@dp.callback_query(F.data == "premium_admin")
async def premium_admin(callback: types.CallbackQuery, state: FSMContext):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа")
        return
    await state.clear()
    await callback.message.edit_text("💰 Управление Premium", reply_markup=premium_admin_keyboard())
    await callback.answer()


@dp.callback_query(F.data == "list_users")
async def list_users(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа")
        return
    if not users:
        await callback.message.edit_text("Пользователей пока нет.", reply_markup=premium_admin_keyboard())
        await callback.answer()
        return
    text = "📋 Список пользователей:\n\n"
    for uid, info in users.items():
        name = info.get("subscription", "Free")
        end = info.get("end_date", "—")
        text += f"ID: <code>{uid}</code> | {name} | до {end}\n"
    await callback.message.edit_text(text, reply_markup=premium_admin_keyboard())
    await callback.answer()


@dp.callback_query(F.data == "add_premium_start")
async def add_premium_start(callback: types.CallbackQuery, state: FSMContext):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа")
        return
    await callback.message.edit_text("Введите ID пользователя для выдачи Premium:")
    await state.set_state(AdminStates.add_premium_id)
    await callback.answer()


@dp.message(AdminStates.add_premium_id)
async def add_premium_id(message: types.Message, state: FSMContext):
    uid = message.text.strip()
    end_date = (datetime.now(tz) + timedelta(days=30)).strftime("%Y-%m-%d")
    if uid not in users:
        users[uid] = {}
    users[uid]["subscription"] = "Premium"
    users[uid]["end_date"] = end_date
    save_json(users_file, users)
    await message.answer(f"✅ Premium выдан пользователю {uid} до {end_date}", reply_markup=premium_admin_keyboard())
    await state.clear()


@dp.callback_query(F.data == "add_premium_all")
async def add_premium_all(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа")
        return
    end_date = (datetime.now(tz) + timedelta(days=30)).strftime("%Y-%m-%d")
    for uid, info in users.items():
        info["subscription"] = "Premium"
        info["end_date"] = end_date
    save_json(users_file, users)
    await callback.message.edit_text(f"✅ Premium выдан всем пользователям до {end_date}", reply_markup=premium_admin_keyboard())
    await callback.answer()


@dp.callback_query(F.data == "remove_premium_start")
async def remove_premium_start(callback: types.CallbackQuery, state: FSMContext):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа")
        return
    await callback.message.edit_text("Введите ID пользователя для снятия Premium:")
    await state.set_state(AdminStates.remove_premium_id)
    await callback.answer()


@dp.message(AdminStates.remove_premium_id)
async def remove_premium_id(message: types.Message, state: FSMContext):
    uid = message.text.strip()
    if uid in users:
        users[uid]["subscription"] = "Free"
        users[uid]["end_date"] = "2026-01-01"
        save_json(users_file, users)
        await message.answer(f"✅ Premium снят с пользователя {uid}", reply_markup=premium_admin_keyboard())
    else:
        await message.answer("Пользователь не найден.", reply_markup=premium_admin_keyboard())
    await state.clear()


@dp.callback_query(F.data == "remove_premium_all")
async def remove_premium_all(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа")
        return
    for uid, info in users.items():
        info["subscription"] = "Free"
        info["end_date"] = "2026-01-01"
    save_json(users_file, users)
    await callback.message.edit_text("✅ Premium снят со всех пользователей", reply_markup=premium_admin_keyboard())
    await callback.answer()


# --- СООБЩЕНИЯ ПОДДЕРЖКИ В АДМИНКЕ ---

@dp.callback_query(F.data == "admin_support")
async def admin_support_menu(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа")
        return
    if not support:
        await callback.message.edit_text(
            "🛠 Сообщений поддержки пока нет.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")]
            ])
        )
        await callback.answer()
        return
    kb = []
    for uid, msgs in support.items():
        name = msgs[-1]["name"] if msgs else "—"
        kb.append([InlineKeyboardButton(
            text=f"💬 {name} ({len(msgs)} сообщ.)",
            callback_data=f"support_view_{uid}"
        )])
    kb.append([InlineKeyboardButton(text="🗑 Очистить все", callback_data="support_clear_all")])
    kb.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")])
    await callback.message.edit_text("🛠 Сообщения поддержки:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await callback.answer()


@dp.callback_query(F.data.startswith("support_view_"))
async def admin_support_view(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа")
        return
    uid = callback.data[len("support_view_"):]
    msgs = support.get(uid, [])
    if not msgs:
        await callback.answer("Сообщений нет", show_alert=True)
        return
    text = f"💬 Переписка с пользователем <code>{uid}</code>:\n\n"
    for m in msgs:
        text += f"👤 {m['name']}\n📅 {m['date']}\n📝 {m['text']}\n\n"
    kb = [
        [InlineKeyboardButton(text="💬 Ответить", callback_data=f"support_reply_{uid}")],
        [InlineKeyboardButton(text="🗑 Очистить переписку", callback_data=f"support_clear_{uid}")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_support")]
    ]
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await callback.answer()


@dp.callback_query(F.data.startswith("support_reply_"))
async def admin_support_reply(callback: types.CallbackQuery, state: FSMContext):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа")
        return
    uid = callback.data[len("support_reply_"):]
    await state.set_state(AdminSupportStates.reply_message)
    await state.update_data(reply_uid=uid)
    await callback.message.edit_text(f"💬 Введите ответ для пользователя <code>{uid}</code>:")
    await callback.answer()


@dp.message(AdminSupportStates.reply_message)
async def admin_support_reply_send(message: types.Message, state: FSMContext):
    data = await state.get_data()
    uid = data.get("reply_uid")
    try:
        await bot.send_message(int(uid), f"💬 Ответ от Администрации:\n\n{message.text}")
        await message.answer("✅ Ответ отправлен пользователю.", reply_markup=admin_keyboard())
    except Exception as e:
        await message.answer(f"❌ Не удалось отправить: {e}", reply_markup=admin_keyboard())
    await state.clear()


@dp.callback_query(F.data.startswith("support_clear_"))
async def admin_support_clear(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа")
        return
    uid = callback.data[len("support_clear_"):]
    if uid in support:
        del support[uid]
        save_json(support_file, support)
    await callback.message.edit_text(
        "✅ Переписка очищена.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_support")]
        ])
    )
    await callback.answer()


@dp.callback_query(F.data == "support_clear_all")
async def admin_support_clear_all(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа")
        return
    support.clear()
    save_json(support_file, support)
    await callback.message.edit_text(
        "✅ Все сообщения поддержки очищены.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_support")]
        ])
    )
    await callback.answer()


# ====================== ЗАПУСК ======================

async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
