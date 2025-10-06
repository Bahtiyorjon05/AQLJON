import asyncio
import logging
import time
import google.generativeai as genai
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ChatMemberHandler
from telegram.error import NetworkError

from modules.config import Config
from modules.memory import MemoryManager
from modules.utils import main_menu_keyboard
from modules.doc_generation.document_generator import DocumentGenerator
from modules.audio_handler import AudioHandler
from modules.video_handler import VideoHandler
from modules.pic_handler import PhotoHandler
from modules.doc_handler import DocumentHandler
from modules.command_handlers import CommandHandlers

# ─── 📝 Logging ────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# ─── 🤖 Gemini Setup ───────────────────────────────────────────
Config.validate()
genai.configure(api_key=Config.GEMINI_KEY)
model = genai.GenerativeModel("gemini-2.5-flash")

# ─── 🧠 Memory Management ─────────────────────────────────────────────────
memory_manager = MemoryManager(
    max_history=Config.MAX_HISTORY,
    max_content_memory=Config.MAX_CONTENT_MEMORY,
    max_users=Config.MAX_USERS_IN_MEMORY,
    max_inactive_days=Config.MAX_INACTIVE_DAYS
)

# ─── 📄 Document Generator ─────────────────────────────────────────────────
doc_generator = DocumentGenerator(model, memory_manager)

# ─── 🎛️ Media Handlers ─────────────────────────────────────────────────
audio_handler = AudioHandler(model, memory_manager)
video_handler = VideoHandler(model, memory_manager)
photo_handler = PhotoHandler(model, memory_manager)
doc_handler = DocumentHandler(model, memory_manager)

# ─── 🔍 Web Search Integration ─────────────────────────────────────────────────
async def search_web(query: str) -> str:
    """Search the web using Serper API"""
    try:
        # Check if SERPER_KEY is available
        if not Config.SERPER_KEY:
            return "❌ Qidiruv xizmati sozlanmagan."
        
        import httpx
        async with httpx.AsyncClient(timeout=10.0) as client:  # Add timeout for better performance
            response = await client.post(
                "https://google.serper.dev/search",
                headers={"X-API-KEY": str(Config.SERPER_KEY), "Content-Type": "application/json"},
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

# ─── 📋 Command Handlers ─────────────────────────────────────────────────
command_handlers = CommandHandlers(memory_manager, doc_generator, search_web)

# ─── 🚫 Bot Blocking Detection ─────────────────────────────────────────────────
async def on_my_chat_member(update, context):
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
            memory_manager.block_user(chat_id)
            logger.info(f"User {chat_id} has blocked the bot")
        elif new_status == "member" and old_status == "kicked":
            # User unblocked/started -> mark active in DB
            memory_manager.unblock_user(chat_id)
            logger.info(f"User {chat_id} has unblocked the bot")
            
            # Track user activity to ensure they appear in admin stats
            # Create a mock update object for tracking
            class MockUser:
                def __init__(self, user_id):
                    self.id = user_id
                    self.username = None
                    self.first_name = None
                    self.last_name = None
                    self.is_bot = False
            
            class MockChat:
                def __init__(self, chat_id):
                    self.id = int(chat_id)
            
            class MockEffectiveUser:
                def __init__(self, chat_id):
                    self.id = int(chat_id)
                    self.username = None
                    self.first_name = None
                    self.last_name = None
                    self.is_bot = False
            
            class MockUpdate:
                def __init__(self, chat_id):
                    self.effective_user = MockEffectiveUser(chat_id)
                    self.effective_chat = MockChat(chat_id)
            
            mock_update = MockUpdate(chat_id)
            memory_manager.track_user_activity(chat_id, "messages", mock_update)

# ─── 🔄 Enhanced Concurrent Handler Wrappers ─────────────────────────────────────────────────
# These wrappers ensure that all handlers run in the background without blocking other users
async def concurrent_text_handler(update, context):
    """Handle text messages with enhanced concurrency"""
    # Import here to get the singleton instance
    from modules.location_features.location_handler import get_location_handler
    location_handler = get_location_handler()
    
    # Check if user is in a location-specific state
    if context.user_data and (
        context.user_data.get('awaiting_city_name') or 
        context.user_data.get('awaiting_favorite_name') or 
        context.user_data.get('awaiting_favorite_location')
    ):
        # Route to location handler for location-specific states
        task = asyncio.create_task(location_handler.handle_text_message(update, context))
    else:
        # For other text messages, use the general command handler
        task = asyncio.create_task(command_handlers.handle_text(update, context))
    
    # Add error handling for the task
    task.add_done_callback(lambda t: handle_task_exception(t, "text handler"))

async def concurrent_photo_handler(update, context):
    """Handle photo uploads with enhanced concurrency"""
    # Use asyncio.create_task but handle it properly
    task = asyncio.create_task(photo_handler.handle_photo(update, context))
    # Add error handling for the task
    task.add_done_callback(lambda t: handle_task_exception(t, "photo handler"))

async def concurrent_audio_handler(update, context):
    """Handle audio/voice messages with enhanced concurrency"""
    # Use asyncio.create_task but handle it properly
    task = asyncio.create_task(audio_handler.handle_audio(update, context))
    # Add error handling for the task
    task.add_done_callback(lambda t: handle_task_exception(t, "audio handler"))

async def concurrent_document_handler(update, context):
    """Handle document uploads with enhanced concurrency"""
    # Use asyncio.create_task but handle it properly
    task = asyncio.create_task(doc_handler.handle_document(update, context))
    # Add error handling for the task
    task.add_done_callback(lambda t: handle_task_exception(t, "document handler"))

async def concurrent_video_handler(update, context):
    """Handle video uploads with enhanced concurrency"""
    # Use asyncio.create_task but handle it properly
    task = asyncio.create_task(video_handler.handle_video(update, context))
    # Add error handling for the task
    task.add_done_callback(lambda t: handle_task_exception(t, "video handler"))

async def concurrent_location_handler(update, context):
    """Handle location messages with enhanced concurrency"""
    # Import here to get the singleton instance
    from modules.location_features.location_handler import get_location_handler
    location_handler = get_location_handler()
    # Use asyncio.create_task but handle it properly
    task = asyncio.create_task(location_handler.handle_location_message(update, context))
    # Add error handling for the task
    task.add_done_callback(lambda t: handle_task_exception(t, "location handler"))

async def concurrent_location_text_handler(update, context):
    """Handle text messages for location features with enhanced concurrency"""
    # Import here to get the singleton instance
    from modules.location_features.location_handler import get_location_handler
    location_handler = get_location_handler()
    # Use asyncio.create_task but handle it properly
    task = asyncio.create_task(location_handler.handle_text_message(update, context))
    # Add error handling for the task
    task.add_done_callback(lambda t: handle_task_exception(t, "location text handler"))

async def concurrent_callback_handler(update, context):
    """Handle callback queries with enhanced concurrency"""
    # Import here to get the singleton instance
    from modules.location_features.location_handler import get_location_handler
    location_handler = get_location_handler()
    # Use asyncio.create_task but handle it properly
    task = asyncio.create_task(location_handler.handle_callback_query(update, context))
    # Add error handling for the task
    task.add_done_callback(lambda t: handle_task_exception(t, "callback handler"))

async def concurrent_admin_stats_callback_handler(update, context):
    """Handle admin stats pagination callbacks with enhanced concurrency"""
    # Use asyncio.create_task but handle it properly
    task = asyncio.create_task(command_handlers.handle_admin_stats_callback(update, context))
    # Add error handling for the task
    task.add_done_callback(lambda t: handle_task_exception(t, "admin stats callback handler"))

# Command handler wrappers
async def start_handler(update, context):
    task = asyncio.create_task(command_handlers.start(update, context))
    task.add_done_callback(lambda t: handle_task_exception(t, "start handler"))

async def help_handler(update, context):
    task = asyncio.create_task(command_handlers.help_command(update, context))
    task.add_done_callback(lambda t: handle_task_exception(t, "help handler"))

async def stats_handler(update, context):
    task = asyncio.create_task(command_handlers.stats_command(update, context))
    task.add_done_callback(lambda t: handle_task_exception(t, "stats handler"))

async def contact_handler(update, context):
    task = asyncio.create_task(command_handlers.contact_command(update, context))
    task.add_done_callback(lambda t: handle_task_exception(t, "contact handler"))

async def generate_handler(update, context):
    task = asyncio.create_task(command_handlers.generate_command(update, context))
    task.add_done_callback(lambda t: handle_task_exception(t, "generate handler"))

async def location_command_handler(update, context):
    task = asyncio.create_task(command_handlers.location_command(update, context))
    task.add_done_callback(lambda t: handle_task_exception(t, "location command handler"))

async def search_command_handler(update, context):
    task = asyncio.create_task(command_handlers.search_command(update, context))
    task.add_done_callback(lambda t: handle_task_exception(t, "search command handler"))

async def adminstats_handler(update, context):
    task = asyncio.create_task(command_handlers.admin_stats_command(update, context))
    task.add_done_callback(lambda t: handle_task_exception(t, "admin stats handler"))

async def monitor_handler(update, context):
    task = asyncio.create_task(command_handlers.system_monitor_command(update, context))
    task.add_done_callback(lambda t: handle_task_exception(t, "monitor handler"))

async def broadcast_handler(update, context):
    task = asyncio.create_task(command_handlers.broadcast_command(update, context))
    task.add_done_callback(lambda t: handle_task_exception(t, "broadcast handler"))

async def update_handler(update, context):
    task = asyncio.create_task(command_handlers.update_command(update, context))
    task.add_done_callback(lambda t: handle_task_exception(t, "update handler"))

async def reply_handler(update, context):
    task = asyncio.create_task(command_handlers.reply_command(update, context))
    task.add_done_callback(lambda t: handle_task_exception(t, "reply handler"))

# Error handling for async tasks
def handle_task_exception(task, handler_name):
    """Handle exceptions in async tasks"""
    try:
        if task.exception():
            logger.error(f"Exception in {handler_name}: {task.exception()}")
    except Exception as e:
        logger.error(f"Error while handling task exception for {handler_name}: {e}")

# ─── 🚀 Main Application Setup ─────────────────────────────────────────────────


def main():
    """Main function to start the AQLJON bot"""
    # Validate configuration first
    try:
        Config.validate()
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        return
    
    # Create application with enhanced error handling and proper configuration
    try:
        app = (Application.builder()
               .token(str(Config.TELEGRAM_TOKEN))
               .read_timeout(Config.NETWORK_TIMEOUT)
               .write_timeout(Config.NETWORK_TIMEOUT)
               .connect_timeout(Config.NETWORK_TIMEOUT)
               .pool_timeout(Config.NETWORK_TIMEOUT)
               .concurrent_updates(True)  # Enable concurrent updates for better performance
               .build())
    except Exception as e:
        logger.error(f"Failed to build application: {e}")
        return
    
    # Register command handlers with concurrency wrappers
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("help", help_handler))
    app.add_handler(CommandHandler("stats", stats_handler))
    app.add_handler(CommandHandler("contact", contact_handler))
    app.add_handler(CommandHandler("generate", generate_handler))
    app.add_handler(CommandHandler("location", location_command_handler))
    app.add_handler(CommandHandler("search", search_command_handler))
    app.add_handler(CommandHandler("adminstats", adminstats_handler))
    app.add_handler(CommandHandler("monitor", monitor_handler))
    app.add_handler(CommandHandler("broadcast", broadcast_handler))
    app.add_handler(CommandHandler("update", update_handler))
    app.add_handler(CommandHandler("reply", reply_handler))

    
    # Register callback handler for inline buttons
    from telegram.ext import CallbackQueryHandler
    app.add_handler(CallbackQueryHandler(concurrent_callback_handler))
    
    # Register callback handler for admin stats pagination
    app.add_handler(CallbackQueryHandler(concurrent_admin_stats_callback_handler, pattern="^admin_stats_"))
    
    # Register message handlers with enhanced concurrency
    # Note: We're using a single text handler that checks for location states internally
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, concurrent_text_handler))
    app.add_handler(MessageHandler(filters.PHOTO, concurrent_photo_handler))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, concurrent_audio_handler))
    app.add_handler(MessageHandler(filters.Document.ALL, concurrent_document_handler))
    app.add_handler(MessageHandler(filters.VIDEO, concurrent_video_handler))
    app.add_handler(MessageHandler(filters.LOCATION, concurrent_location_handler))
    
    # Register chat member handler for blocking detection
    app.add_handler(ChatMemberHandler(on_my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER))
    
    logger.info("🤖 AQLJON SmartBot is now LIVE and listening!") 
    logger.info("🎬 Video processing: Non-blocking with timeouts enabled")
    logger.info("🚀 Bot optimized for concurrent users")
    logger.info("🛡️ Enhanced error handling and rate limiting enabled")
    logger.info("🔄 Concurrent updates enabled for maximum performance")
    
    # Run with enhanced polling settings and better error handling
    retry_count = 0
    max_retries = 5
    
    while retry_count < max_retries:
        try:
            app.run_polling(
                poll_interval=2.0,  # Increased poll interval to reduce API calls
                timeout=Config.NETWORK_TIMEOUT,
                bootstrap_retries=3,  # More retries on startup
                allowed_updates=None,  # Use default updates
                drop_pending_updates=False,  # Process all pending updates
                stop_signals=[]  # Handle stop signals properly
            )
            break  # If successful, break out of retry loop
        except NetworkError as e:
            retry_count += 1
            logger.error(f"Network error in main loop (attempt {retry_count}/{max_retries}): {e}")
            if retry_count < max_retries:
                logger.info(f"Retrying in 5 seconds...")
                time.sleep(5)
            else:
                logger.error("Max retries reached. Exiting.")
                break
        except Exception as e:
            retry_count += 1
            logger.error(f"Unexpected error in main loop (attempt {retry_count}/{max_retries}): {e}")
            if retry_count < max_retries:
                logger.info(f"Retrying in 10 seconds...")
                time.sleep(10)
            else:
                logger.error("Max retries reached. Exiting.")
                break

if __name__ == "__main__":
    main()