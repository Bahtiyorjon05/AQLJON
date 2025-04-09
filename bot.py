
#   Gemini Chatbot

import os 
import logging
import asyncio
import time
from telegram import Update
from telegram.ext import(
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
import json
import hashlib

# Configuration
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
MODEL = genai.GenerativeModel('gemini-2.0-pro')

# Global aiohttp session variable (will be initialized on startup)
aiohttp_session: aiohttp.ClientSession = None

# Initialize Redis client
redis_client = redis.from_url(
    REDIS_URL,
    encoding="utf-8",
    decode_responses=True,
    max_connections=20
)

# Logging configuration
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

MAX_HISTORY_LENGTH = 30  # Maximum stored messages (user + bot pairs)
RATE_LIMIT = 5  # Maximum requests per minute
WELCOME_MESSAGE = ("Assalomu alaykum! Men Gemini Chatbotman. Sizga qanday yordam bera olishim mumkin? ")


# Helper function to generate a unique key for each chat
def generate_cache_key(history: list) -> str:
    key_data = json.dumps(history[-3:])
    hashed_key = hashlib.sha256(key_data.encode("utf-8")).hexdigest()
    return f"cache:{hashed_key}"


@tenacity.retry(stop=tenacity.stop_after_attempt(3), wait=tenacity.wait_fixed(1))
async def ask_gemini(history: list) -> str:
    cache_key = generate_cache_key(history)
    cached_response = await redis.client.get(cache_key)
    if cached_response:
        return cached_response
    
    try:
        url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-pro:generateContent"
        headers = {"Authorization": f"Bearer {os.getenv('GEMINI_API_KEY')}"}
        data = {"contents": history}

        async with aiohttp_session.post(url, headers=headers, json=data) as response:
            result = await response.json()
            response_text = result["text"].strip()

            # Cache response for 1 hour
            await redis_client.setex(cache_key, 3600, response_text)
            return response_text
        
    except Exception as e:
        logger.error(f"Gemini API error: {e}")
        return "Xatolik yuz berdi. Iltimos, qayta urinib ko'ring."

# Get the last messages from Redis  
async def get_history(chat_id: str) -> list:
    history = await redis_client.lrange(chat_id, 0, MAX_HISTORY_LENGTH * 2 - 1)
    return [json.loads(msg) for msg in history]

# Save history to Redis
async def save_history(chat_id: str, history: list):
    pipe = redis_client.pipeline()
    await pipe.delete(chat_id)
    for item in history[-MAX_HISTORY_LENGTH * 2:]:
        await pipe.rpush(chat_id, json.dumps(item))
    await pipe.execute()

# Handlers
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    current_time = time.time()
    rate_limit_key = f"rate_limit:{chat_id}"

    # Check rate limit
    last_requests = await redis_client.lrange(rate_limit_key, 0, -1)
    if len(last_requests) >= RATE_LIMIT:
        oldest = float(last_requests[-1])
        if current_time - oldest < 60:
            return await update.message.reply_text("Juda ko'p so'rov yubordingiz. Iltimos, biroz kuting.")
   
    # Track request time
    await redis_client.lpush(rate_limit_key, current_time)
    await redis_client.expire(rate_limit_key, 60)
    await redis_client.ltrim(rate_limit_key, 0, RATE_LIMIT - 1)

    user_message = update.message.text.strip()
    history = await get_history(chat_id)

    # Add user message to history
    history.append({"role": "user", "content": user_message}) 

    # Simulate typing delay
    typing_delay = min(len(user_message) * 0.01, 2.0)
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
 