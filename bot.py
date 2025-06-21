import os
import re
import asyncio
import logging
import tempfile
from io import BytesIO
from dotenv import load_dotenv
from telegram import Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ContextTypes, filters
)
import google.generativeai as genai
import httpx
from telegram import ReplyKeyboardMarkup, KeyboardButton
from telegram import ReplyKeyboardRemove


# ─── 🔐 Load Environment Variables ─────────────────────────────
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
SERPER_KEY = os.getenv("SERPER_API_KEY")

# ─── 🤖 Gemini Setup ───────────────────────────────────────────
genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel("gemini-2.5-flash")

# ─── 🧠 Memory ─────────────────────────────────────────────────
user_history = {}
MAX_HISTORY = 20

# ─── 📝 Logging ────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# ─── 👋 Welcome Message ────────────────────────────────────────
WELCOME = (
    "<b>👋 Assalomu alaykum!</b>\n"
    "Men <b>Gemini</b> 🤖 — Google AI kuchi bilan ishlayman!\n\n"
    "💬 Xabar yozing\n📷 Rasm yuboring\n🎙️ Ovozingizni yuboring\n"
    "🔍 <code>/search</code> orqali internetdan ma’lumot oling\n\n"
    "Do‘stona, samimiy va foydali suhbat uchun shu yerdaman! 🚀"
)

# ─── 📋 Main Menu Keyboard ────────────────────────────────────
def main_menu_keyboard():
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("/start"), KeyboardButton("/help")],
            [KeyboardButton("/search")]
        ],
        resize_keyboard=True
    )


# ─── 📦 Utilities ──────────────────────────────────────────────
async def send_typing(update: Update):
    try:
        await update.message.chat.send_action(action=ChatAction.TYPING)
    except:
        pass

def clean_html(text: str) -> str:
    return re.sub(r'</?(ul|li|div|span|h\d|blockquote|table|tr|td|th)[^>]*>', '', text)

async def send_long_message(update: Update, text: str):
    text = clean_html(text)
    for i in range(0, len(text), 4096):
        await update.message.reply_text(text[i:i+4096], parse_mode=ParseMode.HTML)
        await asyncio.sleep(0.1)

# ─── 🔍 Search Integration ─────────────────────────────────────
async def search_web(query: str) -> str:
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://google.serper.dev/search",
                headers={"X-API-KEY": SERPER_KEY, "Content-Type": "application/json"},
                json={"q": query}
            )
            data = response.json()
            if "organic" in data and data["organic"]:
                top = data["organic"][0]
                title = top.get("title", "No title")
                snippet = top.get("snippet", "No snippet")
                link = top.get("link", "")
                return f"<b>{title}</b>\n{snippet}\n<a href='{link}'>🔗 Havola</a>"
            else:
                return "⚠️ Hech narsa topilmadi."
    except Exception as e:
        logger.error(f"Search error: {e}")
        return "❌ Qidiruvda xatolik yuz berdi."

# ─── 🧠 Gemini Reply Engine ────────────────────────────────────
async def ask_gemini(history):
    try:
        messages = [{"role": msg["role"], "parts": [msg["content"]]} for msg in history[-10:]]
        messages.insert(0, {
            "role": "user", "parts": [
                "You are a smart friend. Don’t repeat what the user said. Reply casually with humor and warmth 😊. "
                "Awesomely answer with formatting <b>, <i>, <u> and emojis 🧠. Answer in Uzbek if the user speaks Uzbek. Otherwise use appropriate language."
            ]
        })
        response = await model.generate_content_async(messages)
        return response.text.strip()
    except Exception as e:
        logger.error(f"Gemini error: {e}")
        return "<i>⚠️ Gemini hozircha javob bera olmadi.</i>"

# ─── 📌 Handlers ───────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_history[str(update.effective_chat.id)] = []
    await update.message.reply_text(
        WELCOME,
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu_keyboard()
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "<b>🤖 Gemini SmartBot yordam menyusi</b>\n\n"
        "🟢 <b>/start</b> — Botni qayta ishga tushirish\n"
        "🟢 <b>/help</b> — Yordam va buyruqlar roʻyxati\n"
        "🟢 <b>/search [so'z]</b> — Internetdan qidiruv (Google orqali)\n\n"
        "💬 Oddiy xabar yuboring — men siz bilan suhbatlashaman!\n"
        "📷 Rasm yuboring — uni tahlil qilaman!\n"
        "🎙️ Ovoz yuboring — munosib va chiroyli javob beraman!\n\n"
        "🚀 Juda aqlli, samimiy va foydali yordamchi bo'lishga harakat qilaman!"
    )
    await update.message.reply_text(help_text, parse_mode=ParseMode.HTML, reply_markup=main_menu_keyboard())

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_typing(update)
    await update.message.reply_text("💬 Davom etamiz...", reply_markup=ReplyKeyboardRemove())
    chat_id = str(update.effective_chat.id)
    message = update.message.text.strip()

    # Slash-based search
    if message.lower().startswith("/search"):
        parts = message.split(" ", 1)
        if len(parts) == 2:
            query = parts[1].strip()
            result = await search_web(query)
            await send_long_message(update, f"<b>🔎 Qidiruv natijasi:</b>\n{result}")
        else:
            await update.message.reply_text("❓ Qidiruv so‘zini yozing. Masalan: <code>/search Ibn Sina</code>", parse_mode=ParseMode.HTML)
        return

    # Gemini chat
    history = user_history.setdefault(chat_id, [])
    history.append({"role": "user", "content": message})
    reply = await ask_gemini(history)
    history.append({"role": "model", "content": reply})
    user_history[chat_id] = history[-MAX_HISTORY * 2:]
    await send_long_message(update, reply)

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_typing(update)
    file = await context.bot.get_file(update.message.photo[-1].file_id)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp_file:
        await file.download_to_drive(custom_path=tmp_file.name)
        tmp_path = tmp_file.name

    try:
        uploaded = genai.upload_file(tmp_path)
        response = model.generate_content([
            {"role": "user", "parts": [
                "The user sent a photo. Analyze in detail and react like a friend who saw it and gives a warm, friendly and useful reply. No robotic descriptions. Use emojis and formatting awesomely."
            ]},
            {"role": "user", "parts": [uploaded]}
        ])
        reply = response.text.strip()
        chat_id = str(update.effective_chat.id)
        user_history.setdefault(chat_id, []).append({"role": "user", "content": "[sent photo 📸]"})
        user_history[chat_id].append({"role": "model", "content": reply})
        await send_long_message(update, reply)
    finally:
        os.remove(tmp_path)

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_typing(update)
    voice = update.message.voice or update.message.audio
    file = await context.bot.get_file(voice.file_id)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".oga") as tmp_file:
        await file.download_to_drive(custom_path=tmp_file.name)
        tmp_path = tmp_file.name

    try:
        uploaded = genai.upload_file(tmp_path)
        response = model.generate_content([
            {"role": "user", "parts": [
                "The user sent a voice message. Understand and reply like you're talking back — not transcribing. Just continue the conversation warmly. Use Emojis + <i>/<b>/<u> formatting awesomely."
            ]},
            {"role": "user", "parts": [uploaded]}
        ])
        reply = response.text.strip()
        chat_id = str(update.effective_chat.id)
        user_history.setdefault(chat_id, []).append({"role": "user", "content": "[sent voice 🎙️]"})
        user_history[chat_id].append({"role": "model", "content": reply})
        await send_long_message(update, reply)
    finally:
        os.remove(tmp_path)

# ─── 🚀 Start Bot ──────────────────────────────────────────────
def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("search", handle_text))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice))
    logger.info("🤖 Gemini SmartBot is now LIVE and listening!")
    app.run_polling()


if __name__ == "__main__":
    main()
