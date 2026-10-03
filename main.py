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
if "matches" not in matches_data or not isinstance(matches_data["matches"], list):
    matches_data["matches"] = []

users = load_json(users_file)
if not isinstance(users, dict):
    users = {}

support = load_json(support_file)
if not isinstance(support, dict):
    support = {}

tz = ZoneInfo("Europe/Moscow")


# ====================== FSM STATES ======================

class AdminStates(StatesGroup):
    add_match_name = State()
    add_match_country_league = State()
    add_match_text = State()
    give_premium_id = State()
    remove_premium_id = State()
    reply_support = State()

class SupportStates(StatesGroup):
    get_message = State()


# ====================== KEYBOARDS ======================

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
    if sub.get("subscription") == "Free":
        kb.append([InlineKeyboardButton(text="⭐ Купить Premium (300 \u20bd)", callback_data="premium")])
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


def matches_keyboard():
    matches_list = matches_data.get("matches", [])
    if not matches_list:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Матчей пока нет", callback_data="no_matches")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
        ])
    groups = {}
    for i, m in enumerate(matches_list):
        key = f"{m.get('country', '—')} \u2014 {m.get('league', '—')}"
        groups.setdefault(key, []).append(i)
    kb = []
    for key, indices in groups.items():
        kb.append([InlineKeyboardButton(text=f"\U0001f3f4 {key} ({len(indices)})", callback_data=f"group_{key}")])
    kb.append([InlineKeyboardButton(text="\U0001f519 Назад", callback_data="back_to_main")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


def group_matches_keyboard(group_key):
    matches_list = matches_data.get("matches", [])
    kb = []
    for i, m in enumerate(matches_list):
        key = f"{m.get('country', '—')} \u2014 {m.get('league', '—')}"
        if key == group_key:
            kb.append([InlineKeyboardButton(text=f"\u26bd {m['name']}", callback_data=f"match_{i}")])
    kb.append([InlineKeyboardButton(text="\U0001f519 Назад", callback_data="matches")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


def admin_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="\u2795 Добавить матч", callback_data="add_match_start")],
        [InlineKeyboardButton(text="\u274c Удалить матч", callback_data="delete_match")],
        [InlineKeyboardButton(text="\U0001f5d1 Очистить все матчи", callback_data="clear_all_matches")],
        [InlineKeyboardButton(text="\U0001f4b0 Управление Premium", callback_data="premium_admin")],
        [InlineKeyboardButton(text="\U0001f6e0 Сообщения поддержки", callback_data="support_admin")]
    ])


def premium_admin_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="\U0001f4cb Список пользователей", callback_data="list_users")],
        [InlineKeyboardButton(text="\u2795 Выдать Premium по ID", callback_data="give_premium_start")],
        [InlineKeyboardButton(text="\u2795 Выдать Premium всем", callback_data="give_premium_all")],
        [InlineKeyboardButton(text="\u2796 Снять Premium по ID", callback_data="remove_premium_start")],
        [InlineKeyboardButton(text="\u2796 Снять Premium всем", callback_data="remove_premium_all")],
        [InlineKeyboardButton(text="\U0001f519 Назад", callback_data="admin_back")]
    ])


def support_admin_keyboard():
    if not support:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Нет сообщений", callback_data="no_action")],
            [InlineKeyboardButton(text="\U0001f519 Назад", callback_data="admin_back")]
        ])
    kb = []
    for uid, msgs in support.items():
        if msgs:
            name = msgs[-1].get("name", "Без имени")
            count = len(msgs)
            kb.append([InlineKeyboardButton(text=f"{name} ({count} сообщ.)", callback_data=f"support_view_{uid}")])
    kb.append([InlineKeyboardButton(text="\U0001f5d1 Очистить все", callback_data="support_clear_all")])
    kb.append([InlineKeyboardButton(text="\U0001f519 Назад", callback_data="admin_back")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


def support_view_keyboard(uid):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="\U0001f4ac Ответить", callback_data=f"support_reply_{uid}")],
        [InlineKeyboardButton(text="\U0001f5d1 Очистить", callback_data=f"support_clear_{uid}")],
        [InlineKeyboardButton(text="\U0001f519 Назад", callback_data="support_admin")]
    ])


def delete_match_keyboard():
    matches_list = matches_data.get("matches", [])
    if not matches_list:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Матчей нет", callback_data="no_action")],
            [InlineKeyboardButton(text="\U0001f519 Назад", callback_data="admin_back")]
        ])
    kb = []
    for i, m in enumerate(matches_list):
        kb.append([InlineKeyboardButton(text=f"\u274c {m['name']} ({m.get('country', '')} {m.get('league', '')})", callback_data=f"del_match_{i}")])
    kb.append([InlineKeyboardButton(text="\U0001f519 Назад", callback_data="admin_back")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


# ====================== USER FUNCTIONS ======================

async def get_user_subscription(user_id: int) -> dict:
    uid = str(user_id)
    if uid not in users:
        users[uid] = {"subscription": "Free", "end_date": "2026-01-01", "viewed_matches": [], "last_match_date": str(datetime.now(tz).date())}
        save_json(users_file, users)
    return users[uid]


async def check_match_limit(user_id: int, match_idx: int) -> bool:
    sub = await get_user_subscription(user_id)
    if sub.get("subscription") == "Premium":
        return True
    uid = str(user_id)
    today = str(datetime.now(tz).date())
    if users[uid].get("last_match_date") != today:
        users[uid]["last_match_date"] = today
        users[uid]["viewed_matches"] = []
        save_json(users_file, users)
    viewed = users[uid].setdefault("viewed_matches", [])
    if match_idx in viewed:
        return True
    if len(viewed) >= 3:
        return False
    viewed.append(match_idx)
    save_json(users_file, users)
    return True


# ====================== USER HANDLERS ======================

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await get_user_subscription(message.from_user.id)
    await message.answer(
        "\U0001f44b \u0414\u043e\u0431\u0440\u043e \u043f\u043e\u0436\u0430\u043b\u043e\u0432\u0430\u0442\u044c!\n\n"
        "\u042f \u0442\u0432\u043e\u0439 \u043f\u043e\u043c\u043e\u0449\u043d\u0438\u043a \u0432 \u043c\u0438\u0440\u0435 \u0444\u0443\u0442\u0431\u043e\u043b\u0430. "
        "\u0412\u044b\u0431\u0435\u0440\u0438 \u0440\u0430\u0437\u0434\u0435\u043b \u043d\u0438\u0436\u0435:",
        reply_markup=main_keyboard()
    )


@dp.callback_query(F.data == "back_to_main")
async def back_to_main(callback: types.CallbackQuery):
    await callback.message.edit_text("\U0001f44b \u0412\u044b\u0431\u0435\u0440\u0438 \u0440\u0430\u0437\u0434\u0435\u043b:", reply_markup=main_keyboard())
    await callback.answer()


@dp.callback_query(F.data == "account")
async def account(callback: types.CallbackQuery):
    sub = await get_user_subscription(callback.from_user.id)
    sub_emoji = "\u2b50" if sub.get("subscription") == "Premium" else "\U0001f4cb"
    await callback.message.edit_text(
        f"\U0001f464 <b>\u0410\u043a\u043a\u0430\u0443\u043d\u0442</b>\n\n"
        f"<b>ID:</b> <code>{callback.from_user.id}</code>\n"
        f"<b>\u0418\u043c\u044f:</b> {callback.from_user.first_name}\n"
        f"<b>\u0422\u0430\u0440\u0438\u0444:</b> {sub_emoji} <b>{sub.get('subscription', 'Free')}</b>",
        reply_markup=account_keyboard(sub),
        parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query(F.data == "matches")
async def show_matches(callback: types.CallbackQuery):
    await callback.message.edit_text("\U0001f4cb \u0412\u044b\u0431\u0435\u0440\u0438 \u043b\u0438\u0433\u0443:", reply_markup=matches_keyboard())
    await callback.answer()


@dp.callback_query(F.data.startswith("group_"))
async def show_group_matches(callback: types.CallbackQuery):
    group_key = callback.data[6:]
    await callback.message.edit_text(f"\U0001f3df {group_key}\n\n\u0412\u044b\u0431\u0435\u0440\u0438 \u043c\u0430\u0442\u0447:", reply_markup=group_matches_keyboard(group_key))
    await callback.answer()


@dp.callback_query(F.data.startswith("match_"))
async def show_match_details(callback: types.CallbackQuery):
    idx = int(callback.data.split("_")[1])
    matches_list = matches_data.get("matches", [])
    if idx >= len(matches_list):
        await callback.answer("\u041c\u0430\u0442\u0447 \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d")
        return
    allowed = await check_match_limit(callback.from_user.id, idx)
    if not allowed:
        await callback.answer("\u041b\u0438\u043c\u0438\u0442 \u0438\u0441\u0447\u0435\u0440\u043f\u0430\u043d (3 \u043c\u0430\u0442\u0447\u0430 \u0432 \u0434\u0435\u043d\u044c). \u041a\u0443\u043f\u0438 Premium \u0434\u043b\u044f \u0431\u0435\u0437\u043b\u0438\u043c\u0438\u0442\u0430!", show_alert=True)
        return
    match = matches_list[idx]
    text_content = match.get("text", "\u041d\u0435\u0442 \u0434\u0430\u043d\u043d\u044b\u0445")
    await callback.message.edit_text(
        f"\u26bd <b>{match['name']}</b>\n"
        f"\U0001f3f4 {match.get('country', '')} \u2014 {match.get('league', '')}\n\n"
        f"<tg-spoiler>{text_content}</tg-spoiler>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="\U0001f519 \u041d\u0430\u0437\u0430\u0434", callback_data=f"group_{match.get('country', '—')} — {match.get('league', '—')}")]
        ])
    )
    await callback.answer()


@dp.callback_query(F.data == "premium")
async def premium(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "\u2b50 <b>Premium</b>\n\n"
        "\u041f\u043e\u043b\u043d\u044b\u0439 \u0434\u043e\u0441\u0442\u0443\u043f \u043a \u043c\u0430\u0442\u0447\u0430\u043c, \u0430\u043d\u0430\u043b\u0438\u0442\u0438\u043a\u0435 \u0438 \u043f\u0440\u043e\u0433\u043d\u043e\u0437\u0430\u043c.\n\n"
        "\u0426\u0435\u043d\u0430: 300 \u20bd \u0432 \u043c\u0435\u0441\u044f\u0446\n\n"
        "\u041e\u043f\u043b\u0430\u0442\u0430 \u0447\u0435\u0440\u0435\u0437 \u0441\u0441\u044b\u043b\u043a\u0443:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="\u041e\u043f\u043b\u0430\u0442\u0438\u0442\u044c 300 \u20bd", url="https://yoomoney.ru/quickpay/confirm.xml?receiver=your_kassa@mail.ru&sum=300&label=koefbot&formcomment=true")],
            [InlineKeyboardButton(text="\U0001f519 \u041d\u0430\u0437\u0430\u0434", callback_data="back_to_main")]
        ]),
        parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query(F.data == "support")
async def support_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("\U0001f6e0 \u0422\u0435\u0445\u043f\u043e\u0434\u0434\u0435\u0440\u0436\u043a\u0430\n\n\u041d\u0430\u043f\u0438\u0448\u0438 \u0441\u0432\u043e\u0435 \u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u0435 \u043e\u0434\u043d\u0438\u043c \u0442\u0435\u043a\u0441\u0442\u043e\u043c:")
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
    # Уведомление админу
    if admin_users:
        for admin_id in admin_users:
            try:
                await bot.send_message(
                    int(admin_id),
                    f"\U0001f4e9 \u041d\u043e\u0432\u043e\u0435 \u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u0435 \u0432 \u0442\u0435\u0445\u043f\u043e\u0434\u0434\u0435\u0440\u0436\u043a\u0443\n\n"
                    f"\U0001f464 {message.from_user.full_name}\n"
                    f"\U0001f194 ID: <code>{message.from_user.id}</code>\n"
                    f"\U0001f4ac {message.text}\n"
                    f"\U0001f4c5 {datetime.now(tz).strftime('%Y-%m-%d %H:%M')}",
                    parse_mode="HTML"
                )
            except Exception:
                pass
    await message.answer("\u2705 \u0412\u0430\u0448\u0435 \u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u0435 \u0443\u0441\u043f\u0435\u0448\u043d\u043e \u043e\u0442\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u043e \u0410\u0434\u043c\u0438\u043d\u0438\u0441\u0442\u0440\u0430\u0446\u0438\u0438!", reply_markup=main_keyboard())
    await state.clear()


@dp.callback_query(F.data == "no_matches")
async def no_matches(callback: types.CallbackQuery):
    await callback.answer()


@dp.callback_query(F.data == "no_action")
async def no_action(callback: types.CallbackQuery):
    await callback.answer()


@dp.callback_query(F.data == "sub_info")
async def sub_info(callback: types.CallbackQuery):
    await callback.answer("\u0411\u0435\u0441\u043f\u043b\u0430\u0442\u043d\u043e: 3 \u043c\u0430\u0442\u0447\u0430 \u0432 \u0441\u0443\u0442\u043a\u0438. Premium \u2014 \u0431\u0435\u0437\u043b\u0438\u043c\u0438\u0442.", show_alert=True)


# ====================== ADMIN PANEL ======================

@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    if str(message.from_user.id) not in admin_users:
        await message.answer("\u274c \u041d\u0435\u0442 \u0434\u043e\u0441\u0442\u0443\u043f\u0430!")
        return
    await message.answer("\U0001f527 \u0410\u0434\u043c\u0438\u043d-\u043f\u0430\u043d\u0435\u043b\u044c /goal", reply_markup=admin_keyboard())


@dp.callback_query(F.data == "admin_back")
async def admin_back(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer()
        return
    await callback.message.edit_text("\U0001f527 \u0410\u0434\u043c\u0438\u043d-\u043f\u0430\u043d\u0435\u043b\u044c /goal", reply_markup=admin_keyboard())
    await callback.answer()


# --- Добавление матча (3 шага) ---

@dp.callback_query(F.data == "add_match_start")
async def add_match_start(callback: types.CallbackQuery, state: FSMContext):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("\u041d\u0435\u0442 \u0434\u043e\u0441\u0442\u0443\u043f\u0430")
        return
    await callback.message.edit_text("\u2795 \u0428\u0430\u0433 1/3\n\n\u0412\u0432\u0435\u0434\u0438\u0442\u0435 \u043d\u0430\u0437\u0432\u0430\u043d\u0438\u0435 \u043c\u0430\u0442\u0447\u0430:\n\u041f\u0440\u0438\u043c\u0435\u0440: \u0421\u043f\u0430\u0440\u0442\u0430\u043a \u2014 \u0417\u0435\u043d\u0438\u0442")
    await state.set_state(AdminStates.add_match_name)
    await callback.answer()


@dp.message(AdminStates.add_match_name)
async def add_match_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await message.answer(
        "\u2795 \u0428\u0430\u0433 2/3\n\n"
        "\u0412\u0432\u0435\u0434\u0438\u0442\u0435 \u0441\u0442\u0440\u0430\u043d\u0443 \u0438 \u043b\u0438\u0433\u0443 \u0447\u0435\u0440\u0435\u0437 \u043f\u0440\u043e\u0431\u0435\u043b:\n"
        "\u041f\u0440\u0438\u043c\u0435\u0440: \u0420\u043e\u0441\u0441\u0438\u044f \u0420\u041f\u041b"
    )
    await state.set_state(AdminStates.add_match_country_league)


@dp.message(AdminStates.add_match_country_league)
async def add_match_country_league(message: types.Message, state: FSMContext):
    parts = message.text.strip().split(None, 1)
    if len(parts) < 2:
        await message.answer("\u26a0\ufe0f \u041d\u0443\u0436\u043d\u043e \u0434\u0432\u0430 \u0441\u043b\u043e\u0432\u0430 \u0447\u0435\u0440\u0435\u0437 \u043f\u0440\u043e\u0431\u0435\u043b. \u041f\u043e\u043f\u0440\u043e\u0431\u0443\u0439\u0442\u0435 \u0435\u0449\u0435 \u0440\u0430\u0437:\n\u041f\u0440\u0438\u043c\u0435\u0440: \u0420\u043e\u0441\u0441\u0438\u044f \u0420\u041f\u041b")
        return
    await state.update_data(country=parts[0], league=parts[1])
    await message.answer(
        "\u2795 \u0428\u0430\u0433 3/3\n\n"
        "\u0412\u0432\u0435\u0434\u0438\u0442\u0435 \u0442\u0435\u043a\u0441\u0442 \u043c\u0430\u0442\u0447\u0430 \u043e\u0434\u043d\u0438\u043c \u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u0435\u043c.\n"
        "\u042d\u0442\u043e\u0442 \u0442\u0435\u043a\u0441\u0442 \u0443\u0432\u0438\u0434\u0438\u0442 \u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044c \u043f\u0440\u0438 \u043e\u0442\u043a\u0440\u044b\u0442\u0438\u0438 \u043c\u0430\u0442\u0447\u0430."
    )
    await state.set_state(AdminStates.add_match_text)


@dp.message(AdminStates.add_match_text)
async def add_match_text(message: types.Message, state: FSMContext):
    data = await state.get_data()
    new_match = {
        "name": data.get("name", ""),
        "country": data.get("country", ""),
        "league": data.get("league", ""),
        "text": message.text
    }
    matches_data.setdefault("matches", []).append(new_match)
    save_json(matches_file, matches_data)
    await message.answer(
        f"\u2705 \u041c\u0430\u0442\u0447 \u0434\u043e\u0431\u0430\u0432\u043b\u0435\u043d!\n\n"
        f"\u26bd {new_match['name']}\n"
        f"\U0001f3f4 {new_match['country']} \u2014 {new_match['league']}\n"
        f"\U0001f4dd \u0422\u0435\u043a\u0441\u0442: {len(new_match['text'])} \u0441\u0438\u043c\u0432\u043e\u043b\u043e\u0432",
        reply_markup=admin_keyboard()
    )
    await state.clear()


# --- Удаление матча ---

@dp.callback_query(F.data == "delete_match")
async def delete_match_menu(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer()
        return
    await callback.message.edit_text("\u274c \u0412\u044b\u0431\u0435\u0440\u0438 \u043c\u0430\u0442\u0447 \u0434\u043b\u044f \u0443\u0434\u0430\u043b\u0435\u043d\u0438\u044f:", reply_markup=delete_match_keyboard())
    await callback.answer()


@dp.callback_query(F.data.startswith("del_match_"))
async def delete_match(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer()
        return
    idx = int(callback.data.split("_")[2])
    matches_list = matches_data.get("matches", [])
    if idx < len(matches_list):
        removed = matches_list.pop(idx)
        save_json(matches_file, matches_data)
        await callback.message.edit_text(f"\u2705 \u041c\u0430\u0442\u0447 \u0443\u0434\u0430\u043b\u0435\u043d: {removed['name']}", reply_markup=delete_match_keyboard())
    else:
        await callback.answer("\u041c\u0430\u0442\u0447 \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d")
    await callback.answer()


@dp.callback_query(F.data == "clear_all_matches")
async def clear_all_matches(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer()
        return
    matches_data["matches"] = []
    save_json(matches_file, matches_data)
    await callback.message.edit_text("\u2705 \u0412\u0441\u0435 \u043c\u0430\u0442\u0447\u0438 \u043e\u0447\u0438\u0449\u0435\u043d\u044b!", reply_markup=admin_keyboard())
    await callback.answer()


# --- Управление Premium ---

@dp.callback_query(F.data == "premium_admin")
async def premium_admin(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer()
        return
    await callback.message.edit_text("\U0001f4b0 \u0423\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u0438\u0435 Premium:", reply_markup=premium_admin_keyboard())
    await callback.answer()


@dp.callback_query(F.data == "list_users")
async def list_users(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer()
        return
    if not users:
        await callback.message.edit_text("\u041f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u0435\u0439 \u043f\u043e\u043a\u0430 \u043d\u0435\u0442.", reply_markup=premium_admin_keyboard())
        await callback.answer()
        return
    text = "\U0001f4cb \u0421\u043f\u0438\u0441\u043e\u043a \u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u0435\u0439:\n\n"
    for uid, u in users.items():
        sub = u.get("subscription", "Free")
        end = u.get("end_date", "\u2014")
        text += f"\u2022 <code>{uid}</code> \u2014 {sub} ({end})\n"
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=premium_admin_keyboard())
    await callback.answer()


@dp.callback_query(F.data == "give_premium_start")
async def give_premium_start(callback: types.CallbackQuery, state: FSMContext):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer()
        return
    await callback.message.edit_text("\u2795 \u0412\u0432\u0435\u0434\u0438\u0442\u0435 ID \u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044f \u0434\u043b\u044f \u0432\u044b\u0434\u0430\u0447\u0438 Premium:")
    await state.set_state(AdminStates.give_premium_id)
    await callback.answer()


@dp.message(AdminStates.give_premium_id)
async def give_premium_id(message: types.Message, state: FSMContext):
    uid = message.text.strip()
    end_date = (datetime.now(tz) + timedelta(days=30)).strftime("%Y-%m-%d")
    if uid in users:
        users[uid]["subscription"] = "Premium"
        users[uid]["end_date"] = end_date
    else:
        users[uid] = {"subscription": "Premium", "end_date": end_date, "viewed_matches": [], "last_match_date": str(datetime.now(tz).date())}
    save_json(users_file, users)
    await message.answer(f"\u2705 Premium \u0432\u044b\u0434\u0430\u043d \u0434\u043e {end_date} \u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044e <code>{uid}</code>", parse_mode="HTML", reply_markup=premium_admin_keyboard())
    await state.clear()


@dp.callback_query(F.data == "give_premium_all")
async def give_premium_all(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer()
        return
    end_date = (datetime.now(tz) + timedelta(days=30)).strftime("%Y-%m-%d")
    for uid in users:
        users[uid]["subscription"] = "Premium"
        users[uid]["end_date"] = end_date
    save_json(users_file, users)
    await callback.message.edit_text(f"\u2705 Premium \u0432\u044b\u0434\u0430\u043d \u0432\u0441\u0435\u043c ({len(users)} \u0447\u0435\u043b.) \u0434\u043e {end_date}", reply_markup=premium_admin_keyboard())
    await callback.answer()


@dp.callback_query(F.data == "remove_premium_start")
async def remove_premium_start(callback: types.CallbackQuery, state: FSMContext):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer()
        return
    await callback.message.edit_text("\u2796 \u0412\u0432\u0435\u0434\u0438\u0442\u0435 ID \u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044f \u0434\u043b\u044f \u0441\u043d\u044f\u0442\u0438\u044f Premium:")
    await state.set_state(AdminStates.remove_premium_id)
    await callback.answer()


@dp.message(AdminStates.remove_premium_id)
async def remove_premium_id(message: types.Message, state: FSMContext):
    uid = message.text.strip()
    if uid in users:
        users[uid]["subscription"] = "Free"
        users[uid]["end_date"] = "2026-01-01"
        save_json(users_file, users)
        await message.answer(f"\u2705 Premium \u0441\u043d\u044f\u0442 \u0441 \u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044f <code>{uid}</code>", parse_mode="HTML", reply_markup=premium_admin_keyboard())
    else:
        await message.answer("\u26a0\ufe0f \u041f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044c \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d.", reply_markup=premium_admin_keyboard())
    await state.clear()


@dp.callback_query(F.data == "remove_premium_all")
async def remove_premium_all(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer()
        return
    for uid in users:
        users[uid]["subscription"] = "Free"
        users[uid]["end_date"] = "2026-01-01"
    save_json(users_file, users)
    await callback.message.edit_text(f"\u2705 Premium \u0441\u043d\u044f\u0442 \u0443 \u0432\u0441\u0435\u0445 ({len(users)} \u0447\u0435\u043b.)", reply_markup=premium_admin_keyboard())
    await callback.answer()


# --- Техподдержка в админке ---

@dp.callback_query(F.data == "support_admin")
async def support_admin(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer()
        return
    await callback.message.edit_text("\U0001f6e0 \u0421\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u044f \u043f\u043e\u0434\u0434\u0435\u0440\u0436\u043a\u0438:", reply_markup=support_admin_keyboard())
    await callback.answer()


@dp.callback_query(F.data.startswith("support_view_"))
async def support_view(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer()
        return
    uid = callback.data[len("support_view_"):]
    msgs = support.get(uid, [])
    if not msgs:
        await callback.answer("\u041d\u0435\u0442 \u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u0439")
        return
    text = f"\U0001f4ac \u041f\u0435\u0440\u0435\u043f\u0438\u0441\u043a\u0430 \u0441 {msgs[-1].get('name', '??')} (ID: <code>{uid}</code>):\n\n"
    for m in msgs:
        sender = "\U0001f464 \u041f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044c" if m.get("from_user") else "\U0001f3e2 \u0410\u0434\u043c\u0438\u043d"
        text += f"{sender} ({m['date']}):\n{m['text']}\n\n"
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=support_view_keyboard(uid))
    await callback.answer()


@dp.callback_query(F.data.startswith("support_reply_"))
async def support_reply_start(callback: types.CallbackQuery, state: FSMContext):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer()
        return
    uid = callback.data[len("support_reply_"):]
    await state.set_data({"reply_to": uid})
    await callback.message.edit_text(f"\U0001f4ac \u0412\u0432\u0435\u0434\u0438\u0442\u0435 \u043e\u0442\u0432\u0435\u0442 \u0434\u043b\u044f \u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044f <code>{uid}</code>:", parse_mode="HTML")
    await state.set_state(AdminStates.reply_support)
    await callback.answer()


@dp.message(AdminStates.reply_support)
async def support_reply_send(message: types.Message, state: FSMContext):
    data = await state.get_data()
    uid = data.get("reply_to")
    if not uid:
        await message.answer("\u26a0\ufe0f \u041e\u0448\u0438\u0431\u043a\u0430: \u043d\u0435\u0442 ID \u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044f.")
        await state.clear()
        return
    support.setdefault(uid, []).append({
        "id": message.from_user.id,
        "name": message.from_user.full_name,
        "text": message.text,
        "date": datetime.now(tz).strftime("%Y-%m-%d %H:%M"),
        "from_user": False
    })
    save_json(support_file, support)
    try:
        await bot.send_message(int(uid), f"\U0001f4ac \u041e\u0442\u0432\u0435\u0442 \u043e\u0442 \u0442\u0435\u0445\u043f\u043e\u0434\u0434\u0435\u0440\u0436\u043a\u0438:\n\n{message.text}")
    except Exception:
        pass
    await message.answer("\u2705 \u041e\u0442\u0432\u0435\u0442 \u043e\u0442\u043f\u0440\u0430\u0432\u043b\u0435\u043d!", reply_markup=support_admin_keyboard())
    await state.clear()


@dp.callback_query(F.data.startswith("support_clear_"))
async def support_clear_one(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer()
        return
    uid = callback.data[len("support_clear_"):]
    if uid in support:
        del support[uid]
        save_json(support_file, support)
    await callback.message.edit_text("\u2705 \u041f\u0435\u0440\u0435\u043f\u0438\u0441\u043a\u0430 \u043e\u0447\u0438\u0449\u0435\u043d\u0430.", reply_markup=support_admin_keyboard())
    await callback.answer()


@dp.callback_query(F.data == "support_clear_all")
async def support_clear_all(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer()
        return
    support.clear()
    save_json(support_file, support)
    await callback.message.edit_text("\u2705 \u0412\u0441\u0435 \u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u044f \u043e\u0447\u0438\u0449\u0435\u043d\u044b.", reply_markup=support_admin_keyboard())
    await callback.answer()


# ====================== MAIN ======================

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
