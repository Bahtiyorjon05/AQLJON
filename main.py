import asyncio
import logging
import time
import os
from aiohttp import web
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ChatMemberHandler
from telegram.error import NetworkError

from modules.config import Config
from modules.gemini_client import build_gemini_model
from modules.memory import MemoryManager
from modules.doc_generation.document_generator import DocumentGenerator
from modules.audio_handler import AudioHandler
from modules.video_handler import VideoHandler
from modules.pic_handler import PhotoHandler
from modules.doc_handler import DocumentHandler
from modules.command_handlers import CommandHandlers
from dashboard import setup_dashboard  # Import dashboard setup

# ─── 📝 Logging ────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# ─── 🤖 Gemini Setup ───────────────────────────────────────────
try:
    Config.validate()
    model = build_gemini_model()
except Exception as e:
    logger.error(f"Initialization error: {e}")
    model = None

# ─── 🧠 Memory Management ─────────────────────────────────────────────────
memory_manager = MemoryManager(
    max_history=Config.MAX_HISTORY,
    max_content_memory=Config.MAX_CONTENT_MEMORY,
    max_users=Config.MAX_USERS_IN_MEMORY,
    max_inactive_days=Config.MAX_INACTIVE_DAYS
)

# ─── 📄 Document Generator ─────────────────────────────────────────────────
doc_generator = DocumentGenerator(model, memory_manager) if model else None

# ─── 🎛️ Media Handlers ─────────────────────────────────────────────────
audio_handler = AudioHandler(model, memory_manager) if model else None
video_handler = VideoHandler(model, memory_manager) if model else None
photo_handler = PhotoHandler(model, memory_manager) if model else None
doc_handler = DocumentHandler(model, memory_manager) if model else None

# ─── 🔍 Web Search Integration ─────────────────────────────────────────────────
async def search_web(query: str) -> str:
    """Search the web using Serper API"""
    try:
        if not Config.SERPER_KEY:
            return "❌ Qidiruv xizmati sozlanmagan."
        
        import httpx
        async with httpx.AsyncClient(timeout=10.0) as client:
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

# ─── 💾 Periodic Data Persistence Task ─────────────────────────────────────────────────
async def periodic_save(app):
    """Periodically save user data to prevent loss on dyno restart"""
    while True:
        try:
            await asyncio.sleep(5 * 60)  # 5 minutes
            saved = memory_manager.save_persistent_data()
            if saved:
                logger.info(f"Auto-saved user data: {len(memory_manager.user_stats)} users")
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in periodic save: {e}")

# ─── 🧹 Periodic Cleanup Task ─────────────────────────────────────────────────
async def periodic_cleanup(app):
    """Periodically clean up inactive users to preserve memory"""
    while True:
        try:
            await asyncio.sleep(6 * 60 * 60)  # 6 hours
            cleaned_users = memory_manager.cleanup_inactive_users()
            if cleaned_users > 0:
                logger.info(f"Cleaned up {cleaned_users} inactive users")
            memory_manager.save_persistent_data()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in periodic cleanup: {e}")

# ─── ⚙️ Application Post-Initialization ─────────────────────────────────────────────────
async def post_init(application):
    """Initialize background tasks after event loop starts"""
    asyncio.create_task(periodic_save(application))
    asyncio.create_task(periodic_cleanup(application))
    
    if audio_handler:
        asyncio.create_task(audio_handler._cleanup_completed_tasks())
    if video_handler:
        asyncio.create_task(video_handler._cleanup_completed_tasks())
    if photo_handler:
        asyncio.create_task(photo_handler._cleanup_completed_tasks())
    if doc_handler:
        asyncio.create_task(doc_handler._cleanup_completed_tasks())

# ─── 🚫 Bot Blocking Detection ─────────────────────────────────────────────────
async def on_my_chat_member(update, context):
    if not update or not update.my_chat_member:
        return
    cmu = update.my_chat_member
    chat = cmu.chat
    new_status = cmu.new_chat_member.status
    chat_id = str(chat.id)
    if chat.type == chat.PRIVATE:
        if new_status == "kicked":
            memory_manager.block_user(chat_id)
        elif new_status == "member" and cmu.old_chat_member.status == "kicked":
            memory_manager.unblock_user(chat_id)

# ─── 🔄 Enhanced Concurrent Handler Wrappers ─────────────────────────────────────────────────
async def concurrent_text_handler(update, context):
    from modules.location_features.location_handler import get_location_handler
    location_handler = get_location_handler()
    if context.user_data and (
        context.user_data.get('awaiting_city_name') or 
        context.user_data.get('awaiting_favorite_name') or 
        context.user_data.get('awaiting_favorite_location')
    ):
        asyncio.create_task(location_handler.handle_text_message(update, context))
    else:
        asyncio.create_task(command_handlers.handle_text(update, context))

async def concurrent_photo_handler(update, context):
    if photo_handler: asyncio.create_task(photo_handler.handle_photo(update, context))

async def concurrent_audio_handler(update, context):
    if audio_handler: asyncio.create_task(audio_handler.handle_audio(update, context))

async def concurrent_document_handler(update, context):
    if doc_handler: asyncio.create_task(doc_handler.handle_document(update, context))

async def concurrent_video_handler(update, context):
    if video_handler: asyncio.create_task(video_handler.handle_video(update, context))

async def concurrent_location_handler(update, context):
    from modules.location_features.location_handler import get_location_handler
    location_handler = get_location_handler()
    asyncio.create_task(location_handler.handle_location_message(update, context))

async def concurrent_callback_handler(update, context):
    from modules.location_features.location_handler import get_location_handler
    location_handler = get_location_handler()
    asyncio.create_task(location_handler.handle_callback_query(update, context))

async def concurrent_admin_stats_callback_handler(update, context):
    asyncio.create_task(command_handlers.handle_admin_stats_callback(update, context))

# Wrappers
async def start_handler(u, c): asyncio.create_task(command_handlers.start(u, c))
async def help_handler(u, c): asyncio.create_task(command_handlers.help_command(u, c))
async def stats_handler(u, c): asyncio.create_task(command_handlers.stats_command(u, c))
async def contact_handler(u, c): asyncio.create_task(command_handlers.contact_command(u, c))
async def generate_handler(u, c): asyncio.create_task(command_handlers.generate_command(u, c))
async def location_command_handler(u, c): asyncio.create_task(command_handlers.location_command(u, c))
async def search_command_handler(u, c): asyncio.create_task(command_handlers.search_command(u, c))
async def adminstats_handler(u, c): asyncio.create_task(command_handlers.admin_stats_command(u, c))
async def monitor_handler(u, c): asyncio.create_task(command_handlers.system_monitor_command(u, c))
async def broadcast_handler(u, c): asyncio.create_task(command_handlers.broadcast_command(u, c))
async def update_handler(u, c): asyncio.create_task(command_handlers.update_command(u, c))
async def reply_handler(u, c): asyncio.create_task(command_handlers.reply_command(u, c))

async def error_handler(update, context):
    logger.error(f"Exception while handling update: {context.error}", exc_info=context.error)

# ─── 🚀 Main Entry Point ─────────────────────────────────────────────────
async def main_async():
    """Async main function to run both Bot and Web Server"""
    
    # 1. Setup Telegram Bot
    try:
        app = (
            Application.builder()
            .token(str(Config.TELEGRAM_TOKEN))
            .read_timeout(Config.NETWORK_TIMEOUT)
            .write_timeout(Config.NETWORK_TIMEOUT)
            .connect_timeout(Config.NETWORK_TIMEOUT)
            .pool_timeout(Config.NETWORK_TIMEOUT)
            .concurrent_updates(True)
            .job_queue(None)
            .post_init(post_init)
            .build()
        )

        # Register handlers
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

        from telegram.ext import CallbackQueryHandler
        app.add_handler(CallbackQueryHandler(concurrent_admin_stats_callback_handler, pattern="^admin_stats_"))
        app.add_handler(CallbackQueryHandler(concurrent_callback_handler))
        
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, concurrent_text_handler))
        app.add_handler(MessageHandler(filters.PHOTO, concurrent_photo_handler))
        app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, concurrent_audio_handler))
        app.add_handler(MessageHandler(filters.Document.ALL, concurrent_document_handler))
        app.add_handler(MessageHandler(filters.VIDEO, concurrent_video_handler))
        app.add_handler(MessageHandler(filters.LOCATION, concurrent_location_handler))
        
        app.add_handler(ChatMemberHandler(on_my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER))
        app.add_error_handler(error_handler)

        await app.initialize()
        await app.start()
        logger.info("🤖 Bot application started")
        
        # Start polling (non-blocking way)
        await app.updater.start_polling(drop_pending_updates=False)
        logger.info("🚀 Bot polling started")
        
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
        return

    # 2. Setup Web Dashboard
    try:
        web_app = web.Application()
        setup_dashboard(web_app, memory_manager)
        
        port = int(os.environ.get("PORT", 8080))
        runner = web.AppRunner(web_app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', port)
        await site.start()
        
        logger.info(f"🌐 Dashboard started on port {port}")
    except Exception as e:
        logger.error(f"Failed to start dashboard: {e}")

    # Keep alive
    logger.info("✅ System fully operational (Bot + Dashboard)")
    stop_event = asyncio.Event()
    await stop_event.wait()
    
    # Cleanup
    await app.updater.stop()
    await app.stop()
    await app.shutdown()
    await runner.cleanup()

def main():
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.error(f"Fatal error: {e}")

if __name__ == "__main__":
    main()