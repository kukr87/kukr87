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
BOT_USERNAME = os.getenv("BOT_USERNAME", "koef_bot")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

admin_users = {str(ADMIN_ID)}

matches_file = "matches.json"
users_file = "users.json"
support_file = "support.json"
express_file = "express.json"

tz = ZoneInfo("Europe/Moscow")

# ====================== ТАРИФЫ ======================
# Free:      3 матча/день, бесплатно, без срока
# Lite:      10 матчей/день, 100 ₽/мес
# Pro:       20 матчей/день, 200 ₽/мес
# Premium:   безлимит, 300 ₽/мес

TARIFFS = {
    "free": {"name": "🆓 Free", "matches_limit": 3, "price": 0, "duration_days": None},
    "lite": {"name": "📘 Lite", "matches_limit": 10, "price": 100, "duration_days": 30},
    "pro": {"name": "⚡ Pro", "matches_limit": 20, "price": 200, "duration_days": 30},
    "premium": {"name": "⭐ Premium", "matches_limit": None, "price": 300, "duration_days": 30}
}


TARIFF_ORDER = ["Free", "Lite", "Pro", "Premium"]

# ====================== ФЛАГИ ======================

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

def get_flag(country: str) -> str:
    return COUNTRY_FLAGS.get(country, "🏳️")

# ====================== JSON ======================

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
express_data = load_json(express_file)

if "matches" not in matches_data:
    matches_data["matches"] = []

# ====================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ======================

def get_match_status_text(start_time_str: str) -> str:
    try:
        start_dt = datetime.fromisoformat(start_time_str)
    except (ValueError, TypeError):
        return ""
    now = datetime.now(tz)
    if start_dt.tzinfo is None:
        start_dt = start_dt.replace(tzinfo=tz)
    else:
        start_dt = start_dt.astimezone(tz)
    delta = start_dt - now
    if delta.total_seconds() > 0:
        hours, remainder = divmod(int(delta.total_seconds()), 3600)
        minutes, _ = divmod(remainder, 60)
        return f"⏳ До начала: {hours} ч. {minutes} мин."
    elapsed_seconds = -delta.total_seconds()
    minutes_elapsed = int(elapsed_seconds // 60)
    return f"⏱ Идёт матч: {minutes_elapsed}'"

async def get_user_subscription(user_id: int) -> dict:
    uid = str(user_id)
    if uid not in users:
        users[uid] = {
            "subscription": "Free",
            "end_date": None,  # Free — без срока
            "viewed_matches": [],
            "last_check_date": "",
            "referrals": 0,
            "registered": datetime.now(tz).strftime("%Y-%m-%d %H:%M"),
        }
        save_json(users_file, users)
    return users[uid]

async def check_match_limit(user_id: int, match_index: int) -> bool:
    sub = await get_user_subscription(user_id)
    tariff = sub.get("subscription", "Free")
    limit = TARIFFS.get(tariff, TARIFFS["Free"])["limit"]
    if limit == -1:
        return True  # безлимит

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
    if len(viewed) >= limit:
        return False
    users[uid]["viewed_matches"].append(match_index)
    save_json(users_file, users)
    return True

async def get_remaining_matches(user_id: int) -> str:
    sub = await get_user_subscription(user_id)
    tariff = sub.get("subscription", "Free")
    limit = TARIFFS.get(tariff, TARIFFS["Free"])["limit"]
    if limit == -1:
        return "∞"
    uid = str(user_id)
    today = datetime.now(tz).date()
    last_date_str = users[uid].get("last_check_date", "")
    if last_date_str != str(today):
        return str(limit)
    viewed = users[uid].get("viewed_matches", [])
    remaining = limit - len(viewed)
    return str(max(0, remaining))

async def is_subscription_active(user_id: int) -> bool:
    sub = await get_user_subscription(user_id)
    tariff = sub.get("subscription", "Free")
    if tariff == "Free":
        return True  # Free — всегда активен
    end_date_str = sub.get("end_date")
    if not end_date_str:
        return False
    try:
        end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
        return datetime.now(tz).date() <= end_date
    except ValueError:
        return False

async def get_subscription_end_text(user_id: int) -> str:
    sub = await get_user_subscription(user_id)
    tariff = sub.get("subscription", "Free")
    if tariff == "Free":
        return "бессрочно"
    end_date_str = sub.get("end_date")
    if not end_date_str:
        return "не активна"
    try:
        end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
        if datetime.now(tz).date() > end_date:
            return "истекла"
        return f"до {end_date_str}"
    except ValueError:
        return "не активна"

# ====================== КЛАВИАТУРЫ ======================

def main_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📂 Аккаунт", callback_data="account")],
        [InlineKeyboardButton(text="⚽ Матчи", callback_data="matches")],
        [InlineKeyboardButton(text="🚆 Экспресс дня", callback_data="express")],
        [InlineKeyboardButton(text="💬 Чат канала", url="https://t.me/koefchat")],
        [InlineKeyboardButton(text="⭐ Тарифы", callback_data="tariffs")],
        [InlineKeyboardButton(text="🛠 Техподдержка", callback_data="support")]
    ])

def back_keyboard(callback_data="main_menu"):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data=callback_data)]
    ])

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
                callback_data=f"group_{group_name}"
            )
        ])
    if not kb:
        kb = [[InlineKeyboardButton(text="Матчей пока нет", callback_data="no_matches")]]
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

# ====================== STATES ======================

class SupportStates(StatesGroup):
    waiting_for_text = State()

class AdminStates(StatesGroup):
    add_match_name = State()
    add_country_league = State()
    add_text = State()
    add_start_time = State()
    add_coefficient = State()

    express_name = State()
    express_country_league = State()
    express_prediction = State()
    express_coefficient = State()

    premium_give_id = State()
    premium_set_tariff = State()
    premium_remove_id = State()

    reply_support_text = State()

# ====================== ОБРАБОТЧИКИ ======================

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    referrer_id = None
    if len(message.text.split()) > 1:
        param = message.text.split()[1]
        if param.startswith("ref_"):
            referrer_id = param.replace("ref_", "")

    uid = str(message.from_user.id)
    await get_user_subscription(message.from_user.id)

    if referrer_id and referrer_id != uid and referrer_id in users:
        if uid not in users:
            users[uid]["referrer"] = referrer_id
            users[referrer_id]["referrals"] = users[referrer_id].get("referrals", 0) + 1
            # Начисляем 3 дня Premium пригласившему
            ref_sub = users[referrer_id].get("subscription", "Free")
            ref_end = users[referrer_id].get("end_date")
            if ref_sub == "Free" or not ref_end:
                users[referrer_id]["subscription"] = "Premium"
                users[referrer_id]["end_date"] = (datetime.now(tz) + timedelta(days=3)).strftime("%Y-%m-%d")
            else:
                try:
                    end_date = datetime.strptime(ref_end, "%Y-%m-%d")
                    users[referrer_id]["end_date"] = (end_date + timedelta(days=3)).strftime("%Y-%m-%d")
                except ValueError:
                    users[referrer_id]["end_date"] = (datetime.now(tz) + timedelta(days=3)).strftime("%Y-%m-%d")
            save_json(users_file, users)
            try:
                await bot.send_message(
                    int(referrer_id),
                    f"🎉 По вашей ссылке зарегистрировался новый пользователь!\n"
                    f"Вам начислено 3 дня Premium бесплатно!"
                )
            except Exception:
                pass

    # Приветствие по времени суток
    hour = datetime.now(tz).hour
    name = message.from_user.first_name or ""
    if 6 <= hour < 12:
        greeting = f"☀️ Доброе утро, {name}!"
    elif 12 <= hour < 18:
        greeting = f"🌆 Привет, {name}!"
    elif 18 <= hour < 24:
        greeting = f"🌙 Вечер добрый, {name}!"
    else:
        greeting = f"🌙 Доброй ночи, {name}!"

    await message.answer(
        f"{greeting}\n\n"
        f"Я твой помощник в мире футбола: собираю статистику, анализирую и предоставляю прогнозы.",
        reply_markup=main_keyboard()
    )

@dp.callback_query(F.data == "main_menu")
async def to_main_menu(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Главное меню:", reply_markup=main_keyboard())
    await callback.answer()

# ====================== АККАУНТ ======================

@dp.callback_query(F.data == "account")
async def account(callback: types.CallbackQuery):
    sub = await get_user_subscription(callback.from_user.id)
    tariff = sub.get("subscription", "Free")
    tariff_info = TARIFFS.get(tariff, TARIFFS["Free"])
    remaining = await get_remaining_matches(callback.from_user.id)
    end_text = await get_subscription_end_text(callback.from_user.id)
    ref_count = sub.get("referrals", 0)
    total_matches = len(matches_data.get("matches", []))
    total_users = len(users)
    premium_users = sum(1 for u in users.values() if u.get("subscription") in ("Premium", "Pro", "Lite"))

    limit_text = "∞" if tariff_info["limit"] == -1 else f"{remaining} из {tariff_info['limit']}"

    text = (
        f"👤 <b>Аккаунт</b>\n\n"
        f"🆔 ID: <code>{callback.from_user.id}</code>\n"
        f"👤 Имя: {callback.from_user.first_name}\n"
        f"💎 Тариф: {tariff_info['label']}\n"
        f"📅 Доступ: {end_text}\n"
        f"⚽ Матчей сегодня: {limit_text}\n"
        f"🔗 Рефералов: {ref_count}\n\n"
        f"📊 <b>Статистика бота</b>\n"
        f"🏆 Всего матчей: {total_matches}\n"
        f"👥 Пользователей: {total_users}\n"
        f"⭐ Платных подписок: {premium_users}"
    )

    kb = []
    kb.append([InlineKeyboardButton(text="🔗 Моя реферальная ссылка", callback_data="ref_link")])
    if tariff == "Free":
        kb.append([InlineKeyboardButton(text="⭐ Тарифы и подписка", callback_data="tariffs")])
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")])
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "ref_link")
async def ref_link(callback: types.CallbackQuery):
    uid = callback.from_user.id
    link = f"https://t.me/{BOT_USERNAME}?start=ref_{uid}"
    sub = await get_user_subscription(uid)
    ref_count = sub.get("referrals", 0)
    text = (
        f"🔗 <b>Ваша реферальная ссылка</b>\n\n"
        f"<code>{link}</code>\n\n"
        f"📤 Делитесь ссылкой с друзьями.\n"
        f"🎁 За каждого зарегистрировавшегося — 3 дня Premium бесплатно!\n\n"
        f"👥 Приглашено: {ref_count}"
    )
    await callback.message.edit_text(text, reply_markup=back_keyboard("account"), parse_mode="HTML")
    await callback.answer()

# ====================== ТАРИФЫ ======================

@dp.callback_query(F.data == "tariffs")
async def show_tariffs(callback: types.CallbackQuery):
    sub = await get_user_subscription(callback.from_user.id)
    current = sub.get("subscription", "Free")
    text = "💎 <b>Тарифы</b>\n\n"
    for t_name in TARIFF_ORDER:
        t = TARIFFS[t_name]
        limit_text = "безлимит" if t["limit"] == -1 else f"{t['limit']} матчей/день"
        price_text = "бесплатно" if t["price"] == 0 else f"{t['price']} ₽/мес"
        marker = " ✅ (ваш тариф)" if t_name == current else ""
        text += f"{t['label']} — {limit_text}, {price_text}{marker}\n"

    text += "\nВыберите тариф для оплаты:"

    kb = []
    for t_name in ["Lite", "Pro", "Premium"]:
        t = TARIFFS[t_name]
        kb.append([InlineKeyboardButton(text=f" Купить {t['label']} — {t['price']} ₽", callback_data=f"buy_{t_name}")])
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")])
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data.startswith("buy_"))
async def buy_tariff(callback: types.CallbackQuery):
    tariff_name = callback.data.replace("buy_", "")
    if tariff_name not in TARIFFS:
        await callback.answer("Тариф не найден", show_alert=True)
        return
    t = TARIFFS[tariff_name]
    text = (
        f"💳 <b>Покупка тарифа {t['label']}</b>\n\n"
        f"💰 Цена: {t['price']} ₽ в месяц\n"
        f"⚽ Лимит: {'безлимит' if t['limit'] == -1 else f'{t[\"limit\"]} матчей в день'}\n\n"
        f"Для оплаты нажмите кнопку ниже, затем пришлите чек админу."
                                                           )
    pay_url = f"https://yoomoney.ru/quickpay/confirm.xml?receiver=your_kassa@mail.ru&sum={t['price']}&label=koefbot_{tariff_name}&formcomment=true"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"💳 Оплатить {t['price']} ₽", url=pay_url)],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="tariffs")]
    ])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()

# ====================== МАТЧИ ======================

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
        status = get_match_status_text(m.get("start_time", ""))
        btn_text = m["name"]
        if status:
            btn_text += f" | {status}"
        kb_buttons.append([InlineKeyboardButton(text=btn_text, callback_data=f"match_{i}")])
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
        sub = await get_user_subscription(callback.from_user.id)
        tariff = sub.get("subscription", "Free")
        limit = TARIFFS.get(tariff, TARIFFS["Free"])["limit"]
        await callback.answer(f"❌ Лимит исчерпан ({limit} матчей/день). Повысьте тариф!", show_alert=True)
        return
    flag = get_flag(match["country"])
    status_line = get_match_status_text(match.get("start_time", ""))
    text = (
        f"⚽ <b>{match['name']}</b>\n"
        f"🌍 {flag} Страна: {match['country']}\n"
        f"🏆 Лига: {match['league']}\n"
    )
    if status_line:
        text += f"{status_line}\n"
    text += f"\n{match['text']}"
    await callback.message.edit_text(text, reply_markup=back_keyboard("matches"), parse_mode="HTML")
    await callback.answer()

# ====================== ЭКСПРЕСС ДНЯ ======================

@dp.callback_query(F.data == "express")
async def show_express(callback: types.CallbackQuery):
    sub = await get_user_subscription(callback.from_user.id)
    tariff = sub.get("subscription", "Free")
    express_matches = express_data.get("matches", [])
    if not express_matches:
        await callback.message.edit_text("🚆 Экспресс дня пока не сформирован. Загляните позже!", reply_markup=back_keyboard("main_menu"))
        await callback.answer()
        return

    if tariff == "Free":
        text = "🚆 <b>Экспресс дня</b>\n\n"
        text += "🔒 Экспресс дня доступен на тарифах Lite, Pro и Premium.\n\n"
        text += "Оформите подписку, чтобы видеть экспресс с прогнозами и общим коэффициентом!"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⭐ Тарифы", callback_data="tariffs")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")]
        ])
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        await callback.answer()
        return

    text = "🚆 <b>Экспресс дня</b>\n\n"
    total_coeff = 1.0
    for i, m in enumerate(express_matches, 1):
        flag = get_flag(m.get("country", ""))
        coeff = m.get("coefficient", 1.0)
        try:
            coeff_val = float(coeff)
            total_coeff *= coeff_val
        except (ValueError, TypeError):
            coeff_val = 1.0
        text += (
            f"<b>{i}. {m['name']}</b>\n"
            f"{flag} {m.get('country', '')} — {m.get('league', '')}\n"
            f"📊 Прогноз: {m.get('prediction', '—')}\n"
            f"💰 Коэффициент: {coeff}\n\n"
        )
    text += f"🎯 <b>Общий коэффициент: {total_coeff:.2f}</b>"
    await callback.message.edit_text(text, reply_markup=back_keyboard("main_menu"), parse_mode="HTML")
    await callback.answer()

# ====================== ТЕХПОДДЕРЖКА ======================

SUPPORT_CATEGORIES = {
    "bug": "🐛 Баг / ошибка",
    "payment": "💳 Оплата",
    "idea": "💡 Предложение",
    "question": "❓ Вопрос",
}

@dp.callback_query(F.data == "support")
async def support_menu(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    text = "🛠 <b>Техподдержка</b>\n\nВыберите категорию обращения:"
    kb = []
    for cat_id, cat_label in SUPPORT_CATEGORIES.items():
        kb.append([InlineKeyboardButton(text=cat_label, callback_data=f"supcat_{cat_id}")])
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")])
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data.startswith("supcat_"))
async def support_category(callback: types.CallbackQuery, state: FSMContext):
    cat_id = callback.data.replace("supcat_", "")
    cat_label = SUPPORT_CATEGORIES.get(cat_id, "❓ Вопрос")
    await state.update_data(support_cat=cat_id, support_cat_label=cat_label)
    text = f"{cat_label}\n\nНапишите ваше сообщение одним сообщением:"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="support")]
    ])
    await callback.message.edit_text(text, reply_markup=kb)
    await state.set_state(SupportStates.waiting_for_text)
    await callback.answer()

@dp.message(SupportStates.waiting_for_text)
async def handle_support_msg(message: types.Message, state: FSMContext):
    data = await state.get_data()
    cat_label = data.get("support_cat_label", "❓ Вопрос")
    cat_id = data.get("support_cat", "question")
    uid = str(message.from_user.id)
    user_name = message.from_user.full_name or "Без имени"
    text_msg = message.text or "(без текста)"

    support.setdefault("threads", {})
    thread = support["threads"].setdefault(uid, {
        "category": cat_label,
        "messages": []
    })
    thread["category"] = cat_label
    thread["messages"].append({
        "from": "user",
        "id": message.from_user.id,
        "name": user_name,
        "text": text_msg,
        "date": datetime.now(tz).strftime("%Y-%m-%d %H:%M")
    })
    save_json(support_file, support)

    try:
        await bot.send_message(
            ADMIN_ID,
            f"📩 <b>Новое сообщение в техподдержку</b>\n\n"
            f"📂 Категория: {cat_label}\n"
            f"👤 От: {user_name}\n"
            f"🆔 ID: <code>{message.from_user.id}</code>\n"
            f"📝 Текст:\n{text_msg}",
            parse_mode="HTML"
        )
    except Exception:
        pass

    await message.answer("✅ Ваше сообщение отправлено Администрации!", reply_markup=main_keyboard())
    await state.clear()

# ====================== АДМИН ПАНЕЛЬ ======================

@dp.message(Command("admin"))
async def admin_panel(message: types.Message, state: FSMContext):
    await state.clear()
    if str(message.from_user.id) not in admin_users:
        await message.answer("❌ Нет доступа!")
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить матч", callback_data="admin_add_match")],
        [InlineKeyboardButton(text="🗑 Удалить матчи", callback_data="admin_delete_menu")],
        [InlineKeyboardButton(text="🚆 Экспресс дня", callback_data="admin_express_menu")],
        [InlineKeyboardButton(text="💰 Управление тарифами", callback_data="admin_tariff_menu")],
        [InlineKeyboardButton(text="🛠 Сообщения поддержки", callback_data="admin_support_menu")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")]
    ])
    await message.answer("🛠 <b>Админ-панель</b>", reply_markup=kb, parse_mode="HTML")

# --- Добавление матча ---

@dp.callback_query(F.data == "admin_add_match")
async def admin_add_match(callback: types.CallbackQuery, state: FSMContext):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    await callback.message.edit_text(
        "Шаг 1/5: Введите название команд (например: Спартак — Зенит):",
        reply_markup=back_keyboard("admin_panel")
    )
    await state.set_state(AdminStates.add_match_name)
    await callback.answer()

@dp.message(AdminStates.add_match_name)
async def admin_match_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await message.answer("Шаг 2/5: Страна и лига (через пробел, например: Россия РПЛ):", reply_markup=back_keyboard("admin_panel"))
    await state.set_state(AdminStates.add_country_league)

@dp.message(AdminStates.add_country_league)
async def admin_match_country(message: types.Message, state: FSMContext):
    parts = message.text.strip().split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("⚠️ Нужно два слова: страна и лига. Попробуйте ещё раз:")
        return
    await state.update_data(country=parts[0], league=parts[1])
    await message.answer("Шаг 3/5: Введите текст прогноза (можно несколько строк):", reply_markup=back_keyboard("admin_panel"))
    await state.set_state(AdminStates.add_text)

@dp.message(AdminStates.add_text)
async def admin_match_text(message: types.Message, state: FSMContext):
    await state.update_data(text=message.text)
    await message.answer("Шаг 4/5: Введите время начала (формат: ГГГГ-ММ-ДДТЧЧ:ММ:СС+0300)\nНапример: 2024-10-25T19:30:00+0300\nИли отправьте «-» если не нужно:", reply_markup=back_keyboard("admin_panel"))
    await state.set_state(AdminStates.add_start_time)

@dp.message(AdminStates.add_start_time)
async def admin_match_time(message: types.Message, state: FSMContext):
    time_str = message.text.strip()
    if time_str == "-":
        time_str = ""
    await state.update_data(start_time=time_str)
    await message.answer("Шаг 5/5: Введите коэффициент (например: 1.85)\nИли отправьте «-» если не нужно:", reply_markup=back_keyboard("admin_panel"))
    await state.set_state(AdminStates.add_coefficient)

@dp.message(AdminStates.add_coefficient)
async def admin_match_coeff(message: types.Message, state: FSMContext):
    data = await state.get_data()
    coeff_str = message.text.strip()
    if coeff_str == "-":
        coeff_str = ""
    match = {
        "name": data["name"],
        "country": data["country"],
        "league": data["league"],
        "text": data["text"],
        "start_time": data.get("start_time", ""),
        "coefficient": coeff_str
    }
    matches_data.setdefault("matches", []).append(match)
    save_json(matches_file, matches_data)
    await message.answer(
        f"✅ Матч добавлен!\n\n⚽ {match['name']}\n🌍 {match['country']} — {match['league']}",
        reply_markup=back_keyboard("admin_panel")
    )
    await state.clear()

# --- Удаление матчей ---

@dp.callback_query(F.data == "admin_delete_menu")
async def admin_delete_menu(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    total = len(matches_data.get("matches", []))
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗑 Очистить все матчи", callback_data="admin_delete_all")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")]
    ])
    await callback.message.edit_text(f"🗑 <b>Удаление матчей</b>\n\nВсего матчей: {total}", reply_markup=kb, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "admin_delete_all")
async def admin_delete_all(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    matches_data["matches"] = []
    save_json(matches_file, matches_data)
    await callback.message.edit_text("✅ Все матчи удалены!", reply_markup=back_keyboard("admin_panel"))
    await callback.answer()

# --- Экспресс дня (админка) ---

@dp.callback_query(F.data == "admin_express_menu")
async def admin_express_menu(callback: types.CallbackQuery, state: FSMContext):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    await state.clear()
    count = len(express_data.get("matches", []))
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить матч в экспресс", callback_data="admin_express_add")],
        [InlineKeyboardButton(text="🗑 Очистить экспресс", callback_data="admin_express_clear")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")]
    ])
    await callback.message.edit_text(f"🚆 <b>Экспресс дня</b>\n\nМатчей в экспрессе: {count}", reply_markup=kb, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "admin_express_add")
async def admin_express_add(callback: types.CallbackQuery, state: FSMContext):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    count = len(express_data.get("matches", []))
    if count >= 5:
        await callback.answer("Максимум 5 матчей в экспрессе!", show_alert=True)
        return
    await callback.message.edit_text("Шаг 1/4: Введите название команд (например: Спартак — Зенит):", reply_markup=back_keyboard("admin_express_menu"))
    await state.set_state(AdminStates.express_name)
    await callback.answer()

@dp.message(AdminStates.express_name)
async def admin_express_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await message.answer("Шаг 2/4: Страна и лига (через пробел, например: Россия РПЛ):", reply_markup=back_keyboard("admin_express_menu"))
    await state.set_state(AdminStates.express_country_league)

@dp.message(AdminStates.express_country_league)
async def admin_express_country_league(message: types.Message, state: FSMContext):
    parts = message.text.strip().split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("⚠️ Нужно два слова: страна и лига. Попробуйте ещё раз:")
        return
    await state.update_data(country=parts[0], league=parts[1])
    await message.answer("Шаг 3/4: Введите прогноз (например: П1 или ТБ 2.5):", reply_markup=back_keyboard("admin_express_menu"))
    await state.set_state(AdminStates.express_prediction)

@dp.message(AdminStates.express_prediction)
async def admin_express_prediction(message: types.Message, state: FSMContext):
    await state.update_data(prediction=message.text.strip())
    await message.answer("Шаг 4/4: Введите коэффициент (например: 1.85):", reply_markup=back_keyboard("admin_express_menu"))
    await state.set_state(AdminStates.express_coefficient)

@dp.message(AdminStates.express_coefficient)
async def admin_express_coefficient(message: types.Message, state: FSMContext):
    data = await state.get_data()
    match = {
        "name": data["name"],
        "country": data["country"],
        "league": data["league"],
        "prediction": data["prediction"],
        "coefficient": message.text.strip()
    }
    express_data.setdefault("matches", []).append(match)
    save_json(express_file, express_data)
    count = len(express_data["matches"])
    await message.answer(
        f"✅ Матч добавлен в экспресс! (всего: {count})",
        reply_markup=back_keyboard("admin_express_menu")
    )
    await state.clear()

@dp.callback_query(F.data == "admin_express_clear")
async def admin_express_clear(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    express_data["matches"] = []
    save_json(express_file, express_data)
    await callback.message.edit_text("✅ Экспресс очищен!", reply_markup=back_keyboard("admin_express_menu"))
    await callback.answer()

# --- Управление тарифами (админка) ---

@dp.callback_query(F.data == "admin_tariff_menu")
async def admin_tariff_menu(callback: types.CallbackQuery, state: FSMContext):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    await state.clear()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ Выдать Premium", callback_data="admin_tariff_give")],
        [InlineKeyboardButton(text="⚡ Выдать Pro", callback_data="admin_tariff_give_pro")],
        [InlineKeyboardButton(text="📘 Выдать Lite", callback_data="admin_tariff_give_lite")],
        [InlineKeyboardButton(text="🆓 Сбросить на Free", callback_data="admin_tariff_remove")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")]
    ])
    await callback.message.edit_text("💰 <b>Управление тарифами</b>\n\nВыдайте или сбросьте тариф пользователю по ID.", reply_markup=kb, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "admin_tariff_give")
async def admin_tariff_give(callback: types.CallbackQuery, state: FSMContext):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    await callback.message.edit_text("Введите ID пользователя для выдачи Premium:", reply_markup=back_keyboard("admin_tariff_menu"))
    await state.update_data(target_tariff="Premium", days=30)
    await state.set_state(AdminStates.premium_give_id)
    await callback.answer()

@dp.callback_query(F.data == "admin_tariff_give_pro")
async def admin_tariff_give_pro(callback: types.CallbackQuery, state: FSMContext):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    await callback.message.edit_text("Введите ID пользователя для выдачи Pro:", reply_markup=back_keyboard("admin_tariff_menu"))
    await state.update_data(target_tariff="Pro", days=30)
    await state.set_state(AdminStates.premium_give_id)
    await callback.answer()

@dp.callback_query(F.data == "admin_tariff_give_lite")
async def admin_tariff_give_lite(callback: types.CallbackQuery, state: FSMContext):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    await callback.message.edit_text("Введите ID пользователя для выдачи Lite:", reply_markup=back_keyboard("admin_tariff_menu"))
    await state.update_data(target_tariff="Lite", days=30)
    await state.set_state(AdminStates.premium_give_id)
    await callback.answer()

@dp.message(AdminStates.premium_give_id)
async def admin_tariff_give_id(message: types.Message, state: FSMContext):
    data = await state.get_data()
    target_tariff = data.get("target_tariff", "Premium")
    days = data.get("days", 30)
    target_id = message.text.strip()
    if target_id not in users:
        # Создаём запись
        users[target_id] = {
            "subscription": target_tariff,
            "end_date": (datetime.now(tz) + timedelta(days=days)).strftime("%Y-%m-%d"),
            "viewed_matches": [],
            "last_check_date": "",
            "referrals": 0,
            "registered": datetime.now(tz).strftime("%Y-%m-%d %H:%M"),
        }
    else:
        users[target_id]["subscription"] = target_tariff
        users[target_id]["end_date"] = (datetime.now(tz) + timedelta(days=days)).strftime("%Y-%m-%d")
    save_json(users_file, users)
    tariff_label = TARIFFS.get(target_tariff, {}).get("label", target_tariff)
    await message.answer(
        f"✅ {tariff_label} выдан на {days} дней!\nID: <code>{target_id}</code>",
        reply_markup=back_keyboard("admin_tariff_menu"),
        parse_mode="HTML"
    )
    try:
        await bot.send_message(
            int(target_id),
            f"🎉 Вам выдан тариф {tariff_label} на {days} дней!\nПриятной игры!"
        )
    except Exception:
        pass
    await state.clear()

@dp.callback_query(F.data == "admin_tariff_remove")
async def admin_tariff_remove(callback: types.CallbackQuery, state: FSMContext):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    await callback.message.edit_text("Введите ID пользователя для сброса на Free:", reply_markup=back_keyboard("admin_tariff_menu"))
    await state.set_state(AdminStates.premium_remove_id)
    await callback.answer()

@dp.message(AdminStates.premium_remove_id)
async def admin_tariff_remove_id(message: types.Message, state: FSMContext):
    target_id = message.text.strip()
    if target_id in users:
        users[target_id]["subscription"] = "Free"
        users[target_id]["end_date"] = None
        save_json(users_file, users)
        await message.answer(f"✅ Сброшен на Free.\nID: <code>{target_id}</code>", reply_markup=back_keyboard("admin_tariff_menu"), parse_mode="HTML")
    else:
        await message.answer("❌ Пользователь не найден.", reply_markup=back_keyboard("admin_tariff_menu"))
    await state.clear()

# --- Сообщения поддержки (админка) ---

@dp.callback_query(F.data == "admin_support_menu")
async def admin_support_menu(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    threads = support.get("threads", {})
    if not threads:
        await callback.message.edit_text("🛠 Нет сообщений поддержки.", reply_markup=back_keyboard("admin_panel"))
        await callback.answer()
        return
    kb = []
    for uid, thread in threads.items():
        cat = thread.get("category", "—")
        msgs = thread.get("messages", [])
        last_date = msgs[-1].get("date", "") if msgs else ""
        user_name = msgs[0].get("name", "Без имени") if msgs else "Без имени"
        kb.append([InlineKeyboardButton(text=f"{cat} | {user_name} ({len(msgs)} сообщ.) [{last_date}]", callback_data=f"supthread_{uid}")])
    kb.append([InlineKeyboardButton(text="🗑 Очистить все треды", callback_data="admin_support_clear_all")])
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")])
    await callback.message.edit_text("🛠 <b>Сообщения поддержки</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data.startswith("supthread_"))
async def admin_support_thread(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    uid = callback.data.replace("supthread_", "")
    thread = support.get("threads", {}).get(uid, {})
    messages = thread.get("messages", [])
    cat = thread.get("category", "—")
    text = f"🛠 <b>Переписка</b> ({cat})\n\n"
    for m in messages:
        sender = "👤 Пользователь" if m["from"] == "user" else "🛠 Админ"
        text += f"<b>{sender}</b> ({m['date']}):\n{m['text']}\n\n"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Ответить", callback_data=f"supreply_{uid}")],
        [InlineKeyboardButton(text="🗑 Очистить тред", callback_data=f"supclear_{uid}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_support_menu")]
    ])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data.startswith("supreply_"))
async def admin_support_reply(callback: types.CallbackQuery, state: FSMContext):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    uid = callback.data.replace("supreply_", "")
    await state.update_data(reply_uid=uid)
    await callback.message.edit_text("Введите текст ответа пользователю:", reply_markup=back_keyboard("admin_support_menu"))
    await state.set_state(AdminStates.reply_support_text)
    await callback.answer()

@dp.message(AdminStates.reply_support_text)
async def admin_support_reply_text(message: types.Message, state: FSMContext):
    data = await state.get_data()
    uid = data.get("reply_uid", "")
    reply_text = message.text
    if uid in support.get("threads", {}):
        support["threads"][uid]["messages"].append({
            "from": "admin",
            "id": message.from_user.id,
            "name": "Админ",
            "text": reply_text,
            "date": datetime.now(tz).strftime("%Y-%m-%d %H:%M")
        })
        save_json(support_file, support)
    try:
        await bot.send_message(int(uid), f"🛠 <b>Ответ техподдержки:</b>\n\n{reply_text}", parse_mode="HTML")
    except Exception:
        pass
    await message.answer("✅ Ответ отправлен!", reply_markup=back_keyboard("admin_support_menu"))
    await state.clear()

@dp.callback_query(F.data.startswith("supclear_"))
async def admin_support_clear_one(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    uid = callback.data.replace("supclear_", "")
    if uid in support.get("threads", {}):
        del support["threads"][uid]
        save_json(support_file, support)
    await callback.message.edit_text("✅ Тред очищен.", reply_markup=back_keyboard("admin_support_menu"))
    await callback.answer()

@dp.callback_query(F.data == "admin_support_clear_all")
async def admin_support_clear_all(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    support["threads"] = {}
    save_json(support_file, support)
    await callback.message.edit_text("✅ Все треды очищены.", reply_markup=back_keyboard("admin_panel"))
    await callback.answer()

# --- Заглушки ---

@dp.callback_query(F.data == "no_matches")
async def no_matches(callback: types.CallbackQuery):
    await callback.answer()

@dp.callback_query(F.data == "sub_info")
async def sub_info(callback: types.CallbackQuery):
    await callback.answer()

# ====================== ЗАПУСК ======================

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
