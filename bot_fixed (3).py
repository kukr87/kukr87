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
import re

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

admin_users = {str(ADMIN_ID)}

matches_file = "matches.json"
users_file = "users.json"
support_file = "support.json"

tz = ZoneInfo("Europe/Moscow")


# ====================== JSON ======================
def load_json(file):
    if os.path.exists(file):
        try:
            with open(file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, ValueError):
            return {}
    return {}


def save_json(file, data):
    with open(file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


matches_data = load_json(matches_file)
if "matches" not in matches_data:
    matches_data["matches"] = []

users = load_json(users_file)
support = load_json(support_file)


# ====================== ПАРСИНГ ТЕКСТА ======================
def parse_match_text(text: str) -> dict:
    """Разбивает текст по жирным заголовкам на вкладки."""
    # Ищем все позиции жирных заголовков **текст** или <b>текст</b>
    pattern = re.compile(r'(?:\*\*(.+?)\*\*|<b>(.+?)</b>)')
    matches_found = list(pattern.finditer(text))

    tabs = {
        "analitica": "",
        "stats": "",
        "times": "",
        "injuries": "",
        "forecast": "",
    }

    # Ключевые слова для сопоставления заголовков с вкладками
    keywords = {
        "analitica": ["аналитик", "анализ", "aналит"],
        "stats": ["статистик", "стат", "xg", "xg"],
        "times": ["тайм", "таймы", "время"],
        "injuries": ["травм", "травмы", "состав", "дисквал"],
        "forecast": ["прогноз", "прогнозы", "рекоменд", "ставка", "исход"],
    }

    if not matches_found:
        # Если жирных заголовков нет — весь текст в аналитику
        tabs["analitica"] = text.strip()
        return tabs

    for i, m in enumerate(matches_found):
        # Получаем название заголовка
        title = m.group(1) or m.group(2) or ""
        title_lower = title.lower().strip()

        # Текст от конца этого заголовка до начала следующего (или конца текста)
        start = m.end()
        end = matches_found[i + 1].start() if i + 1 < len(matches_found) else len(text)
        content = text[start:end].strip()

        # Определяем, в какую вкладку положить
        target_key = None
        for key, words in keywords.items():
            if any(w in title_lower for w in words):
                target_key = key
                break

        if target_key:
            # Добавляем заголовок к содержимому
            tabs[target_key] = f"**{title}**\n{content}".strip()
        else:
            # Если не распознали — в аналитику
            if tabs["analitica"]:
                tabs["analitica"] += f"\n\n**{title}**\n{content}".strip()
            else:
                tabs["analitica"] = f"**{title}**\n{content}".strip()

    return tabs


# ====================== FSM ======================
class AdminStates(StatesGroup):
    add_match_name = State()
    add_match_country_league = State()
    add_match_text = State()
    delete_match_select = State()
    premium_add_id = State()
    premium_remove_id = State()
    support_reply = State()
    support_reply_target = State()


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
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"Подписка: {sub.get('subscription', 'Free')}", callback_data="sub_info")]
    ])
    if sub.get("subscription", "Free") == "Free":
        kb.inline_keyboard.append([InlineKeyboardButton(text="Купить Premium (300 ₽)", callback_data="premium")])
    return kb


def matches_keyboard():
    """Группирует матчи по 'Страна Лига' и показывает количество."""
    groups = {}
    for i, m in enumerate(matches_data["matches"]):
        key = m.get("country", "") + " " + m.get("league", "")
        groups.setdefault(key, []).append(i)

    kb = []
    for key, indices in groups.items():
        parts = key.split(" ", 1)
        country = parts[0] if parts else ""
        league = parts[1] if len(parts) > 1 else ""
        kb.append([InlineKeyboardButton(
            text=f"{country} — {league} ({len(indices)})",
            callback_data=f"group_{key}"
        )])

    return InlineKeyboardMarkup(inline_keyboard=kb or [[InlineKeyboardButton(text="Матчей пока нет", callback_data="no_matches")]])


def group_matches_keyboard(group_key: str):
    """Показывает матчи внутри выбранной группы."""
    kb = []
    for i, m in enumerate(matches_data["matches"]):
        key = m.get("country", "") + " " + m.get("league", "")
        if key == group_key:
            kb.append([InlineKeyboardButton(
                text=m.get("name", f"Матч {i+1}"),
                callback_data=f"match_{i}"
            )])
    kb.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="matches")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


def match_detail_keyboard(match_idx: int):
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
        [InlineKeyboardButton(text="🛠 Сообщения поддержки", callback_data="support_admin")]
    ])


def premium_admin_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Список пользователей", callback_data="premium_list")],
        [InlineKeyboardButton(text="➕ Выдать Premium по ID", callback_data="premium_add")],
        [InlineKeyboardButton(text="➕ Выдать Premium всем", callback_data="premium_add_all")],
        [InlineKeyboardButton(text="➖ Снять Premium по ID", callback_data="premium_remove")],
        [InlineKeyboardButton(text="➖ Снять Premium всем", callback_data="premium_remove_all")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")]
    ])


def support_admin_keyboard():
    """Список пользователей, написавших в поддержку."""
    kb = []
    for uid, msgs in support.items():
        if msgs:
            user_name = msgs[-1].get("name", "Неизвестно")
            count = len(msgs)
            kb.append([InlineKeyboardButton(
                text=f"{user_name} — {count} сообщ.",
                callback_data=f"support_view_{uid}"
            )])
    if not kb:
        kb.append([InlineKeyboardButton(text="Нет сообщений", callback_data="no_support")])
    kb.append([InlineKeyboardButton(text="🗑 Очистить все", callback_data="support_clear_all")])
    kb.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


def support_user_keyboard(uid: str):
    kb = [
        [InlineKeyboardButton(text="💬 Ответить", callback_data=f"support_reply_{uid}")],
        [InlineKeyboardButton(text="🗑 Очистить переписку", callback_data=f"support_clear_{uid}")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="support_admin")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)


def delete_match_keyboard():
    """Список матчей для удаления."""
    kb = []
    for i, m in enumerate(matches_data["matches"]):
        name = m.get("name", f"Матч {i+1}")
        country = m.get("country", "")
        league = m.get("league", "")
        kb.append([InlineKeyboardButton(
            text=f"🗑 {country} {league} — {name}",
            callback_data=f"del_match_{i}"
        )])
    if not kb:
        kb.append([InlineKeyboardButton(text="Матчей нет", callback_data="no_matches")])
    kb.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


# ====================== ПОДПИСКИ И ЛИМИТЫ ======================
async def get_user_subscription(user_id: int) -> dict:
    uid = str(user_id)
    if uid not in users:
        users[uid] = {"subscription": "Free", "end_date": "2026-01-01"}
        save_json(users_file, users)
    return users[uid]


async def check_match_limit(user_id: int, match_idx: int) -> bool:
    """Проверяет лимит: считает только новые матчи, не повторные просмотры."""
    sub = await get_user_subscription(user_id)
    if sub.get("subscription", "Free") == "Premium":
        return True

    today = datetime.now(tz).date()
    uid = str(user_id)

    if "last_match_date" not in users[uid]:
        users[uid]["last_match_date"] = str(today)
        users[uid]["viewed_matches"] = []
        save_json(users_file, users)

    last = datetime.strptime(users[uid]["last_match_date"], "%Y-%m-%d").date()
    if last != today:
        users[uid]["last_match_date"] = str(today)
        users[uid]["viewed_matches"] = []
        save_json(users_file, users)

    viewed = users[uid].get("viewed_matches", [])
    if match_idx in viewed:
        return True  # уже смотрел — лимит не тратится

    if len(viewed) >= 3:
        return False  # лимит исчерпан

    viewed.append(match_idx)
    users[uid]["viewed_matches"] = viewed
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


@dp.callback_query(F.data == "matches")
async def show_groups(callback: types.CallbackQuery):
    await callback.message.edit_text("📋 Выберите лигу:", reply_markup=matches_keyboard())
    await callback.answer()


@dp.callback_query(F.data.startswith("group_"))
async def show_group_matches(callback: types.CallbackQuery):
    group_key = callback.data[len("group_"):]
    await callback.message.edit_text(
        f"🏟 Матчи: {group_key}",
        reply_markup=group_matches_keyboard(group_key)
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("match_"))
async def show_match_details(callback: types.CallbackQuery):
    idx = int(callback.data.split("_")[1])
    matches_list = matches_data.get("matches", [])

    if idx >= len(matches_list):
        await callback.answer("Матч не найден")
        return

    match = matches_list[idx]

    # Проверяем лимит
    allowed = await check_match_limit(callback.from_user.id, idx)
    if not allowed:
        await callback.answer("❌ Лимит матчей исчерпан (3 в день). Купите Premium для безлимита!")
        return

    name = match.get("name", "Матч")
    country = match.get("country", "")
    league = match.get("league", "")

    await callback.message.edit_text(
        f"⚽ <b>{name}</b>\n"
        f"🏳️ {country} — {league}\n\n"
        "Выберите вкладку:",
        reply_markup=match_detail_keyboard(idx)
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("tab_"))
async def show_tab(callback: types.CallbackQuery):
    """Показывает содержимое вкладки матча."""
    parts = callback.data.split("_")
    tab_name = parts[1]
    match_idx = int(parts[2])
    matches_list = matches_data.get("matches", [])

    if match_idx >= len(matches_list):
        await callback.answer("Матч не найден")
        return

    match = matches_list[match_idx]
    text = match.get(tab_name, "")

    if not text:
        text = "Нет данных для этой вкладки."

    titles = {
        "analitica": "📊 Аналитика",
        "stats": "📈 Статистика",
        "times": "⏱ Таймы",
        "injuries": "🚑 Травмы",
        "forecast": "🔮 Прогноз",
    }

    await callback.message.answer(
        f"<b>{titles.get(tab_name, '')}</b>\n\n<tg-spoiler>{text}</tg-spoiler>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад к матчу", callback_data=f"match_{match_idx}")]
        ])
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
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="account")]
        ])
    )
    await callback.answer()


# ====================== ТЕХПОДДЕРЖКА (ПОЛЬЗОВАТЕЛЬ) ======================

@dp.callback_query(F.data == "support")
async def support_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "🛠 Техподдержка\n\n"
        "Напишите ваше сообщение — оно будет отправлено Администрации."
    )
    await state.set_state(SupportStates.get_message)
    await callback.answer()


@dp.message(SupportStates.get_message)
async def handle_support_message(message: types.Message, state: FSMContext):
    """Принимает сообщение пользователя в поддержку и сохраняет."""
    uid = str(message.chat.id)

    if uid not in support:
        support[uid] = []

    support[uid].append({
        "id": message.from_user.id,
        "name": message.from_user.full_name,
        "text": message.text,
        "date": datetime.now(tz).strftime("%Y-%m-%d %H:%M"),
        "from_admin": False
    })
    save_json(support_file, support)

    # Уведомляем админа
    try:
        admin_text = (
            f"📨 Новое сообщение в поддержку!\n\n"
            f"От: {message.from_user.full_name}\n"
            f"ID: <code>{message.from_user.id}</code>\n"
            f"Дата: {datetime.now(tz).strftime('%Y-%m-%d %H:%M')}\n\n"
            f"Текст:\n{message.text}"
        )
        await bot.send_message(ADMIN_ID, admin_text, parse_mode="HTML")
    except Exception:
        pass  # если админ не писал боту — может не получиться

    await state.clear()
    await message.answer(
        "✅ Ваше сообщение успешно отправлено Администрации!",
        reply_markup=main_keyboard()
    )


# ====================== АДМИН ПАНЕЛЬ ======================

@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    if str(message.from_user.id) not in admin_users:
        await message.answer("❌ Нет доступа!")
        return

    await message.answer(
        "🔧 Админ-панель",
        reply_markup=admin_keyboard()
    )


@dp.callback_query(F.data == "admin_back")
async def admin_back(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа")
        return
    await callback.message.edit_text("🔧 Админ-панель", reply_markup=admin_keyboard())
    await callback.answer()


# --- ДОБАВЛЕНИЕ МАТЧА ---

@dp.callback_query(F.data == "add_match_start")
async def add_match_start(callback: types.CallbackQuery, state: FSMContext):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа")
        return
    await callback.message.edit_text("Шаг 1/3: Введите название матча (например: Спартак — Зенит):")
    await state.set_state(AdminStates.add_match_name)
    await callback.answer()


@dp.message(AdminStates.add_match_name)
async def add_match_name(message: types.Message, state: FSMContext):
    if str(message.from_user.id) not in admin_users:
        return

    name = message.text.strip()
    if not name:
        await message.answer("Название не может быть пустым. Введите название матча:")
        return

    await state.update_data(name=name)
    await message.answer("Шаг 2/3: Введите страну и лигу через пробел (например: Россия РПЛ):")
    await state.set_state(AdminStates.add_match_country_league)


@dp.message(AdminStates.add_match_country_league)
async def add_match_country_league(message: types.Message, state: FSMContext):
    if str(message.from_user.id) not in admin_users:
        return

    parts = message.text.strip().split(" ", 1)
    if len(parts) < 2:
        await message.answer("Нужно два слова через пробел: страна и лига (например: Россия РПЛ). Попробуйте ещё раз:")
        return

    country = parts[0]
    league = parts[1]
    await state.update_data(country=country, league=league)
    await message.answer(
        "Шаг 3/3: Введите текст матча.\n\n"
        "Используйте жирные заголовки для разделения по вкладкам:\n"
        "**Аналитика** — текст аналитики\n"
        "**Статистика** — текст статистики\n"
        "**Таймы** — текст по таймам\n"
        "**Травмы** — текст по травмам\n"
        "**Прогноз** — текст прогноза\n\n"
        "Текст от одного жирного заголовка до следующего попадёт в соответствующую вкладку."
    )
    await state.set_state(AdminStates.add_match_text)


@dp.message(AdminStates.add_match_text)
async def add_match_text(message: types.Message, state: FSMContext):
    if str(message.from_user.id) not in admin_users:
        return

    raw_text = message.text
    data = await state.get_data()

    # Парсим текст по жирным заголовкам
    parsed = parse_match_text(raw_text)

    new_match = {
        "name": data.get("name", "Без названия"),
        "country": data.get("country", ""),
        "league": data.get("league", ""),
        "analitica": parsed["analitica"],
        "stats": parsed["stats"],
        "times": parsed["times"],
        "injuries": parsed["injuries"],
        "forecast": parsed["forecast"],
    }

    matches_data["matches"].append(new_match)
    save_json(matches_file, matches_data)

    # Показываем, что распределилось
    summary = "✅ Матч добавлен!\n\n"
    summary += f"Название: {new_match['name']}\n"
    summary += f"Страна: {new_match['country']}\n"
    summary += f"Лига: {new_match['league']}\n\n"
    summary += "Распределение по вкладкам:\n"
    for tab, label in [("analitica", "Аналитика"), ("stats", "Статистика"), ("times", "Таймы"), ("injuries", "Травмы"), ("forecast", "Прогноз")]:
        content = new_match[tab]
        length = len(content)
        preview = content[:80] + "..." if len(content) > 80 else content
        summary += f"• {label} ({length} симв.): {preview or '—'}\n"

    await state.clear()
    await message.answer(summary, reply_markup=admin_keyboard())


# --- УДАЛЕНИЕ МАТЧЕЙ ---

@dp.callback_query(F.data == "delete_match")
async def delete_match_menu(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа")
        return
    await callback.message.edit_text("Выберите матч для удаления:", reply_markup=delete_match_keyboard())
    await callback.answer()


@dp.callback_query(F.data.startswith("del_match_"))
async def delete_match(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа")
        return

    idx = int(callback.data[len("del_match_"):])
    matches_list = matches_data.get("matches", [])

    if idx < len(matches_list):
        name = matches_list[idx].get("name", f"Матч {idx+1}")
        del matches_list[idx]
        matches_data["matches"] = matches_list
        save_json(matches_file, matches_data)
        await callback.answer(f"Удалён: {name}")
        await callback.message.edit_text("Выберите матч для удаления:", reply_markup=delete_match_keyboard())
    else:
        await callback.answer("Матч не найден")


@dp.callback_query(F.data == "clear_all_matches")
async def clear_all_matches(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа")
        return
    matches_data["matches"] = []
    save_json(matches_file, matches_data)
    await callback.answer("Все матчи удалены!")
    await callback.message.edit_text("🔧 Админ-панель\n\n✅ Все матчи очищены.", reply_markup=admin_keyboard())


# --- УПРАВЛЕНИЕ PREMIUM ---

@dp.callback_query(F.data == "premium_admin")
async def premium_admin_menu(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа")
        return
    await callback.message.edit_text("💰 Управление Premium", reply_markup=premium_admin_keyboard())
    await callback.answer()


@dp.callback_query(F.data == "premium_list")
async def premium_list(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа")
        return

    if not users:
        await callback.answer("Нет пользователей")
        return

    text = "📋 Список пользователей:\n\n"
    for uid, data in users.items():
        sub = data.get("subscription", "Free")
        end = data.get("end_date", "—")
        name = data.get("name", "Неизвестно")
        # Если имя не сохранено, показываем просто ID
        text += f"• ID: <code>{uid}</code> | {sub} | до {end}\n"

    if len(text) > 4000:
        text = text[:4000] + "..."

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=premium_admin_keyboard())
    await callback.answer()


@dp.callback_query(F.data == "premium_add")
async def premium_add_start(callback: types.CallbackQuery, state: FSMContext):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа")
        return
    await callback.message.edit_text("Введите ID пользователя для выдачи Premium (на 30 дней):")
    await state.set_state(AdminStates.premium_add_id)
    await callback.answer()


@dp.message(AdminStates.premium_add_id)
async def premium_add_id(message: types.Message, state: FSMContext):
    if str(message.from_user.id) not in admin_users:
        return

    target_id = message.text.strip()
    end_date = (datetime.now(tz) + timedelta(days=30)).strftime("%Y-%m-%d")

    if target_id not in users:
        users[target_id] = {}

    users[target_id]["subscription"] = "Premium"
    users[target_id]["end_date"] = end_date
    save_json(users_file, users)

    await state.clear()
    await message.answer(f"✅ Premium выдан пользователю {target_id} до {end_date}", reply_markup=admin_keyboard())

    # Уведомляем пользователя
    try:
        await bot.send_message(int(target_id), "⭐ Вам выдан Premium на 30 дней!")
    except Exception:
        pass


@dp.callback_query(F.data == "premium_add_all")
async def premium_add_all(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа")
        return

    end_date = (datetime.now(tz) + timedelta(days=30)).strftime("%Y-%m-%d")
    count = 0
    for uid in users:
        users[uid]["subscription"] = "Premium"
        users[uid]["end_date"] = end_date
        count += 1

    save_json(users_file, users)
    await callback.answer(f"Premium выдан {count} пользователям!")
    await callback.message.edit_text(f"💰 Управление Premium\n\n✅ Premium выдан всем ({count} польз.)", reply_markup=premium_admin_keyboard())


@dp.callback_query(F.data == "premium_remove")
async def premium_remove_start(callback: types.CallbackQuery, state: FSMContext):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа")
        return
    await callback.message.edit_text("Введите ID пользователя для снятия Premium:")
    await state.set_state(AdminStates.premium_remove_id)
    await callback.answer()


@dp.message(AdminStates.premium_remove_id)
async def premium_remove_id(message: types.Message, state: FSMContext):
    if str(message.from_user.id) not in admin_users:
        return

    target_id = message.text.strip()

    if target_id in users:
        users[target_id]["subscription"] = "Free"
        users[target_id]["end_date"] = "2026-01-01"
        save_json(users_file, users)
        await state.clear()
        await message.answer(f"✅ Premium снят с пользователя {target_id}", reply_markup=admin_keyboard())
        try:
            await bot.send_message(int(target_id), "Ваша подписка Premium снята.")
        except Exception:
            pass
    else:
        await state.clear()
        await message.answer(f"❌ Пользователь {target_id} не найден.", reply_markup=admin_keyboard())


@dp.callback_query(F.data == "premium_remove_all")
async def premium_remove_all(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа")
        return

    count = 0
    for uid in users:
        users[uid]["subscription"] = "Free"
        users[uid]["end_date"] = "2026-01-01"
        count += 1

    save_json(users_file, users)
    await callback.answer(f"Premium снят с {count} пользователей!")
    await callback.message.edit_text(f"💰 Управление Premium\n\n✅ Premium снят со всех ({count} польз.)", reply_markup=premium_admin_keyboard())


# --- ТЕХПОДДЕРЖКА (АДМИН) ---

@dp.callback_query(F.data == "support_admin")
async def support_admin_menu(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа")
        return
    await callback.message.edit_text("🛠 Сообщения поддержки:", reply_markup=support_admin_keyboard())
    await callback.answer()


@dp.callback_query(F.data.startswith("support_view_"))
async def support_view(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа")
        return

    uid = callback.data[len("support_view_"):]
    msgs = support.get(uid, [])

    if not msgs:
        await callback.answer("Нет сообщений")
        return

    text = f"📨 Переписка с пользователем {uid}:\n\n"
    for m in msgs:
        sender = "👤 Пользователь" if not m.get("from_admin") else "🛡 Админ"
        text += f"{sender} ({m['date']}):\n{m['text']}\n\n"

    if len(text) > 4000:
        text = text[:4000] + "..."

    await callback.message.edit_text(text, reply_markup=support_user_keyboard(uid))
    await callback.answer()


@dp.callback_query(F.data.startswith("support_reply_"))
async def support_reply_start(callback: types.CallbackQuery, state: FSMContext):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа")
        return

    uid = callback.data[len("support_reply_"):]
    await state.set_state(AdminStates.support_reply)
    await state.update_data(reply_to=uid)
    await callback.message.edit_text(f"Введите ответ для пользователя {uid}:")
    await callback.answer()


@dp.message(AdminStates.support_reply)
async def support_reply_send(message: types.Message, state: FSMContext):
    if str(message.from_user.id) not in admin_users:
        return

    data = await state.get_data()
    target_uid = data.get("reply_to", "")

    if not target_uid:
        await state.clear()
        await message.answer("❌ Не удалось определить получателя.", reply_markup=admin_keyboard())
        return

    reply_text = message.text

    # Сохраняем ответ админа в переписку
    if target_uid not in support:
        support[target_uid] = []
    support[target_uid].append({
        "id": int(target_uid),
        "name": "Админ",
        "text": reply_text,
        "date": datetime.now(tz).strftime("%Y-%m-%d %H:%M"),
        "from_admin": True
    })
    save_json(support_file, support)

    # Отправляем пользователю
    try:
        await bot.send_message(int(target_uid), f"🛍 Ответ от техподдержки:\n\n{reply_text}")
        sent = True
    except Exception:
        sent = False

    await state.clear()
    if sent:
        await message.answer(f"✅ Ответ отправлен пользователю {target_uid}", reply_markup=admin_keyboard())
    else:
        await message.answer(f"⚠️ Не удалось отправить (возможно, пользователь не писал боту).", reply_markup=admin_keyboard())


@dp.callback_query(F.data.startswith("support_clear_"))
async def support_clear_user(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа")
        return

    uid = callback.data[len("support_clear_"):]
    if uid in support:
        del support[uid]
        save_json(support_file, support)

    await callback.answer("Переписка очищена!")
    await callback.message.edit_text("🛠 Сообщения поддержки:", reply_markup=support_admin_keyboard())


@dp.callback_query(F.data == "support_clear_all")
async def support_clear_all(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа")
        return

    support.clear()
    save_json(support_file, support)
    await callback.answer("Все сообщения удалены!")
    await callback.message.edit_text("🛠 Сообщения поддержки:\n\n✅ Все сообщения очищены.", reply_markup=support_admin_keyboard())


# --- ЗАГЛУШКИ ---

@dp.callback_query(F.data == "no_matches")
async def no_matches(callback: types.CallbackQuery):
    await callback.answer("Матчей пока нет")

@dp.callback_query(F.data == "no_support")
async def no_support(callback: types.CallbackQuery):
    await callback.answer("Нет сообщений")

@dp.callback_query(F.data == "sub_info")
async def sub_info(callback: types.CallbackQuery):
    sub = await get_user_subscription(callback.from_user.id)
    await callback.answer(f"Подписка: {sub.get('subscription', 'Free')} до {sub.get('end_date', '—')}")


# ====================== ЗАПУСК ======================

async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
