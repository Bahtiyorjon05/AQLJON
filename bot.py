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
from telegram.error import NetworkError, TelegramError, TimedOut, RetryAfter
import google.generativeai as genai
import httpx
from telegram import ReplyKeyboardMarkup, KeyboardButton


# ─── 🔐 Load Environment Variables ─────────────────────────────
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
SERPER_KEY = os.getenv("SERPER_API_KEY")
ADMIN_ID = os.getenv("ADMIN_ID")

# ─── 🤖 Gemini Setup ───────────────────────────────────────────
genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel("gemini-2.5-flash")

# ─── 🧠 Enhanced Memory ─────────────────────────────────────────────────
user_history = {}
user_content_memory = {}  # Store document/audio content for later reference
user_stats = {}  # Track detailed user statistics
user_info = {}  # Store user information (username, first_name, etc.)
user_contact_messages = {}  # Store contact messages from users to admin
user_daily_activity = {}  # Track daily activity for analytics
MAX_HISTORY = 100
MAX_CONTENT_MEMORY = 50  # Store more content items
MAX_USERS_IN_MEMORY = 2000  # Limit to prevent memory overflow
MAX_INACTIVE_DAYS = 30  # Remove inactive users after 30 days
ADMIN_CHAT_ID = ADMIN_ID  # Admin's Telegram ID from env

# ─── 📝 Logging ────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# ─── 👋 Welcome Message ────────────────────────────────────────
WELCOME = (
    "<b>👋 Assalomu alaykum va rohmatulloh va barokatuh!</b>\n"
    "Men <b>AQLJON</b> ✨ — sizning doimiy hamrohingizman!\n\n"
    "💬 Xabar yozing\n📷 Rasm yuboring\n🎙️ Ovozingizni yuboring\n"
    "📄 Hujjat yuboring\n🎬 Video yuboring\n"
    "🔍 <code>/search</code> orqali internetdan ma'lumot oling\n"
    "📊 <code>/stats</code> — Statistikani ko'ring\n"
    "📞 <code>/contact</code> — Admin bilan bog'laning\n"
    "ℹ️ <code>/help</code> — Yordam oling\n\n"
    "Do'stona, samimiy va foydali suhbat uchun shu yerdaman! 🚀"
)

# ─── 📋 Main Menu Keyboard ────────────────────────────────────
def main_menu_keyboard():
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("🔄 Qayta ishga tushirish"), KeyboardButton("ℹ️ Yordam")],
            [KeyboardButton("🔍 Qidiruv"), KeyboardButton("📊 Statistika")],
            [KeyboardButton("📞 Kontakt")]
        ],
        resize_keyboard=True, one_time_keyboard=True,
    )


# ─── 🛡️ Safe Communication Functions ──────────────────────────────────────
async def safe_reply(update: Update, text: str, parse_mode=ParseMode.HTML, max_retries=3):
    """Safely send reply with automatic retry and fallback"""
    if not update or not update.message:
        return False
    for attempt in range(max_retries):
        try:
            await update.message.reply_text(text, parse_mode=parse_mode)
            return True
        except RetryAfter as e:
            wait_time = e.retry_after + 1
            logger.warning(f"Rate limited, waiting {wait_time} seconds (attempt {attempt + 1})")
            await asyncio.sleep(wait_time)
        except (NetworkError, TelegramError, TimedOut) as e:
            logger.warning(f"Telegram error on attempt {attempt + 1}: {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)  # Exponential backoff

            else:
                # Final attempt with plain text
                try:
                    await update.message.reply_text(text)
                    return True
                except Exception:
                    logger.error("All retry attempts failed")
                    return False
        except Exception as e:
            logger.error(f"Unexpected error in safe_reply: {e}")
            return False
    return False

async def safe_edit_message(message, text: str, parse_mode=ParseMode.HTML, max_retries=3):
    """Safely edit message with automatic retry"""
    for attempt in range(max_retries):
        try:
            await message.edit_text(text, parse_mode=parse_mode)
            return True
        except RetryAfter as e:
            wait_time = e.retry_after + 1
            logger.warning(f"Rate limited on edit, waiting {wait_time} seconds")
            await asyncio.sleep(wait_time)
        except (NetworkError, TelegramError, TimedOut) as e:
            logger.warning(f"Telegram error on edit attempt {attempt + 1}: {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)
        except Exception as e:
            logger.error(f"Error editing message: {e}")
            return False
    return False

# ─── 📦 Utilities ──────────────────────────────────────────────
async def send_typing(update: Update):
    if not update or not update.message or not update.message.chat:
        return
    try:
        await update.message.chat.send_action(action=ChatAction.TYPING)
    except (NetworkError, TelegramError, TimedOut) as e:
        logger.warning(f"Failed to send typing indicator: {e}")
    except Exception as e:
        logger.error(f"Unexpected error in send_typing: {e}")

def clean_html(text: str) -> str:
    return re.sub(r'</?(ul|li|div|span|h\d|blockquote|table|tr|td|th)[^>]*>', '', text)

async def send_long_message(update: Update, text: str):
    if not update or not update.message:
        return
    text = clean_html(text)
    for i in range(0, len(text), 4096):
        try:
            await update.message.reply_text(text[i:i+4096], parse_mode=ParseMode.HTML)
            await asyncio.sleep(0.3)  # Increased delay to prevent rate limiting
        except RetryAfter as e:
            logger.warning(f"Rate limited, waiting {e.retry_after} seconds")
            await asyncio.sleep(e.retry_after + 1)
            try:
                await update.message.reply_text(text[i:i+4096], parse_mode=ParseMode.HTML)
            except Exception:
                await update.message.reply_text(text[i:i+4096])  # Fallback to plain text
        except (NetworkError, TelegramError, TimedOut) as e:
            logger.error(f"Failed to send message chunk: {e}")
            try:
                # Fallback: send as plain text
                await update.message.reply_text(text[i:i+4096])
                await asyncio.sleep(0.3)
            except Exception as fallback_error:
                logger.error(f"Fallback message also failed: {fallback_error}")
                break
        except Exception as e:
            logger.error(f"Unexpected error in send_long_message: {e}")
            break

# ─── 🔍 Search Integration ─────────────────────────────────────
async def search_web(query: str) -> str:
    try:
        # Check if SERPER_KEY is available
        if not SERPER_KEY:
            return "❌ Qidiruv xizmati sozlanmagan."
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://google.serper.dev/search",
                headers={"X-API-KEY": str(SERPER_KEY), "Content-Type": "application/json"},
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

def track_user_activity(chat_id: str, activity_type: str, update: Update | None = None):
    """Track user activity for statistics with daily analytics"""
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
            "search_queries": 0,
            "first_interaction": time.time(),
            "last_active": time.time(),
            "total_characters": 0
        }
    
    user_stats[chat_id][activity_type] += 1
    user_stats[chat_id]["last_active"] = time.time()
    
    # Track daily activity for analytics
    today = datetime.now().strftime("%Y-%m-%d")
    if chat_id not in user_daily_activity:
        user_daily_activity[chat_id] = {}
    
    if today not in user_daily_activity[chat_id]:
        user_daily_activity[chat_id][today] = {
            "messages": 0,
            "photos": 0,
            "voice_audio": 0,
            "documents": 0,
            "videos": 0,
            "search_queries": 0
        }
    
    user_daily_activity[chat_id][today][activity_type] += 1
    
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
def store_content_memory(chat_id: str, content_type: str, content_summary: str, file_name: str | None = None):
    """Store document/audio content for future reference"""
    if chat_id not in user_content_memory:
        user_content_memory[chat_id] = []
    
    memory_item = {
        "type": content_type,
        "summary": content_summary,
        "file_name": file_name if file_name else "unknown",
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
async def ask_gemini(history, chat_id: str | None = None, max_retries=3):
    for attempt in range(max_retries):
        try:
            messages = [{"role": msg["role"], "parts": [msg["content"]]} for msg in history[-10:]]
            
            # Add content memory context if available
            content_context = get_content_context(chat_id) if chat_id else ""
            
            base_instruction = (
                "You are a smart friend. Remember your name is AQLJON . Don't repeat what the user said. Reply casually with humor and warmth 😊. "
                "Awesomely answer with formatting <b>, <i>, <u> and emojis 🧠. Be warm, creative, helpful, friendly! Answer in Uzbek if the user speaks Uzbek. Otherwise use appropriate language."
            )
            
            # Add content context to instruction if available
            full_instruction = base_instruction + content_context
            
            messages.insert(0, {
                "role": "user", "parts": [full_instruction]
            })
            
            # Generate with timeout and retry logic
            response = await asyncio.wait_for(
                asyncio.to_thread(lambda: model.generate_content(messages)),
                timeout=45  # Increased timeout
            )
            return response.text.strip() if response and response.text else ""
            
        except asyncio.TimeoutError:
            logger.warning(f"Gemini timeout on attempt {attempt + 1}")
            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
            else:
                return "<i>⏰ Javob berish juda uzoq davom etdi. Qaytadan urinib ko'ring.</i>"
                
        except Exception as e:
            logger.error(f"Gemini error on attempt {attempt + 1}: {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)
            else:
                # Provide specific error messages
                if "quota" in str(e).lower() or "rate" in str(e).lower():
                    return "<i>📈 API chekloviga yetdik. Biroz kutib, qaytadan urinib ko'ring.</i>"
                elif "network" in str(e).lower() or "connection" in str(e).lower():
                    return "<i>🌐 Tarmoq bilan bog'lanishda muammo. Qaytadan urinib ko'ring.</i>"
                else:
                    return "<i>⚠️ Gemini hozircha javob bera olmadi. Qaytadan urinib ko'ring.</i>"

# ─── 📄 Enhanced Document Analysis ─────────────────────────────────────
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle document uploads and analysis with non-blocking processing."""
    if not update or not update.message or not update.message.document:
        return
        
    await send_typing(update)
    document: Document = update.message.document
    chat_id = str(update.effective_chat.id) if update and update.effective_chat else "unknown"
    
    # Immediate response - don't block other users
    analyzing_msg = await update.message.reply_text(
        "📄 <b>Hujjat qabul qilindi!</b>\n\n"
        "⏳ <i>Tahlil qilinmoqda... Boshqa savollaringizni yuboring, men javob beraman!</i>\n\n"
        "📱 <i>Hujjat tahlili tayyor bo'lganda yuboraman.</i>",
        parse_mode=ParseMode.HTML
    )
    
    # Process document in background - don't await it!
    asyncio.create_task(process_document_background(
        document, chat_id, analyzing_msg, update, context
    ))
    
    # Immediately track activity and return - don't block!
    track_user_activity(chat_id, "documents", update)

async def process_document_background(document: Document, chat_id: str, analyzing_msg, update: Update, context):
    """Process document in background without blocking other users"""
    try:
        # Check file size (limit to 20MB)
        if document.file_size and document.file_size > 20 * 1024 * 1024:
            await analyzing_msg.edit_text(
                "❌ Fayl juda katta. Maksimal hajm: 20MB",
                parse_mode=ParseMode.HTML
            )
            return
        
        file = await context.bot.get_file(document.file_id)
        
        # Create temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{document.file_name}") as tmp_file:
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
                raise Exception("Document file download failed or is empty")
            
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
                            "The user sent a document. Analyze the document and respond to the user awesomely with emojis and nice formatting. Be creative, friendly and helpful and answer educationally that user needs to get lessons from that document. Answer in Uzbek if the user speaks Uzbek. Otherwise use appropriate language."
                        ]},
                        {"role": "user", "parts": [uploaded]}
                    ])
                    
                    return response.text.strip() if response and response.text else "❌ Hujjatni tahlil qila olmadim."
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
                # Store document content in memory for future reference
                store_content_memory(chat_id, "document", reply, document.file_name if document.file_name else "unknown")
                
                user_history.setdefault(chat_id, []).append({"role": "user", "content": f"[uploaded document: {document.file_name if document.file_name else 'unknown'}]"})
                user_history[chat_id].append({"role": "model", "content": reply})
                
                # Update the analyzing message with results
                await analyzing_msg.edit_text(
                    f"📄 <b>Hujjat tahlil natijasi:</b>\n\n{reply}",
                    parse_mode=ParseMode.HTML
                )
            else:
                await analyzing_msg.edit_text(
                    "❌ Hujjat tahlilida xatolik yuz berdi. Qaytadan urinib ko'ring.",
                    parse_mode=ParseMode.HTML
                )
        
        except asyncio.TimeoutError:
            logger.error("Document processing timeout")
            await analyzing_msg.edit_text(
                "⏰ Hujjat tahlili juda uzoq davom etdi. Iltimos, kichikroq hujjat yuboring.",
                parse_mode=ParseMode.HTML
            )
        except Exception as processing_error:
            logger.error(f"Document processing error: {processing_error}")
            
            # Provide specific error messages
            error_msg = "❌ Hujjat tahlilida xatolik:"
            if "quota" in str(processing_error).lower():
                error_msg += "\n📊 API chekloviga yetdik. Biroz kuting va qaytadan urinib ko'ring."
            elif "format" in str(processing_error).lower():
                error_msg += "\n📄 Hujjat formati qo'llab-quvvatlanmaydi."
            elif "size" in str(processing_error).lower():
                error_msg += "\n📏 Hujjat juda katta. 20MB dan kichik hujjat yuboring."
            else:
                error_msg += "\n🔄 Qaytadan urinib ko'ring yoki boshqa hujjat yuboring."
            
            await analyzing_msg.edit_text(error_msg, parse_mode=ParseMode.HTML)
        
        finally:
            # Always clean up temp file
            try:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
            except Exception as cleanup_error:
                logger.warning(f"Failed to cleanup temp file: {cleanup_error}")
            
    except Exception as e:
        logger.error(f"Document handler error: {e}")
        try:
            await analyzing_msg.edit_text(
                "❌ Hujjat yuklashda xatolik yuz berdi. Iltimos qaytadan urinib ko'ring.",
                parse_mode=ParseMode.HTML
            )
        except:
            pass

# ─── 🎬 Enhanced Video Analysis (Non-Blocking) ─────────────────────────────────────
async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle video uploads and analysis with non-blocking processing."""
    if not update or not update.message or not update.message.video:
        return
        
    await send_typing(update)
    video = update.message.video
    chat_id = str(update.effective_chat.id) if update and update.effective_chat else "unknown"
    
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
                            "The user sent a video. Watch and analyze it like a close friend who's genuinely interested and excited to see what they shared! Give a warm, personal, and engaging response about what you see. Be creative, friendly, helpful, use emojis, and react naturally like you're chatting with a good friend. Don't be robotic or give technical descriptions - just be genuine and friendly! Answer in Uzbek if the user speaks Uzbek, otherwise use appropriate language."
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

# ─── 📊 Enhanced Stats Commands ─────────────────────────────────────────
# Keep the statistics functionality from previous.py
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user statistics"""
    if not update.message or not update.effective_chat:
        return
        
    chat_id = str(update.effective_chat.id)
    history = user_history.get(chat_id, [])
    user_stats_data = user_stats.get(chat_id, {})
    user_data = user_info.get(chat_id, {})
    
    total_messages = len(history)
    user_messages = len([m for m in history if m["role"] == "user"])
    bot_messages = len([m for m in history if m["role"] == "model"])
    
    photos_sent = user_stats_data.get("photos", 0)
    voice_audio_sent = user_stats_data.get("voice_audio", 0)
    documents_sent = user_stats_data.get("documents", 0)
    videos_sent = user_stats_data.get("videos", 0)
    search_queries = user_stats_data.get("search_queries", 0)
    total_characters = user_stats_data.get("total_characters", 0)
    
    content_memories = len(user_content_memory.get(chat_id, []))
    
    # First interaction and last active
    first_interaction = user_stats_data.get("first_interaction", time.time())
    last_active = user_stats_data.get("last_active", time.time())
    
    first_date = datetime.fromtimestamp(first_interaction).strftime("%Y-%m-%d %H:%M")
    last_date = datetime.fromtimestamp(last_active).strftime("%Y-%m-%d %H:%M")
    
    # Calculate days since first interaction
    days_active = max(1, int((time.time() - first_interaction) / (24 * 60 * 60)))
    avg_messages_per_day = user_messages / days_active
    
    if user_messages >= 50:
        activity_level = "🔥 Juda faol"
    elif user_messages >= 20:
        activity_level = "⚡ Faol"
    elif user_messages >= 5:
        activity_level = "💪 O'rtacha faol"
    else:
        activity_level = "🌱 Yangi foydalanuvchi"
    
    # User profile info
    username = user_data.get("username", "Yo'q")
    first_name = user_data.get("first_name", "Noma'lum")
    last_name = user_data.get("last_name", "")
    full_name = f"{first_name} {last_name}".strip()
    user_id = user_data.get("user_id", "Noma'lum")
    
    stats_text = (
        f"📊 <b>Sizning to'liq statistikangiz</b>\n\n"
        f"👤 <b>Profil ma'lumotlari:</b>\n"
        f"📝 Ism: <b>{full_name}</b>\n"
        f"🏷️ Username: <b>@{username}</b>\n"
        f"🆔 User ID: <code>{user_id}</code>\n"
        f"🆔 Chat ID: <code>{chat_id}</code>\n\n"
        f"📈 <b>Faollik darajasi:</b> {activity_level}\n\n"
        f"💬 <b>Xabarlar statistikasi:</b>\n"
        f"📝 Sizning xabarlaringiz: <b>{user_messages}</b>\n"
        f"🤖 Bot javobi: <b>{bot_messages}</b>\n"
        f"📊 Jami xabarlar: <b>{total_messages}</b>\n"
        f"📝 Jami belgilar: <b>{total_characters:,}</b>\n"
        f"📅 Kunlik o'rtacha: <b>{avg_messages_per_day:.1f}</b> xabar\n\n"
        f"🎨 <b>Media fayllar:</b>\n"
        f"📷 Rasmlar: <b>{photos_sent}</b>\n"
        f"🎤 Audio/Ovoz: <b>{voice_audio_sent}</b>\n"
        f"📄 Hujjatlar: <b>{documents_sent}</b>\n"
        f"🎥 Videolar: <b>{videos_sent}</b>\n"
        f"🔍 Qidiruv so'rovlari: <b>{search_queries}</b>\n\n"
        f"🕰️ <b>Vaqt ma'lumotlari:</b>\n"
        f"🎆 Birinchi kirish: <b>{first_date}</b>\n"
        f"⏰ Oxirgi faollik: <b>{last_date}</b>\n"
        f"📅 Faol kunlar: <b>{days_active}</b>\n\n"
        f"🧠 <b>Xotira tizimi:</b>\n"
        f"💾 Saqlangan kontentlar: <b>{content_memories}</b>\n"
        f"📝 Xotira chegarasi: <b>{MAX_CONTENT_MEMORY}</b> ta\n"
        f"🔄 Suhbat tarixi: <b>{len(history)}</b>/{MAX_HISTORY * 2} ta\n\n"
        f"<i>🙏 AQLJON siz uchun hamisha shu yerda!</i>"
    )
    
    await send_long_message(update, stats_text)

def get_user_activity_period(chat_id: str, days: int) -> dict:
    """Get user activity for the last N days"""
    activity = {
        "messages": 0,
        "photos": 0,
        "voice_audio": 0,
        "documents": 0,
        "videos": 0,
        "search_queries": 0
    }
    
    if chat_id not in user_daily_activity:
        return activity
    
    # Calculate date range
    today = datetime.now()
    for i in range(days):
        check_date = (today - timedelta(days=i)).strftime("%Y-%m-%d")
        if check_date in user_daily_activity[chat_id]:
            day_activity = user_daily_activity[chat_id][check_date]
            for key in activity.keys():
                activity[key] += day_activity.get(key, 0)
    
    return activity

# ─── 👑 Admin Commands ─────────────────────────────────────────────────
# Keep the admin statistics functionality from previous.py
async def admin_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show detailed admin statistics (admin only)"""
    if not update or not update.message or not update.effective_chat or not update.effective_user:
        return
    
    user_id = str(update.effective_user.id)
    admin_ids = [ADMIN_ID.strip()] if ADMIN_ID and ADMIN_ID.strip() else []
    
    if user_id not in admin_ids:
        # Hide admin command from non-admin users - no response
        return
    
    # Calculate comprehensive statistics
    total_users = len(user_history)
    total_messages = sum(len(history) for history in user_history.values())
    total_user_messages = sum(len([m for m in history if m["role"] == "user"]) for history in user_history.values())
    avg_messages = total_user_messages / total_users if total_users > 0 else 0
    
    # Media statistics
    total_photos = sum(stats.get("photos", 0) for stats in user_stats.values())
    total_voice = sum(stats.get("voice_audio", 0) for stats in user_stats.values())
    total_documents = sum(stats.get("documents", 0) for stats in user_stats.values())
    total_videos = sum(stats.get("videos", 0) for stats in user_stats.values())
    total_searches = sum(stats.get("search_queries", 0) for stats in user_stats.values())
    
    # Activity categorization
    highly_active = sum(1 for history in user_history.values() if len([m for m in history if m["role"] == "user"]) >= 20)
    moderately_active = sum(1 for history in user_history.values() if 5 <= len([m for m in history if m["role"] == "user"]) < 20)
    low_activity = sum(1 for history in user_history.values() if 1 <= len([m for m in history if m["role"] == "user"]) < 5)
    
    # Memory system status
    total_content_memories = sum(len(memories) for memories in user_content_memory.values())
    
    # Top 20 users by message count
    user_message_counts = []
    for chat_id, history in user_history.items():
        user_messages = len([m for m in history if m["role"] == "user"])
        if user_messages > 0:
            user_data = user_info.get(chat_id, {})
            username = user_data.get("username", "Unknown")
            first_name = user_data.get("first_name", "Unknown")
            last_name = user_data.get("last_name", "")
            full_name = f"{first_name} {last_name}".strip() or "Unknown"
            
            user_message_counts.append({
                "chat_id": chat_id,
                "user_id": user_data.get("user_id", "Unknown"),
                "username": username,
                "full_name": full_name,
                "messages": user_messages
            })
    
    user_message_counts.sort(key=lambda x: x["messages"], reverse=True)
    top_20_users = user_message_counts[:20]
    
    admin_stats_text = (
        f"👑 <b>ADMIN STATISTICS DASHBOARD</b>\n\n"
        f"📊 <b>Overall Statistics:</b>\n"
        f"👥 Total Users: <b>{total_users}</b>\n"
        f"💬 Total Messages: <b>{total_messages}</b>\n"
        f"📝 User Messages: <b>{total_user_messages}</b>\n"
        f"📈 Avg Messages/User: <b>{avg_messages:.1f}</b>\n\n"
        f"🎨 <b>Media Breakdown:</b>\n"
        f"📷 Photos: <b>{total_photos}</b>\n"
        f"🎤 Voice/Audio: <b>{total_voice}</b>\n"
        f"📄 Documents: <b>{total_documents}</b>\n"
        f"🎥 Videos: <b>{total_videos}</b>\n"
        f"🔍 Searches: <b>{total_searches}</b>\n\n"
        f"📊 <b>User Activity Categories:</b>\n"
        f"🔥 Highly Active (20+ msgs): <b>{highly_active}</b>\n"
        f"⚡ Moderately Active (5-19 msgs): <b>{moderately_active}</b>\n"
        f"🌱 Low Activity (1-4 msgs): <b>{low_activity}</b>\n\n"
        f"🧠 <b>Memory System:</b>\n"
        f"💾 Content Memories: <b>{total_content_memories}</b>\n"
        f"📝 History Limit: <b>{MAX_HISTORY}</b> msgs/user\n"
        f"👥 User Limit: <b>{MAX_USERS_IN_MEMORY}</b>\n"
        f"🗓️ Cleanup After: <b>{MAX_INACTIVE_DAYS}</b> days\n\n"
    )
    
    # Add top 20 users
    if top_20_users:
        admin_stats_text += "🏆 <b>Top 20 Users by Messages:</b>\n"
        for i, user in enumerate(top_20_users, 1):
            username_display = f"@{user['username']}" if user['username'] != "Unknown" else "No username"
            admin_stats_text += (
                f"{i}. <b>{user['full_name']}</b> ({username_display})\n"
                f"   ID: <code>{user['user_id']}</code> | Chat: <code>{user['chat_id']}</code> | Messages: <b>{user['messages']}</b>\n\n"
            )
    
    admin_stats_text += "<i>🔒 Admin-only information</i>"
    
    await send_long_message(update, admin_stats_text)

# Keep the broadcast functionality from previous.py
async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send broadcast message to all users (admin only)"""
    if not update or not update.message or not update.effective_chat or not update.effective_user:
        return
    
    user_id = str(update.effective_user.id)
    admin_ids = [ADMIN_ID.strip()] if ADMIN_ID and ADMIN_ID.strip() else []
    
    if user_id not in admin_ids:
        # Hide admin command from non-admin users - no response
        return
    
    # Extract message text
    message_text = update.message.text
    if not message_text or len(message_text.split(" ", 1)) < 2:
        await safe_reply(update, "❓ Iltimos broadcast xabarini kiriting. Misol: <code>/broadcast Yangilik...</code>")
        return
    
    broadcast_text = message_text.split(" ", 1)[1]
    
    # Send broadcast to all users
    total_users = len(user_history)
    success_count = 0
    failed_count = 0
    
    status_msg = await safe_reply(update, f"📡 <b>Broadcast boshlandi...</b>\n\n📊 Jami foydalanuvchilar: {total_users}")
    
    if not status_msg:
        logger.error("Failed to send broadcast status message")
        return
    
    for i, chat_id in enumerate(user_history.keys()):
        try:
            # Create a fake update object for sending
            await context.bot.send_message(
                chat_id=int(chat_id),
                text=f"📢 <b>ADMIN XABARI:</b>\n\n{broadcast_text}",
                parse_mode=ParseMode.HTML
            )
            success_count += 1
        except Exception as e:
            logger.warning(f"Failed to send broadcast to {chat_id}: {e}")
            failed_count += 1
        
        # Update status every 10 users
        if (i + 1) % 10 == 0 and status_msg:
            try:
                await safe_edit_message(
                    status_msg,
                    f"📡 <b>Broadcast jarayoni...</b>\n\n"
                    f"✅ Yuborildi: {success_count}\n"
                    f"❌ Xatolik: {failed_count}\n"
                    f"📊 Jarayon: {i + 1}/{total_users}"
                )
            except Exception:
                pass
    
    # Final status
    final_text = (
        f"📡 <b>Broadcast yakunlandi!</b>\n\n"
        f"✅ Muvaffaqiyatli: <b>{success_count}</b>\n"
        f"❌ Xatolik: <b>{failed_count}</b>\n"
        f"📊 Jami: <b>{total_users}</b>\n\n"
        f"<i>🔒 Admin broadcast yakunlandi</i>"
    )
    
    if status_msg:
        await safe_edit_message(status_msg, final_text)
    else:
        await safe_reply(update, final_text)

# Keep the update functionality from previous.py
async def update_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send update message to all users (admin only)"""
    if not update or not update.message or not update.effective_chat or not update.effective_user:
        return
    
    # Check if user is admin
    admin_ids = [ADMIN_ID.strip()] if ADMIN_ID and ADMIN_ID.strip() else []
    
    user_id = str(update.effective_user.id)
    
    if user_id not in admin_ids:
        # Hide admin command from non-admin users - no response at all
        return
    
    # Enhanced update message with current features (like in bot.py)
    update_message = (
        f"🎉🎉🎉 <b>TADAAAAM ! AQLJON yanada AQLLI bo'ldi!</b> 🚀\n\n"
        f"<b>✨ Yangi imkoniyatlar:</b>\n"
        f"📊 <b>Kengaytirilgan statistika</b> - Batafsil faollik tahlili\n"
        f"🕰️ Kunlik, haftalik va oylik statistika\n"
        f"🏆 Yutuqlar tizimi va faollik darajalari\n"
        f"📞 <b>To'g'ridan-to'g'ri aloqa</b> - Admin bilan bog'lanish\n"
        f"📷 Rasm tahlili va xotirasi\n"
        f"🎤 Audio xabarlar va ovozli suhbat\n"
        f"📄 Hujjatlar tahlili\n"
        f"🎥 <b>Video tahlili</b> - videolarni ko'rib tushunadi!\n\n"
        f"<b>🔥 Eng zo'r xususiyatlar:</b>\n"
        f"• <i>Bot barcha yuborgan kontentlaringizni eslab qoladi</i>\n"
        f"• <i>Haftalik va oylik faoliyatingizni kuzatib boradi</i>\n"
        f"• <i>Yutuqlar va mukofotlar tizimi</i>\n"
        f"• <i>Admin bilan to'g'ridan-to'g'ri muloqot</i>\n\n"
        f"💬 Savollar va fikrlaringizni bering va yangi imkoniyatlarni sinab ko'ring!\n\n"
        f"<b>🙏 AQLJON - doimo siz bilan birga!</b>"
    )
    
    # Get all users who have ever interacted with the bot
    all_chat_ids = set()
    
    # From user_history (anyone who sent messages)
    all_chat_ids.update(user_history.keys())
    
    # From user_info (anyone who started the bot)
    all_chat_ids.update(user_info.keys())
    
    # From user_stats (anyone tracked)
    all_chat_ids.update(user_stats.keys())
    
    # From user_content_memory (anyone who sent media)
    all_chat_ids.update(user_content_memory.keys())
    
    if not all_chat_ids:
        await safe_reply(update, "❌ Hech qanday foydalanuvchi topilmadi!")
        return
    
    # Send update message
    successful_sends = 0
    failed_sends = 0
    
    status_msg = await safe_reply(update, f"📤 {len(all_chat_ids)} ta foydalanuvchiga yangilanish haqida xabar yuborilmoqda...")
    
    if not status_msg:
        logger.error("Failed to send update status message")
        return
    
    for chat_id in all_chat_ids:
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
        f"✅ <b>Yangilanish xabari yuborildi!</b>\n\n"
        f"📤 Yuborildi: <b>{successful_sends}</b>\n"
        f"❌ Yuborilmadi: <b>{failed_sends}</b>\n"
        f"👥 Jami foydalanuvchilar: <b>{len(all_chat_ids)}</b>"
    )
    
    if status_msg:
        await safe_edit_message(status_msg, result_text)
    else:
        await safe_reply(update, result_text)

# Add a dictionary to track user states for contact and search flows
user_states = {}

# ─── 📞 Contact Command ─────────────────────────────────────────────────
async def contact_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send contact message to admin (users only)"""
    if not update or not update.message or not update.effective_chat or not update.effective_user:
        return
    
    user_id = str(update.effective_user.id)
    admin_ids = [ADMIN_ID.strip()] if ADMIN_ID and ADMIN_ID.strip() else []
    
    # Admin can't use contact command
    if user_id in admin_ids:
        await safe_reply(update, "⚠️ Admin kontakt buyrug'idan foydalana olmaydi. Bevosita xabar yozing.")
        return
    
    # Extract message text
    message_text = update.message.text
    if not message_text or len(message_text.split(" ", 1)) < 2:
        await safe_reply(update, "❓ Iltimos adminga yubormoqchi bo'lgan xabaringizni kiriting. Misol: <code>/contact Yordam kerak</code>")
        return
    
    contact_text = message_text.split(" ", 1)[1]
    chat_id = str(update.effective_chat.id)
    
    # Store contact message
    if chat_id not in user_contact_messages:
        user_contact_messages[chat_id] = []
    
    contact_message = {
        "message": contact_text,
        "timestamp": time.time(),
        "user_info": user_info.get(chat_id, {}),
        "replied": False
    }
    
    user_contact_messages[chat_id].append(contact_message)
    
    # Send to admin if admin ID is set
    if ADMIN_ID and ADMIN_ID.strip():
        try:
            user_data = user_info.get(chat_id, {})
            username = user_data.get("username", "Unknown")
            first_name = user_data.get("first_name", "Unknown")
            last_name = user_data.get("last_name", "")
            full_name = f"{first_name} {last_name}".strip() or "Unknown"
            
            admin_notification = (
                f"📨 <b>YANGI KONTAKT XABARI</b>\n\n"
                f"👤 <b>Foydalanuvchi:</b> {full_name}\n"
                f"🏷️ <b>Username:</b> @{username}\n"
                f"🆔 <b>User ID:</b> <code>{user_data.get('user_id', 'Unknown')}</code>\n"
                f"🆔 <b>Chat ID:</b> <code>{chat_id}</code>\n\n"
                f"💬 <b>Xabar:</b>\n{contact_text}\n\n"
                f"<i>Javob berish uchun: </i><code>/reply {chat_id} [javob]</code>"
            )
            
            # Send to all admin IDs if there are multiple
            admin_ids = [ADMIN_ID.strip()] if ADMIN_ID and ADMIN_ID.strip() else []
            for admin_id in admin_ids:
                try:
                    await context.bot.send_message(
                        chat_id=int(admin_id),
                        text=admin_notification,
                        parse_mode=ParseMode.HTML
                    )
                except Exception as e:
                    logger.error(f"Failed to send contact message to admin {admin_id}: {e}")
            
            await safe_reply(update, "✅ Xabaringiz adminga yuborildi! Tez orada javob berishadi.")
            
        except Exception as e:
            logger.error(f"Failed to send contact message to admin: {e}")
            await safe_reply(update, "❌ Xabar yuborishda xatolik yuz berdi. Qaytadan urinib ko'ring.")
    else:
        await safe_reply(update, "⚠️ Admin ID sozlanmagan. Xabar saqlandi, lekin adminga yuborilmadi.")

# ─── 🔧 Reply Command (Admin Only) ─────────────────────────────────────────────────
async def reply_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin can reply to specific users"""
    if not update or not update.message or not update.effective_chat or not update.effective_user:
        return
    
    # Check if user is admin
    admin_ids = [ADMIN_ID.strip()] if ADMIN_ID and ADMIN_ID.strip() else []
    user_id = str(update.effective_user.id)
    
    if user_id not in admin_ids:
        # Hide admin command from non-admin users - no response at all
        return
    
    # Extract reply text
    message_text = update.message.text
    if not message_text or len(message_text.split(" ", 2)) < 3:
        await safe_reply(update, "❓ Iltimos javob yuboring. Format: <code>/reply [chat_id] [xabaringiz]</code>")
        return
    
    parts = message_text.split(" ", 2)
    target_chat_id = parts[1]
    admin_reply = parts[2]
    
    # Mark contact messages as replied
    if target_chat_id in user_contact_messages:
        for msg in user_contact_messages[target_chat_id]:
            if not msg["replied"]:
                msg["replied"] = True
    
    # Send reply to user
    reply_msg = (
        f"📞 <b>Admin Javobi</b>\n\n"
        f"💬 <b>Xabar:</b>\n{admin_reply}\n\n"
        f"<i>Kerak bo'lsa /contact bilan yana xabar yubora olasiz.</i>"
    )
    
    try:
        await context.bot.send_message(
            chat_id=int(target_chat_id),
            text=reply_msg,
            parse_mode=ParseMode.HTML
        )
        
        await safe_reply(update, f"✅ Javob muvaffaqiyatli yuborildi foydalanuvchiga: {target_chat_id}")
    except Exception as e:
        logger.error(f"Failed to send reply to user {target_chat_id}: {e}")
        await safe_reply(update, f"❌ Javob yuborishda xatolik yuz berdi. Foydalanuvchi {target_chat_id} botni bloklagandir.")

# ─── 🛠️ System Monitor Command (Admin Only) ─────────────────────────────────────
async def system_monitor_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Monitor system health and performance (admin only)"""
    if not update or not update.message or not update.effective_chat or not update.effective_user:
        return
    
    # Check if user is admin
    admin_ids = [ADMIN_ID.strip()] if ADMIN_ID and ADMIN_ID.strip() else []
    user_id = str(update.effective_user.id)
    
    if user_id not in admin_ids:
        # Hide admin command from non-admin users - no response at all
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
        status = "🔴 MUHIM"
        status_msg = "Zudlik bilan harakat talab qilinadi!"
    elif user_limit_percent > 70 or memory_usage > 100:
        status = "🟡 OGOHLANTIRISH"
        status_msg = "Diqqat bilan kuzatish"
    else:
        status = "🟢 SALOMAT"
        status_msg = "Barcha tizimlar normal"
    
    monitor_text = (
        f"<b>🔠 TIZIM SALOMATLIGI MONITORI</b>\n\n"
        f"<b>Tizim holati:</b> {status}\n"
        f"<i>{status_msg}</i>\n\n"
        f"<b>📊 Resurs foydalanish:</b>\n"
        f"Foydalanuvchilar: <b>{total_users}</b> / {MAX_USERS_IN_MEMORY} ({user_limit_percent:.1f}%)\n"
        f"Xotira: <b>{memory_usage:.1f} MB</b>\n\n"
        f"<b>🧹 Maintenance:</b>\n"
        f"Faol bo'lmagan foydalanuvchilar tozalandi: <b>{cleaned_users}</b>\n"
        f"Tozalash chegarasi: <b>{MAX_INACTIVE_DAYS} kun</b>\n\n"
        f"<b>📍 Tavsiyalar:</b>\n"
    )
    
    # Add recommendations based on status
    if user_limit_percent > 90:
        monitor_text += "⚠️ MAX_USERS_IN_MEMORY ni kamaytirish tavsiya etiladi\n"
    if memory_usage > 150:
        monitor_text += "⚠️ Ma'lumotlar bazasi saqlashni joriy qilish tavsiya etiladi\n"
    if cleaned_users == 0 and total_users > 1000:
        monitor_text += "⚠️ MAX_INACTIVE_DAYS ni kamaytirish tavsiya etiladi\n"
    
    if user_limit_percent < 50 and memory_usage < 50:
        monitor_text += "✅ Tizim optimal ishlayapti\n"
    
    monitor_text += "\n<i>🔄 Har yangi foydalanuvchida avtomatik tozalash ishlaydi</i>"
    
    await safe_reply(update, monitor_text, parse_mode=ParseMode.HTML)

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
        "<b>🤖 AQLJON YORDAM MENU</b>\n\n"
        "🟢 <b>/start</b> — Botni qayta ishga tushirish\n"
        "🟢 <b>/help</b> — Yordam va buyruqlar roʻyxati\n"
        "🟢 <b>/search [so'z]</b> — Internetdan qidiruv (Google orqali)\n"
        "🟢 <b>/stats</b> — Statistikani ko'rish\n"
        "🟢 <b>/contact [xabar]</b> — Admin bilan bog'lanish\n\n"
        "💬 Oddiy xabar yuboring — men siz bilan suhbatlashaman!\n"
        "📷 Rasm yuboring — uni tahlil qilaman!\n"
        "🎙️ Ovoz yuboring — munosib va chiroyli javob beraman!\n"
        "📄 Hujjat yuboring — tahlil qilib xulosa beraman!\n"
        "🎬 Video yuboring — ko'rib tahlil qilaman!\n\n"
        "🚀 Yanada aqlli, samimiy va foydali yordamchi bo'lishga harakat qilaman!"
    )
    
    # Check if user is admin and add admin commands to help
    admin_ids = [ADMIN_ID.strip()] if ADMIN_ID and ADMIN_ID.strip() else []
    user_id = str(update.effective_user.id)
    
    if user_id in admin_ids:
        help_text += (
            "\n\n<b>🔧 Admin Buyruqlari:</b>\n"
            "🟢 <b>/broadcast [xabar]</b> — Barcha foydalanuvchilarga xabar yuborish\n"
            "🟢 <b>/reply [chat_id] [xabar]</b> — Foydalanuvchi murojaatiga javob berish\n"
            "🟢 <b>/update</b> — Barcha foydalanuvchilarga yangilanish haqida xabar\n"
            "🟢 <b>/adminstats</b> — To'liq bot statistikasini ko'rish\n"
            "🟢 <b>/monitor</b> — Tizim salomatligi va unumdorlik monitoringi"
        )
    
    await update.message.reply_text(help_text, parse_mode=ParseMode.HTML, reply_markup=main_menu_keyboard())

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await send_typing(update)
        chat_id = str(update.effective_chat.id) if update and update.effective_chat else "unknown"
        message = update.message.text.strip() if update and update.message and update.message.text else ""

        # Check if user is in a conversational flow
        if chat_id in user_states:
            state = user_states[chat_id]
            
            # Handle contact flow - user has sent their message after being prompted
            if state == "awaiting_contact_message":
                # Remove user from flow state
                del user_states[chat_id]
                
                # Send message to admin
                if ADMIN_ID and ADMIN_ID.strip():
                    try:
                        user_data = user_info.get(chat_id, {})
                        username = user_data.get("username", "Unknown")
                        first_name = user_data.get("first_name", "Unknown")
                        last_name = user_data.get("last_name", "")
                        full_name = f"{first_name} {last_name}".strip() or "Unknown"
                        
                        admin_notification = (
                            f"📨 <b>YANGI KONTAKT XABARI</b>\n\n"
                            f"👤 <b>Foydalanuvchi:</b> {full_name}\n"
                            f"🏷️ <b>Username:</b> @{username}\n"
                            f"🆔 <b>User ID:</b> <code>{user_data.get('user_id', 'Unknown')}</code>\n"
                            f"🆔 <b>Chat ID:</b> <code>{chat_id}</code>\n\n"
                            f"💬 <b>Xabar:</b>\n{message}\n\n"
                            f"<i>Javob berish uchun: </i><code>/reply {chat_id} [javob]</code>"
                        )
                        
                        # Send to all admin IDs if there are multiple
                        admin_ids = [ADMIN_ID.strip()] if ADMIN_ID and ADMIN_ID.strip() else []
                        for admin_id in admin_ids:
                            try:
                                await context.bot.send_message(
                                    chat_id=int(admin_id),
                                    text=admin_notification,
                                    parse_mode=ParseMode.HTML
                                )
                            except Exception as e:
                                logger.error(f"Failed to send contact message to admin {admin_id}: {e}")
                        
                        await safe_reply(update, "✅ Xabaringiz adminga yuborildi! Tez orada javob berishadi.")
                        
                    except Exception as e:
                        logger.error(f"Failed to send contact message to admin: {e}")
                        await safe_reply(update, "❌ Xabar yuborishda xatolik yuz berdi. Qaytadan urinib ko'ring.")
                else:
                    await safe_reply(update, "⚠️ Admin ID sozlanmagan. Xabar saqlandi, lekin adminga yuborilmadi.")
                return
            
            # Handle search flow - user has sent their search query after being prompted
            elif state == "awaiting_search_query":
                # Remove user from flow state
                del user_states[chat_id]
                
                # Track search activity
                track_user_activity(chat_id, "search_queries", update)
                result = await search_web(message)
                if result:  # Check if result is not None
                    await send_long_message(update, f"<b>🔎 Qidiruv natijalari:</b>\n{result}")
                else:
                    await safe_reply(update, "❌ Qidiruvda xatolik yuz berdi.")
                return

        # Handle keyboard button presses for conversational flows
        if message == "📞 Kontakt":
            await safe_reply(update, "📞 Admin uchun xabaringizni yozing:")
            user_states[chat_id] = "awaiting_contact_message"
            return
            
        elif message == "🔍 Qidiruv":
            await safe_reply(update, "🔍 Qidirish uchun so'rov kiriting:")
            user_states[chat_id] = "awaiting_search_query"
            return
            
        elif message == "📊 Statistika":
            await stats_command(update, context)
            return
            
        elif message == "🔄 Qayta ishga tushirish":
            await start(update, context)
            return
            
        elif message == "ℹ️ Yordam":
            await help_command(update, context)
            return

        # Handle stats command
        if message.lower() == "/stats":
            await stats_command(update, context)
            return

        # Slash-based search
        if message.lower().startswith("/search"):
            parts = message.split(" ", 1)
            if len(parts) == 2:
                query = parts[1].strip()
                # Track search activity
                track_user_activity(chat_id, "search_queries", update)
                result = await search_web(query)
                if result:  # Check if result is not None
                    await send_long_message(update, f"<b>🔎 Qidiruv natijalari:</b>\n{result}")
                else:
                    await safe_reply(update, "❌ Qidiruvda xatolik yuz berdi.")
            else:
                await safe_reply(update, "❓ Iltimos qidiruv so'rovini kiriting. Misol: <code>/search Ibn Sina</code>")
            return

        # Handle contact command
        if message.lower().startswith("/contact"):
            # Extract message text
            if len(message.split(" ", 1)) < 2:
                await safe_reply(update, "❓ Iltimos adminga yubormoqchi bo'lgan xabaringizni kiriting. Misol: <code>/contact Yordam kerak</code>")
                return
            
            contact_text = message.split(" ", 1)[1]
            
            # Store contact message
            if chat_id not in user_contact_messages:
                user_contact_messages[chat_id] = []
            
            contact_message = {
                "message": contact_text,
                "timestamp": time.time(),
                "user_info": user_info.get(chat_id, {}),
                "replied": False
            }
            
            user_contact_messages[chat_id].append(contact_message)
            
            # Send to admin if admin ID is set
            if ADMIN_ID and ADMIN_ID.strip():
                try:
                    user_data = user_info.get(chat_id, {})
                    username = user_data.get("username", "Unknown")
                    first_name = user_data.get("first_name", "Unknown")
                    last_name = user_data.get("last_name", "")
                    full_name = f"{first_name} {last_name}".strip() or "Unknown"
                    
                    admin_notification = (
                        f"📨 <b>YANGI KONTAKT XABARI</b>\n\n"
                        f"👤 <b>Foydalanuvchi:</b> {full_name}\n"
                        f"🏷️ <b>Username:</b> @{username}\n"
                        f"🆔 <b>User ID:</b> <code>{user_data.get('user_id', 'Unknown')}</code>\n"
                        f"🆔 <b>Chat ID:</b> <code>{chat_id}</code>\n\n"
                        f"💬 <b>Xabar:</b>\n{contact_text}\n\n"
                        f"<i>Javob berish uchun: </i><code>/reply {chat_id} [javob]</code>"
                    )
                    
                    # Send to all admin IDs if there are multiple
                    admin_ids = [ADMIN_ID.strip()] if ADMIN_ID and ADMIN_ID.strip() else []
                    for admin_id in admin_ids:
                        try:
                            await context.bot.send_message(
                                chat_id=int(admin_id),
                                text=admin_notification,
                                parse_mode=ParseMode.HTML
                            )
                        except Exception as e:
                            logger.error(f"Failed to send contact message to admin {admin_id}: {e}")
                    
                    await safe_reply(update, "✅ Xabaringiz adminga yuborildi! Tez orada javob berishadi.")
                    
                except Exception as e:
                    logger.error(f"Failed to send contact message to admin: {e}")
                    await safe_reply(update, "❌ Xabar yuborishda xatolik yuz berdi. Qaytadan urinib ko'ring.")
            else:
                await safe_reply(update, "⚠️ Admin ID sozlanmagan. Xabar saqlandi, lekin adminga yuborilmadi.")
            return

        # Gemini chat with memory context
        history = user_history.setdefault(chat_id, [])
        history.append({"role": "user", "content": message})
        
        # Track user activity with character count
        track_user_activity(chat_id, "messages", update)
        # Track character count for this message
        if chat_id in user_stats:
            user_stats[chat_id]["total_characters"] = user_stats[chat_id].get("total_characters", 0) + len(message)
        
        try:
            reply = await ask_gemini(history, chat_id)  # Pass chat_id for memory context
            if reply:  # Only add to history if we got a reply
                history.append({"role": "model", "content": reply})
                user_history[chat_id] = history[-MAX_HISTORY * 2:]
                await send_long_message(update, reply)
            else:
                await safe_reply(update, "⚙️ Hozircha javob bera olmayapman. Biroz kutib, qaytadan urinib ko'ring.")
        except Exception as gemini_error:
            logger.error(f"Gemini processing error: {gemini_error}")
            await safe_reply(update, "⚙️ Hozircha javob bera olmayapman. Biroz kutib, qaytadan urinib ko'ring.")
        
    except (NetworkError, TelegramError, TimedOut) as e:
        logger.error(f"Telegram API error in handle_text: {e}")
        await asyncio.sleep(2)  # Wait before next operation
    except Exception as e:
        logger.error(f"Unexpected error in handle_text: {e}")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not update or not update.message or not update.message.photo:
            return
        await send_typing(update)
        file = await context.bot.get_file(update.message.photo[-1].file_id)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp_file:
            await file.download_to_drive(custom_path=tmp_file.name)
            tmp_path = tmp_file.name

        try:
            uploaded = await asyncio.wait_for(
                asyncio.to_thread(lambda: genai.upload_file(tmp_path)),
                timeout=30  # Increased timeout
            )
            response = await asyncio.wait_for(
                asyncio.to_thread(lambda: model.generate_content([
                    {"role": "user", "parts": [
                        "The user sent a photo. Analyze in detail and react like a friend who saw it and gives a warm, friendly and useful reply. No robotic descriptions. Use emojis and formatting awesomely. And always answer awesomely in uzbek language. if user asks in another language then answer in that language."
                    ]},
                    {"role": "user", "parts": [uploaded]}
                ])),
                timeout=30  # Increased timeout
            )
            reply = response.text.strip() if response and response.text else ""
            chat_id = str(update.effective_chat.id) if update and update.effective_chat else "unknown"
            
            # Track photo activity
            track_user_activity(chat_id, "photos", update)
            
            # Store photo analysis in memory for future reference
            store_content_memory(chat_id, "photo", reply)
            
            user_history.setdefault(chat_id, []).append({"role": "user", "content": "[sent photo 📸]"})
            user_history[chat_id].append({"role": "model", "content": reply})
            await send_long_message(update, reply)
        except asyncio.TimeoutError:
            logger.error("Photo processing timeout")
            await safe_reply(update, "⏰ Rasm tahlili juda uzoq davom etdi. Qaytadan urinib ko'ring.")
        except Exception as e:
            logger.error(f"Photo processing error: {e}")
            await safe_reply(update, "❌ Rasmni tahlil qilishda xatolik yuz berdi. Qaytadan urinib ko'ring.")
        finally:
            try:
                os.remove(tmp_path)
            except Exception:
                pass
    except (NetworkError, TelegramError, TimedOut) as e:
        logger.error(f"Telegram API error in handle_photo: {e}")
        await asyncio.sleep(2)  # Wait before retry
    except Exception as e:
        logger.error(f"Unexpected error in handle_photo: {e}")

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not update or not update.message or not (update.message.voice or update.message.audio):
            return
        await send_typing(update)
        voice = update.message.voice or update.message.audio
        if not voice or not voice.file_id:
            return
        file = await context.bot.get_file(voice.file_id)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".oga") as tmp_file:
            await file.download_to_drive(custom_path=tmp_file.name)
            tmp_path = tmp_file.name

        try:
            uploaded = await asyncio.wait_for(
                asyncio.to_thread(lambda: genai.upload_file(tmp_path)),
                timeout=30
            )
            response = await asyncio.wait_for(
                asyncio.to_thread(lambda: model.generate_content([
                    {"role": "user", "parts": [
                        "The user sent an audio message. Listen to it and respond awesomely like a friend who listened to their voice message. Don't repeat what the user said! Be warm, friendly and engaging. Use emojis and nice formatting. Answer in Uzbek if the user speaks Uzbek, otherwise use appropriate language."
                    ]},
                    {"role": "user", "parts": [uploaded]}
                ])),
                timeout=30
            )
            reply = response.text.strip() if response and response.text else ""
            chat_id = str(update.effective_chat.id) if update and update.effective_chat else "unknown"
            
            # Track voice activity
            track_user_activity(chat_id, "voice_audio", update)
            
            # Store audio analysis in memory for future reference
            store_content_memory(chat_id, "audio", reply)
            
            user_history.setdefault(chat_id, []).append({"role": "user", "content": "[sent voice message 🎤]"})
            user_history[chat_id].append({"role": "model", "content": reply})
            await send_long_message(update, reply)
        except asyncio.TimeoutError:
            logger.error("Voice processing timeout")
            await safe_reply(update, "⏰ Audio tahlili juda uzoq davom etdi. Qaytadan urinib ko'ring.")
        except Exception as e:
            logger.error(f"Voice processing error: {e}")
            await safe_reply(update, "❌ Audio xabarni qayta ishlashda xatolik. Qaytadan urinib ko'ring.")
        finally:
            try:
                os.remove(tmp_path)
            except Exception:
                pass
    except (NetworkError, TelegramError, TimedOut) as e:
        logger.error(f"Telegram API error in handle_voice: {e}")
        await asyncio.sleep(2)
    except Exception as e:
        logger.error(f"Unexpected error in handle_voice: {e}")

# ─── 🚀 Start Bot ──────────────────────────────────────────────
def main():
    # Check if required environment variables are set
    if not TELEGRAM_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN environment variable not set")
        return
        
    # Create application with enhanced error handling and proper configuration
    app = (Application.builder()
           .token(str(TELEGRAM_TOKEN))  # Convert to string to ensure type safety
           .read_timeout(30)
           .write_timeout(30)
           .connect_timeout(30)
           .pool_timeout(30)
           .build())
    
    # Note: Connection pooling is now handled automatically by the library
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("contact", contact_command))  # Contact admin
    app.add_handler(CommandHandler("reply", reply_command))  # Admin reply
    app.add_handler(CommandHandler("broadcast", broadcast_command))  # Admin broadcast
    app.add_handler(CommandHandler("update", update_command))  # Quick update broadcast
    app.add_handler(CommandHandler("adminstats", admin_stats_command))  # Admin statistics
    app.add_handler(CommandHandler("monitor", system_monitor_command))  # System monitoring
    app.add_handler(CommandHandler("search", handle_text))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.VIDEO, handle_video))  # Video handler
    
    logger.info("🤖 AQLJON SmartBot is now LIVE and listening!") 
    logger.info("🎬 Video processing: Non-blocking with timeouts enabled")
    logger.info("🚀 Bot optimized for concurrent users")
    logger.info("🛡️ Enhanced error handling and rate limiting enabled")
    
    # Run with enhanced polling settings
    app.run_polling(
        poll_interval=2.0,  # Increased poll interval to reduce API calls
        timeout=30,         # Increased timeout
        bootstrap_retries=5 # More retries on startup
    )


if __name__ == "__main__":
    main()