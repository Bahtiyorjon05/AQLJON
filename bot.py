import os
import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)
import google.generativeai as genai
from typing import List, Dict
import json

# Environment setup
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
MODEL = genai.GenerativeModel('gemini-2.0-flash')

# Logging config
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Constants
MAX_HISTORY_LENGTH = 10
CHUNK_SIZE = 4096
LANGUAGES = ["en", "uz", "ru"]

# Language-specific UI strings (neutral tone)
UI_TEXT = {
    "welcome": {
        "en": "Welcome! This is a Gemini-powered chatbot. Use /help for commands or start chatting.",
        "uz": "Xush kelibsiz! Bu Gemini bilan ishlaydigan chatbot. Buyruqlar uchun /help ni ishlatining yoki suhbatni boshlang.",
        "ru": "Добро пожаловать! Это чат-бот на базе Gemini. Используйте /help для команд или начните общение."
    },
    "help": {
        "en": "Commands:\n/start - Begin\n/forget - Clear history\n/history - Toggle history\n/export - Export chat history as JSON\n/language - Change language\nOr just send a message to chat with Gemini.",
        "uz": "Buyruqlar:\n/start - Boshlash\n/forget - Tarixni tozalash\n/history - Tarixni yoqish/o‘chirish\n/export - Suhbat tarixini JSON sifatida eksport qilish\n/language - Tilni o‘zgartirish\nYoki Gemini bilan suhbatlashish uchun xabar yuboring.",
        "ru": "Команды:\n/start - Начать\n/forget - Очистить историю\n/history - Вкл/выкл историю\n/export - Экспорт истории чата в JSON\n/language - Сменить язык\nИли просто отправьте сообщение для общения с Gemini."
    },
    "name_set": {
        "en": "Name set to {name}. How can I assist you?",
        "uz": "Ism {name} ga o‘rnatildi. Sizga qanday yordam bera olaman?",
        "ru": "Имя установлено как {name}. Чем могу помочь?"
    },
    "history_off": {
        "en": "History tracking is now off.",
        "uz": "Tarix kuzatuvi o‘chirildi.",
        "ru": "Отслеживание истории отключено."
    },
    "history_on": {
        "en": "History tracking is now on.",
        "uz": "Tarix kuzatuvi yoqildi.",
        "ru": "Отслеживание истории включено."
    },
    "no_history": {
        "en": "No history to export yet.",
        "uz": "Hozircha eksport qilish uchun tarix yo‘q.",
        "ru": "Пока нет истории для экспорта."
    },
    "memory_wiped": {
        "en": "History cleared.",
        "uz": "Tarix tozalandi.",
        "ru": "История очищена."
    },
    "language_set": {
        "en": "Language set to {lang}.",
        "uz": "Til {lang} ga o‘zgartirildi.",
        "ru": "Язык установлен на {lang}."
    },
    "pick_language": {
        "en": "Select a language:",
        "uz": "Tilni tanlang:",
        "ru": "Выберите язык:"
    },
    "error": {
        "en": "An error occurred. Please try again.",
        "uz": "Xatolik yuz berdi. Iltimos, qayta urinib ko‘ring.",
        "ru": "Произошла ошибка. Попробуйте снова."
    }
}

# Gemini query (raw response)
async def ask_gemini(history: List[Dict[str, str]]) -> str:
    try:
        gemini_history = [{"parts": [{"text": item["content"]}], "role": item["role"]} for item in history]
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, MODEL.generate_content, gemini_history)
        return response.text.strip()
    except Exception as e:
        logger.error(f"Gemini API error: {e}")
        return "Error: Unable to process your request at this time."

# Chunked message sender
async def send_chunked_message(update: Update, text: str, reply_markup=None):
    if len(text) <= CHUNK_SIZE:
        await update.message.reply_text(text, reply_markup=reply_markup)
    else:
        chunks = [text[i:i+CHUNK_SIZE] for i in range(0, len(text), CHUNK_SIZE)]
        for i, chunk in enumerate(chunks):
            await update.message.reply_text(chunk, reply_markup=reply_markup if i == len(chunks) - 1 else None)
            await asyncio.sleep(0.3)

# History summary
def summarize_history(history: List[Dict[str, str]], lang: str = "en") -> str:
    if not history:
        return UI_TEXT["no_history"][lang]
    summary = {"en": "Chat Summary:\n", "uz": "Suhbat xulosa:\n", "ru": "Сводка чата:\n"}[lang]
    for item in history[-5:]:
        role = {"en": "User" if item["role"] == "user" else "Gemini", "uz": "Foydalanuvchi" if item["role"] == "user" else "Gemini", "ru": "Пользователь" if item["role"] == "user" else "Gemini"}[lang]
        summary += f"- {role}: {item['content'][:50]}...\n"
    return summary.strip()

# /start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data = context.user_data
    user_data["history"] = []
    user_data["history_enabled"] = True
    user_data["lang"] = "en"  # Default language

    keyboard = [
        [InlineKeyboardButton("Help", callback_data="help"), InlineKeyboardButton("Language", callback_data="language")],
        [InlineKeyboardButton("History", callback_data="history")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    welcome = UI_TEXT["welcome"]["en"]
    user_data["history"].append({"role": "assistant", "content": welcome})
    await send_chunked_message(update, welcome, reply_markup)

# /help command
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "en")
    await send_chunked_message(update, UI_TEXT["help"][lang])

# Message handler
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text.strip()
    user_data = context.user_data
    lang = user_data.get("lang", "en")
    if "history" not in user_data:
        user_data["history"] = []

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    if "my name is" in user_message.lower():
        name = user_message.lower().split("my name is")[-1].strip().capitalize()
        user_data["name"] = name
        response = UI_TEXT["name_set"][lang].format(name=name)
        if user_data.get("history_enabled", True):
            user_data["history"].append({"role": "user", "content": user_message})
            user_data["history"].append({"role": "assistant", "content": response})
    else:
        if user_data.get("history_enabled", True):
            user_data["history"].append({"role": "user", "content": user_message})
        response = await ask_gemini(user_data["history"])
        if user_data.get("history_enabled", True):
            user_data["history"].append({"role": "assistant", "content": response})

    await send_chunked_message(update, response)

    if len(user_data["history"]) > MAX_HISTORY_LENGTH * 2:
        user_data["history"] = user_data["history"][-MAX_HISTORY_LENGTH * 2:]

# /forget command
async def forget(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "en")
    context.user_data.clear()
    await update.message.reply_text(UI_TEXT["memory_wiped"][lang])

# /history toggle
async def toggle_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data = context.user_data
    lang = user_data.get("lang", "en")
    user_data["history_enabled"] = not user_data.get("history_enabled", True)
    status = UI_TEXT["history_on"][lang] if user_data["history_enabled"] else UI_TEXT["history_off"][lang]
    await update.message.reply_text(status)

# /export history
async def export_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data = context.user_data
    lang = user_data.get("lang", "en")
    history = user_data.get("history", [])
    if not history:
        await update.message.reply_text(UI_TEXT["no_history"][lang])
    else:
        json_data = json.dumps(history, indent=2, ensure_ascii=False)
        await send_chunked_message(update, f"Chat history:\n```json\n{json_data}\n```")

# Button handler
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_data = context.user_data
    lang = user_data.get("lang", "en")

    if query.data == "help":
        await help_command(query, context)
    elif query.data == "language":
        keyboard = [
            [InlineKeyboardButton("English", callback_data="lang_en"), InlineKeyboardButton("O‘zbek", callback_data="lang_uz")],
            [InlineKeyboardButton("Русский", callback_data="lang_ru")]
        ]
        await query.edit_message_text(UI_TEXT["pick_language"][lang], reply_markup=InlineKeyboardMarkup(keyboard))
    elif query.data.startswith("lang_"):
        new_lang = query.data.split("_")[1]
        user_data["lang"] = new_lang
        await query.edit_message_text(UI_TEXT["language_set"][lang].format(lang=new_lang))
    elif query.data == "history":
        await query.edit_message_text(summarize_history(user_data.get("history", []), lang))

# Error handler
async def error(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(msg="Bot error:", exc_info=context.error)
    if update and hasattr(update, "message"):
        lang = context.user_data.get("lang", "en")
        await update.message.reply_text(UI_TEXT["error"][lang])

# Main setup
def main():
    logger.info("Launching the Gemini chatbot...")
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("forget", forget))
    app.add_handler(CommandHandler("history", toggle_history))
    app.add_handler(CommandHandler("export", export_history))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button))
    app.add_error_handler(error)

    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()