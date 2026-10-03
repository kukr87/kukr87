import asyncio
from datetime import datetime, timedelta
from telegram import (
    Update, InputMediaPhoto, InlineKeyboardButton, InlineKeyboardMarkup,
    ChatMemberUpdated, ChatMember
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters,
    CallbackQueryHandler, ContextTypes, PicklePersistence
)

# ====================== КОНФИГ ======================
TOKEN = "8855640297:AAHtsj7N1d_lc6p2wNxZcZGGQxM5l0X01cI"
CHANNEL_ID = -1001234567890  # больше не используется
ADMIN_PASSWORD = "12345"

users = {}          # user_id -> данные
matches = {}        # match_id -> данные
unread_support = [] # список сообщений поддержки

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
    "Ирландия": ("🇧🇾", "https://flagcdn.com/ie.svg"),
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

REGIONS = list(FLAGS.keys())

# ====================== БАННЕР (исправлено) ======================
BANNER_URL = "https://telegra.ph/file/6J6ZJ6Z.jpg"

# ====================== МЕНЮ ======================
async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_photo(
        chat_id=update.effective_chat.id,
        photo=BANNER_URL,
        caption=(
            "Доброго времени суток!\n\n"
            "Я собираю полную статистику команд (травмы, результаты, положение в турнирной таблице, "
            "xG, статистика по таймам, тренды и многое другое). Анализирую и даю наиболее вероятные исходы."
        ),
        parse_mode=ParseMode.MARKDOWN
    )
    keyboard = [
        [InlineKeyboardButton("🏠 Аккаунт", callback_data="menu_account")],
        [InlineKeyboardButton("⚽ Матчи", callback_data="menu_matches")],
        [InlineKeyboardButton("📢 Канал", callback_data="menu_channel"),
         InlineKeyboardButton("💬 Чат", callback_data="menu_chat")],
    ]
    await update.message.reply_text("Главное меню", reply_markup=InlineKeyboardMarkup(keyboard))

# ====================== ОБРАБОТКА КЛАВИШ ======================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "menu_channel":
        await query.edit_message_text("Канал:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Перейти", url="https://t.me/koefii")]]))

    elif data == "menu_chat":
        await query.edit_message_text("Чат:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Перейти", url="https://t.me/koefchat")]]))

    elif data == "menu_account":
        user_id = query.from_user.id
        user = users.get(user_id, {"name": query.from_user.first_name, "status": "Free", "premium_end": None})
        text = f"👋 Добро пожаловать, {user['name']}!\nID: {user_id}\nСтатус: {user['status']}"
        keyboard = []
        if user["status"] == "Free":
            keyboard.append([InlineKeyboardButton("Купить Premium", callback_data="buy_premium")])
        keyboard.append([InlineKeyboardButton("Поддержка", callback_data="support")])
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "menu_matches":
        keyboard = [[InlineKeyboardButton(region, callback_data=f"region_{region}")] for region in REGIONS]
        await query.edit_message_text("Выбери регион:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("region_"):
        region = data.split("_")[1]
        context.user_data["region"] = region
        keyboard = [[InlineKeyboardButton(FLAGS[region][0], callback_data=f"league_{region}")] for region in REGIONS]
        await query.edit_message_text(f"Выбери лигу для {region}:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("league_"):
        region = data.split("_")[1]
        context.user_data["league"] = region
        await query.edit_message_text("Матчи добавлены (симуляция)", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Назад", callback_data="menu_matches")]]))

    elif data.startswith("match_"):
        match_id = int(data.split("_")[1])
        context.user_data["match_id"] = match_id
        match = matches.get(match_id, {"name": "Матч", "forecast": "Прогноз...", "xg": "2.4", "injuries": "Нет травм", "stats": "Статистика..."})
        keyboard = [
            [InlineKeyboardButton("Прогноз", callback_data=f"tab_Прогноз_{match_id}")],
            [InlineKeyboardButton("Аналитика", callback_data=f"tab_Аналитика_{match_id}")],
            [InlineKeyboardButton("Статистика", callback_data=f"tab_Статистика_{match_id}")],
            [InlineKeyboardButton("Таймы", callback_data=f"tab_Таймы_{match_id}")],
            [InlineKeyboardButton("Травмы", callback_data=f"tab_Травмы_{match_id}")],
        ]
        await query.edit_message_text(f"Матч: {match['name']}\n\nВыбери вкладку:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("tab_"):
        tab = data.split("_")[1]
        match_id = int(data.split("_")[2])
        match = matches.get(match_id, {})
        spoilers = {
            "Прогноз": f"**Прогноз:** {match.get('forecast', 'Прогноз...')}\n\n(скрытый текст)",
            "Аналитика": f"**Аналитика:** xG = {match.get('xg', '2.4')}, тренды...",
            "Статистика": f"**Статистика:** {match.get('stats', 'Статистика...')}",
            "Таймы": "**Таймы:** По таймам...",
            "Травмы": f"**Травмы:** {match.get('injuries', 'Нет травм')}",
        }
        await query.edit_message_text(spoilers.get(tab, "Данные недоступны"), parse_mode=ParseMode.MARKDOWN)

    elif data == "buy_premium":
        keyboard = [
            [InlineKeyboardButton("Купить на месяц (300 руб)", callback_data="premium_month")],
            [InlineKeyboardButton("Купить на 3 месяца", callback_data="premium_3month")],
            [InlineKeyboardButton("Назад", callback_data="menu_account")],
        ]
        await query.edit_message_text("Выбери тариф Premium:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "premium_month":
        await query.edit_message_text("💰 Оплата Premium на месяц: 300 руб.\n\nПосле оплаты напиши мне @код_поддержки", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Назад", callback_data="menu_account")]]))

    elif data == "premium_3month":
        await query.edit_message_text("💰 Оплата Premium на 3 месяца: 800 руб.\n\nПосле оплаты напиши мне @код_поддержки", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Назад", callback_data="menu_account")]]))

    elif data == "support":
        if unread_support:
            text = f"У тебя {len(unread_support)} непрочитанных сообщений.\n\nНажми на сообщение, чтобы прочитать:"
            for i, msg in enumerate(unread_support):
                text += f"\n\n{i+1}. {msg['user_name']} (ID: {msg['user_id']})"
            keyboard = [[InlineKeyboardButton(f"Сообщение {i+1}", callback_data=f"support_msg_{i}")] for i in range(len(unread_support))]
            keyboard.append([InlineKeyboardButton("Назад", callback_data="menu_account")])
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await query.edit_message_text("Непрочитанных сообщений нет.")

    elif data.startswith("support_msg_"):
        idx = int(data.split("_")[2])
        if idx < len(unread_support):
            msg = unread_support.pop(idx)
            keyboard = [
                [InlineKeyboardButton("Ответить", callback_data="answer_support")],
                [InlineKeyboardButton("Назад", callback_data="support")],
            ]
            await query.edit_message_text(f"От {msg['user_name']} (ID: {msg['user_id']}):\n\n{msg['text']}", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "answer_support":
        await query.edit_message_text("✅ Ответ отправлен (симуляция).", reply_markup=None)

# ====================== /START ======================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await main_menu(update, context)

# ====================== /GOAL ======================
async def goal_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_message.text.split()[1] != ADMIN_PASSWORD:
        await update.message.reply_text("Неверный пароль!")
        return
    keyboard = [[InlineKeyboardButton(region, callback_data=f"region_{region}")] for region in REGIONS]
    await update.message.reply_text("Админ-панель:", reply_markup=InlineKeyboardMarkup(keyboard))

# ====================== ЗАПУСК ======================
def main():
    application = Application.builder().token(TOKEN).persistence(PicklePersistence(filepath="bot_data.pickle")).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("goal", goal_command))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    main()
