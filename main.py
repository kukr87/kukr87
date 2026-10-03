import asyncio
import json
import os
from datetime import datetime, timedelta
import requests
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO

from telegram import (
    Update, InputMediaPhoto, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton, ChatMemberUpdated, ChatMember
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters,
    CallbackQueryHandler, ContextTypes, ConversationHandler,
    PicklePersistence
)
import yookassa

# ====================== КОНФИГ ======================
TOKEN = "ТОКЕН_ОТ_BOTFATHER_СЮДА"

CHANNEL_ID = -1001234567890  # ID канала https://t.me/koefii (отрицательный для супергруппы)

ADMIN_PASSWORD = "12345"  # пароль для /goal

YOOKASSA_SHOP_ID = "ТОТ_ШОП_ИЗ_KASSA"
YOOKASSA_SECRET_KEY = "ТОТ_SECRET_ИЗ_KASSA"

# Региональные флаги (unicode + ссылки на публичные файлы)
FLAGS = {
    "Испания": ("🇪🇸", "https://flagcdn.com/es.svg"),
    "Италия": ("🇮🇹", "https://flagcdn.com/it.svg"),
    "Португалия": ("🇵🇹", "https://flagcdn.com/pt.svg"),
    "Швеция": ("🇸🇪", "https://flagcdn.com/se.svg"),
    "Бразилия": ("🇧🇷", "https://flagcdn.com/br.svg"),
    "Аргентина": ("🇦🇷", "https://flagcdn.com/ar.svg"),
    "Англия": ("🏴󠁧󠁢󠁥󠁮󠁧󠁿", "https://flagcdn.com/gb.svg"),
    "Беларусь": ("🇧🇾", "https://flagcdn.com/by.svg"),
    "Бельгия": ("🇧🇪", "https://flagcdn.com/be.svg"),
    "Россия": ("🇷🇺", "https://flagcdn.com/ru.svg"),
    "Венгрия": ("🇭🇺", "https://flagcdn.com/hu.svg"),
    "Германия": ("🇩🇪", "https://flagcdn.com/de.svg"),
    "Греция": ("🇬🇷", "https://flagcdn.com/gr.svg"),
    "Дания": ("🇩🇰", "https://flagcdn.com/dk.svg"),
    "Ирландия": ("🇮🇪", "https://flagcdn.com/ie.svg"),
    "Нидерланды": ("🇳🇱", "https://flagcdn.com/nl.svg"),
    "Норвегия": ("🇳🇴", "https://flagcdn.com/no.svg"),
    "Польша": ("🇵🇱", "https://flagcdn.com/pl.svg"),
    "Турция": ("🇹🇷", "https://flagcdn.com/tr.svg"),
    "Сербия": ("🇷🇸", "https://flagcdn.com/rs.svg"),
    "Франция": ("🇫🇷", "https://flagcdn.com/fr.svg"),
    "Хорватия": ("🇭🇷", "https://flagcdn.com/hr.svg"),
    "Швейцария": ("🇨🇭", "https://flagcdn.com/ch.svg"),
    "Мир": ("🌍", "https://flagcdn.com/xx.svg"),
}

# ====================== ДАННЫЕ ======================
# В реальности используй PostgreSQL / MongoDB. Для примера — dict в памяти + pickle.
users = {}          # user_id -> данные
matches = {}        # match_id -> данные
unread_support = [] # список сообщений поддержки

# ====================== РЕГИОНЫ ======================
REGIONS = list(FLAGS.keys())  # для админ-панели

# ====================== ГЕНЕРАЦИЯ КАРТИНКИ (K + футбол) ======================
def generate_banner():
    img = Image.new("RGB", (1200, 600), color="#0a0a0a")
    draw = ImageDraw.Draw(img)

    # Фон — поле
    draw.rectangle([50, 150, 1150, 550], fill="#1a1a1a")

    # Футболист (простая фигура — можно доработать)
    draw.ellipse([800, 250, 950, 420], fill="#e74c3c", outline="#2c3e50", width=8)
    draw.rectangle([850, 420, 900, 480], fill="#2c3e50")  # торс
    draw.rectangle([880, 420, 910, 500], fill="#2c3e50")  # нога

    # Мяч
    draw.ellipse([680, 320, 820, 460], fill="#f1c40f", outline="#2c3e50", width=6)
    draw.text((720, 370), "⚽", fill="#2c3e50", font=ImageFont.load_default())

    # Сетка ворот
    draw.line([(1050, 200), (1050, 500)], fill="#bdc3c7", width=8)
    draw.line([(1100, 200), (1100, 500)], fill="#bdc3c7", width=8)

    # Буква K на фоне
    draw.text((100, 180), "K", fill="#e74c3c", font=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 350))

    # Графики вверх (простые линии)
    for x in range(300, 900, 80):
        y1 = 200 + int(150 * (1.7 + x % 4 * 0.1))
        y2 = 200 + int(150 * (1.8 + x % 4 * 0.1))
        draw.line([(x, y1), (x + 60, y2)], fill="#27ae60", width=4)

    # Коэффициенты
    coeffs = [(1.7, "#27ae60"), (1.8, "#27ae60"), (2.0, "#f39c12"), (3.0, "#e74c3c")]
    for i, (val, color) in enumerate(coeffs):
        draw.text((400 + i * 140, 520), f"{val} : 1", fill=color, font=ImageFont.load_default())

    # Сохраняем
    path = "/tmp/banner.png"
    img.save(path)
    return path

BANNER_PATH = generate_banner()

# ====================== ОБРАБОТЧИК ПОДПИСКИ ======================
async def is_subscribed(update: Update) -> bool:
    member = await update.get_bot().get_chat_member(CHANNEL_ID, update.effective_user.id)
    return member.status in ("member", "administrator", "creator")

# ====================== ОБРАБОТЧИК ПОДПИСКИ ======================
async def check_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_subscribed(update):
        keyboard = [[InlineKeyboardButton("Подписаться на канал", url="https://t.me/koefii")]]
        await update.message.reply_text(
            "❌ Ты не подписан на канал! Подпишись и нажми кнопку ниже.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return True
    return False

# ====================== МЕНЮ ======================
async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_subscription(update, context):
        return

    keyboard = [
        [InlineKeyboardButton("🏠 Аккаунт", callback_data="menu_account")],
        [InlineKeyboardButton("⚽ Матчи", callback_data="menu_matches")],
        [InlineKeyboardButton("📢 Канал", callback_data="menu_channel"),
         InlineKeyboardButton("💬 Чат", callback_data="menu_chat")],
    ]
    reply = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Главное меню", reply_markup=reply)

# ====================== КАЛЛБЭКИ ======================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data

    if data == "menu_channel":
        await query.edit_message_text("Канал:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Перейти", url="https://t.me/koefii")]]))
    elif data == "menu_chat":
        await query.edit_message_text("Чат:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Перейти", url="https://t.me/koefchat")]]))
    elif data == "menu_account":
        await show_account(update, context)
    elif data == "menu_matches":
        await show_matches_menu(update, context)
    elif data.startswith("match_"):
        match_id = int(data.split("_")[1])
        await show_match_details(update, context, match_id)
    elif data.startswith("tab_"):
        tab = data.split("_")[1]
        match_id = int(query.message.reply_markup.inline_keyboard[0][0].callback_data.split("_")[1])
        await show_tab(update, context, match_id, tab)
    elif data.startswith("region_"):
        region = data.split("_")[1]
        context.user_data["region"] = region
        keyboard = [[InlineKeyboardButton(FLAGS[region][0], callback_data=f"league_{region}")] for region in REGIONS]
        await query.edit_message_text("Выбери лигу:", reply_markup=InlineKeyboardMarkup(keyboard))
    elif data.startswith("league_"):
        region = data.split("_")[1]
        context.user_data["league"] = region
        await query.edit_message_text(f"Матчи для {region} добавлены (симуляция)")

    # Premium / Support / Goal обработка (дальше)

# ====================== АККАУНТ ======================
async def show_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = users.get(user_id, {"name": "Гость", "status": "Free", "premium_end": None})

    text = f"👋 Добро пожаловать, {user['name']}!\nID: {user_id}\nСтатус: {user['status']}"

    keyboard = []
    if user["status"] == "Free":
        keyboard.append([InlineKeyboardButton("Купить Premium", callback_data="buy_premium")])
    keyboard.append([InlineKeyboardButton("Поддержка", callback_data="support")])

    await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

# ====================== МАТЧИ ======================
async def show_matches_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton(region, callback_data=f"region_{region}")] for region in REGIONS]
    await update.callback_query.edit_message_text("Выбери регион:", reply_markup=InlineKeyboardMarkup(keyboard))

# ====================== ТАБЫ (спойлеры) ======================
async def show_tab(update: Update, context: ContextTypes.DEFAULT_TYPE, match_id: int, tab: str):
    match = matches.get(match_id)
    if not match:
        return

    spoilers = {
        "Прогноз": f"**Прогноз:** {match['forecast']}\n\n(скрытый текст)",
        "Аналитика": f"**Аналитика:** xG = {match['xg']}, тренды...",
        "Статистика": f"**Статистика:** Травмы, результаты, таблица...",
        "Таймы": f"**Таймы:** По таймам...",
        "Травмы": f"**Травмы:** {match['injuries']}",
    }
    text = spoilers.get(tab, "Данные недоступны")

    # Простой спойлер (можно улучшить через markdown)
    keyboard = [
        [InlineKeyboardButton("Назад", callback_data=f"match_{match_id}")],
    ]
    await update.callback_query.edit_message_text(f"{text}\n\n(нажми назад)", reply_markup=InlineKeyboardMarkup(keyboard))

# ====================== АДМИН-ПАНЕЛЬ /GOAL ======================
async def goal_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_message.text.split()[1] != ADMIN_PASSWORD:
        await update.message.reply_text("Неверный пароль!")
        return

    # Простая админ-панель: выбор региона, лиги, добавление матча
    keyboard = [[InlineKeyboardButton(r, callback_data=f"region_{r}")] for r in REGIONS]
    await update.message.reply_text("Админ-панель:", reply_markup=InlineKeyboardMarkup(keyboard))

# ====================== ЮKASSA ======================
def create_payment(amount: float, user_id: int):
    payment = yookassa.Payment.create({
        "amount": {"value": f"{amount:.2f}", "currency": "RUB"},
        "confirmation": {"type": "redirect", "return_url": f"https://t.me/{TOKEN}"},
        "description": f"Premium для {user_id}",
    })
    return payment.confirmation.confirmation_url

# ====================== ЗАПУСК ======================
def main():
    application = Application.builder().token(TOKEN).persistence(PicklePersistence(filepath="bot_data.pickle")).build()

    application.add_handler(CommandHandler("start", main_menu))
    application.add_handler(CommandHandler("goal", goal_command))
    application.add_handler(CallbackQueryHandler(button_handler))

    # Long polling для Botshost
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
