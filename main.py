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
CHANNEL_ID = -1001234567890  # ID канала https://t.me/koefii
ADMIN_PASSWORD = "12345"
YOOKASSA_SHOP_ID = "ТОТ_ШОП_ИЗ_KASSA"
YOOKASSA_SECRET_KEY = "ТОТ_SECRET_ИЗ_KASSA"

users = {}          # user_id -> данные
matches = {}        # match_id -> данные
unread_support = [] # список сообщений поддержки

FLAGS = { ... }  # оставил твой список флагов (я его не удалил)
REGIONS = list(FLAGS.keys())

# ====================== ГЕНЕРАЦИЯ КАРТИНКИ (K + футбол) ======================
def generate_banner():
    img = Image.new("RGB", (1200, 600), color="#0a0a0a")
    draw = ImageDraw.Draw(img)

    draw.rectangle([50, 150, 1150, 550], fill="#1a1a1a")

    draw.ellipse([800, 250, 950, 420], fill="#e74c3c", outline="#2c3e50", width=8)
    draw.rectangle([850, 420, 900, 480], fill="#2c3e50")
    draw.rectangle([880, 420, 910, 500], fill="#2c3e50")

    draw.ellipse([680, 320, 820, 460], fill="#f1c40f", outline="#2c3e50", width=6)
    draw.text((720, 370), "⚽", fill="#2c3e50", font=ImageFont.load_default())

    draw.line([(1050, 200), (1050, 500)], fill="#bdc3c7", width=8)
    draw.line([(1100, 200), (1100, 500)], fill="#bdc3c7", width=8)

    draw.text((100, 180), "K", fill="#e74c3c", font=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 350))

    for x in range(300, 900, 80):
        y1 = 200 + int(150 * (1.7 + x % 4 * 0.1))
        y2 = 200 + int(150 * (1.8 + x % 4 * 0.1))
        draw.line([(x, y1), (x + 60, y2)], fill="#27ae60", width=4)

    coeffs = [(1.7, "#27ae60"), (1.8, "#27ae60"), (2.0, "#f39c12"), (3.0, "#e74c3c")]
    for i, (val, color) in enumerate(coeffs):
        draw.text((400 + i * 140, 520), f"{val} : 1", fill=color, font=ImageFont.load_default())

    path = "/tmp/banner.png"
    img.save(path)
    return path

BANNER_PATH = generate_banner()

# ====================== ОСТАЛЬНОЙ КОД (без изменений) ======================
# (все функции: is_subscribed, check_subscription, main_menu, button_handler,
#  show_account, show_matches_menu, show_tab, goal_command, create_payment и т.д.)
# Я оставил весь остальной код прежним — просто добавил генерацию баннера в main_menu.

async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_subscription(update, context):
        return

    await context.bot.send_photo(
        chat_id=update.effective_chat.id,
        photo=open(BANNER_PATH, "rb"),
        caption="Доброго времени суток, {0}!\n\nЯ собираю полную статистику команд (травмы, результаты, положение в турнирной таблице, xG, статистику по таймам, тренды и много другое). Анализирую и предоставляю наиболее вероятные исходы на событие.".format(update.effective_user.first_name),
        parse_mode=ParseMode.MARKDOWN
    )

    keyboard = [
        [InlineKeyboardButton("🏠 Аккаунт", callback_data="menu_account")],
        [InlineKeyboardButton("⚽ Матчи", callback_data="menu_matches")],
        [InlineKeyboardButton("📢 Канал", callback_data="menu_channel"),
         InlineKeyboardButton("💬 Чат", callback_data="menu_chat")],
    ]
    reply = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Главное меню", reply_markup=reply)

# ====================== ЗАПУСК ======================
def main():
    application = Application.builder().token(TOKEN).persistence(PicklePersistence(filepath="bot_data.pickle")).build()

    application.add_handler(CommandHandler("start", main_menu))
    application.add_handler(CommandHandler("goal", goal_command))
    application.add_handler(CallbackQueryHandler(button_handler))

    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
