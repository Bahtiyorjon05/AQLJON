from dotenv import load_dotenv
load_dotenv()

import os
import logging
import asyncio
import time
import json
import hashlib
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import google.generativeai as genai
import redis.asyncio as redis
import aiohttp
import tenacity
from telegram.constants import ChatAction
from telegram.error import TelegramError

# Logging—keep it crisp
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# Config—locked and loaded
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
PORT = int(os.getenv("PORT", 8443))

# Validate env vars with a retry
for _ in range(3):  # Retry 3 times, 2s delay
    if GEMINI_KEY and TELEGRAM_TOKEN:
        break
    logger.warning("Missing GEMINI_API_KEY or TELEGRAM_BOT_TOKEN—retrying...")
    time.sleep(2)
    GEMINI_KEY = os.getenv("GEMINI_API_KEY")
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
else:
    logger.error("Failed to load GEMINI_API_KEY or TELEGRAM_BOT_TOKEN—bot will crash!")
    exit("Bro, set GEMINI_API_KEY and TELEGRAM_BOT_TOKEN!")

# Gemini—straight fire
genai.configure(api_key=GEMINI_KEY)
MODEL = genai.GenerativeModel("gemini-2.0-flash")

# Redis & HTTP—ready to roll
redis_client = redis.from_url(REDIS_URL, encoding="utf-8", decode_responses=True, max_connections=100)
aiohttp_session: aiohttp.ClientSession = None

# Constants—tight and right
MAX_HISTORY = 20
BASE_RATE_LIMIT = 5
WELCOME_MESSAGE = "Yo, bro! I’m your Gemini bot with killer memory. What’s your name?"

# Helpers—fast, clean, pro
def generate_cache_key(chat_id: str, history: list) -> str:
    key_data = json.dumps(history[-3:], sort_keys=True)
    return f"cache:{chat_id}:{hashlib.sha256(key_data.encode()).hexdigest()}"

async def extract_name(history: list) -> str:
    for msg in reversed(history):
        content = msg["content"].lower()
        if any(phrase in content for phrase in ["my name is", "i’m", "i am"]):
            words = content.split()
            for i, word in enumerate(words):
                if word in ["is", "i’m", "am"] and i + 1 < len(words):
                    return words[i + 1].capitalize()
    return ""

async def summarize_history(chat_id: str, history: list) -> str:
    if len(history) <= 10:
        return ""
    summary_key = f"summary:{chat_id}:{hashlib.sha256(json.dumps(history[:-10]).encode()).hexdigest()}"
    if cached := await redis_client.get(summary_key):
        return cached
    try:
        summary = await MODEL.generate_content_async([{"role": "user", "parts": ["Summarize this quick: " + " ".join(m["content"] for m in history[:-10])]}])
        text = summary.text.strip()
        await redis_client.setex(summary_key, 86400, text)
        return text
    except Exception:
        return ""

@tenacity.retry(stop=tenacity.stop_after_attempt(3), wait=tenacity.wait_exponential(multiplier=0.3, min=0.3, max=3))
async def ask_gemini(chat_id: str, history: list) -> str:
    last_input = history[-1]["content"]
    global_cache = f"global:{hashlib.sha256(last_input.encode()).hexdigest()}"
    if cached := await redis_client.get(global_cache):
        return cached

    cache_key = generate_cache_key(chat_id, history)
    if cached := await redis_client.get(cache_key):
        return cached

    try:
        messages = [{"role": m["role"], "parts": [m["content"]]} for m in history[-10:]]
        if summary := await summarize_history(chat_id, history):
            messages.insert(0, {"role": "user", "parts": [f"Past convo summary: {summary}"]})

        start_time = time.time()
        response = await MODEL.generate_content_async(messages)
        text = response.text.strip() or "Gemini’s got nothing, bro."
        logger.info(f"Gemini dropped it in {time.time() - start_time:.2f}s for {chat_id}")

        await redis_client.setex(global_cache, 3600, text)
        await redis_client.setex(cache_key, 180, text)
        return text
    except Exception as e:
        logger.error(f"Gemini crashed: {e}")
        return "Bot’s down, bro—try again soon."

async def get_history(chat_id: str) -> list:
    try:
        data = await redis_client.lrange(chat_id, 0, MAX_HISTORY * 2 - 1)
        return [json.loads(d) for d in data]
    except Exception:
        return []

async def save_history(chat_id: str, history: list):
    async with redis_client.pipeline() as pipe:
        await pipe.delete(chat_id)
        for msg in history[-MAX_HISTORY * 2:]:
            await pipe.rpush(chat_id, json.dumps(msg))
        await pipe.execute()

async def check_rate_limit(chat_id: str) -> bool:
    global_key, user_key = "global_rate", f"rl:{chat_id}"
    active = await redis_client.incr(global_key)
    await redis_client.expire(global_key, 60)

    limit = max(3, 10 - (active // 10))
    count = await redis_client.incr(user_key)
    if count == 1:
        await redis_client.expire(user_key, 60)
    return count > limit and await redis_client.setnx(f"warn:{chat_id}", 1) and await redis_client.expire(f"warn:{chat_id}", 60)

async def send_typing(chat_id, context, duration=1.5):
    end = time.time() + duration
    while time.time() < end:
        try:
            await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        except TelegramError:
            break
        await asyncio.sleep(1)

async def send_long_message(update: Update, text: str):
    if len(text) <= 4096:
        await update.message.reply_text(text)
        return

    chunks, current = [], ""
    for sentence in text.split(". "):
        sentence = sentence.strip() + ". "
        if len(current) + len(sentence) <= 4096:
            current += sentence
        else:
            chunks.append(current)
            current = sentence
    if current:
        chunks.append(current)

    for chunk in chunks:
        await update.message.reply_text(chunk.strip())
        await asyncio.sleep(0.1)

# Handlers—lean and mean
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    await redis_client.delete(chat_id, f"rl:{chat_id}", f"warn:{chat_id}", f"name:{chat_id}")
    await update.message.reply_text(WELCOME_MESSAGE)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    user_input = update.message.text.strip()

    if await check_rate_limit(chat_id):
        await update.message.reply_text("Slow down, bro—you’re too fast!")
        return

    history = await get_history(chat_id)
    history.append({"role": "user", "content": user_input})

    typing_task = asyncio.create_task(send_typing(chat_id, context))
    response = await ask_gemini(chat_id, history)
    typing_task.cancel()

    history.append({"role": "assistant", "content": response})
    await save_history(chat_id, history)
    await send_long_message(update, response)

# Lifecycle—smooth as butter
async def on_startup(app: Application):
    global aiohttp_session
    aiohttp_session = aiohttp.ClientSession()
    await redis_client.ping() and logger.info(f"Redis locked in at {REDIS_URL}")
    logger.info("Bot’s live, bro!")

async def on_shutdown(app: Application):
    if aiohttp_session:
        await aiohttp_session.close()
    await redis_client.close()
    logger.info("Bot’s out—peace!")

# Main—blast off
def main():
    logger.info("Bot’s gearing up...")
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.post_init = on_startup
    app.post_shutdown = on_shutdown

    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=TELEGRAM_TOKEN,
        webhook_url=f"https://web-production-cf21.up.railway.app/{TELEGRAM_TOKEN}"
    )

if __name__ == "__main__":
    main()