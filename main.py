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
ADMIN_ID = int(os.getenv("ADMIN_ID"))

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

admin_users = {str(ADMIN_ID)}

matches_file = "matches.json"
users_file = "users.json"
support_file = "support.json"

tz = ZoneInfo("Europe/Moscow")

# ====================== ФЛАГИ СТРАН ======================
COUNTRY_FLAGS = {
    "Россия": "🇷🇺",
    "Англия": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
    "Испания": "🇪🇸",
    "Италия": "🇮🇹",
    "Германия": "🇩🇪",
    "Франция": "🇫🇷",
    "Португалия": "🇵🇹",
    "Нидерланды": "🇳🇱",
    "Бельгия": "🇧🇪",
    "Турция": "🇹🇷",
    "Греция": "🇬🇷",
    "Бразилия": "🇧🇷",
    "Аргентина": "🇦🇷",
    "США": "🇺🇸",
    "Мексика": "🇲🇽",
    "Украина": "🇺🇦",
    "Польша": "🇵🇱",
    "Шотландия": "🏴󠁧󠁢󠁳󠁣󠁴󠁿",
    "Уэльс": "🏴󠁧󠁢󠁷󠁬󠁳󠁿",
    "Ирландия": "🇮🇪",
    "Дания": "🇩🇰",
    "Швеция": "🇸🇪",
    "Норвегия": "🇳🇴",
    "Финляндия": "🇫🇮",
    "Австрия": "🇦🇹",
    "Швейцария": "🇨🇭",
    "Чехия": "🇨🇿",
    "Хорватия": "🇭🇷",
    "Сербия": "🇷🇸",
    "Румыния": "🇷🇴",
    "Венгрия": "🇭🇺",
    "Болгария": "🇧🇬",
    "Япония": "🇯🇵",
    "Южная Корея": "🇰🇷",
    "Китай": "🇨🇳",
    "Саудовская Аравия": "🇸🇦",
    "ОАЭ": "🇦🇪",
    "Катар": "🇶🇦",
    "Египет": "🇪🇬",
    "Марокко": "🇲🇦",
    "Нигерия": "🇳🇬",
    "Сенегал": "🇸🇳",
    "Уругвай": "🇺🇾",
    "Чили": "🇨🇱",
    "Колумбия": "🇨🇴",
    "Перу": "🇵🇪",
    "Эквадор": "🇪🇨",
    "Канада": "🇨🇦",
    "Австралия": "🇦🇺",
    "Индия": "🇮🇳",
    "Казахстан": "🇰🇿",
    "Узбекистан": "🇺🇿",
    "Азербайджан": "🇦🇿",
    "Грузия": "🇬🇪",
    "Армения": "🇦🇲",
    "Беларусь": "🇧🇾",
    "Молдова": "🇲🇩",
    "Латвия": "🇱🇻",
    "Литва": "🇱🇹",
    "Эстония": "🇪🇪",
    "Словакия": "🇸🇰",
    "Словения": "🇸🇮",
    "Черногория": "🇲🇪",
    "Албания": "🇦🇱",
    "Израиль": "🇮🇱",
    "Кипр": "🇨🇾",
    "Исландия": "🇮🇸",
}

def get_flag(country: str) -> str:
    return COUNTRY_FLAGS.get(country.strip(), "🏳️")

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

if "matches" not in matches_data:
    matches_data["matches"] = []

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
    kb = []
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
        country = group_matches[0]["country"]
        flag = get_flag(country)
        count = len(group_matches)
        kb.append([InlineKeyboardButton(text=f"{flag} {group_name} ({count})", callback_data=f"group_{group_name}")])

    if not kb:
        kb = [[InlineKeyboardButton(text="Матчей пока нет", callback_data="no_matches")]]
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def back_keyboard(callback_data="matches"):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data=callback_data)]
    ])

def admin_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить матч", callback_data="add_match_start")],
        [InlineKeyboardButton(text="🗑 Удалить матч / Очистить все", callback_data="delete_match_menu")],
        [InlineKeyboardButton(text="💰 Управление Premium", callback_data="premium_admin_menu")],
        [InlineKeyboardButton(text="🛠 Сообщения поддержки", callback_data="support_admin_menu")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")]
    ])

def premium_admin_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Список пользователей", callback_data="premium_list")],
        [InlineKeyboardButton(text="➕ Выдать Premium по ID", callback_data="premium_give_id_start")],
        [InlineKeyboardButton(text="➕ Выдать Premium всем", callback_data="premium_give_all")],
        [InlineKeyboardButton(text="➖ Снять Premium по ID", callback_data="premium_remove_id_start")],
        [InlineKeyboardButton(text="➖ Снять Premium всем", callback_data="premium_remove_all")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")]
    ])

# ====================== ВСПОМОГАТЕЛЬНЫЕ ======================

async def get_user_subscription(user_id: int) -> dict:
    uid = str(user_id)
    if uid not in users:
        users[uid] = {
            "subscription": "Free",
            "end_date": "",
            "viewed_matches": [],
            "last_check_date": ""
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
        pass

# ====================== STATES ======================

class SupportStates(StatesGroup):
    waiting_message = State()

class AdminStates(StatesGroup):
    add_match_name = State()
    add_country_league = State()
    add_text = State()
    premium_give_id = State()
    premium_remove_id = State()
    reply_support = State()

# ====================== ГЛАВНОЕ МЕНЮ ======================

@dp.callback_query(F.data == "main_menu")
async def main_menu(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "Доброго времени суток!\n\n"
        "Я твой помощник в мире футбола, собираю статистику, анализирую и предоставляю прогнозы.",
        reply_markup=main_keyboard()
    )
    await callback.answer()

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await get_user_subscription(message.from_user.id)
    await message.answer(
        "Доброго времени суток!\n\n"
        "Я твой помощник в мире футбола, собираю статистику, анализирую и предоставляю прогнозы.",
        reply_markup=main_keyboard()
    )

# ====================== АККАУНТ ======================

@dp.callback_query(F.data == "account")
async def account(callback: types.CallbackQuery):
    sub = await get_user_subscription(callback.from_user.id)
    tariff = "⭐ Premium" if sub["subscription"] == "Premium" else "🆓 Free"
    text = (
        f"👤 Аккаунт\n\n"
        f"ID: <code>{callback.from_user.id}</code>\n"
        f"Имя: {callback.from_user.first_name}\n"
        f"Тариф: {tariff}"
    )
    await callback.message.edit_text(text, reply_markup=account_keyboard(sub), parse_mode="HTML")
    await callback.answer()

# ====================== МАТЧИ ======================

@dp.callback_query(F.data == "matches")
async def show_matches(callback: types.CallbackQuery):
    await callback.message.edit_text("📋 Выберите группу (страна — лига):", reply_markup=matches_keyboard())
    await callback.answer()

@dp.callback_query(F.data.startswith("group_"))
async def show_group_matches(callback: types.CallbackQuery):
    group_name = callback.data.replace("group_", "", 1)
    country, league = group_name.split(" — ")

    all_matches = matches_data.get("matches", [])
    group_matches = []
    for idx, m in enumerate(all_matches):
        if m["country"] == country and m["league"] == league:
            group_matches.append((idx, m))

    if not group_matches:
        await callback.message.edit_text("В этой группе матчей нет.", reply_markup=back_keyboard("matches"))
        await callback.answer()
        return

    flag = get_flag(country)
    text = f"{flag} {group_name}\n\n"
    kb_buttons = []
    for i, (global_idx, m) in enumerate(group_matches):
        text += f"{i+1}. {m['name']}\n"
        kb_buttons.append([InlineKeyboardButton(text=f"{i+1}. {m['name']}", callback_data=f"match_{global_idx}")])

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
        f"{flag} Страна: {match['country']}\n"
        f"🏆 Лига: {match['league']}\n\n"
        f"{match['text']}"
    )

    await callback.message.edit_text(text, reply_markup=back_keyboard("matches"), parse_mode="HTML")
    await callback.answer()

# ====================== PREMIUM ======================

@dp.callback_query(F.data == "premium")
async def premium_info(callback: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Оплатить 300 ₽", url="https://yoomoney.ru/quickpay/confirm.xml?receiver=your_kassa@mail.ru&sum=300&label=koefbot&formcomment=true")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")]
    ])
    await callback.message.edit_text(
        "⭐ Premium — полный доступ к матчам и аналитике.\n\n"
        "Цена: 300 ₽ в месяц\n\n"
        "Оплата через ЮKassa",
        reply_markup=kb
    )
    await callback.answer()

# ====================== ТЕХПОДДЕРЖКА ======================

@dp.callback_query(F.data == "support")
async def support_start(callback: types.CallbackQuery, state: FSMContext):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")]
    ])
    await callback.message.edit_text("🛠 Техподдержка — напишите сообщение (кратко суть):", reply_markup=kb)
    await state.set_state(SupportStates.waiting_message)
    await callback.answer()

@dp.message(SupportStates.waiting_message)
async def handle_support_message(message: types.Message, state: FSMContext):
    uid = str(message.from_user.id)
    user_name = message.from_user.full_name or "Без имени"
    text_msg = message.text or ""

    if not text_msg.strip():
        await message.answer("Пожалуйста, отправьте текстовое сообщение.")
        return

    if uid not in support:
        support[uid] = {"name": user_name, "messages": []}

    support[uid]["name"] = user_name
    support[uid]["messages"].append({
        "from": "user",
        "text": text_msg,
        "date": datetime.now(tz).strftime("%Y-%m-%d %H:%M")
    })
    save_json(support_file, support)

    await notify_admin_support(message.from_user.id, user_name, text_msg)

    await message.answer("✅ Ваше сообщение успешно отправлено Администрации!", reply_markup=main_keyboard())
    await state.clear()

# ====================== АДМИН ПАНЕЛЬ ======================

@dp.message(Command("admin"))
async def admin_panel(message: types.Message, state: FSMContext):
    if str(message.from_user.id) not in admin_users:
        await message.answer("❌ Нет доступа!")
        return
    await state.clear()
    await message.answer("Админ-панель", reply_markup=admin_keyboard())

@dp.callback_query(F.data == "admin_panel")
async def admin_panel_callback(callback: types.CallbackQuery, state: FSMContext):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    await state.clear()
    await callback.message.edit_text("Админ-панель", reply_markup=admin_keyboard())
    await callback.answer()

# --- Добавление матча ---

@dp.callback_query(F.data == "add_match_start")
async def add_match_start(callback: types.CallbackQuery, state: FSMContext):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")]
    ])
    await callback.message.edit_text("Шаг 1/3: Введите название команд (например: Спартак — Зенит):", reply_markup=kb)
    await state.set_state(AdminStates.add_match_name)
    await callback.answer()

@dp.message(AdminStates.add_match_name)
async def add_match_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")]
    ])
    await message.answer("Шаг 2/3: Страна и лига (через пробел, например: Россия РПЛ):", reply_markup=kb)
    await state.set_state(AdminStates.add_country_league)

@dp.message(AdminStates.add_country_league)
async def add_country_league(message: types.Message, state: FSMContext):
    parts = message.text.strip().split(maxsplit=1)
    if len(parts) < 2:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")]
        ])
        await message.answer("Пожалуйста, введите страну и лигу через пробел (например: Россия РПЛ).", reply_markup=kb)
        return
    country, league = parts[0], parts[1]
    await state.update_data(country=country, league=league)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")]
    ])
    await message.answer("Шаг 3/3: Введите полный текст матча (одним сообщением):", reply_markup=kb)
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

    flag = get_flag(new_match["country"])
    await message.answer(
        f"✅ Матч добавлен!\n\n"
        f"Название: {new_match['name']}\n"
        f"Группа: {flag} {new_match['country']} — {new_match['league']}\n"
        f"Текст сохранён целиком.",
        reply_markup=admin_keyboard()
    )
    await state.clear()

# --- Удаление матчей ---

@dp.callback_query(F.data == "delete_match_menu")
async def delete_match_menu(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return

    all_matches = matches_data.get("matches", [])
    kb = []
    for i, m in enumerate(all_matches):
        kb.append([InlineKeyboardButton(text=f"❌ {m['name']} ({m['country']} — {m['league']})", callback_data=f"del_match_{i}")])

    kb.append([InlineKeyboardButton(text="🗑 Очистить все матчи", callback_data="del_all_matches")])
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")])

    if not all_matches:
        text = "Матчей нет."
    else:
        text = "Выберите матч для удаления:"

    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await callback.answer()

@dp.callback_query(F.data.startswith("del_match_"))
async def delete_one_match(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    idx = int(callback.data.replace("del_match_", ""))
    all_matches = matches_data.get("matches", [])
    if idx < len(all_matches):
        removed = all_matches.pop(idx)
        save_json(matches_file, matches_data)
        await callback.answer(f"Удалён: {removed['name']}", show_alert=True)
    await delete_match_menu(callback)

@dp.callback_query(F.data == "del_all_matches")
async def delete_all_matches(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    matches_data["matches"] = []
    save_json(matches_file, matches_data)
    await callback.answer("Все матчи удалены!", show_alert=True)
    await delete_match_menu(callback)

# --- Управление Premium ---

@dp.callback_query(F.data == "premium_admin_menu")
async def premium_admin_menu(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    await callback.message.edit_text("💰 Управление Premium", reply_markup=premium_admin_keyboard())
    await callback.answer()

@dp.callback_query(F.data == "premium_list")
async def premium_list(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    if not users:
        await callback.answer("Пользователей нет", show_alert=True)
        return

    text = "📋 Список пользователей:\n\n"
    for uid, data in users.items():
        sub = data.get("subscription", "Free")
        end = data.get("end_date", "")
        text += f"ID: <code>{uid}</code> | {sub} | до {end}\n"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="premium_admin_menu")]
    ])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "premium_give_id_start")
async def premium_give_id_start(callback: types.CallbackQuery, state: FSMContext):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="premium_admin_menu")]
    ])
    await callback.message.edit_text("Введите ID пользователя для выдачи Premium (на 30 дней):", reply_markup=kb)
    await state.set_state(AdminStates.premium_give_id)
    await callback.answer()

@dp.message(AdminStates.premium_give_id)
async def premium_give_id(message: types.Message, state: FSMContext):
    uid = message.text.strip()
    if uid not in users:
        users[uid] = {"subscription": "Free", "end_date": "", "viewed_matches": [], "last_check_date": ""}
    end_date = (datetime.now(tz) + timedelta(days=30)).strftime("%Y-%m-%d")
    users[uid]["subscription"] = "Premium"
    users[uid]["end_date"] = end_date
    save_json(users_file, users)
    await message.answer(f"✅ Premium выдан пользователю {uid} до {end_date}.", reply_markup=premium_admin_keyboard())
    await state.clear()

@dp.callback_query(F.data == "premium_give_all")
async def premium_give_all(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    end_date = (datetime.now(tz) + timedelta(days=30)).strftime("%Y-%m-%d")
    for uid in users:
        users[uid]["subscription"] = "Premium"
        users[uid]["end_date"] = end_date
    save_json(users_file, users)
    await callback.answer(f"✅ Premium выдан всем ({len(users)} чел.) до {end_date}!", show_alert=True)

@dp.callback_query(F.data == "premium_remove_id_start")
async def premium_remove_id_start(callback: types.CallbackQuery, state: FSMContext):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="premium_admin_menu")]
    ])
    await callback.message.edit_text("Введите ID пользователя для снятия Premium:", reply_markup=kb)
    await state.set_state(AdminStates.premium_remove_id)
    await callback.answer()

@dp.message(AdminStates.premium_remove_id)
async def premium_remove_id(message: types.Message, state: FSMContext):
    uid = message.text.strip()
    if uid in users:
        users[uid]["subscription"] = "Free"
        users[uid]["end_date"] = ""
        save_json(users_file, users)
        await message.answer(f"✅ Premium снят с пользователя {uid}.", reply_markup=premium_admin_keyboard())
    else:
        await message.answer("Пользователь не найден.", reply_markup=premium_admin_keyboard())
    await state.clear()

@dp.callback_query(F.data == "premium_remove_all")
async def premium_remove_all(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    for uid in users:
        users[uid]["subscription"] = "Free"
        users[uid]["end_date"] = ""
    save_json(users_file, users)
    await callback.answer(f"✅ Premium снят со всех ({len(users)} чел.)!", show_alert=True)

# --- Техподдержка (админ) ---

@dp.callback_query(F.data == "support_admin_menu")
async def support_admin_menu(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return

    if not support:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")]
        ])
        await callback.message.edit_text("Сообщений поддержки нет.", reply_markup=kb)
        await callback.answer()
        return

    text = "🛠 Сообщения поддержки:\n\n"
    kb = []
    for uid, data in support.items():
        name = data.get("name", "—")
        count = len(data.get("messages", []))
        text += f"👤 {name} (ID: <code>{uid}</code>) — {count} сообщ.\n"
        kb.append([InlineKeyboardButton(text=f"{name} ({count} сообщ.)", callback_data=f"support_view_{uid}")])

    kb.append([InlineKeyboardButton(text="🗑 Очистить все", callback_data="support_clear_all")])
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")])

    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data.startswith("support_view_"))
async def support_view(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    uid = callback.data.replace("support_view_", "", 1)

    if uid not in support:
        await callback.answer("Переписка не найдена", show_alert=True)
        return

    data = support[uid]
    name = data.get("name", "—")
    messages = data.get("messages", [])

    text = f"🛠 Переписка с {name} (ID: <code>{uid}</code>):\n\n"
    for msg in messages:
        sender = "👤 Пользователь" if msg["from"] == "user" else "🛡 Админ"
        text += f"{sender} ({msg['date']}):\n{msg['text']}\n\n"

    kb = [
        [InlineKeyboardButton(text="💬 Ответить", callback_data=f"support_reply_{uid}")],
        [InlineKeyboardButton(text="🗑 Очистить переписку", callback_data=f"support_clear_{uid}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="support_admin_menu")]
    ]
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data.startswith("support_reply_"))
async def support_reply_start(callback: types.CallbackQuery, state: FSMContext):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    uid = callback.data.replace("support_reply_", "", 1)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data=f"support_view_{uid}")]
    ])
    await callback.message.edit_text(f"Введите ответ для пользователя {uid}:", reply_markup=kb)
    await state.set_state(AdminStates.reply_support)
    await state.update_data(reply_uid=uid)
    await callback.answer()

@dp.message(AdminStates.reply_support)
async def support_reply_send(message: types.Message, state: FSMContext):
    data = await state.get_data()
    uid = data.get("reply_uid")
    reply_text = message.text

    if uid not in support:
        support[uid] = {"name": "—", "messages": []}

    support[uid]["messages"].append({
        "from": "admin",
        "text": reply_text,
        "date": datetime.now(tz).strftime("%Y-%m-%d %H:%M")
    })
    save_json(support_file, support)

    try:
        await bot.send_message(int(uid), f"🛡 Ответ от Администрации:\n\n{reply_text}")
    except Exception:
        pass

    await message.answer("✅ Ответ отправлен пользователю.", reply_markup=admin_keyboard())
    await state.clear()

@dp.callback_query(F.data.startswith("support_clear_"))
async def support_clear_one(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    uid = callback.data.replace("support_clear_", "", 1)
    if uid in support:
        del support[uid]
        save_json(support_file, support)
    await callback.answer("Переписка очищена", show_alert=True)
    await support_admin_menu(callback)

@dp.callback_query(F.data == "support_clear_all")
async def support_clear_all(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    support.clear()
    save_json(support_file, support)
    await callback.answer("Все сообщения очищены", show_alert=True)
    await support_admin_menu(callback)

# --- Заглушки ---

@dp.callback_query(F.data == "no_matches")
async def no_matches(callback: types.CallbackQuery):
    await callback.answer("Матчей пока нет", show_alert=True)

@dp.callback_query(F.data == "sub_info")
async def sub_info(callback: types.CallbackQuery):
    await callback.answer()

# ====================== ЗАПУСК ======================

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
