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


# ====================== FSM STATES ======================

class SupportStates(StatesGroup):
    get_message = State()


class AdminStates(StatesGroup):
    add_match_name = State()
    add_country_league = State()
    add_text = State()
    premium_give_id = State()
    premium_remove_id = State()
    reply_support_text = State()


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
    kb = [[InlineKeyboardButton(text=f"Тариф: {sub['subscription']}", callback_data="sub_info")]]
    if sub["subscription"] == "Free":
        kb.append([InlineKeyboardButton(text="Купить Premium (300 ₽)", callback_data="premium")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


def matches_keyboard():
    groups = {}
    for m in matches_data.get("matches", []):
        key = f"{m['country']} — {m['league']}"
        groups.setdefault(key, []).append(m)

    kb = []
    for group_name, group_matches in groups.items():
        count = len(group_matches)
        kb.append([InlineKeyboardButton(
            text=f"🏳️ {group_name} ({count})",
            callback_data=f"group_{group_name}"
        )])

    if not kb:
        kb = [[InlineKeyboardButton(text="Матчей пока нет", callback_data="no_matches")]]

    return InlineKeyboardMarkup(inline_keyboard=kb)


def back_keyboard(callback_data="matches"):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data=callback_data)]
    ])


# ====================== ВСПОМОГАТЕЛЬНЫЕ ======================

async def get_user_subscription(user_id: int) -> dict:
    uid = str(user_id)
    if uid not in users:
        users[uid] = {
            "subscription": "Free",
            "end_date": (datetime.now(tz) + timedelta(days=30)).strftime("%Y-%m-%d"),
            "viewed_matches": []
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


# ====================== ОБРАБОТЧИКИ ПОЛЬЗОВАТЕЛЯ ======================

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await get_user_subscription(message.from_user.id)
    await message.answer(
        "Доброго времени суток!\n\n"
        "Я твой помощник в мире футбола, собираю статистику, "
        "анализирую и предоставляю прогнозы.",
        reply_markup=main_keyboard()
    )


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


@dp.callback_query(F.data == "sub_info")
async def sub_info(callback: types.CallbackQuery):
    await callback.answer()


@dp.callback_query(F.data == "no_matches")
async def no_matches(callback: types.CallbackQuery):
    await callback.answer("Матчей пока нет", show_alert=True)


@dp.callback_query(F.data == "matches")
async def show_leagues(callback: types.CallbackQuery):
    await callback.message.edit_text("📋 Выберите группу (страна — лига):", reply_markup=matches_keyboard())
    await callback.answer()


@dp.callback_query(F.data.startswith("group_"))
async def show_group_matches(callback: types.CallbackQuery):
    group_name = callback.data.replace("group_", "", 1)

    # Ищем матчи этой группы
    all_matches = matches_data.get("matches", [])

    # Кнопки матчей с глобальным индексом
    kb_buttons = []
    text_lines = []
    for global_idx, m in enumerate(all_matches):
        full_group = f"{m['country']} — {m['league']}"
        if full_group == group_name:
            display_num = len(text_lines) + 1
            text_lines.append(f"{display_num}. {m['name']}")
            kb_buttons.append(InlineKeyboardButton(
                text=f"{display_num}. {m['name']}",
                callback_data=f"match_{global_idx}"
            ))

    if not kb_buttons:
        await callback.message.edit_text(
            "В этой группе матчей нет.",
            reply_markup=back_keyboard("matches")
        )
        await callback.answer()
        return

    text = f"🏟 {group_name}\n\n" + "\n".join(text_lines)

    kb_rows = [kb_buttons[i:i + 2] for i in range(0, len(kb_buttons), 2)]
    kb_rows.append([InlineKeyboardButton(text="🔙 Назад", callback_data="matches")])

    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows))
    await callback.answer()


@dp.callback_query(F.data.startswith("match_"))
async def show_match_details(callback: types.CallbackQuery):
    idx = int(callback.data.split("_", 1)[1])
    all_matches = matches_data.get("matches", [])

    if idx >= len(all_matches) or idx < 0:
        await callback.answer("Матч не найден", show_alert=True)
        return

    match = all_matches[idx]

    allowed = await check_match_limit(callback.from_user.id, idx)
    if not allowed:
        await callback.answer(
            "❌ Лимит матчей исчерпан (3 в день). Купите Premium.",
            show_alert=True
        )
        return

    text = (
        f"⚽ <b>{match['name']}</b>\n"
        f"🌍 {match['country']} — {match['league']}\n\n"
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
            [InlineKeyboardButton(
                text="Оплатить 300 ₽",
                url="https://yoomoney.ru/quickpay/confirm.xml?receiver=your_kassa@mail.ru&sum=300&label=koefbot&formcomment=true"
            )],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="account")]
        ])
    )
    await callback.answer()


@dp.callback_query(F.data == "support")
async def support_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("🛠 Техподдержка — напишите сообщение (кратко суть):")
    await state.set_state(SupportStates.get_message)
    await callback.answer()


@dp.message(SupportStates.get_message)
async def handle_support(message: types.Message, state: FSMContext):
    uid = str(message.chat.id)
    user_name = message.from_user.full_name or "Без имени"
    text_msg = message.text or "(нет текста)"

    support.setdefault(uid, []).append({
        "id": message.from_user.id,
        "name": user_name,
        "text": text_msg,
        "date": datetime.now(tz).strftime("%Y-%m-%d %H:%M")
    })
    save_json(support_file, support)

    await notify_admin_support(message.from_user.id, user_name, text_msg)

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

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить матч", callback_data="add_match_start")],
        [InlineKeyboardButton(text="🗑 Удалить матч / Очистить все", callback_data="delete_match_menu")],
        [InlineKeyboardButton(text="💰 Управление Premium", callback_data="premium_admin_menu")],
        [InlineKeyboardButton(text="🛠 Сообщения поддержки", callback_data="support_admin_menu")]
    ])
    await message.answer("🔧 Админ-панель", reply_markup=kb)


@dp.callback_query(F.data == "admin_back")
async def admin_back(callback: types.CallbackQuery, state: FSMContext):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    await state.clear()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить матч", callback_data="add_match_start")],
        [InlineKeyboardButton(text="🗑 Удалить матч / Очистить все", callback_data="delete_match_menu")],
        [InlineKeyboardButton(text="💰 Управление Premium", callback_data="premium_admin_menu")],
        [InlineKeyboardButton(text="🛠 Сообщения поддержки", callback_data="support_admin_menu")]
    ])
    await callback.message.edit_text("🔧 Админ-панель", reply_markup=kb)
    await callback.answer()


# --- Добавление матча (3 шага) ---

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
        await message.answer("Введите страну и лигу через пробел (например: Россия РПЛ):")
        return
    await state.update_data(country=parts[0], league=parts[1])
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
    await state.clear()


# --- Удаление матчей ---

@dp.callback_query(F.data == "delete_match_menu")
async def delete_match_menu(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return

    all_matches = matches_data.get("matches", [])
    kb_rows = [
        [InlineKeyboardButton(text="🗑 Очистить ВСЕ матчи", callback_data="delete_all_matches")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")]
    ]

    for i, m in enumerate(all_matches):
        kb_rows.insert(-1, [InlineKeyboardButton(
            text=f"❌ {m['name']} ({m['country']} {m['league']})",
            callback_data=f"delete_match_{i}"
        )])

    await callback.message.edit_text(
        f"🗑 Удаление матчей (всего: {len(all_matches)})",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows)
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("delete_match_"))
async def delete_single_match(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return

    idx = int(callback.data.replace("delete_match_", ""))
    all_matches = matches_data.get("matches", [])

    if 0 <= idx < len(all_matches):
        removed = all_matches.pop(idx)
        save_json(matches_file, matches_data)
        await callback.answer(f"Удалён: {removed['name']}", show_alert=True)
    else:
        await callback.answer("Матч не найден", show_alert=True)

    await delete_match_menu(callback)


@dp.callback_query(F.data == "delete_all_matches")
async def delete_all_matches(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return

    matches_data["matches"] = []
    save_json(matches_file, matches_data)

    await callback.message.edit_text(
        "✅ Все матчи удалены!",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")]
        ])
    )
    await callback.answer()


# --- Управление Premium ---

@dp.callback_query(F.data == "premium_admin_menu")
async def premium_admin_menu(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Список пользователей", callback_data="premium_list")],
        [InlineKeyboardButton(text="➕ Выдать Premium по ID", callback_data="premium_give_id_start")],
        [InlineKeyboardButton(text="➕ Выдать Premium всем", callback_data="premium_give_all")],
        [InlineKeyboardButton(text="➖ Снять Premium по ID", callback_data="premium_remove_id_start")],
        [InlineKeyboardButton(text="➖ Снять Premium всем", callback_data="premium_remove_all")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")]
    ])
    await callback.message.edit_text("💰 Управление Premium", reply_markup=kb)
    await callback.answer()


@dp.callback_query(F.data == "premium_list")
async def premium_list(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return

    if not users:
        await callback.message.edit_text(
            "Пользователей пока нет.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Назад", callback_data="premium_admin_menu")]
            ])
        )
        await callback.answer()
        return

    lines = ["📋 Список пользователей:\n"]
    for uid, u in users.items():
        sub = u.get("subscription", "Free")
        end = u.get("end_date", "—")
        lines.append(f"ID: <code>{uid}</code> | {sub} | до {end}")

    text = "\n".join(lines)
    if len(text) > 4000:
        text = text[:4000] + "..."

    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="premium_admin_menu")]
        ]),
        parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query(F.data == "premium_give_id_start")
async def premium_give_id_start(callback: types.CallbackQuery, state: FSMContext):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    await callback.message.edit_text("Введите ID пользователя для выдачи Premium:")
    await state.set_state(AdminStates.premium_give_id)
    await callback.answer()


@dp.message(AdminStates.premium_give_id)
async def premium_give_id(message: types.Message, state: FSMContext):
    uid = message.text.strip()
    if uid not in users:
        users[uid] = {"subscription": "Free", "end_date": "—", "viewed_matches": []}

    users[uid]["subscription"] = "Premium"
    users[uid]["end_date"] = (datetime.now(tz) + timedelta(days=30)).strftime("%Y-%m-%d")
    save_json(users_file, users)

    await message.answer(f"✅ Premium выдан пользователю {uid} на 30 дней.")
    await state.clear()


@dp.callback_query(F.data == "premium_give_all")
async def premium_give_all(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return

    end_date = (datetime.now(tz) + timedelta(days=30)).strftime("%Y-%m-%d")
    count = 0
    for uid in users:
        users[uid]["subscription"] = "Premium"
        users[uid]["end_date"] = end_date
        count += 1

    save_json(users_file, users)
    await callback.message.edit_text(
        f"✅ Premium выдан всем пользователям ({count} чел.) на 30 дней.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="premium_admin_menu")]
        ])
    )
    await callback.answer()


@dp.callback_query(F.data == "premium_remove_id_start")
async def premium_remove_id_start(callback: types.CallbackQuery, state: FSMContext):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    await callback.message.edit_text("Введите ID пользователя для снятия Premium:")
    await state.set_state(AdminStates.premium_remove_id)
    await callback.answer()


@dp.message(AdminStates.premium_remove_id)
async def premium_remove_id(message: types.Message, state: FSMContext):
    uid = message.text.strip()
    if uid in users:
        users[uid]["subscription"] = "Free"
        users[uid]["end_date"] = "—"
        save_json(users_file, users)
        await message.answer(f"✅ Premium снят с пользователя {uid}.")
    else:
        await message.answer("Пользователь не найден.")
    await state.clear()


@dp.callback_query(F.data == "premium_remove_all")
async def premium_remove_all(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return

    count = 0
    for uid in users:
        users[uid]["subscription"] = "Free"
        users[uid]["end_date"] = "—"
        count += 1

    save_json(users_file, users)
    await callback.message.edit_text(
        f"✅ Premium снят со всех пользователей ({count} чел.).",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="premium_admin_menu")]
        ])
    )
    await callback.answer()


# --- Техподдержка (админ) ---

@dp.callback_query(F.data == "support_admin_menu")
async def support_admin_menu(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return

    if not support:
        await callback.message.edit_text(
            "🛠 Сообщений в техподдержку пока нет.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")]
            ])
        )
        await callback.answer()
        return

    kb_rows = []
    for uid, msgs in support.items():
        name = msgs[-1].get("name", "Неизвестно") if msgs else "Неизвестно"
        count = len(msgs)
        kb_rows.append([InlineKeyboardButton(
            text=f"👤 {name} — {count} сообщ. (ID: {uid})",
            callback_data=f"support_view_{uid}"
        )])

    kb_rows.append([InlineKeyboardButton(text="🗑 Очистить все", callback_data="support_clear_all")])
    kb_rows.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")])

    await callback.message.edit_text(
        "🛠 Сообщения поддержки:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows)
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("support_view_"))
async def support_view(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return

    uid = callback.data.replace("support_view_", "")
    msgs = support.get(uid, [])

    if not msgs:
        await callback.answer("Сообщений нет", show_alert=True)
        return

    lines = []
    for m in msgs:
        lines.append(f"📅 {m['date']}\n👤 {m['name']} (ID: {m['id']})\n📝 {m['text']}\n")

    text = "\n".join(lines)
    if len(text) > 4000:
        text = text[:4000] + "..."

    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💬 Ответить", callback_data=f"support_reply_{uid}")],
            [InlineKeyboardButton(text="🗑 Очистить", callback_data=f"support_clear_{uid}")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="support_admin_menu")]
        ])
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("support_reply_"))
async def support_reply_start(callback: types.CallbackQuery, state: FSMContext):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return

    uid = callback.data.replace("support_reply_", "")
    await state.set_state(AdminStates.reply_support_text)
    await state.update_data(reply_uid=uid)

    await callback.message.edit_text(f"💬 Введите текст ответа для пользователя {uid}:")
    await callback.answer()


@dp.message(AdminStates.reply_support_text)
async def support_reply_send(message: types.Message, state: FSMContext):
    data = await state.get_data()
    uid = data.get("reply_uid")
    reply_text = message.text

    if uid and uid in support:
        support[uid].append({
            "id": ADMIN_ID,
            "name": "Админ",
            "text": reply_text,
            "date": datetime.now(tz).strftime("%Y-%m-%d %H:%M")
        })
        save_json(support_file, support)

    # Отправка пользователю
    try:
        await bot.send_message(
            int(uid),
            f"💬 Ответ от техподдержки:\n\n{reply_text}"
        )
        await message.answer("✅ Ответ отправлен пользователю.")
    except Exception:
        await message.answer("❌ Не удалось отправить (возможно, бот не запущен у пользователя).")

    await state.clear()


@dp.callback_query(F.data.startswith("support_clear_"))
async def support_clear_one(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return

    uid = callback.data.replace("support_clear_", "")
    if uid == "all":
        support.clear()
        save_json(support_file, support)
        await callback.message.edit_text(
            "✅ Вся переписка очищена.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")]
            ])
        )
    else:
        if uid in support:
            del support[uid]
            save_json(support_file, support)
        await callback.answer("Переписка очищена", show_alert=True)
        await support_admin_menu(callback)

    await callback.answer()


@dp.callback_query(F.data == "support_clear_all")
async def support_clear_all(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return

    support.clear()
    save_json(support_file, support)

    await callback.message.edit_text(
        "✅ Вся переписка очищена.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")]
        ])
    )
    await callback.answer()


# ====================== ЗАПУСК ======================

async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
