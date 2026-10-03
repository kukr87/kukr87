import asyncio
import datetime
import json
import os
import re
from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup,
    Message, WebAppInfo
)
from yookassa import Configuration, Payment

# ==================== КОНФИГ (меняйте под себя) ====================
TOKEN = os.getenv("BOT_TOKEN")  # BotHost передаёт в env
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID"))  # твой ID
PASSWORD = "1234"  # пароль для /goal

# ЮKassa (замени на свои)
Configuration.configure(os.getenv("YOOKASSA_SHOP_ID"), os.getenv("YOOKASSA_SECRET"))
YOOKASSA_REDIRECT = "https://t.me/koefchat"  # куда уйдёт после оплаты

# Канал
CHANNEL = "koefii"
# ============================================================

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# ==================== STATE ====================
class AccountFSM(StatesGroup):
    waiting_premium_end = State()

class AdminFSM(StatesGroup):
    waiting_command = State()
    waiting_password = State()
    waiting_premium_type = State()
    waiting_premium_days = State()
    waiting_premium_user_id = State()
    waiting_support = State()

# ==================== ПОМОЩНИКИ ====================
def get_user_status(user_id: int):
    # Здесь подключи БД (SQLite или PostgreSQL на BotHost)
    # Пока заглушка
    return {"premium_end": "2026-12-31", "matches_today": 0}

def check_subscription(user_id: int):
    return True  # заглушка, замени на реальную проверку

async def check_user_subscription(user_id: int):
    if not check_subscription(user_id):
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Подписаться на канал", url=f"https://t.me/{CHANNEL}")]
        ])
        await bot.send_message(user_id, "❌ Вы не подписаны на канал!\nПодпишитесь и нажмите кнопку ниже.", reply_markup=kb)
        return False
    return True

# ==================== КНОПКИ ====================
def main_menu_kb(user_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Аккаунт", callback_data="account")],
        [InlineKeyboardButton(text="⚽ Матчи", callback_data="matches")],
        [InlineKeyboardButton(text="📢 Канал", url=f"https://t.me/{CHANNEL}")],
        [InlineKeyboardButton(text="💬 Чат", url="https://t.me/koefchat")]
    ])

def matches_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇷🇺 Россия", callback_data="matches_Russia")],
        [InlineKeyboardButton(text="🇪🇸 Испания", callback_data="matches_Spain")],
        [InlineKeyboardButton(text="🇮🇹 Италия", callback_data="matches_Italy")],
        [InlineKeyboardButton(text="🇧🇷 Бразилия", callback_data="matches_Brazil")],
        [InlineKeyboardButton(text="🇬🇧 Англия", callback_data="matches_England")],
        [InlineKeyboardButton(text="🌍 Мир", callback_data="matches_World")]
    ])

def match_tabs_kb(match_name: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔮 Прогноз", callback_data=f"tab_Прогноз_{match_name}")],
        [InlineKeyboardButton(text="📊 Аналитика", callback_data=f"tab_Аналитика_{match_name}")],
        [InlineKeyboardButton(text="📈 Статистика", callback_data=f"tab_Статистика_{match_name}")],
        [InlineKeyboardButton(text="⏱ Таймы", callback_data=f"tab_Таймы_{match_name}")],
        [InlineKeyboardButton(text="🤕 Травмы", callback_data=f"tab_Травмы_{match_name}")]
    ])

# ==================== МЕНЮ ====================
async def send_main_menu(message: Message | CallbackQuery):
    if isinstance(message, CallbackQuery):
        await message.message.delete()
    await message.answer(
        "Доброго времени суток и имя пользователя!\n\n"
        "Я собираю полную статистику команд (травмы, результаты, положение в турнирной таблице, xG, статистика по таймам, тренды и много другое). "
        "Анализирую и предоставляю наиболее вероятные исходы на событие.",
        reply_markup=main_menu_kb(message.from_user.id)
    )

# ==================== CALLBACKS ====================
@dp.callback_query(F.data == "account")
async def account_menu(cb: CallbackQuery, state: FSMContext):
    if not await check_user_subscription(cb.from_user.id):
        return
    status = get_user_status(cb.from_user.id)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Мои матчи (3 сегодня)", callback_data="my_matches")],
        [InlineKeyboardButton(text="💰 Поддержка", callback_data="support")]
    ])
    premium_text = f"Premium до {status['premium_end']}" if status.get("premium_end") else "Free"
    await cb.message.edit_text(
        f"👤 **Аккаунт**\n\n"
        f"ID: {cb.from_user.id}\n"
        f"Имя: @{cb.from_user.username or 'не указано'}\n"
        f"Подписка: {premium_text}\n\n"
        f"Бот отслеживает месяц. Если закончится — станет Free.",
        reply_markup=kb
    )
    await state.set_state(AccountFSM.waiting_premium_end)

@dp.callback_query(F.data == "matches")
async def matches_menu(cb: CallbackQuery):
    if not await check_user_subscription(cb.from_user.id):
        return
    await cb.message.edit_text("⚽ **Выберите лигу/страну**", reply_markup=matches_menu_kb())

@dp.callback_query(F.data.startswith("matches_"))
async def matches_list(cb: CallbackQuery):
    country = cb.data.split("_")[1]
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=f"Матч {i}", callback_data=f"match_{country}_{i}") for i in range(1, 6)]])
    await cb.message.edit_text(f"⚽ **Матчи {country}**", reply_markup=kb)

@dp.callback_query(F.data.startswith("match_"))
async def show_match(cb: CallbackQuery):
    match_name = cb.data.split("_")[-1]
    await cb.message.edit_text(
        f"⚽ **{match_name}**\n\n"
        f"Тайм: 45:00\n"
        f"Счёт: 1-1\n"
        f"Позиция в таблице: 3-е место\n"
        f"xG: 1.8 / 1.2",
        reply_markup=match_tabs_kb(match_name)
    )

@dp.callback_query(F.data.startswith("tab_"))
async def show_tab(cb: CallbackQuery):
    tab = cb.data.split("_")[1]
    match_name = cb.data.split("_")[-1]
    spoiler_text = {
        "Прогноз": "🔮 **Прогноз**\n\nНа матч очень высокая вероятность домашней победы.",
        "Аналитика": "📊 **Аналитика**\n\nxG, травмы, форма команд...",
        "Статистика": "📈 **Статистика**\n\nСтатистика по таймам, xG и т.д.",
        "Таймы": "⏱ **Таймы**\n\nПодробная статистика по таймам",
        "Травмы": "🤕 **Травмы**\n\nСписок травмированных игроков"
    }.get(tab, "Данные не найдены")

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад к матчу", callback_data=f"match_{match_name}")],
        [InlineKeyboardButton(text="❌ Закрыть", callback_data="close")]
    ])

    await cb.message.edit_text(
        f"📌 **{tab}**\n\n"
        f"{spoiler_text}\n\n"
        f"**{match_name}**",
        reply_markup=kb
    )

@dp.callback_query(F.data == "close")
async def close_spoiler(cb: CallbackQuery):
    await cb.message.delete()

# ==================== АККАУНТ (Premium) ====================
@dp.callback_query(F.data == "my_matches")
async def my_matches(cb: CallbackQuery):
    if not await check_user_subscription(cb.from_user.id):
        return
    status = get_user_status(cb.from_user.id)
    if status["matches_today"] >= 3 and not status.get("premium_end"):
        await cb.answer("❌ Вы достигли лимита 3 матчей в сутки. Купите Premium!")
        return
    await cb.message.edit_text("✅ Ваши 3 матча готовы к просмотру.")

@dp.callback_query(F.data == "support")
async def open_support(cb: CallbackQuery, state: FSMContext):
    if not await check_user_subscription(cb.from_user.id):
        return
    await cb.message.edit_text(
        "💬 **Поддержка**\n\n"
        f"У вас {get_user_status(cb.from_user.id).get('unread_support', 0)} непрочитанных писем.\n\n"
        "Напишите текст обращения:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="close")]])
    )
    await state.set_state(AdminFSM.waiting_support)

# ==================== ЮKassa ====================
@dp.callback_query(F.data == "premium")
async def premium_payment(cb: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📅 На 1 месяц — 300 ₽", callback_data="pay_1month")],
        [InlineKeyboardButton(text="❌ Убрать Premium", callback_data="remove_premium")]
    ])
    await cb.message.edit_text("💰 **Подписка Premium**\n\nВыберите срок:", reply_markup=kb)

@dp.callback_query(F.data.startswith("pay_"))
async def process_payment(cb: CallbackQuery):
    payment = Payment.create({
        "amount": {"value": 300.00, "currency": "RUB"},
        "confirmation": {"type": "redirect", "return_url": YOOKASSA_REDIRECT},
        "capture": True,
        "description": "Подписка Premium"
    })
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Оплатить", url=payment.confirmation.confirmation_url)]
    ])
    await cb.message.edit_text("💳 **Оплата через ЮKassa**\n\nНажмите кнопку и оплатите. После оплаты Premium будет активировано автоматически.", reply_markup=kb)

@dp.callback_query(F.data == "remove_premium")
async def remove_premium(cb: CallbackQuery, state: FSMContext):
    await cb.message.edit_text("✅ Premium удалён. Теперь Free.")
    await state.update_data(premium_end=None)

# ==================== АДМИН ПАНЕЛЬ ====================
@dp.message(CommandStart())
async def cmd_start(message: Message):
    await send_main_menu(message)

@dp.message(CommandStart(deep_link="/goal"))
async def admin_start(message: Message):
    await message.answer("🔑 **Админ-панель**\n\nВведите пароль:")
    await AdminFSM.waiting_password.set()

@dp.message(AdminFSM.waiting_password)
async def admin_password(message: Message, state: FSMContext):
    if message.text != PASSWORD:
        await message.answer("❌ Неверный пароль")
        return
    await message.answer(
        "🛠 **Админ-панель**\n\nВыберите действие:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить лигу", callback_data="add_league")],
            [InlineKeyboardButton(text="📅 Управление Premium", callback_data="admin_premium")],
            [InlineKeyboardButton(text="💬 Поддержка", callback_data="admin_support")]
        ])
    )
    await state.clear()

# Далее обработчики для /goal (добавление матчей, флагов, премиум и т.д.) — можно расширять аналогично выше.

# ==================== ЗАПУСК ====================
async def on_startup():
    print("🚀 Бот запущен на BotHost")

async def main():
    await on_startup()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
