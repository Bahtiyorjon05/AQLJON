from dotenv import load_dotenv
load_dotenv()

import os
import logging
import asyncio
import time
import json
import hashlib
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes
)
import google.generativeai as genai
import redis.asyncio as redis
import aiohttp
import tenacity
from telegram.constants import ChatAction
from telegram.error import TelegramError

# Logging
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuration
GEMINI_KEY = os.getenv("GEMINI_API_KEY") or exit("GEMINI_API_KEY not set")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or exit("TELEGRAM_BOT_TOKEN not set")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
PORT = int(os.getenv("PORT", 8443))

genai.configure(api_key=GEMINI_KEY)
MODEL = genai.GenerativeModel('gemini-2.0-flash')

# Redis & HTTP Session
redis_client = redis.from_url(
    REDIS_URL, encoding="utf-8", decode_responses=True, max_connections=100
)
aiohttp_session: aiohttp.ClientSession = None

MAX_HISTORY = 20
BASE_RATE_LIMIT = 5
WELCOME_MESSAGE = "As-salamu alaykum! I'm your memory-backed Gemini bot. What’s your name, akhi?"

# Helper Functions
def generate_cache_key(chat_id: str, history: list) -> str:
    key_data = json.dumps(history[-3:])
    hashed = hashlib.sha256(key_data.encode()).hexdigest()
    return f"cache:{chat_id}:{hashed}"

async def extract_name(history: list) -> str:
    for msg in reversed(history):
        content = msg["content"].lower()
        if any(p in content for p in ["my name is", "i’m", "i am"]):
            words = content.split()
            for i, word in enumerate(words):
                if word in ["is", "i’m", "am"] and i + 1 < len(words):
                    return words[i + 1].capitalize()
    return ""

async def summarize_history(chat_id: str, history: list) -> str:
    if len(history) <= 10:
        return ""
    summary_input = [{"role": m["role"], "parts": [m["content"]]} for m in history[:-10]]
    cache_key = f"summary:{chat_id}:{hashlib.sha256(json.dumps(summary_input).encode()).hexdigest()}"
    cached = await redis_client.get(cache_key)
    if cached:
        return cached
    try:
        summary = await MODEL.generate_content_async([
            {"role": "user", "parts": [f"Summarize this fast: {json.dumps(summary_input)}"]}
        ])
        text = summary.text.strip()
        await redis_client.setex(cache_key, 86400, text)
        return text
    except Exception:
        return ""

@tenacity.retry(
    stop=tenacity.stop_after_attempt(3),
    wait=tenacity.wait_exponential(multiplier=0.3, min=0.3, max=3),
)
async def ask_gemini(chat_id: str, history: list) -> str:
    last_input = history[-1]['content']
    global_cache = f"global:{hashlib.sha256(last_input.encode()).hexdigest()}"
    if (cached := await redis_client.get(global_cache)):
        return cached

    cache_key = generate_cache_key(chat_id, history)
    if (cached := await redis_client.get(cache_key)):
        return cached

    try:
        messages = [{"role": m["role"], "parts": [m["content"]]} for m in history[-10:]]
        name = await redis_client.get(f"name:{chat_id}") or await extract_name(history)
        if name:
            await redis_client.setex(f"name:{chat_id}", 86400, name)

        summary = await summarize_history(chat_id, history)
        if summary:
            messages.insert(0, {"role": "user", "parts": [f"Summary: {summary}"]})

        start_time = time.time()
        response = await MODEL.generate_content_async(messages)
        text = response.text.strip() if response.text else "Couldn’t respond right now, akhi."
        if name and name not in text:
            text = f"{name}, {text}"
        logger.info(f"Gemini responded in {time.time() - start_time:.2f}s for {chat_id}")

        await redis_client.setex(global_cache, 3600, text)
        await redis_client.setex(cache_key, 180, text)
        return text
    except Exception as e:
        logger.error(f"Gemini error: {type(e).__name__} - {e}")
        return "Error happened, akhi. Try again later."

async def get_history(chat_id: str) -> list:
    try:
        data = await redis_client.lrange(chat_id, 0, MAX_HISTORY * 2 - 1)
        return [json.loads(d) for d in data]
    except Exception:
        return []

async def save_history(chat_id: str, history: list):
    try:
        pipe = redis_client.pipeline()
        await pipe.delete(chat_id)
        for msg in history[-MAX_HISTORY * 2:]:
            await pipe.rpush(chat_id, json.dumps(msg))
        await pipe.execute()
    except Exception:
        pass

async def check_rate_limit(chat_id: str) -> bool:
    global_key = "global_rate"
    user_key = f"rl:{chat_id}"
    warn_key = f"warn:{chat_id}"

    active = await redis_client.incr(global_key)
    await redis_client.expire(global_key, 60)

    limit = max(3, 10 - (active // 10))
    count = await redis_client.incr(user_key)
    if count == 1:
        await redis_client.expire(user_key, 60)

    if count > limit:
        if not await redis_client.exists(warn_key):
            await redis_client.setex(warn_key, 60, "1")
            return True
        return False
    return False

async def send_typing(chat_id, context, duration=2):
    end = time.time() + duration
    while time.time() < end:
        try:
            await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        except TelegramError:
            break
        await asyncio.sleep(1.5)

# Handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    for key in [chat_id, f"rl:{chat_id}", f"warn:{chat_id}", f"name:{chat_id}"]:
        await redis_client.delete(key)
    await update.message.reply_text(WELCOME_MESSAGE)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    user_input = update.message.text.strip()

    if await check_rate_limit(chat_id):
        await update.message.reply_text("Too fast, akhi. Wait a bit.")
        return

    history = await get_history(chat_id)
    history.append({"role": "user", "content": user_input})

    typing_task = asyncio.create_task(send_typing(chat_id, context))
    response = await ask_gemini(chat_id, history)
    typing_task.cancel()

    history.append({"role": "assistant", "content": response})
    await save_history(chat_id, history)

    try:
        if len(response) > 4096:
            for i in range(0, len(response), 4096):
                await update.message.reply_text(response[i:i + 4096])
                await asyncio.sleep(0.05)  # Add slight delay for Telegram
        else:
            await update.message.reply_text(response)
    except TelegramError:
        await update.message.reply_text("Message too long to send, akhi.")

# Lifecycle
async def on_startup(app: Application):
    global aiohttp_session
    aiohttp_session = aiohttp.ClientSession()
    try:
        await redis_client.ping()
        logger.info(f"Connected to Redis at {REDIS_URL}")
    except Exception:
        logger.warning("Redis connection failed!")
    logger.info("Bot is running...")

async def on_shutdown(app: Application):
    if aiohttp_session:
        await aiohttp_session.close()
    await redis_client.close()
    logger.info("Bot shutdown complete.")

# Main
def main():
    logger.info("Starting bot...")
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.post_init = on_startup
    app.post_shutdown = on_shutdown

    if os.getenv("HEROKU_APP_NAME"):
        app.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=TELEGRAM_TOKEN,
            webhook_url=f"https://{os.getenv('HEROKU_APP_NAME')}.herokuapp.com/{TELEGRAM_TOKEN}"
        )
    else:
        app.run_polling()

if __name__ == "__main__":
    main()