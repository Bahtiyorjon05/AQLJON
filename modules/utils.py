import re
import asyncio
import logging
import tempfile
import time
from datetime import datetime, timedelta
from io import BytesIO
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.constants import ChatAction, ParseMode
from telegram.error import NetworkError, TelegramError, TimedOut, RetryAfter

# ─── 📝 Logging Setup ────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# ─── 🛡️ Safe Communication Functions ──────────────────────────────────────
async def safe_reply(update: Update, text: str, parse_mode=ParseMode.HTML, max_retries=1):
    """Safely send reply with automatic retry and fallback - optimized for faster response"""
    if not update or not update.message:
        return None
    
    # For keyboard button selections, we want immediate response with no retries
    # to ensure snappy UI feedback
    try:
        message = await update.message.reply_text(text, parse_mode=parse_mode)
        return message
    except (NetworkError, TelegramError, TimedOut) as e:
        logger.warning(f"Telegram error on immediate reply: {e}")
        # Try once more with plain text as fallback
        try:
            message = await update.message.reply_text(text)
            return message
        except Exception:
            logger.error("Fallback reply also failed")
            return None
    except Exception as e:
        logger.error(f"Unexpected error in safe_reply: {e}")
        return None

async def safe_edit_message(message, text: str, parse_mode=ParseMode.HTML, max_retries=3, reply_markup=None):
    """Safely edit message with automatic retry and handle long messages"""
    # Check if message is a valid message object
    if not message or isinstance(message, bool):
        logger.warning("Invalid message object for editing")
        return False
    
    # Check length without cleaning HTML to preserve formatting
    # cleaned_text = clean_html(text)  # Commented out to preserve HTML formatting
    cleaned_text = text
    
    # If message is too long for Telegram (4096 chars), send as new messages instead
    if len(cleaned_text) > 4096:
        logger.info(f"Message too long ({len(cleaned_text)} chars), sending as new messages instead of editing")
        # Delete the original message first
        try:
            await message.delete()
        except Exception as e:
            logger.warning(f"Could not delete original message: {e}")
        
        # Send as new long message
        update = Update(0, message=message)
        await send_long_message(update, text, parse_mode=parse_mode)
        return True
    
    for attempt in range(max_retries):
        try:
            if reply_markup:
                edited_message = await message.edit_text(text, parse_mode=parse_mode, reply_markup=reply_markup)
            else:
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

def send_fast_reply(message, text: str, parse_mode=ParseMode.HTML, reply_markup=None):
    """Send a fast reply without blocking by using asyncio.create_task - optimized for maximum speed"""
    try:
        # Create a background task for sending the reply with highest priority
        task = asyncio.create_task(_send_reply_background(message, text, parse_mode, reply_markup))
        # Don't wait for the task to complete - return immediately for maximum responsiveness
        return task
    except Exception as e:
        logger.warning(f"Failed to send fast reply: {e}")
        # Fallback to regular reply if fast reply fails
        try:
            task = asyncio.create_task(_send_reply_fallback(message, text, parse_mode, reply_markup))
            return task
        except Exception as fallback_error:
            logger.error(f"Fallback reply also failed: {fallback_error}")
            return None

async def _send_reply_background(message, text: str, parse_mode=ParseMode.HTML, reply_markup=None):
    """Background task for sending replies - optimized for speed"""
    try:
        if reply_markup:
            await message.reply_text(text, parse_mode=parse_mode, reply_markup=reply_markup)
        else:
            await message.reply_text(text, parse_mode=parse_mode)
    except Exception as e:
        logger.warning(f"Background reply failed: {e}")

async def _send_reply_fallback(message, text: str, parse_mode=ParseMode.HTML, reply_markup=None):
    """Fallback task for sending replies - optimized for speed"""
    try:
        if reply_markup:
            await message.reply_text(text, parse_mode=parse_mode, reply_markup=reply_markup)
        else:
            await message.reply_text(text, parse_mode=parse_mode)
    except Exception as e:
        logger.error(f"Fallback reply failed: {e}")

# ─── 📦 Utilities ──────────────────────────────────────────────
async def send_typing(update: Update):
    """Send typing indicator to user"""
    if not update or not update.message or not update.message.chat:
        return
    try:
        await update.message.chat.send_action(action=ChatAction.TYPING)
    except (NetworkError, TelegramError, TimedOut) as e:
        logger.warning(f"Failed to send typing indicator: {e}")
    except Exception as e:
        logger.error(f"Unexpected error in send_typing: {e}")

def clean_html(text: str) -> str:
    """Remove potentially problematic HTML tags"""
    return re.sub(r'</?(ul|li|div|span|h\d|blockquote|table|tr|td|th)[^>]*>', '', text)

async def send_long_message(update: Update, text: str, parse_mode=ParseMode.HTML):
    if not update or not update.effective_message:
        return
    # Don't clean HTML for media responses as they need formatting
    # text = clean_html(text)  # Commented out to preserve HTML formatting
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
            await update.effective_message.reply_text(chunk, parse_mode=parse_mode)
            # Add delay between messages except for the last one
            if i < len(chunks) - 1:
                await asyncio.sleep(0.3)  # Increased delay to prevent rate limiting
        except RetryAfter as e:
            logger.warning(f"Rate limited, waiting {e.retry_after} seconds")
            await asyncio.sleep(e.retry_after + 1)
            try:
                await update.effective_message.reply_text(chunk, parse_mode=parse_mode)
                if i < len(chunks) - 1:
                    await asyncio.sleep(0.3)
            except Exception:
                await update.effective_message.reply_text(chunk)  # Fallback to plain text
        except (NetworkError, TelegramError, TimedOut) as e:
            logger.error(f"Failed to send message chunk: {e}")
            try:
                # Fallback: send as plain text
                await update.effective_message.reply_text(chunk)
                if i < len(chunks) - 1:
                    await asyncio.sleep(0.3)
            except Exception as fallback_error:
                logger.error(f"Fallback message also failed: {fallback_error}")
                break
        except Exception as e:
            logger.error(f"Unexpected error in send_long_message: {e}")
            break

# ─── 📋 Keyboard Functions ────────────────────────────────────
def main_menu_keyboard():
    """Create main menu keyboard"""
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("🔄 Qayta ishga tushirish"), KeyboardButton("ℹ️ Yordam")],
            [KeyboardButton("🔍 Qidiruv"), KeyboardButton("📊 Statistika")],
            [KeyboardButton("📞 Aloqa"), KeyboardButton("🌍 Joylashuv")],
            [KeyboardButton("📑 Hujjatlar tuzish")]
        ],
        resize_keyboard=True, one_time_keyboard=True,
    )

def document_generation_keyboard():
    """Create document generation keyboard"""
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("📄 PDF fayl"), KeyboardButton("📊 Excel fayl")],
            [KeyboardButton("📝 Word hujjat"), KeyboardButton("📽️ PowerPoint slayd")],
            [KeyboardButton("🏠 Bosh menyu")]
        ],
        resize_keyboard=True, one_time_keyboard=True,
    )

def location_initial_keyboard():
    """Create initial location keyboard - only share location or search by city"""
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("📍 Mening joylashuvim", request_location=True)],
            [KeyboardButton("🏙️ Shahar bo'yicha qidirish")],
            [KeyboardButton("🏠 Bosh menyu")]
        ],
        resize_keyboard=True, one_time_keyboard=False,
    )

def location_services_keyboard():
    """Create location services keyboard - main services only"""
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("🕋 Namoz vaqtlari")],
            [KeyboardButton("📍 Yaqin-atrofim"), KeyboardButton("⭐ Sevimli joylarim")],
            [KeyboardButton("⬅️ Orqaga"), KeyboardButton("🏠 Bosh menyu")]
        ],
        resize_keyboard=True, one_time_keyboard=False,
    )