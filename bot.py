import os
import re
import asyncio
import logging
import tempfile
from io import BytesIO
from dotenv import load_dotenv
from telegram import Update, Document
from telegram.constants import ChatAction, ParseMode
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ContextTypes, filters
)
import google.generativeai as genai
import httpx
from telegram import ReplyKeyboardMarkup, KeyboardButton


# ─── 🔐 Load Environment Variables ─────────────────────────────
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
SERPER_KEY = os.getenv("SERPER_API_KEY")

# ─── 🤖 Gemini Setup ───────────────────────────────────────────
genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel("gemini-2.5-flash")

# ─── 🧠 Enhanced Memory ─────────────────────────────────────────────────
user_history = {}
user_content_memory = {}  # Store document/audio content for later reference
MAX_HISTORY = 20
MAX_CONTENT_MEMORY = 50  # Store more content items

# ─── 📝 Logging ────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# ─── 👋 Welcome Message ────────────────────────────────────────
WELCOME = (
    "<b>👋 Assalomu alaykum va rohmatulloh va barokatuh!</b>\n"
    "Men <b>Gemini</b> 🤖 — Googlening aqqli modellaridan biriman!\n\n"
    "💬 Xabar yozing\n📷 Rasm yuboring\n🎙️ Ovozingizni yuboring\n"
    "📄 Hujjat yuboring\n"
    "🔍 <code>/search</code> orqali internetdan ma'lumot oling\n"
    "📊 <code>/stats</code> — Statistikani ko'ring\n\n"
    "Do'stona, samimiy va foydali suhbat uchun shu yerdaman! 🚀"
)

# ─── 📋 Main Menu Keyboard ────────────────────────────────────
def main_menu_keyboard():
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("/start"), KeyboardButton("/help")],
            [KeyboardButton("/search"), KeyboardButton("/stats")]
        ],
        resize_keyboard=True, one_time_keyboard=True,
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

# ─── 🧠 Memory Management Functions ─────────────────────────────────────────────────
def store_content_memory(chat_id: str, content_type: str, content_summary: str, file_name: str = None):
    """Store document/audio content for future reference"""
    if chat_id not in user_content_memory:
        user_content_memory[chat_id] = []
    
    memory_item = {
        "type": content_type,
        "summary": content_summary,
        "file_name": file_name,
        "timestamp": "just now"
    }
    
    user_content_memory[chat_id].append(memory_item)
    
    # Keep only recent content memories
    if len(user_content_memory[chat_id]) > MAX_CONTENT_MEMORY:
        user_content_memory[chat_id] = user_content_memory[chat_id][-MAX_CONTENT_MEMORY:]

def get_content_context(chat_id: str) -> str:
    """Get content memory context for AI"""
    if chat_id not in user_content_memory or not user_content_memory[chat_id]:
        return ""
    
    context_parts = []
    recent_content = user_content_memory[chat_id][-5:]  # Last 5 content items
    
    for item in recent_content:
        if item["type"] == "document":
            context_parts.append(f"Document '{item['file_name']}': {item['summary'][:200]}...")
        elif item["type"] == "audio":
            context_parts.append(f"Audio message: {item['summary'][:200]}...")
        elif item["type"] == "photo":
            context_parts.append(f"Photo: {item['summary'][:200]}...")
    
    if context_parts:
        return "\n\nPrevious content user shared: " + " | ".join(context_parts)
    return ""

# ─── 🧠 Enhanced Gemini Reply Engine ────────────────────────────────────
async def ask_gemini(history, chat_id: str = None):
    try:
        messages = [{"role": msg["role"], "parts": [msg["content"]]} for msg in history[-10:]]
        
        # Add content memory context if available
        content_context = get_content_context(chat_id) if chat_id else ""
        
        base_instruction = (
            "You are a smart friend. Don't repeat what the user said. Reply casually with humor and warmth 😊. "
            "Awesomely answer with formatting <b>, <i>, <u> and emojis 🧠. Answer in Uzbek if the user speaks Uzbek. Otherwise use appropriate language."
        )
        
        # Add content context to instruction if available
        full_instruction = base_instruction + content_context
        
        messages.insert(0, {
            "role": "user", "parts": [full_instruction]
        })
        
        response = await model.generate_content_async(messages)
        return response.text.strip()
    except Exception as e:
        logger.error(f"Gemini error: {e}")
        return "<i>⚠️ Gemini hozircha javob bera olmadi.</i>"

# ─── 📄 Enhanced Document Analysis ─────────────────────────────────────
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle document uploads and analysis."""
    if not update.message or not update.message.document:
        return
        
    await send_typing(update)
    document: Document = update.message.document
    
    # Send analyzing message
    analyzing_msg = await update.message.reply_text(
        "📄 <b>Hujjat tahlil qilinmoqda...</b>\n\n"
        "⏳ <i>Bu biroz vaqt olishi mumkin, iltimos kuting...</i>",
        parse_mode=ParseMode.HTML
    )
    
    try:
        # Check file size (limit to 20MB)
        if document.file_size and document.file_size > 20 * 1024 * 1024:
            # Delete analyzing message and send error
            await analyzing_msg.delete()
            await update.message.reply_text("❌ Fayl juda katta. Maksimal hajm: 20MB")
            return
        
        file = await context.bot.get_file(document.file_id)
        
        # Create temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{document.file_name}") as tmp_file:
            await file.download_to_drive(custom_path=tmp_file.name)
            tmp_path = tmp_file.name
        
        try:
            # Upload to Gemini for analysis
            uploaded = genai.upload_file(tmp_path)
            response = model.generate_content([
                {"role": "user", "parts": [
                    "The user sent a document. Analyze the document and respond to the user awesomely with emojis and nice formatting. Be creative and answer educationally that user needs to get lessons from that document. Answer in Uzbek if the user speaks Uzbek. Otherwise use appropriate language."
                ]},
                {"role": "user", "parts": [uploaded]}
            ])
            
            reply = response.text.strip() if response.text else "❌ Hujjatni tahlil qila olmadim."
            
            chat_id = str(update.effective_chat.id)
            
            # Store document content in memory for future reference
            store_content_memory(chat_id, "document", reply, document.file_name)
            
            user_history.setdefault(chat_id, []).append({"role": "user", "content": f"[uploaded document: {document.file_name}]"})
            user_history[chat_id].append({"role": "model", "content": reply})
            
            # Delete analyzing message before sending response
            await analyzing_msg.delete()
            
            # Send the actual response
            await send_long_message(update, f"{reply}")
            
        finally:
            os.unlink(tmp_path)  # Clean up temp file
            
    except Exception as e:
        logger.error(f"Document processing error: {e}")
        # Delete analyzing message and send error
        await analyzing_msg.delete()
        await update.message.reply_text("❌ Hujjatni qayta ishlashda xatolik. Qaytadan urinib ko'ring.")

# ─── 📊 Stats Command ─────────────────────────────────────────
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user statistics."""
    if not update.message or not update.effective_chat:
        return
        
    chat_id = str(update.effective_chat.id)
    history = user_history.get(chat_id, [])
    
    total_messages = len(history)
    user_messages = len([m for m in history if m["role"] == "user"])
    bot_messages = len([m for m in history if m["role"] == "model"])
    
    stats_text = (
        f"<b>📊 Sizning statistikangiz</b>\n\n"
        f"💬 Jami xabarlar: <b>{total_messages}</b>\n"
        f"👤 Sizning xabarlaringiz: <b>{user_messages}</b>\n"
        f"🤖 Bot javoblari: <b>{bot_messages}</b>\n\n"
        f"<i>Gemini Bot dan foydalanganingiz uchun rahmat! 🚀</i>"
    )
    
    await update.message.reply_text(stats_text, parse_mode=ParseMode.HTML)

# ─── 📢 Broadcast System ─────────────────────────────────────
async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Broadcast message to all users (admin only)."""
    if not update.message or not update.effective_chat:
        return
    
    # Check if user is admin (you can add your Telegram ID here)
    admin_ids = ["7050582441"]  # Replace 123456789 with your actual Telegram ID
    user_id = str(update.effective_user.id)
    
    if user_id not in admin_ids:
        await update.message.reply_text("❌ Bu buyruq faqat admin uchun!")
        return
    
    # Get message text after /broadcast command
    text = update.message.text.strip()
    parts = text.split(" ", 1)
    
    if len(parts) < 2:
        await update.message.reply_text(
            "📢 <b>Broadcast Usage:</b>\n\n"
            "<code>/broadcast Your message here</code>\n\n"
            "Bu barcha foydalanuvchilarga xabar yuboradi.",
            parse_mode=ParseMode.HTML
        )
        return
    
    broadcast_message = parts[1]
    
    # Get all users who have interacted with the bot
    all_users = list(user_history.keys())
    
    if not all_users:
        await update.message.reply_text("❌ Hech qanday foydalanuvchi topilmadi!")
        return
    
    # Send broadcast message
    successful_sends = 0
    failed_sends = 0
    
    await update.message.reply_text(f"📤 {len(all_users)} ta foydalanuvchiga xabar yuborilmoqda...")
    
    for chat_id in all_users:
        try:
            await context.bot.send_message(
                chat_id=int(chat_id),
                text=broadcast_message,
                parse_mode=ParseMode.HTML
            )
            successful_sends += 1
            await asyncio.sleep(0.1)  # Small delay to avoid rate limits
        except Exception as e:
            failed_sends += 1
            logger.warning(f"Failed to send to {chat_id}: {e}")
    
    # Send results to admin
    result_text = (
        f"✅ <b>Broadcast completed!</b>\n\n"
        f"📤 Yuborildi: <b>{successful_sends}</b>\n"
        f"❌ Yuborilmadi: <b>{failed_sends}</b>\n"
        f"👥 Jami foydalanuvchilar: <b>{len(all_users)}</b>"
    )
    
    await update.message.reply_text(result_text, parse_mode=ParseMode.HTML)

# ─── 📢 Quick Update Broadcast ─────────────────────────────────
async def send_update_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Quick command to send bot update message."""
    if not update.message or not update.effective_chat:
        return
    
    # Check if user is admin
    admin_ids = ["7050582441"]  # Replace 123456789 with your actual Telegram ID
    user_id = str(update.effective_user.id)
    
    if user_id not in admin_ids:
        await update.message.reply_text("❌ Bu buyruq faqat admin uchun!")
        return
    
    # Pre-written update message
    update_message = (
        "🎉 <b>Bot yangilandi!</b> 🚀\n\n"
        "<b>✨ Yangi imkoniyatlar:</b>\n"
        "📄 Hujjatlarni tahlil qilish\n"
        "🧠 Yaxshilangan xotira tizimi\n"
        "📊 Foydalanish statistikasi\n"
        "🎤 Audio xabarlarni yaxshiroq tushunish\n"
        "📷 Rasmlarni chuqurroq tahlil qilish\n\n"
        "<b>🔥 Eng asosiysi:</b>\n"
        "<i>Bot endi yuborgan hujjat, audio va rasmlaringizni eslab qoladi va keyinroq ularga murojaat qila oladi!</i>\n\n"
        "💬 Menga savolingizni bering va yangi imkoniyatlarni sinab ko'ring!\n\n"
        "<b>🙏 Botdan foydalanganingiz uchun rahmat!</b>"
    )
    
    # Get all users
    all_users = list(user_history.keys())
    
    if not all_users:
        await update.message.reply_text("❌ Hech qanday foydalanuvchi topilmadi!")
        return
    
    # Send update message
    successful_sends = 0
    failed_sends = 0
    
    await update.message.reply_text(f"📤 {len(all_users)} ta foydalanuvchiga yangilanish haqida xabar yuborilmoqda...")
    
    for chat_id in all_users:
        try:
            await context.bot.send_message(
                chat_id=int(chat_id),
                text=update_message,
                parse_mode=ParseMode.HTML
            )
            successful_sends += 1
            await asyncio.sleep(0.15)  # Delay to avoid rate limits
        except Exception as e:
            failed_sends += 1
            logger.warning(f"Failed to send update to {chat_id}: {e}")
    
    # Send results to admin
    result_text = (
        f"✅ <b>Update broadcast completed!</b>\n\n"
        f"📤 Yuborildi: <b>{successful_sends}</b>\n"
        f"❌ Yuborilmadi: <b>{failed_sends}</b>\n"
        f"👥 Jami foydalanuvchilar: <b>{len(all_users)}</b>"
    )
    
    await update.message.reply_text(result_text, parse_mode=ParseMode.HTML)

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
        "<b>🤖 Gemini yordam menyusi</b>\n\n"
        "🟢 <b>/start</b> — Botni qayta ishga tushirish\n"
        "🟢 <b>/help</b> — Yordam va buyruqlar roʻyxati\n"
        "🟢 <b>/search [so'z]</b> — Internetdan qidiruv (Google orqali)\n"
        "🟢 <b>/stats</b> — Statistika ko'rish\n\n"
        "💬 Oddiy xabar yuboring — men siz bilan suhbatlashaman!\n"
        "📷 Rasm yuboring — uni tahlil qilaman!\n"
        "🎙️ Ovoz yuboring — munosib va chiroyli javob beraman!\n"
        "📄 Hujjat yuboring — tahlil qilib xulosa beraman!\n\n"
        "🚀 Juda aqlli, samimiy va foydali yordamchi bo'lishga harakat qilaman!"
    )
    await update.message.reply_text(help_text, parse_mode=ParseMode.HTML, reply_markup=main_menu_keyboard())

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_typing(update)
    chat_id = str(update.effective_chat.id)
    message = update.message.text.strip()

    # Handle stats command
    if message.lower() == "/stats":
        await stats_command(update, context)
        return

    # Slash-based search
    if message.lower().startswith("/search"):
        parts = message.split(" ", 1)
        if len(parts) == 2:
            query = parts[1].strip()
            result = await search_web(query)
            await send_long_message(update, f"<b>🔎 Qidiruv natijasi:</b>\n{result}")
        else:
            await update.message.reply_text("❓ Qidiruv so'zini yozing. Masalan: <code>/search Ibn Sina</code>", parse_mode=ParseMode.HTML)
        return

    # Gemini chat with memory context
    history = user_history.setdefault(chat_id, [])
    history.append({"role": "user", "content": message})
    reply = await ask_gemini(history, chat_id)  # Pass chat_id for memory context
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
                "The user sent a photo. Analyze in detail and react like a friend who saw it and gives a warm, friendly and useful reply. No robotic descriptions. Use emojis and formatting awesomely. And always answer awesomely in uzbek language. if user asks in another language then answer in that language."
            ]},
            {"role": "user", "parts": [uploaded]}
        ])
        reply = response.text.strip()
        chat_id = str(update.effective_chat.id)
        
        # Store photo analysis in memory for future reference
        store_content_memory(chat_id, "photo", reply)
        
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
        
        # Store audio content in memory for future reference
        store_content_memory(chat_id, "audio", reply)
        
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
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("broadcast", broadcast_command))  # Admin broadcast
    app.add_handler(CommandHandler("update", send_update_broadcast))  # Quick update broadcast
    app.add_handler(CommandHandler("search", handle_text))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    logger.info("🤖 Gemini SmartBot is now LIVE and listening!")
    app.run_polling()


if __name__ == "__main__":
    main()
