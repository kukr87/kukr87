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

BOT_USERNAME = "koef_bot"

SUPPORT_CATEGORIES = {
    "bug": "🐛 Баг / ошибка",
    "payment": "💳 Оплата",
    "suggestion": "💡 Предложение",
    "question": "❓ Вопрос",
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

if "matches" not in matches_data:
    matches_data["matches"] = []


# ====================== КЛАВИАТУРЫ ======================

def main_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📂 Аккаунт", callback_data="account")],
        [InlineKeyboardButton(text="⚽ Матчи", callback_data="matches")],
        [InlineKeyboardButton(text="💬 Чат канала", url="https://t.me/koefchat")],
        [InlineKeyboardButton(text="⭐ Premium", callback_data="premium")],
        [InlineKeyboardButton(text="🛠 Техподдержка", callback_data="support")],
    ])


def account_keyboard(sub, uid):
    kb = []
    if sub["subscription"] == "Free":
        kb.append([InlineKeyboardButton(text="Купить Premium (300 ₽)", callback_data="premium")])
    kb.append([InlineKeyboardButton(text="🔗 Моя реферальная ссылка", callback_data=f"reflink_{uid}")])
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
                callback_data=f"group_{group_name}",
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
        [InlineKeyboardButton(text="💳 Оплата", callback_data="supcat_payment")],
        [InlineKeyboardButton(text="💡 Предложение", callback_data="supcat_suggestion")],
        [InlineKeyboardButton(text="❓ Вопрос", callback_data="supcat_question")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")],
    ])


def admin_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить матч", callback_data="add_match_start")],
        [InlineKeyboardButton(text="🗑 Удалить матч / Очистить все", callback_data="delete_match_menu")],
        [InlineKeyboardButton(text="💰 Управление Premium", callback_data="premium_admin_menu")],
        [InlineKeyboardButton(text="🛠 Сообщения поддержки", callback_data="support_admin_menu")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")],
    ])


def admin_back_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад в админ-панель", callback_data="admin_back")]
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
            "register_date": datetime.now(tz).strftime("%Y-%m-%d"),
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


async def notify_admin_support(user_id, user_name, category, text):
    try:
        cat_label = SUPPORT_CATEGORIES.get(category, "❓ Без категории")
        await bot.send_message(
            ADMIN_ID,
            f"📩 <b>Новое сообщение в техподдержку!</b>\n\n"
            f"📂 Категория: {cat_label}\n"
            f"👤 От: {user_name}\n"
            f"ID: <code>{user_id}</code>\n"
            f"📝 Текст:\n{text}",
            parse_mode="HTML",
        )
    except Exception:
        pass


def apply_referral_bonus(referrer_id: str):
    """Начисляет 3 дня Premium за 1 реферала."""
    sub = users[referrer_id]
    if sub["subscription"] == "Premium":
        end_date = datetime.strptime(sub["end_date"], "%Y-%m-%d").date()
        end_date = end_date + timedelta(days=3)
    else:
        end_date = (datetime.now(tz) + timedelta(days=3)).date()
        sub["subscription"] = "Premium"
    sub["end_date"] = end_date.strftime("%Y-%m-%d")
    save_json(users_file, users)


# ====================== FSM STATES ======================

class SupportStates(StatesGroup):
    waiting_for_message = State()


class AdminStates(StatesGroup):
    add_match_name = State()
    add_country_league = State()
    add_text = State()
    delete_match_index = State()
    premium_give_id = State()
    premium_remove_id = State()
    reply_support_text = State()


# ====================== ОБРАБОТЧИКИ ПОЛЬЗОВАТЕЛЯ ======================

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    uid = str(message.from_user.id)
    args = message.text.split()
    ref_code = None

    if len(args) > 1 and args[1].startswith("ref_"):
        ref_code = args[1].replace("ref_", "")

    await get_user_subscription(message.from_user.id)

    if uid not in users:
        users[uid] = {
            "subscription": "Free",
            "end_date": (datetime.now(tz) + timedelta(days=30)).strftime("%Y-%m-%d"),
            "viewed_matches": [],
            "referrals": [],
            "referred_by": None,
            "register_date": datetime.now(tz).strftime("%Y-%m-%d"),
        }
        save_json(users_file, users)

    if ref_code and ref_code != uid:
        if ref_code in users and uid not in users[ref_code].get("referrals", []):
            users[ref_code].setdefault("referrals", []).append(uid)
            users[uid]["referred_by"] = ref_code
            save_json(users_file, users)
            apply_referral_bonus(ref_code)
            try:
                await bot.send_message(
                    int(ref_code),
                    f"🎉 По вашей реферальной ссылке зарегистрировался новый пользователь!\n"
                    f"Вам начислено 3 дня Premium бесплатно!"
                )
            except Exception:
                pass

    await message.answer(
        "Доброго времени суток!\n\n"
        "Я твой помощник в мире футбола, собираю статистику, анализирую и предоставляю прогнозы.",
        reply_markup=main_keyboard(),
    )


@dp.callback_query(F.data == "main_menu")
async def to_main_menu(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "Главное меню:",
        reply_markup=main_keyboard(),
    )
    await callback.answer()


@dp.callback_query(F.data == "account")
async def account(callback: types.CallbackQuery):
    sub = await get_user_subscription(callback.from_user.id)
    uid = str(callback.from_user.id)
    register_date = users[uid].get("register_date", "—")
    referrals_count = len(users[uid].get("referrals", []))
    total_matches = len(matches_data.get("matches", []))
    total_users = len(users)

    premium_count = sum(1 for u in users.values() if u.get("subscription") == "Premium")

    if sub["subscription"] == "Premium":
        matches_left = "∞"
    else:
        today = datetime.now(tz).date()
        last_date_str = users[uid].get("last_check_date", "")
        if last_date_str != str(today):
            viewed_count = 0
        else:
            viewed_count = len(users[uid].get("viewed_matches", []))
        matches_left = max(0, 3 - viewed_count)

    text = (
        f"👤 <b>Аккаунт</b>\n\n"
        f"🆔 ID: <code>{callback.from_user.id}</code>\n"
        f"👤 Имя: {callback.from_user.first_name}\n"
        f"💎 Тариф: {'⭐ Premium' if sub['subscription'] == 'Premium' else '🆓 Free'}\n"
        f"📅 С нами с: {register_date}\n"
        f"⚽ Матчей осталось сегодня: {matches_left}\n"
        f"🏆 Всего матчей в базе: {total_matches}\n"
        f"👥 Всего пользователей: {total_users}\n"
        f"⭐ Premium-пользователей: {premium_count}\n"
        f"🔗 Рефералов: {referrals_count}\n\n"
        f"💡 За 1 реферала — 3 дня Premium бесплатно!"
    )
    await callback.message.edit_text(text, reply_markup=account_keyboard(sub, uid), parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data.startswith("reflink_"))
async def show_reflink(callback: types.CallbackQuery):
    uid = callback.data.replace("reflink_", "")
    link = f"https://t.me/{BOT_USERNAME}?start=ref_{uid}"
    text = (
        f"🔗 <b>Ваша реферальная ссылка</b>\n\n"
        f"{link}\n\n"
        f"📢 Поделитесь ссылкой с друзьями!\n"
        f"За каждого, кто перейдёт по ней и запустит бота — 3 дня Premium бесплатно!\n\n"
        f"📊 Рефералов: {len(users.get(uid, {}).get('referrals', []))}"
    )
    await callback.message.edit_text(text, reply_markup=back_keyboard("account"), parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data == "matches")
async def show_leagues(callback: types.CallbackQuery):
    await callback.message.edit_text("📋 Выберите группу (страна — лига):", reply_markup=matches_keyboard())
    await callback.answer()


@dp.callback_query(F.data.startswith("group_"))
async def show_group_matches(callback: types.CallbackQuery):
    group_name = callback.data.replace("group_", "")
    country, league = group_name.split(" — ", 1)

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


@dp.callback_query(F.data == "premium")
async def premium(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "⭐ Premium — полный доступ к матчам и аналитике.\n\n"
        "Цена: 300 ₽ в месяц\n\n"
        "Оплата через ЮKassa",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Оплатить 300 ₽", url="https://yoomoney.ru/quickpay/confirm.xml?receiver=your_kassa@mail.ru&sum=300&label=koefbot&formcomment=true")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")],
        ]),
    )
    await callback.answer()


# ====================== ТЕХПОДДЕРЖКА (С КАТЕГОРИЯМИ) ======================

@dp.callback_query(F.data == "support")
async def support_start(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "🛠 <b>Техподдержка</b>\n\nВыберите категорию обращения:",
        reply_markup=support_categories_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("supcat_"))
async def support_select_category(callback: types.CallbackQuery, state: FSMContext):
    category = callback.data.replace("supcat_", "")
    cat_label = SUPPORT_CATEGORIES.get(category, "❓ Без категории")
    await state.update_data(support_category=category)
    await state.set_state(SupportStates.waiting_for_message)
    await callback.message.edit_text(
        f"🛠 Категория: <b>{cat_label}</b>\n\nНапишите ваше сообщение одним текстом:",
        reply_markup=back_keyboard("support"),
        parse_mode="HTML",
    )
    await callback.answer()


@dp.message(SupportStates.waiting_for_message)
async def handle_support_message(message: types.Message, state: FSMContext):
    data = await state.get_data()
    category = data.get("support_category", "unknown")
    cat_label = SUPPORT_CATEGORIES.get(category, "❓ Без категории")
    uid = str(message.chat.id)
    user_name = message.from_user.full_name or "Без имени"
    text_msg = message.text

    support.setdefault("threads", {})
    support["threads"].setdefault(uid, []).append({
        "from": "user",
        "id": message.from_user.id,
        "name": user_name,
        "category": category,
        "category_label": cat_label,
        "text": text_msg,
        "date": datetime.now(tz).strftime("%Y-%m-%d %H:%M"),
    })
    save_json(support_file, support)

    await notify_admin_support(message.from_user.id, user_name, category, text_msg)

    await message.answer("✅ Ваше сообщение успешно отправлено Администрации!", reply_markup=main_keyboard())
    await state.clear()


# ====================== АДМИН ПАНЕЛЬ ======================

@dp.message(Command("admin"))
async def admin_panel(message: types.Message, state: FSMContext):
    await state.clear()
    if str(message.from_user.id) not in admin_users:
        await message.answer("❌ Нет доступа!")
        return
    await message.answer("🛠 <b>Админ-панель</b>", reply_markup=admin_keyboard(), parse_mode="HTML")


@dp.callback_query(F.data == "admin_back")
async def admin_back(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    await callback.message.edit_text("🛠 <b>Админ-панель</b>", reply_markup=admin_keyboard(), parse_mode="HTML")
    await callback.answer()


# --- Добавление матча ---

@dp.callback_query(F.data == "add_match_start")
async def add_match_start(callback: types.CallbackQuery, state: FSMContext):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    await callback.message.edit_text(
        "Шаг 1/3: Введите название команд (например: Спартак — Зенит):",
        reply_markup=back_keyboard("admin_back"),
    )
    await state.set_state(AdminStates.add_match_name)
    await callback.answer()


@dp.message(AdminStates.add_match_name)
async def add_match_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await message.answer(
        "Шаг 2/3: Страна и лига (через пробел, например: Россия РПЛ):",
        reply_markup=back_keyboard("admin_back"),
    )
    await state.set_state(AdminStates.add_country_league)


@dp.message(AdminStates.add_country_league)
async def add_country_league(message: types.Message, state: FSMContext):
    parts = message.text.strip().split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Пожалуйста, введите страну и лигу через пробел (например: Россия РПЛ).")
        return
    country, league = parts[0], parts[1]
    await state.update_data(country=country, league=league)
    await message.answer(
        "Шаг 3/3: Введите полный текст матча (одним сообщением):",
        reply_markup=back_keyboard("admin_back"),
    )
    await state.set_state(AdminStates.add_text)


@dp.message(AdminStates.add_text)
async def add_match_text(message: types.Message, state: FSMContext):
    data = await state.get_data()
    new_match = {
        "name": data["name"],
        "country": data["country"],
        "league": data["league"],
        "text": message.text,
    }
    matches_data.setdefault("matches", []).append(new_match)
    save_json(matches_file, matches_data)
    await state.clear()
    await message.answer(
        f"✅ Матч добавлен!\n\n{new_match['name']}\n{new_match['country']} — {new_match['league']}",
        reply_markup=admin_back_keyboard(),
    )


# --- Удаление матчей ---

@dp.callback_query(F.data == "delete_match_menu")
async def delete_match_menu(callback: types.CallbackQuery, state: FSMContext):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    await state.clear()
    all_matches = matches_data.get("matches", [])
    if not all_matches:
        await callback.message.edit_text("Матчей нет.", reply_markup=admin_back_keyboard())
        await callback.answer()
        return

    kb = []
    for i, m in enumerate(all_matches):
        kb.append([InlineKeyboardButton(text=f"{m['name']} ({m['country']} {m['league']})", callback_data=f"delmatch_{i}")])
    kb.append([InlineKeyboardButton(text="🗑 Очистить все", callback_data="delmatch_all")])
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")])
    await callback.message.edit_text("Выберите матч для удаления:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await callback.answer()


@dp.callback_query(F.data.startswith("delmatch_"))
async def delete_match(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    action = callback.data.replace("delmatch_", "")
    if action == "all":
        matches_data["matches"] = []
        save_json(matches_file, matches_data)
        await callback.message.edit_text("✅ Все матчи удалены.", reply_markup=admin_back_keyboard())
        await callback.answer()
        return
    idx = int(action)
    all_matches = matches_data.get("matches", [])
    if idx < len(all_matches):
        removed = all_matches.pop(idx)
        save_json(matches_file, matches_data)
        await callback.message.edit_text(
            f"✅ Удалён: {removed['name']}",
            reply_markup=admin_back_keyboard(),
        )
    else:
        await callback.answer("Матч не найден", show_alert=True)
    await callback.answer()


# --- Управление Premium ---

@dp.callback_query(F.data == "premium_admin_menu")
async def premium_admin_menu(callback: types.CallbackQuery, state: FSMContext):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    await state.clear()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ Выдать Premium по ID", callback_data="prem_give")],
        [InlineKeyboardButton(text="❌ Снять Premium по ID", callback_data="prem_remove")],
        [InlineKeyboardButton(text="⭐ Выдать всем", callback_data="prem_give_all")],
        [InlineKeyboardButton(text="❌ Снять у всех", callback_data="prem_remove_all")],
        [InlineKeyboardButton(text="📋 Список Premium", callback_data="prem_list")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")],
    ])
    await callback.message.edit_text("💰 Управление Premium", reply_markup=kb)
    await callback.answer()


@dp.callback_query(F.data == "prem_give")
async def prem_give_start(callback: types.CallbackQuery, state: FSMContext):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    await callback.message.edit_text(
        "Введите ID пользователя для выдачи Premium:",
        reply_markup=back_keyboard("premium_admin_menu"),
    )
    await state.set_state(AdminStates.premium_give_id)
    await callback.answer()


@dp.message(AdminStates.premium_give_id)
async def prem_give_id(message: types.Message, state: FSMContext):
    target_id = message.text.strip()
    if target_id not in users:
        await message.answer("Пользователь не найден!", reply_markup=admin_back_keyboard())
        await state.clear()
        return
    users[target_id]["subscription"] = "Premium"
    users[target_id]["end_date"] = (datetime.now(tz) + timedelta(days=30)).strftime("%Y-%m-%d")
    save_json(users_file, users)
    await message.answer(f"✅ Premium выдан пользователю {target_id}", reply_markup=admin_back_keyboard())
    await state.clear()


@dp.callback_query(F.data == "prem_remove")
async def prem_remove_start(callback: types.CallbackQuery, state: FSMContext):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    await callback.message.edit_text(
        "Введите ID пользователя для снятия Premium:",
        reply_markup=back_keyboard("premium_admin_menu"),
    )
    await state.set_state(AdminStates.premium_remove_id)
    await callback.answer()


@dp.message(AdminStates.premium_remove_id)
async def prem_remove_id(message: types.Message, state: FSMContext):
    target_id = message.text.strip()
    if target_id not in users:
        await message.answer("Пользователь не найден!", reply_markup=admin_back_keyboard())
        await state.clear()
        return
    users[target_id]["subscription"] = "Free"
    save_json(users_file, users)
    await message.answer(f"✅ Premium снят у пользователя {target_id}", reply_markup=admin_back_keyboard())
    await state.clear()


@dp.callback_query(F.data == "prem_give_all")
async def prem_give_all(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    for uid, u in users.items():
        u["subscription"] = "Premium"
        u["end_date"] = (datetime.now(tz) + timedelta(days=30)).strftime("%Y-%m-%d")
    save_json(users_file, users)
    await callback.message.edit_text("✅ Premium выдан всем пользователям!", reply_markup=admin_back_keyboard())
    await callback.answer()


@dp.callback_query(F.data == "prem_remove_all")
async def prem_remove_all(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    for uid, u in users.items():
        u["subscription"] = "Free"
    save_json(users_file, users)
    await callback.message.edit_text("✅ Premium снят у всех пользователей!", reply_markup=admin_back_keyboard())
    await callback.answer()


@dp.callback_query(F.data == "prem_list")
async def prem_list(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    premium_users = [uid for uid, u in users.items() if u.get("subscription") == "Premium"]
    if not premium_users:
        text = "Premium-пользователей нет."
    else:
        lines = [f"<code>{uid}</code> — до {u.get('end_date', '?')}" for uid, u in users.items() if u.get("subscription") == "Premium"]
        text = f"⭐ Premium-пользователи ({len(premium_users)}):\n\n" + "\n".join(lines)
    await callback.message.edit_text(text, reply_markup=admin_back_keyboard(), parse_mode="HTML")
    await callback.answer()


# --- Техподдержка в админке ---

@dp.callback_query(F.data == "support_admin_menu")
async def support_admin_menu(callback: types.CallbackQuery, state: FSMContext):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    await state.clear()
    threads = support.get("threads", {})
    if not threads:
        await callback.message.edit_text("Сообщений поддержки нет.", reply_markup=admin_back_keyboard())
        await callback.answer()
        return

    kb = []
    for uid, msgs in threads.items():
        last_msg = msgs[-1] if msgs else {}
        cat_label = last_msg.get("category_label", "❓")
        user_name = last_msg.get("name", "Неизвестно")
        count = len(msgs)
        last_date = last_msg.get("date", "—")
        kb.append([
            InlineKeyboardButton(
                text=f"{cat_label} | {user_name} ({count} сообщ.) [{last_date}]",
                callback_data=f"supthread_{uid}",
            )
        ])
    kb.append([InlineKeyboardButton(text="🗑 Очистить все переписки", callback_data="supclear_all")])
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")])
    await callback.message.edit_text("🛠 Сообщения поддержки:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await callback.answer()


@dp.callback_query(F.data.startswith("supthread_"))
async def show_support_thread(callback: types.CallbackQuery, state: FSMContext):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    uid = callback.data.replace("supthread_", "")
    threads = support.get("threads", {})
    if uid not in threads or not threads[uid]:
        await callback.answer("Переписка не найдена", show_alert=True)
        return

    msgs = threads[uid]
    lines = []
    for m in msgs:
        sender = "👤 Пользователь" if m["from"] == "user" else "🛠 Админ"
        cat = m.get("category_label", "")
        cat_str = f" [{cat}]" if cat else ""
        lines.append(f"{sender}{cat_str}\n📝 {m['text']}\n🕒 {m['date']}\n")

    text = f"🛠 <b>Переписка с {msgs[0].get('name', 'Неизвестно')}</b> (ID: <code>{uid}</code>)\n\n" + "\n".join(lines)

    await state.update_data(reply_to_uid=uid)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Ответить", callback_data=f"supreply_{uid}")],
        [InlineKeyboardButton(text="🗑 Очистить эту переписку", callback_data=f"supclear_{uid}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="support_admin_menu")],
    ])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data.startswith("supreply_"))
async def supreply_start(callback: types.CallbackQuery, state: FSMContext):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    uid = callback.data.replace("supreply_", "")
    await state.update_data(reply_to_uid=uid)
    await state.set_state(AdminStates.reply_support_text)
    await callback.message.edit_text(
        f"💬 Напишите ответ для пользователя (ID: {uid}):",
        reply_markup=back_keyboard(f"supthread_{uid}"),
    )
    await callback.answer()


@dp.message(AdminStates.reply_support_text)
async def supreply_send(message: types.Message, state: FSMContext):
    data = await state.get_data()
    uid = data.get("reply_to_uid")
    if not uid:
        await message.answer("Ошибка: не найден ID пользователя.", reply_markup=admin_back_keyboard())
        await state.clear()
        return

    reply_text = message.text
    threads = support.get("threads", {})
    threads.setdefault(uid, []).append({
        "from": "admin",
        "id": message.from_user.id,
        "name": "Админ",
        "text": reply_text,
        "date": datetime.now(tz).strftime("%Y-%m-%d %H:%M"),
    })
    save_json(support_file, support)

    try:
        await bot.send_message(
            int(uid),
            f"🛠 <b>Ответ от техподдержки:</b>\n\n{reply_text}",
            parse_mode="HTML",
            reply_markup=main_keyboard(),
        )
    except Exception:
        pass

    await message.answer("✅ Ответ отправлен пользователю!", reply_markup=admin_back_keyboard())
    await state.clear()


@dp.callback_query(F.data.startswith("supclear_"))
async def supclear_one(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    uid = callback.data.replace("supclear_", "")
    if uid in support.get("threads", {}):
        del support["threads"][uid]
        save_json(support_file, support)
    await callback.message.edit_text("✅ Переписка очищена.", reply_markup=admin_back_keyboard())
    await callback.answer()


@dp.callback_query(F.data == "supclear_all")
async def supclear_all(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    support["threads"] = {}
    save_json(support_file, support)
    await callback.message.edit_text("✅ Все переписки очищены.", reply_markup=admin_back_keyboard())
    await callback.answer()


@dp.callback_query(F.data == "no_matches")
async def no_matches(callback: types.CallbackQuery):
    await callback.answer("Матчей пока нет. Загляните позже!", show_alert=True)


# ====================== ЗАПУСК ======================

async def main():
    await dp.start_polling(bot, skip_updates=True)


if __name__ == "__main__":
    asyncio.run(main())
