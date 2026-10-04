import os
import json
import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

tz = ZoneInfo("Europe/Moscow")

try:
    from aiogram import Bot, Dispatcher, F, types
    from aiogram.filters import Command, CommandStart
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    from aiogram.exceptions import TelegramBadRequest
except ImportError:
    print("aiogram not installed")

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = str(os.getenv("ADMIN_ID", ""))
BOT_USERNAME = os.getenv("BOT_USERNAME", "your_bot")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)
users_file = os.path.join(DATA_DIR, "users.json")
matches_file = os.path.join(DATA_DIR, "matches.json")
express_file = os.path.join(DATA_DIR, "express.json")
support_file = os.path.join(DATA_DIR, "support.json")

TARIFFS = {
    "free": {"name": "Free", "emoji": "🆓", "matches_limit": 3, "price": 0, "duration_days": None},
    "lite": {"name": "Lite", "emoji": "📘", "matches_limit": 10, "price": 100, "duration_days": 30},
    "pro": {"name": "Pro", "emoji": "⚡", "matches_limit": 20, "price": 200, "duration_days": 30},
    "premium": {"name": "Premium", "emoji": "⭐", "matches_limit": None, "price": 300, "duration_days": 30},
}

COUNTRY_FLAGS = {
    "Россия": "🇷🇺", "Англия": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "Испания": "🇪🇸", "Италия": "🇮🇹",
    "Германия": "🇩🇪", "Франция": "🇫🇷", "Португалия": "🇵🇹", "Нидерланды": "🇳🇱",
    "Бразилия": "🇧🇷", "Аргентина": "🇦🇷", "Турция": "🇹🇷", "Бельгия": "🇧🇪",
    "Шотландия": "🏴󠁧󠁢󠁳󠁣󠁴󠁿", "Уэльс": "🏴󠁧󠁢󠁷󠁬󠁳󠁿", "США": "🇺🇸", "Мексика": "🇲🇽",
    "Япония": "🇯🇵", "Китай": "🇨🇳", "Южная Корея": "🇰🇷", "Австралия": "🇦🇺",
    "Швеция": "🇸🇪", "Норвегия": "🇳🇴", "Дания": "🇩🇰", "Финляндия": "🇫🇮",
    "Польша": "🇵🇱", "Чехия": "🇨🇿", "Австрия": "🇦🇹", "Швейцария": "🇨🇭",
    "Греция": "🇬🇷", "Хорватия": "🇭🇷", "Сербия": "🇷🇸", "Украина": "🇺🇦",
}

SUPPORT_CATEGORIES = {
    "bug": "🐛 Баг / ошибка",
    "payment": "💳 Оплата",
    "idea": "💡 Предложение",
    "question": "❓ Вопрос",
}

admin_states = {}
user_states = {}


def load_json(path, default):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default
    return default


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


users = load_json(users_file, {})
matches_data = load_json(matches_file, {"matches": []})
express_data = load_json(express_file, {"matches": [], "total_coeff": 0})
support_data = load_json(support_file, {"threads": {}})


def get_flag(country):
    return COUNTRY_FLAGS.get(country, "🌍")


def get_user_tariff(user_id):
    user = users.get(user_id, {})
    return user.get("tariff", "free")


def is_premium(user_id):
    return get_user_tariff(user_id) in ("premium", "pro", "lite")


def check_match_limit(user_id):
    today = datetime.now(tz).strftime("%Y-%m-%d")
    user = users.get(user_id, {})
    tariff_key = user.get("tariff", "free")
    tariff = TARIFFS.get(tariff_key, TARIFFS["free"])
    if tariff["matches_limit"] is None:
        return True, ""
    views_today = user.get("views_by_day", {}).get(today, 0)
    if views_today < tariff["matches_limit"]:
        return True, ""
    limit = tariff["matches_limit"]
    msg = "Лимит исчерпан: сегодня вы посмотрели " + str(limit) + " матчей. Купите подписку выше."
    return False, msg


def update_view_count(user_id):
    today = datetime.now(tz).strftime("%Y-%m-%d")
    user_data = users.setdefault(user_id, {})
    views_by_day = user_data.setdefault("views_by_day", {})
    views_by_day[today] = views_by_day.get(today, 0) + 1
    save_json(users_file, users)


def get_match_status_text(start_time_str):
    if not start_time_str:
        return "⏳ Время матча не указано"
    try:
        start_dt = datetime.fromisoformat(start_time_str)
    except (ValueError, TypeError):
        return "⏳ Время матча не указано"
    now = datetime.now(tz)
    if start_dt.tzinfo is None:
        start_dt = start_dt.replace(tzinfo=tz)
    else:
        start_dt = start_dt.astimezone(tz)
    delta = start_dt - now
    if delta.total_seconds() > 0:
        hours, remainder = divmod(int(delta.total_seconds()), 3600)
        minutes, _ = divmod(remainder, 60)
        return "⏳ До начала: " + str(hours) + " ч. " + str(minutes) + " мин."
    elapsed_seconds = -delta.total_seconds()
    minutes_elapsed = int(elapsed_seconds // 60)
    if minutes_elapsed < 120:
        return "⏱ Идёт матч: " + str(minutes_elapsed) + "'"
    return "✅ Матч завершён"


def back_keyboard(callback_data):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data=callback_data)]
    ])


def main_menu_kb(user_id):
    rows = [
        [InlineKeyboardButton(text="⚽ Матчи", callback_data="matches")],
        [InlineKeyboardButton(text="🚆 Экспресс дня", callback_data="express")],
        [InlineKeyboardButton(text="👤 Аккаунт", callback_data="account"),
         InlineKeyboardButton(text="💳 Тарифы", callback_data="tariffs")],
        [InlineKeyboardButton(text="🛠 Техподдержка", callback_data="support")],
    ]
    if str(user_id) == ADMIN_ID:
        rows.append([InlineKeyboardButton(text="🔧 Админка", callback_data="admin")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_main_menu_text(name):
    return (
        "👋 Здравствуйте, " + name + "!\n\n"
        "Это бот с прогнозами на футбольные матчи.\n"
        "Выберите раздел ниже:"
    )


# ===================== START =====================

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    user_id = str(message.from_user.id)
    name = message.from_user.first_name or "Пользователь"
    args = message.text.split()
    ref_id = None
    if len(args) > 1 and args[1].startswith("ref_"):
        ref_id = args[1][4:]

    is_new = user_id not in users
    if is_new:
        users[user_id] = {
            "name": name,
            "tariff": "free",
            "subscription_end": None,
            "views_by_day": {},
            "referrals_count": 0,
            "referred_by": ref_id if ref_id and ref_id in users else None,
            "registered_at": datetime.now(tz).strftime("%Y-%m-%d %H:%M"),
        }
        if ref_id and ref_id in users and ref_id != user_id:
            ref_user = users[ref_id]
            ref_user["referrals_count"] = ref_user.get("referrals_count", 0) + 1
            if "ref_ids" not in ref_user:
                ref_user["ref_ids"] = []
            ref_user["ref_ids"].append(user_id)
            premium_end = (datetime.now(tz) + timedelta(days=3)).strftime("%Y-%m-%d")
            ref_user["subscription_end"] = premium_end
            ref_user["tariff"] = "premium"
            try:
                await bot.send_message(
                    int(ref_id),
                    "🎉 По вашей реферальной ссылке зарегистрировался новый пользователь!\n"
                    "Вам начислено 3 дня Premium бесплатно!"
                )
            except Exception:
                pass
        save_json(users_file, users)
    else:
        users[user_id]["name"] = name
        save_json(users_file, users)

    await message.answer(get_main_menu_text(name), reply_markup=main_menu_kb(user_id))


# ===================== ГЛАВНОЕ МЕНЮ =====================

@dp.callback_query(F.data == "main_menu")
async def cb_main_menu(callback: types.CallbackQuery):
    user_id = str(callback.from_user.id)
    name = users.get(user_id, {}).get("name", "Пользователь")
    await callback.message.edit_text(get_main_menu_text(name), reply_markup=main_menu_kb(user_id))
    await callback.answer()


# ===================== МАТЧИ =====================

@dp.callback_query(F.data == "matches")
async def cb_matches(callback: types.CallbackQuery):
    all_matches = matches_data.get("matches", [])
    if not all_matches:
        await callback.message.edit_text(
            "⚽ Матчи\n\nСейчас нет доступных матчей.",
            reply_markup=back_keyboard("main_menu")
        )
        await callback.answer()
        return

    user_id = str(callback.from_user.id)
    tariff_key = get_user_tariff(user_id)
    tariff = TARIFFS.get(tariff_key, TARIFFS["free"])
    today = datetime.now(tz).strftime("%Y-%m-%d")
    views_today = users.get(user_id, {}).get("views_by_day", {}).get(today, 0)
    limit = tariff["matches_limit"]

    if limit is None:
        limit_str = "Безлимит"
    else:
        limit_str = str(views_today) + "/" + str(limit)

    text = "⚽ Матчи\n\nЛимит сегодня: " + limit_str + "\n"
    rows = []
    for i, match in enumerate(all_matches):
        flag = get_flag(match.get("country", ""))
        btn_text = flag + " " + match.get("name", "Матч")
        rows.append([InlineKeyboardButton(text=btn_text, callback_data="match_" + str(i))])
    rows.append([InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")])
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await callback.answer()


@dp.callback_query(F.data.startswith("match_"))
async def cb_match_details(callback: types.CallbackQuery):
    idx_str = callback.data.replace("match_", "")
    try:
        idx = int(idx_str)
    except ValueError:
        await callback.answer("Ошибка", show_alert=True)
        return
    all_matches = matches_data.get("matches", [])
    if idx >= len(all_matches) or idx < 0:
        await callback.answer("Матч не найден", show_alert=True)
        return

    user_id = str(callback.from_user.id)
    allowed, error_msg = check_match_limit(user_id)
    if not allowed:
        await callback.answer(error_msg, show_alert=True)
        return

    update_view_count(user_id)

    match = all_matches[idx]
    flag = get_flag(match.get("country", ""))
    status_line = get_match_status_text(match.get("start_time", ""))
    coeff = match.get("coefficient", "")
    coeff_text = ""
    if coeff:
        coeff_text = "\n💰 Коэффициент: " + str(coeff)

    text = (
        "⚽ <b>" + match.get("name", "") + "</b>\n"
        + flag + " " + match.get("country", "") + " | " + match.get("league", "") + "\n"
        + status_line + coeff_text + "\n\n"
        + match.get("text", "")
    )

    await callback.message.edit_text(text, reply_markup=back_keyboard("matches"), parse_mode="HTML")
    await callback.answer()


# ===================== ЭКСПРЕСС ДНЯ =====================

@dp.callback_query(F.data == "express")
async def cb_express(callback: types.CallbackQuery):
    user_id = str(callback.from_user.id)
    tariff_key = get_user_tariff(user_id)
    express_matches = express_data.get("matches", [])

    if not express_matches:
        await callback.message.edit_text(
            "🚆 Экспресс дня\n\nЭкспресс пока не составлен. Загляните позже!",
            reply_markup=back_keyboard("main_menu")
        )
        await callback.answer()
        return

    if tariff_key == "free":
        preview = "🚆 Экспресс дня\n\n"
        preview += "🔒 Полный экспресс доступен на тарифах Lite, Pro и Premium.\n\n"
        preview += "В экспрессе " + str(len(express_matches)) + " матчей.\n"
        preview += "Общий коэффициент: " + str(express_data.get("total_coeff", 0)) + "\n\n"
        preview += "💳 Оформите подписку в разделе «Тарифы»."
        await callback.message.edit_text(preview, reply_markup=back_keyboard("main_menu"))
        await callback.answer()
        return

    text = "🚆 <b>Экспресс дня</b>\n\n"
    for i, m in enumerate(express_matches, 1):
        flag = get_flag(m.get("country", ""))
        text += "<b>" + str(i) + ". " + m.get("name", "") + "</b>\n"
        text += flag + " " + m.get("country", "") + " | " + m.get("league", "") + "\n"
        text += "Прогноз: " + m.get("prediction", "") + "\n"
        text += "💰 Коэффициент: " + str(m.get("coefficient", "")) + "\n\n"

    text += "━━━━━━━━━━━━━━━━\n"
    text += "🎯 Общий коэффициент: <b>" + str(express_data.get("total_coeff", 0)) + "</b>"

    await callback.message.edit_text(text, reply_markup=back_keyboard("main_menu"), parse_mode="HTML")
    await callback.answer()


# ===================== АККАУНТ =====================

@dp.callback_query(F.data == "account")
async def cb_account(callback: types.CallbackQuery):
    user_id = str(callback.from_user.id)
    user = users.get(user_id, {})
    tariff_key = user.get("tariff", "free")
    tariff = TARIFFS.get(tariff_key, TARIFFS["free"])

    today = datetime.now(tz).strftime("%Y-%m-%d")
    views_today = user.get("views_by_day", {}).get(today, 0)
    limit = tariff["matches_limit"]

    if limit is None:
        limit_text = "✅ Безлимит"
    else:
        limit_text = "📊 Сегодня: " + str(views_today) + " из " + str(limit)

    end_date = user.get("subscription_end")
    if tariff_key == "free":
        date_text = "♾ Бессрочно"
    elif end_date:
        date_text = "📅 До: " + end_date
    else:
        date_text = "⚠️ Подписка истекла"

    total_matches = len(matches_data.get("matches", []))
    total_users = len(users)
    premium_count = sum(1 for u in users.values() if u.get("tariff") == "premium")
    total_views = sum(user.get("views_by_day", {}).values())

    text = (
        "👤 <b>Аккаунт</b>\n\n"
        "🆔 ID: <code>" + user_id + "</code>\n"
        "👤 Имя: " + user.get("name", "—") + "\n"
        + tariff["emoji"] + " " + tariff["name"] + "\n"
        + limit_text + "\n"
        + date_text + "\n\n"
        "⭐ Рефералов: " + str(user.get("referrals_count", 0)) + "\n"
        "⚽ Всего просмотрено: " + str(total_views) + "\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "📊 Статистика бота:\n"
        "⚽ Матчей в базе: " + str(total_matches) + "\n"
        "👥 Пользователей: " + str(total_users) + "\n"
        "💎 Premium: " + str(premium_count)
    )

    rows = [
        [InlineKeyboardButton(text="🔗 Моя реферальная ссылка", callback_data="ref_link")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")],
    ]
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data == "ref_link")
async def cb_ref_link(callback: types.CallbackQuery):
    user_id = str(callback.from_user.id)
    ref_link = "https://t.me/" + BOT_USERNAME + "?start=ref_" + user_id
    text = (
        "🔗 <b>Ваша реферальная ссылка</b>\n\n"
        "Поделитесь ссылкой с друзьями. За каждого пользователя, зарегистрировавшегося по ней, "
        "вы получаете 3 дня Premium бесплатно!\n\n"
        "<code>" + ref_link + "</code>"
    )
    await callback.message.edit_text(text, reply_markup=back_keyboard("account"), parse_mode="HTML")
    await callback.answer()


# ===================== ТАРИФЫ =====================

@dp.callback_query(F.data == "tariffs")
async def cb_tariffs(callback: types.CallbackQuery):
    user_id = str(callback.from_user.id)
    current = get_user_tariff(user_id)

    text = "💳 <b>Тарифы и оплата</b>\n\n"
    rows = []
    for key, info in TARIFFS.items():
        mark = "✅" if key == current else "  "
        if info["matches_limit"] is None:
            lim = "Безлимит матчей/день"
        else:
            lim = str(info["matches_limit"]) + " матчей/день"
        price_str = "Бесплатно" if info["price"] == 0 else str(info["price"]) + " ₽/мес"
        text += mark + " " + info["emoji"] + " " + info["name"] + " — " + lim + " — " + price_str + "\n"
        if key != current and key != "free":
            rows.append([InlineKeyboardButton(
                text="Купить " + info["name"] + " (" + str(info["price"]) + " ₽)",
                callback_data="buy_" + key
            )])
    rows.append([InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")])
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data.startswith("buy_"))
async def cb_buy(callback: types.CallbackQuery):
    key = callback.data.replace("buy_", "")
    if key not in TARIFFS:
        await callback.answer("Ошибка тарифа", show_alert=True)
        return
    info = TARIFFS[key]
    user_id = str(callback.from_user.id)

    users.setdefault(user_id, {})
    users[user_id]["tariff"] = key
    if key == "free":
        users[user_id]["subscription_end"] = None
    else:
        users[user_id]["subscription_end"] = (datetime.now(tz) + timedelta(days=info["duration_days"])).strftime("%Y-%m-%d")
    users[user_id]["views_by_day"] = {}
    save_json(users_file, users)

    await callback.message.edit_text(
        "🎉 Вы успешно перешли на тариф " + info["emoji"] + " " + info["name"] + "!",
        reply_markup=back_keyboard("main_menu")
    )
    await callback.answer()


# ===================== ТЕХПОДДЕРЖКА =====================

@dp.callback_query(F.data == "support")
async def cb_support(callback: types.CallbackQuery):
    rows = []
    for cat_key, cat_label in SUPPORT_CATEGORIES.items():
        rows.append([InlineKeyboardButton(text=cat_label, callback_data="supcat_" + cat_key)])
    rows.append([InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")])
    await callback.message.edit_text(
        "🛠 <b>Техподдержка</b>\n\nВыберите категорию обращения:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("supcat_"))
async def cb_supcat(callback: types.CallbackQuery):
    cat_key = callback.data.replace("supcat_", "")
    user_id = str(callback.from_user.id)
    user_states[user_id] = {"action": "support_message", "category": cat_key}
    cat_label = SUPPORT_CATEGORIES.get(cat_key, "Вопрос")
    await callback.message.edit_text(
        cat_label + "\n\nНапишите ваше сообщение одним текстом. "
        "Администратор увидит его и ответит вам.\n\n"
        "Для отмены нажмите «🔙 Назад».",
        reply_markup=back_keyboard("support")
    )
    await callback.answer()


@dp.message(F.text)
async def handle_text(message: types.Message):
    user_id = str(message.from_user.id)
    state = user_states.get(user_id)

    if state and state.get("action") == "support_message":
        cat_key = state.get("category", "question")
        cat_label = SUPPORT_CATEGORIES.get(cat_key, "❓ Вопрос")
        text = message.text

        threads = support_data.setdefault("threads", {})
        thread = threads.setdefault(user_id, {"messages": [], "category": cat_key})
        thread["messages"].append({
            "from": "user",
            "text": text,
            "time": datetime.now(tz).strftime("%Y-%m-%d %H:%M"),
            "category": cat_key,
        })
        thread["category"] = cat_key
        save_json(support_file, support_data)

        await message.answer(
            "✅ Ваше сообщение успешно отправлено Администрации!\n"
            "Ожидайте ответа.",
            reply_markup=back_keyboard("main_menu")
        )

        try:
            admin_text = (
                "🛠 <b>Новое обращение в поддержку</b>\n\n"
                "📂 Категория: " + cat_label + "\n"
                "👤 Пользователь: " + message.from_user.first_name + "\n"
                "🆔 ID: <code>" + user_id + "</code>\n\n"
                "Сообщение:\n" + text
            )
            await bot.send_message(int(ADMIN_ID), admin_text, parse_mode="HTML")
        except Exception:
            pass

        user_states.pop(user_id, None)
        return

    if state and state.get("action") == "admin_reply":
        target_id = state.get("target_id")
        threads = support_data.get("threads", {})
        thread = threads.get(target_id, {"messages": []})
        thread["messages"].append({
            "from": "admin",
            "text": message.text,
            "time": datetime.now(tz).strftime("%Y-%m-%d %H:%M"),
        })
        save_json(support_file, support_data)
        try:
            await bot.send_message(
                int(target_id),
                "💬 <b>Ответ от администрации:</b>\n\n" + message.text,
                parse_mode="HTML"
            )
        except Exception:
            pass
        await message.answer("✅ Ответ отправлен пользователю.", reply_markup=back_keyboard("admin"))
        user_states.pop(user_id, None)
        return

    if state and state.get("action") == "admin_add_match":
        step = state.get("step")
        if step == "name":
            state["match_data"] = {"name": message.text}
            state["step"] = "country"
            await message.answer("🌍 Введите страну (например, Россия, Англия):")
        elif step == "country":
            state["match_data"]["country"] = message.text
            state["step"] = "league"
            await message.answer("🏆 Введите лигу (например, АПЛ, Ла Лига):")
        elif step == "league":
            state["match_data"]["league"] = message.text
            state["step"] = "coefficient"
            await message.answer("💰 Введите коэффициент (например, 1.85):")
        elif step == "coefficient":
            try:
                coeff = float(message.text.replace(",", "."))
            except ValueError:
                await message.answer("❌ Неверный формат. Введите число, например 1.85:")
                return
            state["match_data"]["coefficient"] = coeff
            state["step"] = "start_time"
            await message.answer(
                "⏰ Введите время начала матча в формате YYYY-MM-DDTHH:MM:SS+0300\n"
                "Например: 2024-10-25T19:30:00+0300\n"
                "Или отправьте «-» если не знаете время."
            )
        elif step == "start_time":
            st = message.text.strip()
            if st == "-":
                state["match_data"]["start_time"] = ""
            else:
                state["match_data"]["start_time"] = st
            state["step"] = "text"
            await message.answer("📝 Введите текст прогноза (можно многострочный):")
        elif step == "text":
            state["match_data"]["text"] = message.text
            matches_data.setdefault("matches", []).append(state["match_data"])
            save_json(matches_file, matches_data)
            await message.answer("✅ Матч добавлен!", reply_markup=back_keyboard("admin"))
            user_states.pop(user_id, None)
        return

    if state and state.get("action") == "admin_add_express":
        step = state.get("step")
        if step == "name":
            state["match_data"] = {"name": message.text}
            state["step"] = "country"
            await message.answer("🌍 Введите страну:")
        elif step == "country":
            state["match_data"]["country"] = message.text
            state["step"] = "league"
            await message.answer("🏆 Введите лигу:")
        elif step == "league":
            state["match_data"]["league"] = message.text
            state["step"] = "prediction"
            await message.answer("📝 Введите прогноз:")
        elif step == "prediction":
            state["match_data"]["prediction"] = message.text
            state["step"] = "coefficient"
            await message.answer("💰 Введите коэффициент:")
        elif step == "coefficient":
            try:
                coeff = float(message.text.replace(",", "."))
            except ValueError:
                await message.answer("❌ Неверный формат. Введите число:")
                return
            state["match_data"]["coefficient"] = coeff
            express_data.setdefault("matches", []).append(state["match_data"])
            total = 1.0
            for m in express_data["matches"]:
                total *= m.get("coefficient", 1)
            express_data["total_coeff"] = round(total, 2)
            save_json(express_file, express_data)

            count = len(express_data["matches"])
            if count < 5:
                await message.answer(
                    "✅ Матч " + str(count) + " добавлен в экспресс.\n"
                    "Общий коэффициент: " + str(express_data["total_coeff"]) + "\n\n"
                    "Добавить ещё или завершить?",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="➕ Добавить ещё", callback_data="admin_express_add")],
                        [InlineKeyboardButton(text="✅ Завершить", callback_data="admin_express_done")],
                        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_express")],
                    ])
                )
            else:
                await message.answer(
                    "✅ Достигнут максимум (5 матчей). Экспресс сохранён!\n"
                    "Общий коэффициент: " + str(express_data["total_coeff"]),
                    reply_markup=back_keyboard("admin_express")
                )
            user_states.pop(user_id, None)
        return


# ===================== АДМИНКА =====================

@dp.callback_query(F.data == "admin")
async def cb_admin(callback: types.CallbackQuery):
    user_id = str(callback.from_user.id)
    if user_id != ADMIN_ID:
        await callback.answer("Нет доступа", show_alert=True)
        return
    total_users = len(users)
    total_matches = len(matches_data.get("matches", []))
    total_tickets = len(support_data.get("threads", {}))
    text = (
        "🔧 <b>Админ-панель</b>\n\n"
        "👥 Пользователей: " + str(total_users) + "\n"
        "⚽ Матчей: " + str(total_matches) + "\n"
        "🛠 Тикетов: " + str(total_tickets) + "\n"
        "🚆 Экспрессов: " + str(len(express_data.get("matches", []))) + "\n"
    )
    rows = [
        [InlineKeyboardButton(text="➕ Добавить матч", callback_data="admin_add_match"),
         InlineKeyboardButton(text="🗑 Удалить матч", callback_data="admin_del_match")],
        [InlineKeyboardButton(text="🚆 Экспресс дня", callback_data="admin_express")],
        [InlineKeyboardButton(text="👤 Выдать тариф", callback_data="admin_give_tariff")],
        [InlineKeyboardButton(text="🛠 Сообщения поддержки", callback_data="admin_support")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")],
    ]
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data == "admin_add_match")
async def cb_admin_add_match(callback: types.CallbackQuery):
    user_id = str(callback.from_user.id)
    if user_id != ADMIN_ID:
        await callback.answer("Нет доступа", show_alert=True)
        return
    user_states[user_id] = {"action": "admin_add_match", "step": "name"}
    await callback.message.edit_text(
        "➕ <b>Добавление матча</b>\n\nВведите название матча (например, Спартак — Зенет):",
        reply_markup=back_keyboard("admin"),
        parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query(F.data == "admin_del_match")
async def cb_admin_del_match(callback: types.CallbackQuery):
    user_id = str(callback.from_user.id)
    if user_id != ADMIN_ID:
        await callback.answer("Нет доступа", show_alert=True)
        return
    all_matches = matches_data.get("matches", [])
    if not all_matches:
        await callback.message.edit_text("Нет матчей для удаления.", reply_markup=back_keyboard("admin"))
        await callback.answer()
        return
    rows = []
    for i, m in enumerate(all_matches):
        rows.append([InlineKeyboardButton(
            text=m.get("name", "Матч " + str(i)) + " | " + m.get("country", ""),
            callback_data="delmatch_" + str(i)
        )])
    rows.append([InlineKeyboardButton(text="🗑 Удалить все", callback_data="delmatch_all")])
    rows.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin")])
    await callback.message.edit_text("Выберите матч для удаления:", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await callback.answer()


@dp.callback_query(F.data.startswith("delmatch_"))
async def cb_delmatch(callback: types.CallbackQuery):
    user_id = str(callback.from_user.id)
    if user_id != ADMIN_ID:
        await callback.answer("Нет доступа", show_alert=True)
        return
    val = callback.data.replace("delmatch_", "")
    if val == "all":
        matches_data["matches"] = []
        save_json(matches_file, matches_data)
        await callback.message.edit_text("✅ Все матчи удалены.", reply_markup=back_keyboard("admin"))
        await callback.answer()
        return
    idx = int(val)
    all_matches = matches_data.get("matches", [])
    if idx < len(all_matches):
        all_matches.pop(idx)
        save_json(matches_file, matches_data)
    await callback.message.edit_text("✅ Матч удалён.", reply_markup=back_keyboard("admin"))
    await callback.answer()


# --- Экспресс ---

@dp.callback_query(F.data == "admin_express")
async def cb_admin_express(callback: types.CallbackQuery):
    user_id = str(callback.from_user.id)
    if user_id != ADMIN_ID:
        await callback.answer("Нет доступа", show_alert=True)
        return
    express_matches = express_data.get("matches", [])
    text = "🚆 <b>Экспресс дня</b>\n\n"
    if express_matches:
        for i, m in enumerate(express_matches, 1):
            text += str(i) + ". " + m.get("name", "") + " — " + str(m.get("coefficient", "")) + "\n"
        text += "\nОбщий коэффициент: " + str(express_data.get("total_coeff", 0))
    else:
        text += "Экспресс пуст."
    rows = [
        [InlineKeyboardButton(text="➕ Добавить матч в экспресс", callback_data="admin_express_add")],
        [InlineKeyboardButton(text="🗑 Очистить экспресс", callback_data="admin_express_clear")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin")],
    ]
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data == "admin_express_add")
async def cb_admin_express_add(callback: types.CallbackQuery):
    user_id = str(callback.from_user.id)
    if user_id != ADMIN_ID:
        await callback.answer("Нет доступа", show_alert=True)
        return
    count = len(express_data.get("matches", []))
    if count >= 5:
        await callback.answer("Максимум 5 матчей в экспрессе", show_alert=True)
        return
    user_states[user_id] = {"action": "admin_add_express", "step": "name"}
    await callback.message.edit_text(
        "➕ Добавление матча в экспресс (" + str(count + 1) + "/5)\n\nВведите название матча:",
        reply_markup=back_keyboard("admin_express")
    )
    await callback.answer()


@dp.callback_query(F.data == "admin_express_done")
async def cb_admin_express_done(callback: types.CallbackQuery):
    await callback.message.edit_text("✅ Экспресс сохранён!", reply_markup=back_keyboard("admin"))
    await callback.answer()


@dp.callback_query(F.data == "admin_express_clear")
async def cb_admin_express_clear(callback: types.CallbackQuery):
    user_id = str(callback.from_user.id)
    if user_id != ADMIN_ID:
        await callback.answer("Нет доступа", show_alert=True)
        return
    express_data["matches"] = []
    express_data["total_coeff"] = 0
    save_json(express_file, express_data)
    await callback.message.edit_text("✅ Экспресс очищен.", reply_markup=back_keyboard("admin"))
    await callback.answer()


# --- Выдача тарифа ---

@dp.callback_query(F.data == "admin_give_tariff")
async def cb_admin_give_tariff(callback: types.CallbackQuery):
    user_id = str(callback.from_user.id)
    if user_id != ADMIN_ID:
        await callback.answer("Нет доступа", show_alert=True)
        return
    rows = [
        [InlineKeyboardButton(text="⭐ Premium (30 дней)", callback_data="givetariff_premium")],
        [InlineKeyboardButton(text="⚡ Pro (30 дней)", callback_data="givetariff_pro")],
        [InlineKeyboardButton(text="📘 Lite (30 дней)", callback_data="givetariff_lite")],
        [InlineKeyboardButton(text="🆓 Сброс на Free", callback_data="givetariff_free")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin")],
    ]
    await callback.message.edit_text(
        "👤 <b>Выдача тарифа</b>\n\nВведите ID пользователя (или нажмите тариф, чтобы выдать всем):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("givetariff_"))
async def cb_givetariff(callback: types.CallbackQuery):
    user_id = str(callback.from_user.id)
    if user_id != ADMIN_ID:
        await callback.answer("Нет доступа", show_alert=True)
        return
    tariff_key = callback.data.replace("givetariff_", "")
    admin_states[user_id] = {"action": "give_tariff", "tariff": tariff_key}
    await callback.message.edit_text(
        "Введите ID пользователя, которому выдать тариф " + TARIFFS.get(tariff_key, {}).get("name", "") + ":",
        reply_markup=back_keyboard("admin_give_tariff")
    )
    await callback.answer()


# --- Поддержка (админ) ---

@dp.callback_query(F.data == "admin_support")
async def cb_admin_support(callback: types.CallbackQuery):
    user_id = str(callback.from_user.id)
    if user_id != ADMIN_ID:
        await callback.answer("Нет доступа", show_alert=True)
        return
    threads = support_data.get("threads", {})
    if not threads:
        await callback.message.edit_text("🛠 Нет обращений в поддержку.", reply_markup=back_keyboard("admin"))
        await callback.answer()
        return
    rows = []
    for tid, thread in threads.items():
        cat_label = SUPPORT_CATEGORIES.get(thread.get("category", ""), "❓")
        uname = users.get(tid, {}).get("name", "Пользователь")
        msg_count = len(thread.get("messages", []))
        rows.append([InlineKeyboardButton(
            text=cat_label + " | " + uname + " (" + str(msg_count) + " сообщ.)",
            callback_data="support_thread_" + tid
        )])
    rows.append([InlineKeyboardButton(text="🗑 Очистить все", callback_data="support_clear_all")])
    rows.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin")])
    await callback.message.edit_text("🛠 <b>Обращения в поддержку</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data.startswith("support_thread_"))
async def cb_support_thread(callback: types.CallbackQuery):
    user_id = str(callback.from_user.id)
    if user_id != ADMIN_ID:
        await callback.answer("Нет доступа", show_alert=True)
        return
    target_id = callback.data.replace("support_thread_", "")
    threads = support_data.get("threads", {})
    thread = threads.get(target_id, {})
    messages = thread.get("messages", [])
    cat_label = SUPPORT_CATEGORIES.get(thread.get("category", ""), "❓ Вопрос")

    text = cat_label + " | <b>Переписка</b>\n\n"
    for msg in messages:
        sender = "👤 Пользователь" if msg.get("from") == "user" else "💬 Админ"
        text += sender + " (" + msg.get("time", "") + "):\n" + msg.get("text", "") + "\n\n"

    rows = [
        [InlineKeyboardButton(text="💬 Ответить", callback_data="support_reply_" + target_id)],
        [InlineKeyboardButton(text="🗑 Очистить", callback_data="support_clear_" + target_id)],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_support")],
    ]
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data.startswith("support_reply_"))
async def cb_support_reply(callback: types.CallbackQuery):
    user_id = str(callback.from_user.id)
    if user_id != ADMIN_ID:
        await callback.answer("Нет доступа", show_alert=True)
        return
    target_id = callback.data.replace("support_reply_", "")
    user_states[user_id] = {"action": "admin_reply", "target_id": target_id}
    await callback.message.edit_text(
        "💬 Напишите ответ пользователю:",
        reply_markup=back_keyboard("admin_support")
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("support_clear_"))
async def cb_support_clear(callback: types.CallbackQuery):
    user_id = str(callback.from_user.id)
    if user_id != ADMIN_ID:
        await callback.answer("Нет доступа", show_alert=True)
        return
    val = callback.data.replace("support_clear_", "")
    if val == "all":
        support_data["threads"] = {}
    else:
        support_data.get("threads", {}).pop(val, None)
    save_json(support_file, support_data)
    await callback.message.edit_text("✅ Очищено.", reply_markup=back_keyboard("admin"))
    await callback.answer()


# ===================== ЗАПУСК =====================

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
