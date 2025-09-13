import os
import re
import asyncio
import logging
import tempfile
import time
import threading
import weakref
from datetime import datetime, timedelta
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor
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
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or ""
GEMINI_KEY = os.getenv("GEMINI_API_KEY") or ""
SERPER_KEY = os.getenv("SERPER_API_KEY") or ""
ADMIN_ID = os.getenv("ADMIN_ID") or ""

# ─── 🤖 Gemini Setup with Enhanced Configuration ───────────────
genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel("gemini-2.5-flash")

# ─── 🔧 Global Resource Management for Deadlock Prevention ───
MAX_CONCURRENT_UPLOADS = 2  # Strict limit for Railway
MAX_USER_CONCURRENT = 1  # Only 1 media per user at a time
upload_semaphore = asyncio.Semaphore(MAX_CONCURRENT_UPLOADS)
gemini_executor = ThreadPoolExecutor(
    max_workers=MAX_CONCURRENT_UPLOADS, 
    thread_name_prefix="gemini_safe"
)

# ─── 📊 User Processing Queue System ───
user_processing_queue = {}  # Track processing tasks per user
user_queue_lock = asyncio.Lock()

# ─── 🧹 Active File Tracking for Cleanup ───
active_temp_files = weakref.WeakSet()
_cleanup_lock = threading.Lock()

# ─── 📊 Queue Management for Multiple Media Processing ───
async def add_to_user_queue(chat_id: str, media_task):
    """Add media processing task to user queue - processes one by one"""
    async with user_queue_lock:
        if chat_id not in user_processing_queue:
            user_processing_queue[chat_id] = asyncio.Queue(maxsize=5)  # Max 5 pending per user
        
        try:
            user_processing_queue[chat_id].put_nowait(media_task)
            logger.info(f"Added media task to queue for user {chat_id}")
            
            # Start queue processor if not running
            if not hasattr(user_processing_queue[chat_id], '_processor_running'):
                user_processing_queue[chat_id]._processor_running = True
                asyncio.create_task(process_user_queue(chat_id))
                
        except asyncio.QueueFull:
            # Queue full - reject new media
            return False
    return True

async def process_user_queue(chat_id: str):
    """Process media queue for a specific user one by one"""
    queue = user_processing_queue.get(chat_id)
    if not queue:
        return
        
    try:
        while True:
            try:
                # Get next task with timeout
                media_task = await asyncio.wait_for(queue.get(), timeout=1.0)
                
                # Process the media task
                await media_task
                
                # Mark task as done
                queue.task_done()
                
                # Small delay between processing
                await asyncio.sleep(0.5)
                
            except asyncio.TimeoutError:
                # No more tasks, exit processor
                break
            except Exception as e:
                logger.error(f"Error processing media queue for {chat_id}: {e}")
                
    finally:
        # Reset processor flag
        if hasattr(queue, '_processor_running'):
            delattr(queue, '_processor_running')
        logger.info(f"Queue processor finished for user {chat_id}")

def cleanup_temp_file(file_path: str):
    try:
        if os.path.exists(file_path):
            os.unlink(file_path)
            logger.debug(f"Cleaned up temp file: {file_path}")
    except Exception as e:
        logger.warning(f"Failed to cleanup temp file {file_path}: {e}")

# ─── 🛡️ Enhanced Gemini API Safety Functions ──────────────────
async def safe_upload_to_gemini(file_path: str, timeout: int = 20) -> tuple:
    """Safely upload file to Gemini with deadlock prevention"""
    async with upload_semaphore:  # Critical: limit concurrent uploads
        try:
            def upload_task():
                try:
                    if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
                        return False, None, "File not found or empty"
                    uploaded_file = genai.upload_file(file_path)
                    return True, uploaded_file, None
                except Exception as e:
                    logger.error(f"Upload error: {e}")
                    return False, None, str(e)
            
            success, result, error = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(gemini_executor, upload_task),
                timeout=timeout
            )
            return success, result, error
            
        except asyncio.TimeoutError:
            return False, None, f"Upload timeout after {timeout}s"
        except Exception as e:
            return False, None, str(e)

async def safe_generate_content(messages: list, timeout: int = 15) -> tuple:
    """Safely generate content with Gemini"""
    try:
        def generate_task():
            try:
                response = model.generate_content(messages)
                return True, response.text.strip() if response.text else "No response", None
            except Exception as e:
                return False, None, str(e)
        
        success, content, error = await asyncio.wait_for(
            asyncio.get_event_loop().run_in_executor(gemini_executor, generate_task),
            timeout=timeout
        )
        return success, content, error
        
    except asyncio.TimeoutError:
        return False, None, "Generation timeout"
    except Exception as e:
        return False, None, str(e)

# ─── 🧠 Enhanced Memory ─────────────────────────────────────────────────
user_history = {}
user_content_memory = {}
user_stats = {}
user_info = {}
user_contact_messages = {}
user_daily_activity = {}
MAX_HISTORY = 20
MAX_CONTENT_MEMORY = 50
MAX_USERS_IN_MEMORY = 2000
MAX_INACTIVE_DAYS = 30
ADMIN_CHAT_ID = ADMIN_ID

def cleanup_inactive_users():
    """Remove inactive users to prevent memory overflow"""
    current_time = time.time()
    inactive_threshold = current_time - (MAX_INACTIVE_DAYS * 24 * 60 * 60)
    
    inactive_users = []
    for chat_id, stats in user_stats.items():
        last_active = stats.get("last_active", 0)
        if isinstance(last_active, str):
            last_active = current_time
        
        if last_active < inactive_threshold:
            inactive_users.append(chat_id)
    
    removed_count = 0
    for chat_id in inactive_users:
        for storage in [user_history, user_content_memory, user_stats, user_info]:
            storage.pop(chat_id, None)
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
            user_activity = []
            for chat_id, stats in user_stats.items():
                last_active = stats.get("last_active", 0)
                if isinstance(last_active, str):
                    last_active = 0
                user_activity.append((chat_id, last_active))
            
            user_activity.sort(key=lambda x: x[1])
            to_remove = len(user_history) - MAX_USERS_IN_MEMORY + 100
            
            for i in range(min(to_remove, len(user_activity))):
                chat_id = user_activity[i][0]
                for storage in [user_history, user_content_memory, user_stats, user_info]:
                    storage.pop(chat_id, None)
            
            logger.info(f"Removed {to_remove} oldest users to maintain memory limits")

# ─── 📝 Logging ────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# ─── 👋 Welcome Message ────────────────────────────────────────
WELCOME = (
    "<b>👋 Assalomu alaykum va rohmatulloh va barokatuh!</b>\n"
    "Men <b>AQLJON</b> 🤖 — sizning doimiy hamrohingizman!\n\n"
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
                await asyncio.sleep(2 ** attempt)
            else:
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
            await asyncio.sleep(0.3)
        except RetryAfter as e:
            logger.warning(f"Rate limited, waiting {e.retry_after} seconds")
            await asyncio.sleep(e.retry_after + 1)
            try:
                await update.message.reply_text(text[i:i+4096], parse_mode=ParseMode.HTML)
            except Exception:
                await update.message.reply_text(text[i:i+4096])
        except (NetworkError, TelegramError, TimedOut) as e:
            logger.error(f"Failed to send message chunk: {e}")
            try:
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
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://google.serper.dev/search",
                headers={"X-API-KEY": SERPER_KEY or "", "Content-Type": "application/json"},
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

# ─── 📊 User Statistics Functions ─────────────────────────────────────────────────
def track_user_activity(chat_id: str, activity_type: str, update=None):
    """Track user activity for statistics"""
    # Check memory limits before adding new users
    if chat_id not in user_stats:
        check_memory_limits()
    
    if chat_id not in user_stats:
        user_stats[chat_id] = {
            "messages": 0, "photos": 0, "voice_audio": 0, "documents": 0,
            "videos": 0, "search_queries": 0, "first_interaction": time.time(),
            "last_active": time.time(), "total_characters": 0
        }
    
    user_stats[chat_id][activity_type] += 1
    user_stats[chat_id]["last_active"] = time.time()
    
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

def store_content_memory(chat_id: str, content_type: str, content_summary: str, file_name=None):
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
    
    if len(user_content_memory[chat_id]) > MAX_CONTENT_MEMORY:
        user_content_memory[chat_id] = user_content_memory[chat_id][-MAX_CONTENT_MEMORY:]

def get_content_context(chat_id: str) -> str:
    """Get content memory context for AI"""
    if chat_id not in user_content_memory or not user_content_memory[chat_id]:
        return ""
    
    context_parts = []
    recent_content = user_content_memory[chat_id][-5:]
    
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
async def ask_gemini(history, chat_id=None, max_retries=2):
    for attempt in range(max_retries):
        try:
            messages = [{"role": msg["role"], "parts": [msg["content"]]} for msg in history[-10:]]
            
            content_context = get_content_context(chat_id) if chat_id else ""
            
            base_instruction = (
                "You are a smart friend. Remember your name is AQLJON . Don't repeat what the user said. Reply casually with humor and warmth 😊. "
                "Awesomely answer with formatting <b>, <i>, <u> and emojis 🧠. Answer in Uzbek if the user speaks Uzbek. Otherwise use appropriate language."
            )
            
            full_instruction = base_instruction + content_context
            
            messages.insert(0, {
                "role": "user", "parts": [full_instruction]
            })
            
            success, response, error = await safe_generate_content(messages, timeout=25)
            
            if success:
                return response
            else:
                logger.error(f"Gemini generation failed: {error}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)
                    continue
                    
        except Exception as e:
            logger.error(f"Gemini error on attempt {attempt + 1}: {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(1)
    
    return "<i>⚠️ Gemini hozircha javob bera olmadi. Qaytadan urinib ko'ring.</i>"

# ─── 📄 Document Handler with Queue Management ─────────────────
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle document uploads with queue management for sequential processing"""
    if not update or not update.message or not update.message.document or not update.effective_chat:
        return
    
    document: Document = update.message.document
    chat_id = str(update.effective_chat.id)
    
    # Check file size (Railway limit: 15MB)
    if document.file_size and document.file_size > 15 * 1024 * 1024:
        await safe_reply(update, "❌ Fayl juda katta. Maksimal hajm: 15MB")
        return
    
    # Create media processing task
    async def process_document():
        await send_typing(update)
        analyzing_msg = await safe_reply(update, 
            "📄 <b>Hujjat qabul qilindi!</b>\n\n"
            "⏳ <i>Tahlil qilinmoqda... Biroz sabr qiling!</i>"
        )
        
        tmp_path = None
        try:
            file = await context.bot.get_file(document.file_id)
            
            with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{document.file_name}") as tmp_file:
                tmp_path = tmp_file.name
            
            active_temp_files.add(tmp_path)
            
            # Download with timeout
            await asyncio.wait_for(
                file.download_to_drive(custom_path=tmp_path),
                timeout=20
            )
            
            # Use safe upload to prevent deadlock
            success, uploaded_file, error = await safe_upload_to_gemini(tmp_path, timeout=20)
            
            if not success:
                error_msg = "❌ Hujjat yuklashda xatolik:\n"
                if "quota" in str(error).lower():
                    error_msg += "📊 API chekloviga yetdik. Biroz kuting."
                elif "timeout" in str(error).lower():
                    error_msg += "⏰ Fayl juda katta yoki tarmoq sekin."
                else:
                    error_msg += "🔄 Qaytadan urinib ko'ring."
                
                await safe_edit_message(analyzing_msg, error_msg)
                return
            
            # Safe content generation
            messages = [
                {"role": "user", "parts": [
                    "The user sent a document. Analyze the document and respond to the user awesomely with emojis and nice formatting. Be creative and answer educationally that user needs to get lessons from that document. Answer in Uzbek if the user speaks Uzbek. Otherwise use appropriate language."
                ]},
                {"role": "user", "parts": [uploaded_file]}
            ]
            
            success, reply, error = await safe_generate_content(messages, timeout=20)
            
            if success and reply:
                track_user_activity(chat_id, "documents", update)
                store_content_memory(chat_id, "document", reply, document.file_name)
                
                user_history.setdefault(chat_id, []).append({"role": "user", "content": f"[uploaded document: {document.file_name}]"})
                user_history[chat_id].append({"role": "model", "content": reply})
                
                await safe_edit_message(analyzing_msg, f"📄 <b>Hujjat tahlil natijasi:</b>\n\n{reply}")
            else:
                await safe_edit_message(analyzing_msg, "❌ Hujjat tahlilida xatolik yuz berdi. Qaytadan urinib ko'ring.")
                
        except asyncio.TimeoutError:
            await safe_edit_message(analyzing_msg, "⏰ Hujjat qayta ishlash juda uzoq davom etdi. Kichikroq fayl yuboring.")
        except Exception as e:
            logger.error(f"Document processing error: {e}")
            await safe_edit_message(analyzing_msg, "❌ Hujjat qayta ishlashda xatolik. Qaytadan urinib ko'ring.")
        finally:
            if tmp_path:
                cleanup_temp_file(tmp_path)
    
    # Add to queue for sequential processing
    queued = await add_to_user_queue(chat_id, process_document())
    if not queued:
        await safe_reply(update, "⚠️ Juda ko'p media yuborildi. Biroz kutib, qaytadan urinib ko'ring.")

# ─── 📷 Photo Handler with Queue Management ─────────────────
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle photo uploads with queue management"""
    if not update or not update.message or not update.message.photo or not update.effective_chat:
        return
    
    chat_id = str(update.effective_chat.id)
    
    # Create media processing task
    async def process_photo():
        await send_typing(update)
        analyzing_msg = await safe_reply(update, "📷 <b>Rasm qabul qilindi!</b>\n\n⏳ <i>Tahlil qilinmoqda...</i>")
        
        tmp_path = None
        try:
            if not update.message or not update.message.photo:
                await safe_edit_message(analyzing_msg, "❌ Rasm topilmadi.")
                return
                
            file = await context.bot.get_file(update.message.photo[-1].file_id)
            with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp_file:
                tmp_path = tmp_file.name
            
            await asyncio.wait_for(file.download_to_drive(custom_path=tmp_path), timeout=15)
            
            success, uploaded_file, error = await safe_upload_to_gemini(tmp_path, timeout=15)
            
            if success:
                messages = [{"role": "user", "parts": ["Analyze this photo and respond warmly with emojis. Answer in Uzbek if user speaks Uzbek."]}, {"role": "user", "parts": [uploaded_file]}]
                success, reply, error = await safe_generate_content(messages, timeout=15)
                
                if success:
                    track_user_activity(chat_id, "photos", update)
                    store_content_memory(chat_id, "photo", reply)
                    user_history.setdefault(chat_id, []).append({"role": "user", "content": "[sent photo 📸]"})
                    user_history[chat_id].append({"role": "model", "content": reply})
                    await safe_edit_message(analyzing_msg, f"📷 <b>Rasm tahlili:</b>\n\n{reply}")
                else:
                    await safe_edit_message(analyzing_msg, "❌ Rasm tahlilida xatolik.")
            else:
                await safe_edit_message(analyzing_msg, "❌ Rasm yuklashda xatolik.")
        
        except Exception as e:
            logger.error(f"Photo processing error: {e}")
            await safe_edit_message(analyzing_msg, "❌ Rasm qayta ishlashda xatolik.")
        finally:
            if tmp_path:
                cleanup_temp_file(tmp_path)
    
    # Add to queue
    queued = await add_to_user_queue(chat_id, process_photo())
    if not queued:
        await safe_reply(update, "⚠️ Juda ko'p media yuborildi. Biroz kutib, qaytadan urinib ko'ring.")

# ─── 🎙️ Voice Handler with Queue Management ─────────────────
async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle voice/audio with queue management"""
    if not update or not update.message or not update.effective_chat:
        return
    
    voice = update.message.voice or update.message.audio
    if not voice:
        return
    
    chat_id = str(update.effective_chat.id)
    
    async def process_voice():
        await send_typing(update)
        analyzing_msg = await safe_reply(update, "🎙️ <b>Audio qabul qilindi!</b>\n\n⏳ <i>Tahlil qilinmoqda...</i>")
        
        tmp_path = None
        try:
            file = await context.bot.get_file(voice.file_id)
            with tempfile.NamedTemporaryFile(delete=False, suffix=".oga") as tmp_file:
                tmp_path = tmp_file.name
            
            await asyncio.wait_for(file.download_to_drive(custom_path=tmp_path), timeout=15)
            
            success, uploaded_file, error = await safe_upload_to_gemini(tmp_path, timeout=15)
            
            if success:
                messages = [{"role": "user", "parts": ["Listen and respond warmly like a friend. Use emojis. Answer in Uzbek if user speaks Uzbek."]}, {"role": "user", "parts": [uploaded_file]}]
                success, reply, error = await safe_generate_content(messages, timeout=15)
                
                if success:
                    track_user_activity(chat_id, "voice_audio", update)
                    store_content_memory(chat_id, "audio", reply)
                    user_history.setdefault(chat_id, []).append({"role": "user", "content": "[sent voice 🎤]"})
                    user_history[chat_id].append({"role": "model", "content": reply})
                    await safe_edit_message(analyzing_msg, f"🎙️ <b>Audio tahlili:</b>\n\n{reply}")
                else:
                    await safe_edit_message(analyzing_msg, "❌ Audio tahlilida xatolik.")
            else:
                await safe_edit_message(analyzing_msg, "❌ Audio yuklashda xatolik.")
        
        except Exception as e:
            logger.error(f"Voice processing error: {e}")
            await safe_edit_message(analyzing_msg, "❌ Audio qayta ishlashda xatolik.")
        finally:
            if tmp_path:
                cleanup_temp_file(tmp_path)
    
    queued = await add_to_user_queue(chat_id, process_voice())
    if not queued:
        await safe_reply(update, "⚠️ Juda ko'p media yuborildi. Biroz kutib, qaytadan urinib ko'ring.")

# ─── 🎬 Video Handler with Queue Management ─────────────────
async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle video uploads with queue management"""
    if not update or not update.message or not update.message.video or not update.effective_chat:
        return
    
    video = update.message.video
    chat_id = str(update.effective_chat.id)
    
    # Check file size (Railway limit: 20MB for videos)
    if video.file_size and video.file_size > 20 * 1024 * 1024:
        await safe_reply(update, "❌ Video juda katta. Maksimal hajm: 20MB")
        return
    
    async def process_video():
        await send_typing(update)
        analyzing_msg = await safe_reply(update, "🎬 <b>Video qabul qilindi!</b>\n\n⏳ <i>Tahlil qilinmoqda...</i>")
        
        tmp_path = None
        try:
            file = await context.bot.get_file(video.file_id)
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as tmp_file:
                tmp_path = tmp_file.name
            
            await asyncio.wait_for(file.download_to_drive(custom_path=tmp_path), timeout=30)
            
            success, uploaded_file, error = await safe_upload_to_gemini(tmp_path, timeout=30)
            
            if success:
                messages = [{"role": "user", "parts": ["Analyze this video and respond warmly with emojis. Answer in Uzbek if user speaks Uzbek."]}, {"role": "user", "parts": [uploaded_file]}]
                success, reply, error = await safe_generate_content(messages, timeout=25)
                
                if success:
                    track_user_activity(chat_id, "videos", update)
                    store_content_memory(chat_id, "video", reply)
                    user_history.setdefault(chat_id, []).append({"role": "user", "content": "[sent video 🎬]"})
                    user_history[chat_id].append({"role": "model", "content": reply})
                    await safe_edit_message(analyzing_msg, f"🎬 <b>Video tahlili:</b>\n\n{reply}")
                else:
                    await safe_edit_message(analyzing_msg, "❌ Video tahlilida xatolik.")
            else:
                await safe_edit_message(analyzing_msg, "❌ Video yuklashda xatolik.")
        
        except Exception as e:
            logger.error(f"Video processing error: {e}")
            await safe_edit_message(analyzing_msg, "❌ Video qayta ishlashda xatolik.")
        finally:
            if tmp_path:
                cleanup_temp_file(tmp_path)
    
    queued = await add_to_user_queue(chat_id, process_video())
    if not queued:
        await safe_reply(update, "⚠️ Juda ko'p media yuborildi. Biroz kutib, qaytadan urinib ko'ring.")

# ─── 📌 Essential Handlers ───────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update or not update.effective_chat:
        return
        
    chat_id = str(update.effective_chat.id)
    user_history[chat_id] = []
    
    if update.effective_user:
        user = update.effective_user
        user_info[chat_id] = {
            "user_id": user.id,
            "username": user.username if user.username else None,
            "first_name": user.first_name if user.first_name else None,
            "last_name": user.last_name if user.last_name else None
        }
    
    if not update or not update.message:
        return
        
    await update.message.reply_text(
        WELCOME,
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu_keyboard()
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update or not update.message:
        return
        
    help_text = (
        "<b>🤖 AQLJON YORDAM MENU</b>\n\n"
        "🟢 <b>/start</b> — Botni qayta ishga tushirish\n"
        "🟢 <b>/help</b> — Yordam va buyruqlar roʻyxati\n"
        "🟢 <b>/search [so'z]</b> — Internetdan qidiruv\n"
        "🟢 <b>/stats</b> — Statistikani ko'rish\n\n"
        "💬 Oddiy xabar yuboring — men siz bilan suhbatlashaman!\n"
        "📷 Rasm yuboring — uni tahlil qilaman!\n"
        "🎙️ Ovoz yuboring — javob beraman!\n"
        "📄 Hujjat yuboring — tahlil qilib xulosa beraman!\n"
        "🎬 Video yuboring — ko'rib tahlil qilaman!\n\n"
        "🚀 Yanada aqlli, samimiy va foydali yordamchi bo'lishga harakat qilaman!"
    )
    
    await update.message.reply_text(help_text, parse_mode=ParseMode.HTML, reply_markup=main_menu_keyboard())

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not update or not update.message or not update.effective_chat or not update.message.text:
            return
            
        await send_typing(update)
        chat_id = str(update.effective_chat.id)
        message = update.message.text.strip()

        if message.lower().startswith("/search"):
            parts = message.split(" ", 1)
            if len(parts) == 2:
                query = parts[1].strip()
                track_user_activity(chat_id, "search_queries", update)
                result = await search_web(query)
                await send_long_message(update, f"<b>🔎 Qidiruv natijalari:</b>\n{result}")
            else:
                await safe_reply(update, "❓ Iltimos qidiruv so'rovini kiriting. Misol: <code>/search Ibn Sina</code>")
            return

        # Gemini chat with memory context
        history = user_history.setdefault(chat_id, [])
        history.append({"role": "user", "content": message})
        
        track_user_activity(chat_id, "messages", update)
        if chat_id in user_stats:
            user_stats[chat_id]["total_characters"] = user_stats[chat_id].get("total_characters", 0) + len(message)
        
        reply = await ask_gemini(history, chat_id)
        history.append({"role": "model", "content": reply})
        user_history[chat_id] = history[-MAX_HISTORY * 2:]
        await send_long_message(update, reply)
        
    except Exception as e:
        logger.error(f"Text handler error: {e}")
        await safe_reply(update, "⚙️ Hozircha javob bera olmayapman. Biroz kutib, qaytadan urinib ko'ring.")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user statistics"""
    if not update.message or not update.effective_chat:
        return
        
    chat_id = str(update.effective_chat.id)
    history = user_history.get(chat_id, [])
    user_stats_data = user_stats.get(chat_id, {})
    
    total_messages = len(history)
    user_messages = len([m for m in history if m["role"] == "user"])
    
    photos_sent = user_stats_data.get("photos", 0)
    voice_audio_sent = user_stats_data.get("voice_audio", 0)
    documents_sent = user_stats_data.get("documents", 0)
    videos_sent = user_stats_data.get("videos", 0)
    search_queries = user_stats_data.get("search_queries", 0)
    
    content_memories = len(user_content_memory.get(chat_id, []))
    
    if user_messages >= 50:
        activity_level = "🔥 Juda faol"
    elif user_messages >= 20:
        activity_level = "⚡ Faol"
    elif user_messages >= 5:
        activity_level = "💪 O'rtacha faol"
    else:
        activity_level = "🌱 Yangi foydalanuvchi"
    
    stats_text = (
        f"📊 <b>Sizning statistikangiz</b>\n\n"
        f"📈 Faollik darajasi: <b>{activity_level}</b>\n"
        f"📝 Sizning xabarlaringiz: <b>{user_messages}</b>\n"
        f"📊 Jami xabarlar: <b>{total_messages}</b>\n"
        f"🔍 Qidiruv so'rovlari: <b>{search_queries}</b>\n\n"
        f"🎨 <b>Media fayllar:</b>\n"
        f"📷 Rasmlar: <b>{photos_sent}</b>\n"
        f"🎤 Audio/Ovoz: <b>{voice_audio_sent}</b>\n"
        f"📄 Hujjatlar: <b>{documents_sent}</b>\n"
        f"🎥 Videolar: <b>{videos_sent}</b>\n\n"
        f"🧠 <b>Xotira tizimi:</b>\n"
        f"💾 Saqlangan kontentlar: <b>{content_memories}</b>\n\n"
        f"<i>🙏 AQLJON siz uchun hamisha shu yerda!</i>"
    )
    
    await send_long_message(update, stats_text)

# ─── 🚀 Enhanced Bot Startup with Railway Optimization ──────────────────────
def main():
    app = (Application.builder()
           .token(TELEGRAM_TOKEN)
           .read_timeout(20)
           .write_timeout(20)
           .connect_timeout(15)
           .pool_timeout(15)
           .build())
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("search", handle_text))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice))
    app.add_handler(MessageHandler(filters.VIDEO, handle_video))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    
    logger.info("🤖 AQLJON SmartBot is now LIVE and listening!")
    logger.info("🔧 Enhanced with deadlock prevention for Railway")
    logger.info("⚡ Queue-based sequential media processing enabled")
    logger.info("🛡️ Advanced error handling and timeout controls")
    logger.info("📊 Optimized for Railway cloud deployment")
    
    try:
        app.run_polling(
            poll_interval=1.0,
            timeout=15,
            bootstrap_retries=3
        )
    except KeyboardInterrupt:
        logger.info("🛑 Bot stopped by user")
    except Exception as e:
        logger.error(f"🚨 Bot crashed: {e}")
    finally:
        try:
            gemini_executor.shutdown(wait=False)
            logger.info("🧹 Resources cleaned up")
        except Exception:
            pass

if __name__ == "__main__":
    main()