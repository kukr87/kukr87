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

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

admin_users = {str(ADMIN_ID)} if ADMIN_ID else set()

matches_file = "matches.json"
users_file = "users.json"
support_file = "support.json"

tz = ZoneInfo("Europe/Moscow")


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
users = load_json(users_file)
support = load_json(support_file)

if "matches" not in matches_data:
    matches_data["matches"] = []


class AddMatchStates(StatesGroup):
    name = State()
    country_league = State()
    text = State()


class SupportStates(StatesGroup):
    get_message = State()


class PremiumAdminStates(StatesGroup):
    add_by_id = State()
    remove_by_id = State()


class SupportReplyStates(StatesGroup):
    reply = State()


# ===================== КЛАВИАТУРЫ =====================

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
    kb.append([InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_main")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


def matches_keyboard():
    kb = []
    seen = set()
    for m in matches_data.get("matches", []):
        key = (m.get("country", ""), m.get("league", ""))
        if key not in seen:
            seen.add(key)
            kb.append([InlineKeyboardButton(
                text=f"🏳️ {m['country']} — {m['league']}",
                callback_data=f"league_{m['country']}_{m['league']}"
            )])
    if not kb:
        kb = [[InlineKeyboardButton(text="Матчей пока нет", callback_data="no_matches")]]
    kb.append([InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_main")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


def match_list_keyboard(country, league):
    kb = []
    idx = 0
    for m in matches_data.get("matches", []):
        if m.get("country") == country and m.get("league") == league:
            kb.append([InlineKeyboardButton(
                text=f"{m['name']}",
                callback_data=f"match_{idx}"
            )])
        idx += 1
    if not kb:
        kb = [[InlineKeyboardButton(text="Матчей нет", callback_data="no_matches")]]
    kb.append([InlineKeyboardButton(text="◀️ Назад", callback_data="matches")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


def match_detail_keyboard(idx):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Аналитика", callback_data=f"tab_text_{idx}"),
         InlineKeyboardButton(text="◀️ Назад", callback_data="matches")]
    ])


def admin_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить матч", callback_data="add_match_start")],
        [InlineKeyboardButton(text="🗑 Удалить матч", callback_data="delete_match")],
        [InlineKeyboardButton(text="💰 Управление Premium", callback_data="premium_admin")],
        [InlineKeyboardButton(text="🛠 Сообщения поддержки", callback_data="support_admin")],
        [InlineKeyboardButton(text="◀️ Выйти", callback_data="back_to_main")]
    ])


def premium_admin_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Список пользователей", callback_data="premium_list")],
        [InlineKeyboardButton(text="➕ Выдать Premium по ID", callback_data="premium_add_id")],
        [InlineKeyboardButton(text="➕ Выдать Premium всем", callback_data="premium_add_all")],
        [InlineKeyboardButton(text="➖ Снять Premium по ID", callback_data="premium_remove_id")],
        [InlineKeyboardButton(text="➖ Снять Premium всем", callback_data="premium_remove_all")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")]
    ])


def is_admin(user_id):
    return str(user_id) in admin_users


# ===================== ПОЛЬЗОВАТЕЛИ =====================

async def get_user_subscription(user_id: int) -> dict:
    uid = str(user_id)
    if uid not in users:
        users[uid] = {"subscription": "Free", "end_date": "2026-01-01"}
        save_json(users_file, users)
    return users[uid]


async def check_match_limit(user_id: int) -> bool:
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


# ===================== /start =====================

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


# ===================== АККАУНТ =====================

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


@dp.callback_query(F.data == "sub_info")
async def sub_info(callback: types.CallbackQuery):
    await callback.answer("Информация о подписке", show_alert=True)


# ===================== МАТЧИ =====================

@dp.callback_query(F.data == "matches")
async def show_leagues(callback: types.CallbackQuery):
    await callback.message.edit_text("📋 Выберите лигу:", reply_markup=matches_keyboard())
    await callback.answer()


@dp.callback_query(F.data.startswith("league_"))
async def show_matches_in_league(callback: types.CallbackQuery):
    parts = callback.data.split("_", 2)
    if len(parts) < 3:
        await callback.answer("Ошибка")
        return
    country = parts[1]
    league = parts[2]
    await callback.message.edit_text(
        f"🏟 {country} — {league}\n\nВыберите матч:",
        reply_markup=match_list_keyboard(country, league)
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("match_"))
async def show_match_details(callback: types.CallbackQuery):
    idx = int(callback.data.split("_")[1])
    matches_list = matches_data.get("matches", [])

    if idx < 0 or idx >= len(matches_list):
        await callback.message.edit_text("Матч не найден.")
        await callback.answer()
        return

    allowed = await check_match_limit(callback.from_user.id)
    if not allowed:
        await callback.message.edit_text(
            "❌ Дневной лимит матчей исчерпан (3 в сутки).\n"
            "Оформите Premium для безлимитного доступа.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⭐ Premium", callback_data="premium")],
                [InlineKeyboardButton(text="◀️ Назад", callback_data="matches")]
            ])
        )
        await callback.answer()
        return

    m = matches_list[idx]
    await callback.message.edit_text(
        f"⚽ <b>{m['name']}</b>\n🏳️ {m.get('country', '')} — {m.get('league', '')}\n\n"
        f"Нажмите кнопку ниже, чтобы посмотреть аналитику:",
        reply_markup=match_detail_keyboard(idx)
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("tab_text_"))
async def show_match_text(callback: types.CallbackQuery):
    idx = int(callback.data.split("_")[2])
    matches_list = matches_data.get("matches", [])
    if idx < 0 or idx >= len(matches_list):
        await callback.answer("Матч не найден")
        return

    m = matches_list[idx]
    text = m.get("text", "Нет данных")
    await callback.message.answer(
        f"📊 <b>{m['name']}</b>\n\n<tg-spoiler>{text}</tg-spoiler>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data=f"match_{idx}")]
        ])
    )
    await callback.answer()


@dp.callback_query(F.data == "no_matches")
async def no_matches(callback: types.CallbackQuery):
    await callback.answer("Матчей пока нет")


# ===================== PREMIUM (пользователь) =====================

@dp.callback_query(F.data == "premium")
async def premium(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "⭐ Premium — полный доступ к матчам, аналитике, статистике и прогнозам.\n\n"
        "Цена: 300 ₽ в месяц\n\n"
        "Оплата через ЮKassa",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Оплатить 300 ₽", url="https://yoomoney.ru/quickpay/confirm.xml?receiver=your_kassa@mail.ru&sum=300&label=koefbot&formcomment=true")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_main")]
        ])
    )
    await callback.answer()


# ===================== ТЕХПОДДЕРЖКА =====================

@dp.callback_query(F.data == "support")
async def support_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "🛠 Техподдержка\n\nНапишите ваше сообщение одним сообщением:"
    )
    await state.set_state(SupportStates.get_message)
    await callback.answer()


@dp.message(SupportStates.get_message)
async def handle_support_message(message: types.Message, state: FSMContext):
    uid = str(message.from_user.id)
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


# ===================== АДМИН ПАНЕЛЬ =====================

@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ Нет доступа!")
        return
    await message.answer("Админ-панель /goal", reply_markup=admin_keyboard())


@dp.callback_query(F.data == "admin_back")
async def admin_back(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа")
        return
    await callback.message.edit_text("Админ-панель /goal", reply_markup=admin_keyboard())
    await callback.answer()


@dp.callback_query(F.data == "back_to_main")
async def back_to_main(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "Главное меню:",
        reply_markup=main_keyboard()
    )
    await callback.answer()


# ===================== ДОБАВЛЕНИЕ МАТЧА (3 шага) =====================

@dp.callback_query(F.data == "add_match_start")
async def add_match_start(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа")
        return
    await callback.message.edit_text("Шаг 1/3 — Введите название матча (например: Спартак — Зенит):")
    await state.set_state(AddMatchStates.name)
    await callback.answer()


@dp.message(AddMatchStates.name)
async def add_match_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await message.answer("Шаг 2/3 — Введите страну и лигу через пробел (например: Россия РПЛ):")
    await state.set_state(AddMatchStates.country_league)


@dp.message(AddMatchStates.country_league)
async def add_match_country_league(message: types.Message, state: FSMContext):
    parts = message.text.strip().split(" ", 1)
    if len(parts) < 2:
        await message.answer("❌ Нужно ввести страну и лигу через пробел, например: Россия РПЛ\nПопробуйте ещё раз:")
        return
    await state.update_data(country=parts[0], league=parts[1])
    await message.answer("Шаг 3/3 — Введите текст матча (аналитика, статистика — всё одним сообщением):")
    await state.set_state(AddMatchStates.text)


@dp.message(AddMatchStates.text)
async def add_match_text(message: types.Message, state: FSMContext):
    data = await state.get_data()
    new_match = {
        "name": data["name"],
        "country": data["country"],
        "league": data["league"],
        "text": message.text
    }
    matches_data.setdefault("matches", []).append(new_match)
    save_json(matches_file, matches_data)
    await state.clear()
    await message.answer(
        f"✅ Матч добавлен!\n\n"
        f"⚽ {new_match['name']}\n"
        f"🏳️ {new_match['country']} — {new_match['league']}\n"
        f"Текст: {new_match['text'][:100]}...",
        reply_markup=admin_keyboard()
    )


# ===================== УДАЛЕНИЕ МАТЧА =====================

@dp.callback_query(F.data == "delete_match")
async def delete_match_menu(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа")
        return
    matches_list = matches_data.get("matches", [])
    if not matches_list:
        await callback.message.edit_text("Матчей нет.", reply_markup=admin_keyboard())
        await callback.answer()
        return
    kb = []
    for i, m in enumerate(matches_list):
        kb.append([InlineKeyboardButton(
            text=f"🗑 {m['name']} ({m['country']} — {m['league']})",
            callback_data=f"del_match_{i}"
        )])
    kb.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")])
    await callback.message.edit_text("Выберите матч для удаления:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await callback.answer()


@dp.callback_query(F.data.startswith("del_match_"))
async def delete_match_confirm(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа")
        return
    idx = int(callback.data.split("_")[2])
    matches_list = matches_data.get("matches", [])
    if 0 <= idx < len(matches_list):
        removed = matches_list.pop(idx)
        save_json(matches_file, matches_data)
        await callback.message.edit_text(
            f"✅ Удалено: {removed['name']}",
            reply_markup=admin_keyboard()
        )
    else:
        await callback.message.edit_text("Матч не найден.", reply_markup=admin_keyboard())
    await callback.answer()


# ===================== УПРАВЛЕНИЕ PREMIUM =====================

@dp.callback_query(F.data == "premium_admin")
async def premium_admin_menu(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа")
        return
    await callback.message.edit_text("💰 Управление Premium:", reply_markup=premium_admin_keyboard())
    await callback.answer()


@dp.callback_query(F.data == "premium_list")
async def premium_list(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа")
        return
    if not users:
        await callback.message.edit_text("Пользователей пока нет.", reply_markup=premium_admin_keyboard())
        await callback.answer()
        return
    text = "📋 Список пользователей:\n\n"
    for uid, u in users.items():
        name = u.get("name", "—")
        sub = u.get("subscription", "Free")
        end = u.get("end_date", "—")
        text += f"ID: <code>{uid}</code>\nИмя: {name}\nПодписка: {sub}\nДо: {end}\n\n"
    await callback.message.edit_text(text, reply_markup=premium_admin_keyboard())
    await callback.answer()


@dp.callback_query(F.data == "premium_add_id")
async def premium_add_id_start(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа")
        return
    await callback.message.edit_text("Введите ID пользователя для выдачи Premium:")
    await state.set_state(PremiumAdminStates.add_by_id)
    await callback.answer()


@dp.message(PremiumAdminStates.add_by_id)
async def premium_add_id_done(message: types.Message, state: FSMContext):
    uid = message.text.strip()
    if uid not in users:
        users[uid] = {"subscription": "Free", "end_date": "2026-01-01"}
    users[uid]["subscription"] = "Premium"
    users[uid]["end_date"] = (datetime.now(tz) + timedelta(days=30)).strftime("%Y-%m-%d")
    save_json(users_file, users)
    await state.clear()
    await message.answer(f"✅ Premium выдан пользователю {uid} на 30 дней.", reply_markup=admin_keyboard())


@dp.callback_query(F.data == "premium_add_all")
async def premium_add_all(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа")
        return
    end_date = (datetime.now(tz) + timedelta(days=30)).strftime("%Y-%m-%d")
    for uid in users:
        users[uid]["subscription"] = "Premium"
        users[uid]["end_date"] = end_date
    save_json(users_file, users)
    await callback.message.edit_text(f"✅ Premium выдан всем пользователям ({len(users)} чел.) до {end_date}.", reply_markup=admin_keyboard())
    await callback.answer()


@dp.callback_query(F.data == "premium_remove_id")
async def premium_remove_id_start(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа")
        return
    await callback.message.edit_text("Введите ID пользователя для снятия Premium:")
    await state.set_state(PremiumAdminStates.remove_by_id)
    await callback.answer()


@dp.message(PremiumAdminStates.remove_by_id)
async def premium_remove_id_done(message: types.Message, state: FSMContext):
    uid = message.text.strip()
    if uid in users:
        users[uid]["subscription"] = "Free"
        users[uid]["end_date"] = "2026-01-01"
        save_json(users_file, users)
        await state.clear()
        await message.answer(f"✅ Premium снят с пользователя {uid}.", reply_markup=admin_keyboard())
    else:
        await state.clear()
        await message.answer(f"❌ Пользователь {uid} не найден.", reply_markup=admin_keyboard())


@dp.callback_query(F.data == "premium_remove_all")
async def premium_remove_all(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа")
        return
    for uid in users:
        users[uid]["subscription"] = "Free"
        users[uid]["end_date"] = "2026-01-01"
    save_json(users_file, users)
    await callback.message.edit_text("✅ Premium снят у всех пользователей.", reply_markup=admin_keyboard())
    await callback.answer()


# ===================== СООБЩЕНИЯ ПОДДЕРЖКИ В АДМИНКЕ =====================

@dp.callback_query(F.data == "support_admin")
async def support_admin_menu(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа")
        return
    if not support:
        await callback.message.edit_text("Нет сообщений в техподдержке.", reply_markup=admin_keyboard())
        await callback.answer()
        return
    kb = []
    for uid, msgs in support.items():
        name = msgs[-1]["name"] if msgs else "—"
        count = len(msgs)
        kb.append([InlineKeyboardButton(
            text=f"💬 {name} ({count} сообщ.) — ID: {uid}",
            callback_data=f"support_view_{uid}"
        )])
    kb.append([InlineKeyboardButton(text="🗑 Очистить все", callback_data="support_clear_all")])
    kb.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")])
    await callback.message.edit_text("🛠 Сообщения в техподдержку:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await callback.answer()


@dp.callback_query(F.data.startswith("support_view_"))
async def support_view(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа")
        return
    uid = callback.data.split("_", 2)[2]
    msgs = support.get(uid, [])
    if not msgs:
        await callback.message.edit_text("Сообщений нет.", reply_markup=admin_keyboard())
        await callback.answer()
        return
    text = f"🛠 Переписка с пользователем {uid}:\n\n"
    for m in msgs:
        text += f"📅 {m['date']}\n👤 {m['name']} (ID: {m['id']})\n💬 {m['text']}\n\n"
    kb = [
        [InlineKeyboardButton(text="💬 Ответить", callback_data=f"support_reply_{uid}")],
        [InlineKeyboardButton(text="🗑 Очистить", callback_data=f"support_clear_{uid}")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="support_admin")]
    ]
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await callback.answer()


@dp.callback_query(F.data.startswith("support_reply_"))
async def support_reply_start(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа")
        return
    uid = callback.data.split("_", 2)[2]
    await state.set_data({"reply_to": uid})
    await state.set_state(SupportReplyStates.reply)
    await callback.message.edit_text(f"Введите ответ для пользователя {uid}:")
    await callback.answer()


@dp.message(SupportReplyStates.reply)
async def support_reply_send(message: types.Message, state: FSMContext):
    data = await state.get_data()
    uid = data.get("reply_to")
    if not uid:
        await state.clear()
        await message.answer("Ошибка: получатель не найден.", reply_markup=admin_keyboard())
        return
    try:
        await bot.send_message(
            int(uid),
            f"📩 Ответ от техподдержки:\n\n{message.text}"
        )
        await message.answer("✅ Ответ отправлен пользователю.", reply_markup=admin_keyboard())
    except Exception:
        await message.answer("❌ Не удалось отправить. Возможно, пользователь заблокировал бота.", reply_markup=admin_keyboard())
    await state.clear()


@dp.callback_query(F.data.startswith("support_clear_"))
async def support_clear_user(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа")
        return
    uid = callback.data.split("_", 2)[2]
    if uid in support:
        del support[uid]
        save_json(support_file, support)
    await callback.message.edit_text("✅ Переписка очищена.", reply_markup=admin_keyboard())
    await callback.answer()


@dp.callback_query(F.data == "support_clear_all")
async def support_clear_all(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа")
        return
    support.clear()
    save_json(support_file, support)
    await callback.message.edit_text("✅ Все сообщения техподдержки очищены.", reply_markup=admin_keyboard())
    await callback.answer()


# ===================== ЗАПУСК =====================

async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
