import os
import re
import asyncio
import logging
import tempfile
import time
from datetime import datetime, timedelta
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
user_stats = {}  # Track detailed user statistics
user_info = {}  # Store user information (username, first_name, etc.)
MAX_HISTORY = 20
MAX_CONTENT_MEMORY = 50  # Store more content items
MAX_USERS_IN_MEMORY = 2000  # Limit to prevent memory overflow
MAX_INACTIVE_DAYS = 30  # Remove inactive users after 30 days

# ─── 📝 Logging ────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# ─── 👋 Welcome Message ────────────────────────────────────────
WELCOME = (
    "<b>👋 Assalomu alaykum va rohmatulloh va barokatuh!</b>\n"
    "Men <b>Gemini</b> 🤖 — Googlening aqqli modellaridan biriman!\n\n"
    "💬 Xabar yozing\n📷 Rasm yuboring\n🎙️ Ovozingizni yuboring\n"
    "📄 Hujjat yuboring\n🎬 Video yuboring\n"
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

# ─── 📊 User Statistics Tracking ─────────────────────────────────────────────────
def cleanup_inactive_users():
    """Remove inactive users to prevent memory overflow"""
    current_time = time.time()
    inactive_threshold = current_time - (MAX_INACTIVE_DAYS * 24 * 60 * 60)
    
    # Find inactive users
    inactive_users = []
    for chat_id, stats in user_stats.items():
        # Convert "now" to actual timestamp for comparison
        if stats.get("last_active") == "now":
            stats["last_active"] = current_time
        
        last_active = stats.get("last_active", 0)
        if isinstance(last_active, str):
            last_active = current_time  # Default to current time if string
        
        if last_active < inactive_threshold:
            inactive_users.append(chat_id)
    
    # Remove inactive users
    removed_count = 0
    for chat_id in inactive_users:
        if chat_id in user_history:
            del user_history[chat_id]
        if chat_id in user_content_memory:
            del user_content_memory[chat_id]
        if chat_id in user_stats:
            del user_stats[chat_id]
        if chat_id in user_info:
            del user_info[chat_id]
        removed_count += 1
    
    if removed_count > 0:
        logger.info(f"Cleaned up {removed_count} inactive users")
    
    return removed_count

def check_memory_limits():
    """Check and enforce memory limits"""
    total_users = len(user_history)
    
    if total_users > MAX_USERS_IN_MEMORY:
        logger.warning(f"User limit exceeded: {total_users}/{MAX_USERS_IN_MEMORY}")
        cleanup_count = cleanup_inactive_users()
        
        # If still over limit, remove oldest users
        if len(user_history) > MAX_USERS_IN_MEMORY:
            # Sort by last activity and remove oldest
            user_activity = []
            for chat_id, stats in user_stats.items():
                last_active = stats.get("last_active", 0)
                if isinstance(last_active, str):
                    last_active = 0
                user_activity.append((chat_id, last_active))
            
            user_activity.sort(key=lambda x: x[1])  # Sort by last_active (oldest first)
            
            # Remove oldest users until under limit
            to_remove = len(user_history) - MAX_USERS_IN_MEMORY + 100  # Remove extra for buffer
            for i in range(min(to_remove, len(user_activity))):
                chat_id = user_activity[i][0]
                if chat_id in user_history:
                    del user_history[chat_id]
                if chat_id in user_content_memory:
                    del user_content_memory[chat_id]
                if chat_id in user_stats:
                    del user_stats[chat_id]
                if chat_id in user_info:
                    del user_info[chat_id]
            
            logger.info(f"Removed {to_remove} oldest users to maintain memory limits")

def track_user_activity(chat_id: str, activity_type: str, update: Update = None):
    """Track user activity for statistics"""
    # Check memory limits before adding new users
    if chat_id not in user_stats:
        check_memory_limits()
    
    if chat_id not in user_stats:
        user_stats[chat_id] = {
            "messages": 0,
            "photos": 0,
            "voice_audio": 0,
            "documents": 0,
            "videos": 0,
            "first_interaction": time.time(),
            "last_active": time.time()
        }
    
    user_stats[chat_id][activity_type] += 1
    user_stats[chat_id]["last_active"] = time.time()
    
    # Store user information if available
    if update and update.effective_user:
        user = update.effective_user
        user_info[chat_id] = {
            "user_id": user.id,
            "username": user.username if user.username else None,
            "first_name": user.first_name if user.first_name else None,
            "last_name": user.last_name if user.last_name else None,
            "is_bot": user.is_bot if hasattr(user, 'is_bot') else False,
            "last_seen": time.time()
        }

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
        "📄 <b>Hujjat qabul qilindi!</b>\n\n"
        "⏳ <i>Tahlil qilinmoqda... Boshqa savollaringizni yuboring!</i>",
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
            # Upload to Gemini for analysis with timeout
            uploaded = await asyncio.wait_for(
                asyncio.to_thread(lambda: genai.upload_file(tmp_path)),
                timeout=30
            )
            response = await asyncio.wait_for(
                asyncio.to_thread(lambda: model.generate_content([
                    {"role": "user", "parts": [
                        "The user sent a document. Analyze the document and respond to the user awesomely with emojis and nice formatting. Be creative and answer educationally that user needs to get lessons from that document. Answer in Uzbek if the user speaks Uzbek. Otherwise use appropriate language."
                    ]},
                    {"role": "user", "parts": [uploaded]}
                ])),
                timeout=30
            )
            
            reply = response.text.strip() if response.text else "❌ Hujjatni tahlil qila olmadim."
            
            chat_id = str(update.effective_chat.id)
            
            # Track document activity
            track_user_activity(chat_id, "documents", update)
            
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

# ─── 🎬 Enhanced Video Analysis (Non-Blocking) ─────────────────────────────────────
async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle video uploads and analysis with non-blocking processing."""
    if not update.message or not update.message.video:
        return
        
    await send_typing(update)
    video = update.message.video
    chat_id = str(update.effective_chat.id)
    
    # Immediate response - don't block other users
    analyzing_msg = await update.message.reply_text(
        "🎬 <b>Video qabul qilindi!</b>\n\n"
        "⏳ <i>Tahlil qilinmoqda... Boshqa savollaringizni yuboring, men javob beraman!</i>\n\n"
        "📱 <i>Video tahlili tayyor bo'lganda yuboraman.</i>",
        parse_mode=ParseMode.HTML
    )
    
    # Process video in background - don't await it!
    asyncio.create_task(process_video_background(
        video, chat_id, analyzing_msg, update, context
    ))
    
    # Immediately track activity and return - don't block!
    track_user_activity(chat_id, "videos", update)

async def process_video_background(video, chat_id: str, analyzing_msg, update: Update, context):
    """Process video in background without blocking other users"""
    try:
        # Check file size (limit to 50MB for videos)
        if video.file_size and video.file_size > 50 * 1024 * 1024:
            await analyzing_msg.edit_text(
                "❌ Video juda katta. Maksimal hajm: 50MB",
                parse_mode=ParseMode.HTML
            )
            return
        
        # Check video duration (limit to 10 minutes)
        if video.duration and video.duration > 600:  # 10 minutes
            await analyzing_msg.edit_text(
                "❌ Video juda uzun. Maksimal davomiyligi: 10 daqiqa",
                parse_mode=ParseMode.HTML
            )
            return
        
        file = await context.bot.get_file(video.file_id)
        
        # Create temporary file with proper extension
        file_extension = ".mp4"  # Default to mp4
        if video.mime_type:
            if "webm" in video.mime_type:
                file_extension = ".webm"
            elif "mov" in video.mime_type:
                file_extension = ".mov"
            elif "avi" in video.mime_type:
                file_extension = ".avi"
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_extension) as tmp_file:
            tmp_path = tmp_file.name
        
        try:
            # Download file with timeout
            await asyncio.wait_for(
                file.download_to_drive(custom_path=tmp_path),
                timeout=60  # 1 minute timeout for download
            )
            
            # Wait a moment for file to be fully written
            await asyncio.sleep(0.5)
            
            # Check if file exists and has content
            if not os.path.exists(tmp_path) or os.path.getsize(tmp_path) == 0:
                raise Exception("Video file download failed or is empty")
            
            # Process with Gemini in separate thread
            def process_with_gemini():
                try:
                    # Upload to Gemini
                    uploaded = genai.upload_file(tmp_path)
                    
                    # Wait for processing
                    import time
                    time.sleep(3)  # Give Gemini time to process
                    
                    # Generate response
                    response = model.generate_content([
                        {"role": "user", "parts": [
                            "The user sent a video. Watch and analyze it like a close friend who's genuinely interested and excited to see what they shared! Give a warm, personal, and engaging response about what you see. Be conversational, use emojis, and react naturally like you're chatting with a good friend. Don't be robotic or give technical descriptions - just be genuine and friendly! Answer in Uzbek if the user speaks Uzbek, otherwise use appropriate language."
                        ]},
                        {"role": "user", "parts": [uploaded]}
                    ])
                    
                    return response.text.strip() if response and response.text else "🎬 Video juda qiziq edi! Lekin to'liq tahlil qila olmadim."
                except Exception as e:
                    logger.error(f"Gemini processing error: {e}")
                    return None
            
            # Run Gemini processing in thread pool with timeout
            try:
                reply = await asyncio.wait_for(
                    asyncio.to_thread(process_with_gemini),
                    timeout=45  # 45 second timeout
                )
            except asyncio.TimeoutError:
                reply = None
            
            if reply:
                # Store video analysis in memory for future reference
                video_duration = video.duration if video.duration else "unknown"
                video_summary = f"Video ({video_duration}s): {reply[:200]}..."
                store_content_memory(chat_id, "video", video_summary, f"video_{video.file_id[:8]}.mp4")
                
                user_history.setdefault(chat_id, []).append({"role": "user", "content": "[sent video 🎬]"})
                user_history[chat_id].append({"role": "model", "content": reply})
                
                # Update the analyzing message with results
                await analyzing_msg.edit_text(
                    f"🎬 <b>Video tahlil natijasi:</b>\n\n{reply}",
                    parse_mode=ParseMode.HTML
                )
            else:
                await analyzing_msg.edit_text(
                    "❌ Video tahlilida xatolik yuz berdi. Qaytadan urinib ko'ring.",
                    parse_mode=ParseMode.HTML
                )
        
        except asyncio.TimeoutError:
            logger.error("Video processing timeout")
            await analyzing_msg.edit_text(
                "⏰ Video tahlili juda uzoq davom etdi. Iltimos, qisqaroq video yuboring.",
                parse_mode=ParseMode.HTML
            )
        except Exception as processing_error:
            logger.error(f"Video processing error: {processing_error}")
            
            # Provide specific error messages
            error_msg = "❌ Video tahlilida xatolik:"
            if "quota" in str(processing_error).lower():
                error_msg += "\n📊 API chekloviga yetdik. Biroz kuting va qaytadan urinib ko'ring."
            elif "format" in str(processing_error).lower() or "codec" in str(processing_error).lower():
                error_msg += "\n🎬 Video formati qo'llab-quvvatlanmaydi. MP4, WebM yoki MOV formatida yuboring."
            elif "size" in str(processing_error).lower():
                error_msg += "\n📏 Video juda katta. 50MB dan kichik video yuboring."
            else:
                error_msg += "\n🔄 Qaytadan urinib ko'ring yoki boshqa video yuboring."
            
            await analyzing_msg.edit_text(error_msg, parse_mode=ParseMode.HTML)
        
        finally:
            # Always clean up temp file
            try:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
            except Exception as cleanup_error:
                logger.warning(f"Failed to cleanup temp file: {cleanup_error}")
            
    except Exception as e:
        logger.error(f"Video handler error: {e}")
        try:
            await analyzing_msg.edit_text(
                "❌ Video yuklashda xatolik yuz berdi. Iltimos qaytadan urinib ko'ring.",
                parse_mode=ParseMode.HTML
            )
        except:
            pass

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
        "📷 Rasmlarni chuqurroq tahlil qilish\n"
        "🎬 <b>YANGI!</b> Video tahlili - videolaringizni ko'rib tushunadi!\n\n"
        "<b>🔥 Eng asosiysi:</b>\n"
        "<i>Bot endi yuborgan hujjat, audio va rasmlaringizni eslab qoladi va keyinroq ularga murojaat qila oladi!</i>\n\n"
        "💬 Botga savolingizni bering va yangi imkoniyatlarni sinab ko'ring!\n\n"
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

# ─── 📊 Admin Statistics Command ─────────────────────────────────
async def admin_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show comprehensive bot statistics (admin only)."""
    if not update.message or not update.effective_chat:
        return
    
    # Check if user is admin
    admin_ids = ["7050582441"]  # Replace with your actual Telegram ID
    user_id = str(update.effective_user.id)
    
    if user_id not in admin_ids:
        await update.message.reply_text("❌ Bu buyruq faqat admin uchun!")
        return
    
    # Calculate comprehensive statistics
    total_users = len(user_history)
    total_messages = sum(len(history) for history in user_history.values())
    
    # Count media types from user_stats
    total_photos = sum(stats.get("photos", 0) for stats in user_stats.values())
    total_voice_audio = sum(stats.get("voice_audio", 0) for stats in user_stats.values())
    total_documents = sum(stats.get("documents", 0) for stats in user_stats.values())
    total_videos = sum(stats.get("videos", 0) for stats in user_stats.values())
    
    # Count content memories
    total_content_memories = sum(len(memories) for memories in user_content_memory.values())
    
    # Memory usage estimation
    estimated_memory_mb = (
        (total_users * 5) +  # ~5KB per user for basic data
        (total_messages * 0.5) +  # ~0.5KB per message
        (total_content_memories * 2)  # ~2KB per content memory
    ) / 1024  # Convert to MB
    
    memory_status = "🟢 Good" if estimated_memory_mb < 100 else "🟡 Warning" if estimated_memory_mb < 200 else "🔴 Critical"
    
    # Most active users (top 10)
    user_activity = []
    for chat_id, history in user_history.items():
        user_messages = len([m for m in history if m["role"] == "user"])
        if user_messages > 0:
            # Get user info if available
            user_data = user_info.get(chat_id, {})
            username = user_data.get("username")
            first_name = user_data.get("first_name")
            last_name = user_data.get("last_name")
            
            # Build display name
            display_name = f"ID: {chat_id}"
            if username:
                display_name += f" (@{username})"
            if first_name:
                display_name += f" - {first_name}"
                if last_name:
                    display_name += f" {last_name}"
            
            user_activity.append((chat_id, user_messages, display_name))
    
    user_activity.sort(key=lambda x: x[1], reverse=True)
    top_users = user_activity[:10]  # Top 10 users
    
    # Calculate average messages per user
    avg_messages = total_messages / total_users if total_users > 0 else 0
    
    # Build comprehensive statistics message
    stats_text = (
        f"<b>🤖 COMPREHENSIVE BOT STATISTICS</b>\n\n"
        f"👥 <b>User Analytics:</b>\n"
        f"Total Users: <b>{total_users}</b> / {MAX_USERS_IN_MEMORY}\n"
        f"Total Messages: <b>{total_messages}</b>\n"
        f"Average Messages/User: <b>{avg_messages:.1f}</b>\n\n"
        f"<b>📁 Media Statistics:</b>\n"
        f"📷 Photos Analyzed: <b>{total_photos}</b>\n"
        f"🎙️ Voice/Audio: <b>{total_voice_audio}</b>\n"
        f"📄 Documents Processed: <b>{total_documents}</b>\n"
        f"🎬 Videos Analyzed: <b>{total_videos}</b>\n"
        f"Total Media Files: <b>{total_photos + total_voice_audio + total_documents + total_videos}</b>\n\n"
        f"🧠 <b>Memory System:</b>\n"
        f"Content Memories Stored: <b>{total_content_memories}</b>\n"
        f"Active User Sessions: <b>{len(user_history)}</b>\n"
        f"Estimated Memory Usage: <b>{estimated_memory_mb:.1f} MB</b>\n"
        f"Memory Status: {memory_status}\n\n"
    )
    
    if top_users:
        stats_text += "<b>🏆 TOP 10 MOST ACTIVE USERS:</b>\n"
        for i, (chat_id, msg_count, display_name) in enumerate(top_users, 1):
            # Limit display name length for readability
            if len(display_name) > 60:
                display_name = display_name[:57] + "..."
            stats_text += f"{i}. {display_name}: <b>{msg_count}</b> msgs\n"
        
        # Add user breakdown by activity level
        stats_text += "\n<b>📈 User Activity Breakdown:</b>\n"
        highly_active = len([u for u in user_activity if u[1] >= 20])
        moderately_active = len([u for u in user_activity if 5 <= u[1] < 20])
        low_active = len([u for u in user_activity if 1 <= u[1] < 5])
        
        stats_text += f"Highly Active (20+ msgs): <b>{highly_active}</b>\n"
        stats_text += f"Moderately Active (5-19 msgs): <b>{moderately_active}</b>\n"
        stats_text += f"Low Activity (1-4 msgs): <b>{low_active}</b>\n"
    
    stats_text += "\n<i>🔥 Bot is running smoothly! All systems operational.</i>"
    
    # Send stats in chunks if too long
    if len(stats_text) > 4096:
        # Split into chunks
        chunks = []
        current_chunk = ""
        
        for line in stats_text.split("\n"):
            if len(current_chunk + line + "\n") > 4000:
                chunks.append(current_chunk)
                current_chunk = line + "\n"
            else:
                current_chunk += line + "\n"
        
        if current_chunk:
            chunks.append(current_chunk)
        
        # Send each chunk
        for i, chunk in enumerate(chunks):
            if i == 0:
                await update.message.reply_text(chunk, parse_mode=ParseMode.HTML)
            else:
                await asyncio.sleep(0.1)  # Small delay between messages
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=chunk,
                    parse_mode=ParseMode.HTML
                )
    else:
        await update.message.reply_text(stats_text, parse_mode=ParseMode.HTML)

# ─── 🛠️ System Monitoring Command ─────────────────────────────────────
async def system_monitor_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Monitor system health and performance (admin only)."""
    if not update.message or not update.effective_chat:
        return
    
    # Check if user is admin
    admin_ids = ["7050582441"]  # Replace with your actual Telegram ID
    user_id = str(update.effective_user.id)
    
    if user_id not in admin_ids:
        await update.message.reply_text("❌ Bu buyruq faqat admin uchun!")
        return
    
    # Perform cleanup and get metrics
    cleaned_users = cleanup_inactive_users()
    
    total_users = len(user_history)
    memory_usage = (
        (total_users * 5) +
        (sum(len(history) for history in user_history.values()) * 0.5) +
        (sum(len(memories) for memories in user_content_memory.values()) * 2)
    ) / 1024
    
    # Check if approaching limits
    user_limit_percent = (total_users / MAX_USERS_IN_MEMORY) * 100
    
    # Determine system status
    if user_limit_percent > 90 or memory_usage > 200:
        status = "🔴 CRITICAL"
        status_msg = "Immediate action required!"
    elif user_limit_percent > 70 or memory_usage > 100:
        status = "🟡 WARNING"
        status_msg = "Monitor closely"
    else:
        status = "🟢 HEALTHY"
        status_msg = "All systems normal"
    
    monitor_text = (
        f"<b>🛠️ SYSTEM HEALTH MONITOR</b>\n\n"
        f"<b>System Status:</b> {status}\n"
        f"<i>{status_msg}</i>\n\n"
        f"<b>📊 Resource Usage:</b>\n"
        f"Users: <b>{total_users}</b> / {MAX_USERS_IN_MEMORY} ({user_limit_percent:.1f}%)\n"
        f"Memory: <b>{memory_usage:.1f} MB</b>\n\n"
        f"<b>🧼 Maintenance:</b>\n"
        f"Inactive users cleaned: <b>{cleaned_users}</b>\n"
        f"Cleanup threshold: <b>{MAX_INACTIVE_DAYS} days</b>\n\n"
        f"<b>📍 Recommendations:</b>\n"
    )
    
    # Add recommendations based on status
    if user_limit_percent > 90:
        monitor_text += "⚠️ Consider reducing MAX_USERS_IN_MEMORY\n"
    if memory_usage > 150:
        monitor_text += "⚠️ Consider implementing database storage\n"
    if cleaned_users == 0 and total_users > 1000:
        monitor_text += "⚠️ Consider reducing MAX_INACTIVE_DAYS\n"
    
    if user_limit_percent < 50 and memory_usage < 50:
        monitor_text += "✅ System running optimally\n"
    
    monitor_text += "\n<i>🔄 Auto-cleanup runs on each new user</i>"
    
    await update.message.reply_text(monitor_text, parse_mode=ParseMode.HTML)

# ─── 📌 Handlers ───────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    user_history[chat_id] = []
    
    # Track user info when they start
    if update.effective_user:
        user = update.effective_user
        user_info[chat_id] = {
            "user_id": user.id,
            "username": user.username if user.username else None,
            "first_name": user.first_name if user.first_name else None,
            "last_name": user.last_name if user.last_name else None,
            "is_bot": user.is_bot if hasattr(user, 'is_bot') else False
        }
    
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
        "📄 Hujjat yuboring — tahlil qilib xulosa beraman!\n"
        "🎬 Video yuboring — ko'rib tahlil qilaman!\n\n"
        "🚀 Juda aqlli, samimiy va foydali yordamchi bo'lishga harakat qilaman!"
    )
    
    # Check if user is admin and add admin commands to help
    admin_ids = ["7050582441"]  # Replace with your actual Telegram ID
    user_id = str(update.effective_user.id)
    
    if user_id in admin_ids:
        help_text += (
            "\n\n<b>🔧 Admin Commands:</b>\n"
            "🟢 <b>/broadcast [message]</b> — Send message to all users\n"
            "🟢 <b>/update</b> — Send update notification to all users\n"
            "🟢 <b>/adminstats</b> — View comprehensive bot statistics\n"
            "🟢 <b>/monitor</b> — System health and performance monitoring"
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
    
    # Track user activity
    track_user_activity(chat_id, "messages", update)
    
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
        uploaded = await asyncio.wait_for(
            asyncio.to_thread(lambda: genai.upload_file(tmp_path)),
            timeout=20
        )
        response = await asyncio.wait_for(
            asyncio.to_thread(lambda: model.generate_content([
                {"role": "user", "parts": [
                    "The user sent a photo. Analyze in detail and react like a friend who saw it and gives a warm, friendly and useful reply. No robotic descriptions. Use emojis and formatting awesomely. And always answer awesomely in uzbek language. if user asks in another language then answer in that language."
                ]},
                {"role": "user", "parts": [uploaded]}
            ])),
            timeout=20
        )
        reply = response.text.strip()
        chat_id = str(update.effective_chat.id)
        
        # Track photo activity
        track_user_activity(chat_id, "photos", update)
        
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
        uploaded = await asyncio.wait_for(
            asyncio.to_thread(lambda: genai.upload_file(tmp_path)),
            timeout=20
        )
        response = await asyncio.wait_for(
            asyncio.to_thread(lambda: model.generate_content([
                {"role": "user", "parts": [
                    "The user sent a voice message. Understand and reply like you're talking back — not transcribing. Just continue the conversation warmly. Use Emojis + <i>/<b>/<u> formatting awesomely."
                ]},
                {"role": "user", "parts": [uploaded]}
            ])),
            timeout=20
        )
        reply = response.text.strip()
        chat_id = str(update.effective_chat.id)
        
        # Track voice/audio activity
        track_user_activity(chat_id, "voice_audio", update)
        
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
    app.add_handler(CommandHandler("adminstats", admin_stats_command))  # Admin statistics
    app.add_handler(CommandHandler("monitor", system_monitor_command))  # System monitoring
    app.add_handler(CommandHandler("search", handle_text))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.VIDEO, handle_video))  # Video handler
    logger.info("🤖 Gemini SmartBot is now LIVE and listening!") 
    logger.info("🎬 Video processing: Non-blocking with timeouts enabled")
    logger.info("🚀 Bot optimized for concurrent users")
    app.run_polling()


if __name__ == "__main__":
    main()
