from dotenv import load_dotenv
load_dotenv()

import os
import logging
import time
import json
import hashlib
import asyncio
import aiohttp
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ContextTypes, filters
)
import google.generativeai as genai
import tenacity
from telegram.error import TelegramError

# Logging
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# Environment
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
PORT = int(os.getenv("PORT", 8443))
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://your-production-url.up.railway.app")

# Validate keys
for _ in range(3):
    if GEMINI_KEY and TELEGRAM_TOKEN:
        break
    logger.warning("Missing GEMINI_API_KEY or TELEGRAM_BOT_TOKEN — retrying...")
    time.sleep(2)
    GEMINI_KEY = os.getenv("GEMINI_API_KEY")
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
else:
    logger.error("Missing GEMINI_API_KEY or TELEGRAM_BOT_TOKEN")
    exit("Set .env values correctly")

# Setup
genai.configure(api_key=GEMINI_KEY)
MODEL = genai.GenerativeModel("gemini-2.0-flash")

MAX_HISTORY = 20
WELCOME_MESSAGE = "<b>Yo, bro!</b> 👋 I'm your <i>Gemini bot</i> with <u>killer memory</u>. What's your name?"

user_history = {}

async def extract_name(history: list) -> str:
    for msg in reversed(history):
        content = msg["content"].lower()
        if any(phrase in content for phrase in ["my name is", "i’m", "i am"]):
            words = content.split()
            for i, word in enumerate(words):
                if word in ["is", "i’m", "am"] and i + 1 < len(words):
                    return words[i + 1].capitalize()
    return ""

@tenacity.retry(stop=tenacity.stop_after_attempt(3), wait=tenacity.wait_exponential(min=0.3))
async def ask_gemini(chat_id: str, history: list) -> str:
    try:
        # Prepare messages in correct Gemini format
        messages = [{"role": msg["role"], "parts": [msg["content"]]} for msg in history[-10:]]
        
        # Insert style instruction as user message (not system)
        messages.insert(0, {
            "role": "user",
            "parts": ["You're a friendly assistant. Use HTML tags like <b>, <i>, <u>, and emojis in your answers."]
        })

        response = await MODEL.generate_content_async(messages)
        text = response.text.strip() or "<b>Gemini's speechless, bro.</b>"
        return text
    except Exception as e:
        logger.error(f"Gemini error: {e}")
        return "<b>Gemini failed, bro 😟</b>"


async def send_long_message(update: Update, text: str, parse_mode="HTML"):
    if len(text) <= 4096:
        await update.message.reply_text(text, parse_mode=parse_mode)
        return
    chunks = [text[i:i+4096] for i in range(0, len(text), 4096)]
    for chunk in chunks:
        await update.message.reply_text(chunk, parse_mode=parse_mode)
        await asyncio.sleep(0.1)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    user_history[chat_id] = []
    await update.message.reply_text(WELCOME_MESSAGE, parse_mode="HTML")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("""<b>Gemini Bot Commands</b>

/start - Restart the bot
/help - Show help
/status - Bot status
/clear - Clear history

<i>Just message me and I’ll reply with memory!</i>""", parse_mode="HTML")

async def clear_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    user_history.pop(chat_id, None)
    await update.message.reply_text("<b>Memory cleared.</b>", parse_mode="HTML")

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        start_time = time.time()
        _ = await MODEL.generate_content_async([{"role": "user", "parts": ["Hello"]}])
        latency = time.time() - start_time
        await update.message.reply_text(
            f"<b>Status:</b> \nGemini latency: {latency:.2f}s", parse_mode="HTML")
    except Exception as e:
        await update.message.reply_text(f"<b>Status check failed:</b>\n{e}", parse_mode="HTML")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    text = update.message.text.strip()
    history = user_history.get(chat_id, [])
    history.append({"role": "user", "content": text})
    response = await ask_gemini(chat_id, history)
    history.append({"role": "assistant", "content": response})
    user_history[chat_id] = history[-MAX_HISTORY * 2:]
    await send_long_message(update, response)

# App
def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("clear", clear_history))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("Gemini Bot is up!")
    app.run_polling()

if __name__ == "__main__":
    main()
