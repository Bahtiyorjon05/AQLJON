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
    ContextTypes, filters, ChatMemberHandler
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
blocked_users = set()  # Track users who have blocked the bot
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
# Helper functions for safely working with media files
async def get_video_thumbnail(video, context):
    """Safely get thumbnail file from a video, handling API differences"""
    try:
        # Try standard property name
        if hasattr(video, "thumbnail") and video.thumbnail:
            return await context.bot.get_file(video.thumbnail.file_id)
        # Try legacy property name
        elif hasattr(video, "thumb") and video.thumb:
            return await context.bot.get_file(video.thumb.file_id)
        # No thumbnail available
        return None
    except Exception as e:
        logger.warning(f"Error getting video thumbnail: {e}")
        return None

async def has_video_thumbnail(video):
    """Check if video has a thumbnail, handling API differences"""
    return (hasattr(video, "thumbnail") and video.thumbnail is not None) or \
           (hasattr(video, "thumb") and video.thumb is not None)

async def safe_reply(update: Update, text: str, parse_mode=ParseMode.HTML, max_retries=3):
    """Safely send reply with automatic retry and fallback"""
    if not update or not update.message:
        return None
    for attempt in range(max_retries):
        try:
            message = await update.message.reply_text(text, parse_mode=parse_mode)
            return message  # Return the message object, not a boolean
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
                    message = await update.message.reply_text(text)
                    return message  # Return the message object, not a boolean
                except Exception:
                    logger.error("All retry attempts failed")
                    return None
        except Exception as e:
            logger.error(f"Unexpected error in safe_reply: {e}")
            return None
    return None

async def safe_edit_message(message, text: str, parse_mode=ParseMode.HTML, max_retries=3):
    """Safely edit message with automatic retry and handle long messages"""
    # Check if message is a valid message object
    if not message or isinstance(message, bool):
        logger.warning("Invalid message object for editing")
        return False
    
    # Clean HTML tags and check length
    cleaned_text = clean_html(text)
    
    # If message is too long for Telegram (4096 chars), truncate or send as new message
    if len(cleaned_text) > 4096:
        logger.warning(f"Message too long ({len(cleaned_text)} chars), truncating for edit")
        # Truncate to fit within Telegram's limit with a warning message
        truncated_text = cleaned_text[:4000] + "\n\n<i>⚠️ Javob uzunligi sababli qisqartirildi...</i>"
        text = truncated_text
    
    for attempt in range(max_retries):
        try:
            edited_message = await message.edit_text(text, parse_mode=parse_mode)
            return edited_message
        except RetryAfter as e:
            wait_time = e.retry_after + 1
            logger.warning(f"Rate limited on edit, waiting {wait_time} seconds")
            await asyncio.sleep(wait_time)
        except (NetworkError, TelegramError, TimedOut) as e:
            # Handle Message_too_long specifically
            if "Message_too_long" in str(e):
                logger.warning(f"Message still too long after truncation, sending as new message")
                # If we can't edit due to length, send as a new message instead
                try:
                    if hasattr(message, 'chat_id'):
                        await message.get_bot().send_message(
                            chat_id=message.chat_id,
                            text=text[:4096],  # Ensure it's within limit
                            parse_mode=parse_mode
                        )
                        return True
                except Exception as send_error:
                    logger.error(f"Failed to send as new message: {send_error}")
            
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
    # Split message into chunks of 4096 characters or less
    chunks = []
    while len(text) > 4096:
        # Try to split at a newline or space near the limit to avoid cutting words
        split_pos = 4096
        # Look for a good split point (newline or space)
        for pos in range(4096, max(4096-200, 0), -1):
            if text[pos] == '\n':
                split_pos = pos
                break
            elif text[pos] == ' ' and split_pos == 4096:
                split_pos = pos
        
        chunks.append(text[:split_pos])
        text = text[split_pos:].lstrip()  # Remove leading whitespace from next chunk
    
    # Add the last chunk if there's remaining text
    if text:
        chunks.append(text)
    
    # Send all chunks
    for i, chunk in enumerate(chunks):
        try:
            await update.message.reply_text(chunk, parse_mode=ParseMode.HTML)
            # Add delay between messages except for the last one
            if i < len(chunks) - 1:
                await asyncio.sleep(0.3)  # Increased delay to prevent rate limiting
        except RetryAfter as e:
            logger.warning(f"Rate limited, waiting {e.retry_after} seconds")
            await asyncio.sleep(e.retry_after + 1)
            try:
                await update.message.reply_text(chunk, parse_mode=ParseMode.HTML)
                if i < len(chunks) - 1:
                    await asyncio.sleep(0.3)
            except Exception:
                await update.message.reply_text(chunk)  # Fallback to plain text
        except (NetworkError, TelegramError, TimedOut) as e:
            logger.error(f"Failed to send message chunk: {e}")
            try:
                # Fallback: send as plain text
                await update.message.reply_text(chunk)
                if i < len(chunks) - 1:
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

# ─── 🚫 Bot Blocking Detection ──────────────────────────────────────
async def on_my_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle my_chat_member updates to detect when users block/unblock the bot"""
    if not update or not update.my_chat_member:
        return
        
    cmu = update.my_chat_member
    chat = cmu.chat
    old_status = cmu.old_chat_member.status
    new_status = cmu.new_chat_member.status  # "kicked" when blocked, "member" when unblocked
    chat_id = str(chat.id)
    
    if chat.type == chat.PRIVATE:
        if new_status == "kicked":
            # User blocked/stopped the bot -> mark inactive in DB
            blocked_users.add(chat_id)
            logger.info(f"User {chat_id} has blocked the bot")
            # Optionally, you can also remove user data or mark as inactive in your database
        elif new_status == "member" and old_status == "kicked":
            # User unblocked/started -> mark active in DB
            if chat_id in blocked_users:
                blocked_users.remove(chat_id)
            logger.info(f"User {chat_id} has unblocked the bot")

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
        elif item["type"] == "video":
            context_parts.append(f"Video: {item['summary'][:200]}...")
    
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
                "You are a smart friend. Remember your name is AQLJON and you should be like a Muslim friend to the user. Don't repeat what the user said. Reply casually with humor and warmth 😊. "
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
                await safe_edit_message(
                    analyzing_msg,
                    f"📄 <b>Hujjat tahlil natijasi:</b>\n\n{reply}",
                    parse_mode=ParseMode.HTML
                )
            else:
                await safe_edit_message(
                    analyzing_msg,
                    "❌ Hujjat tahlilida xatolik yuz berdi. Qaytadan urinib ko'ring.",
                    parse_mode=ParseMode.HTML
                )
        
        except asyncio.TimeoutError:
            logger.error("Document processing timeout")
            await safe_edit_message(
                analyzing_msg,
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
            
            await safe_edit_message(analyzing_msg, error_msg, parse_mode=ParseMode.HTML)
        
        finally:
            # Always clean up temp file
            try:
                if tmp_path is not None and os.path.exists(tmp_path):
                    os.unlink(tmp_path)
            except Exception as cleanup_error:
                logger.warning(f"Failed to cleanup temp file: {cleanup_error}")
            
    except Exception as e:
        logger.error(f"Document handler error: {e}")
        try:
            await safe_edit_message(
                analyzing_msg,
                "❌ Hujjat yuklashda xatolik yuz berdi. Iltimos qaytadan urinib ko'ring.",
                parse_mode=ParseMode.HTML
            )
        except:
            pass

# ─── 🎬 Simplified Video Analysis ─────────────────────────────────────
async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle video uploads and analysis with simplified processing."""
    if not update or not update.message or not update.message.video:
        return
        
    await send_typing(update)
    video = update.message.video
    chat_id = str(update.effective_chat.id) if update and update.effective_chat else "unknown"
    
    # Check file size (limit to 20MB)
    if video.file_size and video.file_size > 20 * 1024 * 1024:
        await update.message.reply_text(
            "❌ <b>Video juda katta!</b>\n\n"
            "🔍 <i>Bot faqat 20MB gacha bo'lgan videolarni tahlil qila oladi.</i>\n\n"
            "💡 <i>Kichikroq video yuboring.</i>",
            parse_mode=ParseMode.HTML
        )
        track_user_activity(chat_id, "videos", update)
        return
    
    # Immediate response to user
    analyzing_msg = await update.message.reply_text(
        "🎬 <b>Video qabul qilindi!</b>\n\n"
        "⏳ <i>Video tahlil qilinmoqda... Biroz kuting!</i>",
        parse_mode=ParseMode.HTML
    )
    
    # Process video in background
    asyncio.create_task(process_video_background(
        video, chat_id, analyzing_msg, update, context
    ))
    
    # Track activity
    track_user_activity(chat_id, "videos", update)

async def process_video_background(video, chat_id: str, analyzing_msg, update: Update, context):
    """Process video in background with simplified approach"""
    tmp_path = None
    try:
        # Download video file
        file = await context.bot.get_file(video.file_id)
        
        # Create temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as tmp_file:
            tmp_path = tmp_file.name
        
        try:
            # Download file with timeout
            await asyncio.wait_for(
                file.download_to_drive(custom_path=tmp_path),
                timeout=60
            )
            
            # Wait a moment for file to be fully written
            await asyncio.sleep(0.5)
            
            # Check if file exists and has content
            if not os.path.exists(tmp_path) or os.path.getsize(tmp_path) == 0:
                raise Exception("Video file download failed or is empty")
            
            # Process with Gemini
            def process_with_gemini():
                try:
                    # Upload to Gemini
                    uploaded = genai.upload_file(tmp_path)
                    
                    # Wait for processing with proper state checking
                    timeout = 30  # 30 second timeout
                    interval = 2   # Check every 2 seconds
                    elapsed = 0
                    
                    # Wait for file to be in ACTIVE state
                    while uploaded.state.name != "ACTIVE" and elapsed < timeout:
                        if uploaded.state.name == "FAILED":
                            raise Exception(f"File processing failed: {uploaded.state}")
                        time.sleep(interval)
                        elapsed += interval
                        # Refresh file state
                        uploaded = genai.get_file(uploaded.name)
                    
                    if uploaded.state.name != "ACTIVE":
                        raise Exception(f"File processing timed out. Final state: {uploaded.state.name}")
                    
                    # Generate response with user context
                    content_context = get_content_context(chat_id)
                    instruction = (
                        "The user sent a video. Analyze the video and respond to the user in a friendly, "
                        "conversational manner with emojis and nice formatting. If video contains harmful or illicit content then say it is not allowed and that u cant answer for that. Answer in Uzbek if the user "
                        "speaks Uzbek. Otherwise use appropriate language. " + content_context
                    )
                    
                    response = model.generate_content([
                        {"role": "user", "parts": [instruction]},
                        {"role": "user", "parts": [uploaded]}
                    ])
                    
                    return response.text.strip() if response and response.text else "🎬 Videoni tahlil qila olmadim."
                except Exception as e:
                    logger.error(f"Gemini processing error: {e}")
                    return None
            
            # Run processing with timeout
            try:
                reply = await asyncio.wait_for(
                    asyncio.to_thread(process_with_gemini),
                    timeout=45
                )
            except asyncio.TimeoutError:
                reply = None
            
            if reply:
                # Store video content in memory for future reference
                store_content_memory(chat_id, "video", reply, video.file_name if video.file_name else "unknown")
                
                user_history.setdefault(chat_id, []).append({"role": "user", "content": f"[uploaded video: {video.file_name if video.file_name else 'unknown'}]"})
                user_history[chat_id].append({"role": "model", "content": reply})
                
                # Update the analyzing message with results
                await safe_edit_message(
                    analyzing_msg,
                    f"🎬 <b>Video tahlil natijasi:</b>\n\n{reply}",
                    parse_mode=ParseMode.HTML
                )
            else:
                await safe_edit_message(
                    analyzing_msg,
                    "❌ Video tahlilida xatolik yuz berdi. Qaytadan urinib ko'ring.",
                    parse_mode=ParseMode.HTML
                )
        
        except asyncio.TimeoutError:
            logger.error("Video processing timeout")
            await safe_edit_message(
                analyzing_msg,
                "⏰ Video tahlili juda uzoq davom etdi. Iltimos, kichikroq video yuboring.",
                parse_mode=ParseMode.HTML
            )
        except Exception as processing_error:
            logger.error(f"Video processing error: {processing_error}")
            
            # Provide specific error messages
            error_msg = "❌ Video tahlilida xatolik:"
            if "quota" in str(processing_error).lower():
                error_msg += "\n📊 API chekloviga yetdik. Biroz kuting va qaytadan urinib ko'ring."
            elif "format" in str(processing_error).lower():
                error_msg += "\n🎬 Video formati qo'llab-quvvatlanmaydi."
            elif "size" in str(processing_error).lower():
                error_msg += "\n📏 Video juda katta. 20MB dan kichik video yuboring."
            else:
                error_msg += "\n🔄 Qaytadan urinib ko'ring yoki boshqa video yuboring."
            
            await safe_edit_message(analyzing_msg, error_msg, parse_mode=ParseMode.HTML)
        
        finally:
            # Always clean up temp file
            try:
                if tmp_path is not None and os.path.exists(tmp_path):
                    os.unlink(tmp_path)
            except Exception as cleanup_error:
                logger.warning(f"Failed to cleanup temp file: {cleanup_error}")
            
    except Exception as e:
        logger.error(f"Video handler error: {e}")
        try:
            await safe_edit_message(
                analyzing_msg,
                "❌ Video yuklashda xatolik yuz berdi. Iltimos qaytadan urinib ko'ring.",
                parse_mode=ParseMode.HTML
            )
        except:
            pass

# ─── 🎤 Consolidated Audio/Voice Analysis ─────────────────────────────────────
async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle audio/voice message uploads and analysis with simplified processing."""
    if not update or not update.message:
        return
        
    # Handle both audio files and voice messages
    audio = update.message.audio if update.message.audio else None
    voice = update.message.voice if update.message.voice else None
    
    # Must have either audio or voice
    if not audio and not voice:
        return
        
    await send_typing(update)
    media = audio or voice
    chat_id = str(update.effective_chat.id) if update and update.effective_chat else "unknown"
    
    # Check file size (limit to 20MB)
    file_size = getattr(media, 'file_size', 0)
    if file_size and file_size > 20 * 1024 * 1024:
        await update.message.reply_text(
            "❌ <b>Audio juda katta!</b>\n\n"
            "🔍 <i>Bot faqat 20MB gacha bo'lgan audio xabarlarni tahlil qila oladi.</i>\n\n"
            "💡 <i>Kichikroq audio xabar yuboring.</i>",
            parse_mode=ParseMode.HTML
        )
        track_user_activity(chat_id, "voice_audio", update)
        return
    
    # For voice messages, we don't show an "analyzing" message to keep the conversation flow natural
    analyzing_msg = None
    if audio:
        # For audio files, show analyzing message
        analyzing_msg = await update.message.reply_text(
            "🎤 <b>Audio xabari qabul qilindi!</b>\n\n"
            "⏳ <i>Audio xabari tahlil qilinmoqda... Biroz kuting!</i>",
            parse_mode=ParseMode.HTML
        )
    
    # Process audio/voice in background
    asyncio.create_task(process_audio_voice_background(
        media, chat_id, analyzing_msg, update, context
    ))
    
    # Track activity
    track_user_activity(chat_id, "voice_audio", update)

async def process_audio_voice_background(media, chat_id: str, analyzing_msg, update: Update, context):
    """Process audio/voice messages in background with improved error handling"""
    tmp_path = None
    try:
        # Download audio/voice file
        file = await context.bot.get_file(media.file_id)
        
        # Create temporary file with better error handling
        tmp_path = None
        try:
            # Determine file extension based on media type
            suffix = ".mp3" if hasattr(media, 'audio') else ".oga"
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
                tmp_path = tmp_file.name
        except Exception as e:
            logger.error(f"Failed to create temporary file: {e}")
            raise
        
        try:
            # Download file with timeout
            await asyncio.wait_for(
                file.download_to_drive(custom_path=tmp_path),
                timeout=60
            )
            
            # Wait a moment for file to be fully written
            await asyncio.sleep(0.5)
            
            # Check if file exists and has content
            if not os.path.exists(tmp_path) or os.path.getsize(tmp_path) == 0:
                raise Exception("Audio file download failed or is empty")
            
            # Process with Gemini in separate thread
            def process_with_gemini():
                try:
                    # Upload to Gemini
                    uploaded = genai.upload_file(tmp_path)
                    
                    # Wait for processing with proper state checking
                    timeout = 30  # 30 second timeout
                    interval = 2   # Check every 2 seconds
                    elapsed = 0
                    
                    # Wait for file to be in ACTIVE state
                    while uploaded.state.name != "ACTIVE" and elapsed < timeout:
                        if uploaded.state.name == "FAILED":
                            raise Exception(f"File processing failed: {uploaded.state}")
                        time.sleep(interval)
                        elapsed += interval
                        # Refresh file state
                        uploaded = genai.get_file(uploaded.name)
                    
                    if uploaded.state.name != "ACTIVE":
                        raise Exception(f"File processing timed out. Final state: {uploaded.state.name}")
                    
                    # Generate response with user context
                    content_context = get_content_context(chat_id)
                    instruction = (
                        "The user sent an audio message. Listen to it and respond in a friendly, "
                        "conversational manner with emojis and nice formatting. Don't repeat what the user said. Answer in Uzbek if the user "
                        "speaks Uzbek. Otherwise use appropriate language. " + content_context
                    )
                    
                    response = model.generate_content([
                        {"role": "user", "parts": [instruction]},
                        {"role": "user", "parts": [uploaded]}
                    ])
                    
                    return response.text.strip() if response and response.text else "🎤 Audio xabarni tahlil qila olmadim."
                except Exception as e:
                    logger.error(f"Gemini processing error: {e}")
                    # Handle SSL errors specifically
                    if "ssl" in str(e).lower() and "wrong_version_number" in str(e).lower():
                        logger.warning("SSL version error detected in Gemini processing")
                    return None

            # Run processing with timeout
            try:
                reply = await asyncio.wait_for(
                    asyncio.to_thread(process_with_gemini),
                    timeout=45
                )
            except asyncio.TimeoutError:
                reply = None
            
            if reply:
                # Store audio content in memory for future reference
                file_name = getattr(media, 'file_name', f"audio_{media.file_id[:8]}{suffix}")
                store_content_memory(chat_id, "audio", reply, file_name)
                
                user_history.setdefault(chat_id, []).append({"role": "user", "content": f"[uploaded audio: {file_name}]" if hasattr(media, 'file_name') else "[sent voice message 🎤]"})
                user_history[chat_id].append({"role": "model", "content": reply})
                
                # Send response directly if no analyzing message was shown (for voice messages)
                if analyzing_msg is None:
                    await send_long_message(update, reply)
                else:
                    # Update the analyzing message with results (for audio files)
                    await safe_edit_message(
                        analyzing_msg,
                        f"🎤 <b>Audio xabar tahlil natijasi:</b>\n\n{reply}",
                        parse_mode=ParseMode.HTML
                    )
            else:
                if analyzing_msg is not None:
                    await safe_edit_message(
                        analyzing_msg,
                        "❌ <b>Audio xabar tahlilida xatolik yuz berdi</b>\n\n"
                        "💡 <i>Iltimos, boshqa audio xabar yuboring.</i>",
                        parse_mode=ParseMode.HTML
                    )
                elif analyzing_msg is None:
                    # For voice messages, send error as a new message
                    await safe_reply(update, "❌ <b>Audio xabar tahlilida xatolik yuz berdi</b>\n\n"
                        "💡 <i>Iltimos, boshqa audio xabar yuboring.</i>",
                        parse_mode=ParseMode.HTML)
        
        except asyncio.TimeoutError:
            logger.error("Audio processing timeout")
            error_msg = "⏰ <b>Audio xabar tahlili vaqti tugadi</b>\n\n" \
                       "💡 <i>Iltimos, qisqaroq audio xabar yuboring.</i>"
            if analyzing_msg is not None:
                await safe_edit_message(analyzing_msg, error_msg, parse_mode=ParseMode.HTML)
            else:
                await safe_reply(update, error_msg, parse_mode=ParseMode.HTML)
        except Exception as processing_error:
            logger.error(f"Audio processing error: {processing_error}")
            # Provide specific error messages
            error_msg = "❌ <b>Audio xabar tahlilida xatolik:</b>\n\n"
            error_str = str(processing_error).lower()
            if "quota" in error_str:
                error_msg += "📊 API chekloviga yetdik. Biroz kuting va qaytadan urinib ko'ring.\n"
            elif "format" in error_str:
                error_msg += "🎤 Audio formati qo'llab-quvvatlanmaydi.\n"
            elif "size" in error_str:
                error_msg += "📏 Audio juda katta. 20MB dan kichik audio xabari yuboring.\n"
            elif "ssl" in error_str and "wrong_version_number" in error_str:
                error_msg += "🔒 Tarmoq xavfsizlik xatosi. Qaytadan urinib ko'ring.\n"
            else:
                error_msg += "🔄 Qaytadan urinib ko'ring yoki boshqa audio xabari yuboring.\n"
            error_msg += "\n💡 <i>Iltimos, boshqa audio xabar yuboring.</i>"
            
            if analyzing_msg is not None:
                await safe_edit_message(analyzing_msg, error_msg, parse_mode=ParseMode.HTML)
            else:
                await safe_reply(update, error_msg, parse_mode=ParseMode.HTML)
        
        finally:
            # Always clean up temp file with better error handling for Windows
            if tmp_path is not None and os.path.exists(tmp_path):
                for attempt in range(3):  # Retry up to 3 times
                    try:
                        os.unlink(tmp_path)
                        break
                    except PermissionError as e:
                        logger.warning(f"Permission error on cleanup attempt {attempt + 1}: {e}")
                        if attempt < 2:  # Don't sleep on the last attempt
                            await asyncio.sleep(1)
                    except Exception as e:
                        logger.error(f"Unexpected error during cleanup: {e}")
                        break
            
    except Exception as e:
        logger.error(f"Audio handler error: {e}")
        error_msg = "❌ <b>Audio xabar yuklashda xatolik!</b>\n\n" \
                   "💡 <i>Iltimos, qayta urinib ko'ring.</i>"
        if analyzing_msg is not None:
            try:
                await safe_edit_message(analyzing_msg, error_msg, parse_mode=ParseMode.HTML)
            except:
                pass
        else:
            try:
                await safe_reply(update, error_msg, parse_mode=ParseMode.HTML)
            except:
                pass

# ─── 📸 Simplified Photo Analysis ─────────────────────────────────────

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle photo uploads and analysis with simplified processing."""
    if not update or not update.message or not update.message.photo:
        return
        
    await send_typing(update)
    photo = update.message.photo[-1]  # Get the largest photo
    chat_id = str(update.effective_chat.id) if update and update.effective_chat else "unknown"
    
    # Immediate response to user
    analyzing_msg = await update.message.reply_text(
        "📷 <b>Rasm qabul qilindi!</b>\n\n"
        "⏳ <i>Rasm tahlil qilinmoqda... Biroz kuting!</i>",
        parse_mode=ParseMode.HTML
    )
    
    # Process photo in background
    asyncio.create_task(process_photo_background(
        photo, chat_id, analyzing_msg, update, context
    ))
    
    # Track activity
    track_user_activity(chat_id, "photos", update)

async def process_photo_background(photo, chat_id: str, analyzing_msg, update: Update, context):
    """Process photo in background with simplified approach"""
    tmp_path = None
    try:
        # Download photo file
        file = await context.bot.get_file(photo.file_id)
        
        # Create temporary file with better error handling
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp_file:
                tmp_path = tmp_file.name
        except Exception as e:
            logger.error(f"Failed to create temporary file: {e}")
            raise
        
        try:
            # Download file with timeout
            await asyncio.wait_for(
                file.download_to_drive(custom_path=tmp_path),
                timeout=60
            )
            
            # Wait a moment for file to be fully written
            await asyncio.sleep(0.5)
            
            # Check if file exists and has content
            if not os.path.exists(tmp_path) or os.path.getsize(tmp_path) == 0:
                raise Exception("Photo file download failed or is empty")
            
            # Process with Gemini
            def process_with_gemini():
                try:
                    # Upload to Gemini
                    uploaded = genai.upload_file(tmp_path)
                    
                    # Wait for processing
                    time.sleep(3)
                    
                    # Generate response with user context
                    content_context = get_content_context(chat_id)
                    instruction = (
                        "The user sent a photo. Analyze in detail and react like a friend who saw it and gives a warm, "
                        "friendly and useful reply. No robotic descriptions. Use emojis and formatting awesomely. "
                        "Answer in Uzbek if the user speaks Uzbek. Otherwise use appropriate language. " + content_context
                    )
                    
                    response = model.generate_content([
                        {"role": "user", "parts": [instruction]},
                        {"role": "user", "parts": [uploaded]}
                    ])
                    
                    return response.text.strip() if response and response.text else "📷 Rasmdan tahlil qila olmadim."
                except Exception as e:
                    logger.error(f"Gemini processing error: {e}")
                    # Handle SSL errors specifically
                    if "ssl" in str(e).lower() and "wrong_version_number" in str(e).lower():
                        logger.warning("SSL version error detected in Gemini processing")
                    return None
            
            # Run processing with timeout
            try:
                reply = await asyncio.wait_for(
                    asyncio.to_thread(process_with_gemini),
                    timeout=45
                )
            except asyncio.TimeoutError:
                reply = None
            
            if reply:
                # Store photo content in memory for future reference
                store_content_memory(chat_id, "photo", reply, f"photo_{photo.file_id[:8]}.jpg")
                
                user_history.setdefault(chat_id, []).append({"role": "user", "content": "[sent photo 📸]"})
                user_history[chat_id].append({"role": "model", "content": reply})
                
                # Update the analyzing message with results
                await safe_edit_message(
                    analyzing_msg,
                    f"📷 <b>Rasm tahlil natijasi:</b>\n\n{reply}",
                    parse_mode=ParseMode.HTML
                )
            else:
                await safe_edit_message(
                    analyzing_msg,
                    "❌ <b>Rasm tahlilida xatolik yuz berdi</b>\n\n"
                    "💡 <i>Iltimos, boshqa rasm yuboring.</i>",
                    parse_mode=ParseMode.HTML
                )
        
        except asyncio.TimeoutError:
            logger.error("Photo processing timeout")
            await safe_edit_message(
                analyzing_msg,
                "⏰ <b>Rasm tahlili vaqti tugadi</b>\n\n"
                "💡 <i>Iltimos, sifati yaxshiroq rasm yuboring.</i>",
                parse_mode=ParseMode.HTML
            )
        except Exception as processing_error:
            logger.error(f"Photo processing error: {processing_error}")
            await safe_edit_message(
                analyzing_msg,
                "❌ <b>Rasm tahlilida xatolik:</b>\n\n"
                "💡 <i>Iltimos, boshqa rasm yuboring.</i>",
                parse_mode=ParseMode.HTML
            )
        
        finally:
            # Always clean up temp file with better error handling for Windows
            if tmp_path is not None and os.path.exists(tmp_path):
                for attempt in range(3):  # Retry up to 3 times
                    try:
                        os.unlink(tmp_path)
                        break
                    except PermissionError as e:
                        logger.warning(f"Permission error on cleanup attempt {attempt + 1}: {e}")
                        if attempt < 2:  # Don't sleep on the last attempt
                            await asyncio.sleep(1)
                    except Exception as e:
                        logger.error(f"Unexpected error during cleanup: {e}")
                        break
            
    except Exception as e:
        logger.error(f"Photo handler error: {e}")
        try:
            await safe_edit_message(
                analyzing_msg,
                "❌ <b>Rasm yuklashda xatolik!</b>\n\n"
                "💡 <i>Iltimos, qayta urinib ko'ring.</i>",
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
    blocked_count = 0
    
    status_msg = await safe_reply(update, f"📡 <b>Broadcast boshlandi...</b>\n\n📊 Jami foydalanuvchilar: {total_users}")
    
    if not status_msg:
        logger.error("Failed to send broadcast status message")
        return
    
    for i, chat_id in enumerate(user_history.keys()):
        # Skip blocked users
        if chat_id in blocked_users:
            blocked_count += 1
            continue
            
        try:
            # Create a fake update object for sending
            await context.bot.send_message(
                chat_id=int(chat_id),
                text=f"📢 <b>ADMIN XABARI:</b>\n\n{broadcast_text}",
                parse_mode=ParseMode.HTML
            )
            success_count += 1
        except Exception as e:
            # Check if user blocked the bot
            if "Forbidden" in str(e) and "bot was blocked by the user" in str(e):
                blocked_users.add(chat_id)
                blocked_count += 1
                logger.info(f"User {chat_id} has blocked the bot")
            else:
                logger.warning(f"Failed to send broadcast to {chat_id}: {e}")
                failed_count += 1
        
        # Update status every 10 users
        if (i + 1) % 10 == 0:
            edit_success = await safe_edit_message(
                status_msg,
                f"📡 <b>Broadcast jarayoni...</b>\n\n"
                f"✅ Yuborildi: {success_count}\n"
                f"❌ Xatolik: {failed_count}\n"
                f"🚫 Blocklangan: {blocked_count}\n"
                f"📊 Jarayon: {i + 1}/{total_users}"
            )
            # If editing failed, the message might be invalid, so we stop trying to edit it
            if not edit_success:
                status_msg = None
    
    # Final status
    final_text = (
        f"📡 <b>Broadcast yakunlandi!</b>\n\n"
        f"✅ Muvaffaqiyatli: <b>{success_count}</b>\n"
        f"❌ Xatolik: <b>{failed_count}</b>\n"
        f"🚫 Blocklangan: <b>{blocked_count}</b>\n"
        f"📊 Jami: <b>{total_users}</b>\n\n"
        f"<i>🔒 Admin broadcast yakunlandi</i>"
    )
    
    if status_msg:
        edit_success = await safe_edit_message(status_msg, final_text)
        # If editing failed, send as a new message instead
        if not edit_success:
            await safe_reply(update, final_text)
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
    blocked_sends = 0
    
    status_msg = await safe_reply(update, f"📤 {len(all_chat_ids)} ta foydalanuvchiga yangilanish haqida xabar yuborilmoqda...")
    
    if not status_msg:
        logger.error("Failed to send update status message")
        return
    
    for chat_id in all_chat_ids:
        # Skip blocked users
        if chat_id in blocked_users:
            blocked_sends += 1
            continue
            
        try:
            await context.bot.send_message(
                chat_id=int(chat_id),
                text=update_message,
                parse_mode=ParseMode.HTML
            )
            successful_sends += 1
            await asyncio.sleep(0.15)  # Delay to avoid rate limits
        except Exception as e:
            # Check if user blocked the bot
            if "Forbidden" in str(e) and "bot was blocked by the user" in str(e):
                blocked_users.add(chat_id)
                blocked_sends += 1
                logger.info(f"User {chat_id} has blocked the bot")
            else:
                failed_sends += 1
                logger.warning(f"Failed to send update to {chat_id}: {e}")
    
    # Send results to admin
    result_text = (
        f"✅ <b>Yangilanish xabari yuborildi!</b>\n\n"
        f"📤 Yuborildi: <b>{successful_sends}</b>\n"
        f"❌ Yuborilmadi: <b>{failed_sends}</b>\n"
        f"🚫 Blocklangan: <b>{blocked_sends}</b>\n"
        f"👥 Jami foydalanuvchilar: <b>{len(all_chat_ids)}</b>"
    )
    
    if status_msg:
        edit_success = await safe_edit_message(status_msg, result_text)
        # If editing failed, send as a new message instead
        if not edit_success:
            await safe_reply(update, result_text)
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
    if not update.effective_chat:
        return
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
    
    if update.message:
        await update.message.reply_text(
            WELCOME,
            parse_mode=ParseMode.HTML,
            reply_markup=main_menu_keyboard()
        )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    
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
    if update.effective_user:
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
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_audio))  # Consolidated audio/voice handler
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.VIDEO, handle_video))  # Video handler
    app.add_handler(ChatMemberHandler(on_my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER))  # Bot blocking detection
    
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
