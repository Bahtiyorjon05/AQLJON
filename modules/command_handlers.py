import asyncio
import time
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from modules.utils import safe_reply, send_long_message, main_menu_keyboard, safe_edit_message, send_typing
from modules.config import Config
from modules.memory import MemoryManager
from modules.doc_generation.document_generator import DocumentGenerator

logger = logging.getLogger(__name__)

# ── 👋 Welcome Message ────────────────────────────────────────
WELCOME = (
    "<b>👋 Assalomu alaykum va rohmatulloh va barokatuh!</b>\n"
    "Men <b>AQLJON</b> ✨ — sizning doimiy hamrohingizman!\n\n"
    "💬 Xabar yozing\n📷 Rasm yuboring\n🎙️ Ovozingizni yuboring\n"
    "📄 Hujjat yuboring\n🎬 Video yuboring\n"
    "🔍 <code>/search</code> orqali internetdan ma'lumot oling\n"
    "📊 <code>/stats</code> — Statistikani ko'ring\n"
    "📞 <code>/contact</code> — Admin bilan bog'laning\n"
    "ℹ️ <code>/help</code> — Yordam oling\n"
    "📑 <code>/generate</code> — Hujjatlar tuzing\n"
    "📍 <code>/location</code> — Joylashuv xizmatlaridan zavqlaning\n"
    "Do'stona, samimiy va foydali suhbat uchun shu yerdaman! 😊"
)

class CommandHandlers:
    """Handles all bot commands and user interactions"""
    
    def __init__(self, memory_manager: MemoryManager, doc_generator: DocumentGenerator, search_function):
        self.memory = memory_manager
        self.doc_generator = doc_generator
        self.search_web = search_function
        self.user_states = {}  # Track user states for conversational flows
        self._admin_stats_cache = {}  # Cache for admin stats
        self._admin_stats_cache_time = {}  # Cache timestamps for admin stats
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        if not update.effective_chat:
            return
        chat_id = str(update.effective_chat.id)
        self.memory.clear_history(chat_id)
        
        # Track user info and activity when they start
        if update.effective_user:
            user = update.effective_user
            self.memory.user_info[chat_id] = {
                "user_id": user.id,
                "username": user.username if user.username else None,
                "first_name": user.first_name if user.first_name else None,
                "last_name": user.last_name if user.last_name else None,
                "is_bot": user.is_bot if hasattr(user, 'is_bot') else False
            }
            
            # Track user activity to ensure they appear in admin stats
            # This will preserve existing stats if they already exist
            self.memory.track_user_activity(chat_id, "messages", update)
    
        if update.message:
            # Use fast reply for better performance
            from modules.utils import send_fast_reply
            send_fast_reply(update.message, WELCOME, reply_markup=main_menu_keyboard())
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        if not update.message:
            return
        
        help_text = (
            "<b>✨ AQLJON YORDAM MENUSI</b>\n\n"
            "🟢 <b>/start</b> — Botni qayta ishga tushiring\n"
            "🟢 <b>/help</b> — Yordam va buyruqlar ro'yxatini ko'ring\n"
            "🟢 <b>/search [so'z]</b> — Internetdan qidiring (Google orqali)\n"
            "🟢 <b>/stats</b> — Statistikangizni ko'ring\n"
            "🟢 <b>/contact [xabar]</b> — Admin bilan bog'laning\n"
            "🟢 <b>/generate</b> — Hujjatlar tuzing\n"
            "🟢 <b>/location</b> — Joylashuv xizmatlaridan foydalaning\n\n"
            "💬 Oddiy xabar yuboring — men siz bilan suhbatlashaman!\n"
            "📷 Rasm yuboring — uni tahlil qilaman!\n"
            "🎙️ Ovoz yuboring — munosib va chiroyli javob beraman!\n"
            "📄 Hujjat yuboring — tahlil qilib xulosa beraman!\n"
            "🎬 Video yuboring — ko'rib tahlil qilaman!\n"
            "📍 Joylashuv yuboring — namoz vaqtlari va yaqin joylaringiz haqida ma'lumot oling!\n\n"
            "🚀 Yanada aqlli, samimiy va foydali yordamchi bo'lishga harakat qilaman 😊"
        )
        
        # Check if user is admin and add admin commands to help
        admin_ids = [Config.ADMIN_ID.strip()] if Config.ADMIN_ID and Config.ADMIN_ID.strip() else []
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
        
        # Use fast reply for better performance
        from modules.utils import send_fast_reply
        send_fast_reply(update.message, help_text, reply_markup=main_menu_keyboard())
    
    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show user statistics"""
        if not update.message or not update.effective_chat:
            return
            
        chat_id = str(update.effective_chat.id)
        history = self.memory.get_history(chat_id)
        user_stats_data = self.memory.user_stats.get(chat_id, {})
        user_data = self.memory.user_info.get(chat_id, {})
        
        total_messages = len(history)
        user_messages = len([m for m in history if m["role"] == "user"])
        bot_messages = len([m for m in history if m["role"] == "model"])
        
        photos_sent = user_stats_data.get("photos", 0)
        voice_audio_sent = user_stats_data.get("voice_audio", 0)
        documents_sent = user_stats_data.get("documents", 0)
        videos_sent = user_stats_data.get("videos", 0)
        search_queries = user_stats_data.get("search_queries", 0)
        total_characters = user_stats_data.get("total_characters", 0)
        
        # Document generation statistics
        pdf_generated = user_stats_data.get("pdf_generated", 0)
        excel_generated = user_stats_data.get("excel_generated", 0)
        word_generated = user_stats_data.get("word_generated", 0)
        ppt_generated = user_stats_data.get("ppt_generated", 0)
        
        content_memories = len(self.memory.user_content_memory.get(chat_id, []))
        
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
        elif user_messages >= 25:
            activity_level = "⚡ Faol"
        elif user_messages >= 10:
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
            f"👤 <b>Profil ma'lumotlaringiz:</b>\n"
            f"📝 Ism: <b>{full_name}</b>\n"
            f"🏷️ Username: <b>@{username}</b>\n"
            f"🆔 User ID: <code>{user_id}</code>\n"
            f"🆔 Chat ID: <code>{chat_id}</code>\n\n"
            f"📈 <b>Faollik darajangiz:</b> {activity_level}\n\n"
            f"💬 <b>Xabarlaringiz:</b>\n"
            f"📝 Sizning xabarlaringiz: <b>{user_messages}</b>\n"
            f"✨ AQLJON javoblari: <b>{bot_messages}</b>\n"
            f"📊 Jami xabarlar: <b>{total_messages}</b>\n"
            f"📝 Jami belgilar: <b>{total_characters:,}</b>\n"
            f"📅 Kunlik o'rtacha: <b>{avg_messages_per_day:.1f}</b> xabar\n\n"
            f"🎨 <b>Media fayllar:</b>\n"
            f"📷 Rasmlar: <b>{photos_sent}</b>\n"
            f"🎤 Audio: <b>{voice_audio_sent}</b>\n"
            f"📄 Hujjatlar: <b>{documents_sent}</b>\n"
            f"🎥 Videolar: <b>{videos_sent}</b>\n"
            f"🔍 Qidiruv so'rovlari: <b>{search_queries}</b>\n\n"
            f"📑 <b>Hujjatlar tuzish:</b>\n"
            f"📄 PDF fayllar: <b>{pdf_generated}</b>\n"
            f"📊 Excel fayllar: <b>{excel_generated}</b>\n"
            f"📝 Word fayllar: <b>{word_generated}</b>\n"
            f"📽️ PowerPoint fayllar: <b>{ppt_generated}</b>\n\n"
            f"🕰️ <b>Vaqt ma'lumotlari:</b>\n"
            f"🎆 Birinchi kirish: <b>{first_date}</b>\n"
            f"⏰ Oxirgi faollik: <b>{last_date}</b>\n"
            f"📅 Faol kunlaringiz: <b>{days_active}</b>\n\n"
            f"🧠 <b>Xotira tizimi:</b>\n"
            f"💾 Saqlangan kontentlar: <b>{content_memories}</b>\n"
            f"📝 Xotira chegarasi: <b>{Config.MAX_CONTENT_MEMORY}</b> ta\n"
            f"🔄 Suhbat tarixi: <b>{len(history)}</b>/{Config.MAX_HISTORY * 2} ta\n\n"
            f"<i>✨ AQLJON siz uchun hamisha shu yerda!</i>"
        )
        
        # Use fast reply for better performance
        from modules.utils import send_fast_reply
        send_fast_reply(update.message, stats_text)

    async def admin_stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show detailed admin statistics (admin only) with pagination"""
        if not update or not update.message or not update.effective_chat or not update.effective_user:
            return
        
        user_id = str(update.effective_user.id)
        admin_ids = [Config.ADMIN_ID.strip()] if Config.ADMIN_ID and Config.ADMIN_ID.strip() else []
        
        if user_id not in admin_ids:
            # Hide admin command from non-admin users - no response
            return
        
        # Get page number from context or default to 1
        page = 1
        blocked_page = 1
        if context.user_data:
            if 'admin_stats_page' in context.user_data:
                page = context.user_data['admin_stats_page']
            if 'admin_stats_blocked_page' in context.user_data:
                blocked_page = context.user_data['admin_stats_blocked_page']
        
        # Check cache first for better performance - reduced cache time for more responsive updates
        cache_key = f"admin_stats_{page}_{blocked_page}"
        current_time = time.time()
        
        # Clear old cache entries (older than 5 seconds)
        old_cache_keys = [k for k, v in self._admin_stats_cache_time.items() if current_time - v > 5]
        for k in old_cache_keys:
            if k in self._admin_stats_cache:
                del self._admin_stats_cache[k]
            if k in self._admin_stats_cache_time:
                del self._admin_stats_cache_time[k]
        
        if cache_key in self._admin_stats_cache and cache_key in self._admin_stats_cache_time:
            # Cache is valid for 1 second only (reduced from 2 for even more responsive updates)
            if current_time - self._admin_stats_cache_time[cache_key] < 1:
                cached_result = self._admin_stats_cache[cache_key]
                if cached_result[1]:  # Has reply markup
                    await update.message.reply_text(cached_result[0], parse_mode=ParseMode.HTML, reply_markup=cached_result[1])
                else:
                    await send_long_message(update, cached_result[0])
                return
        
        # Calculate comprehensive statistics
        # Include all users who have started the bot, not just those who sent messages
        all_users = self.memory.get_all_users()
        total_users = len(all_users)
        
        # Count messages from user_stats instead of user_history since history gets cleaned up
        total_messages = sum(stats.get("messages", 0) for stats in self.memory.user_stats.values())
        total_user_messages = total_messages  # Since we're counting all user messages
        avg_messages = total_user_messages / len(self.memory.user_stats) if len(self.memory.user_stats) > 0 else 0
        
        # Media statistics
        total_photos = sum(stats.get("photos", 0) for stats in self.memory.user_stats.values())
        total_voice = sum(stats.get("voice_audio", 0) for stats in self.memory.user_stats.values())
        total_documents = sum(stats.get("documents", 0) for stats in self.memory.user_stats.values())
        total_videos = sum(stats.get("videos", 0) for stats in self.memory.user_stats.values())
        total_searches = sum(stats.get("search_queries", 0) for stats in self.memory.user_stats.values())
        
        # Document generation statistics
        total_pdf = sum(stats.get("pdf_generated", 0) for stats in self.memory.user_stats.values())
        total_excel = sum(stats.get("excel_generated", 0) for stats in self.memory.user_stats.values())
        total_word = sum(stats.get("word_generated", 0) for stats in self.memory.user_stats.values())
        total_ppt = sum(stats.get("ppt_generated", 0) for stats in self.memory.user_stats.values())
        
        # Activity categorization - based on actual message counts in user_stats
        highly_active = sum(1 for stats in self.memory.user_stats.values() if stats.get("messages", 0) >= 20)
        moderately_active = sum(1 for stats in self.memory.user_stats.values() if 5 <= stats.get("messages", 0) < 20)
        low_activity = sum(1 for stats in self.memory.user_stats.values() if 1 <= stats.get("messages", 0) < 5)
        
        # Memory system status
        total_content_memories = sum(len(memories) for memories in self.memory.user_content_memory.values())
        
        # Blocked users information with blocking time
        blocked_users_count = len(self.memory.blocked_users)
        blocked_users_details = []
        for chat_id in self.memory.blocked_users:
            user_data = self.memory.user_info.get(chat_id, {})
            username = user_data.get("username", "No username")
            first_name = user_data.get("first_name", "Unknown")
            last_name = user_data.get("last_name", "")
            full_name = f"{first_name} {last_name}".strip() or "Unknown"
            user_id_info = user_data.get("user_id", "Unknown")
            
            # Get blocking time if available
            blocking_time = "Unknown"
            if chat_id in self.memory.user_stats:
                # Try to get last active time as approximate blocking time
                last_active = self.memory.user_stats[chat_id].get("last_active", "Unknown")
                if last_active != "Unknown" and isinstance(last_active, (int, float)):
                    blocking_time = datetime.fromtimestamp(last_active).strftime("%Y-%m-%d %H:%M")
            
            blocked_users_details.append({
                "chat_id": chat_id,
                "user_id": user_id_info,
                "username": username,
                "full_name": full_name,
                "blocking_time": blocking_time
            })
        
        # Pagination for blocked users (10 users per page)
        blocked_users_per_page = 10
        total_blocked_pages = max(1, (len(blocked_users_details) + blocked_users_per_page - 1) // blocked_users_per_page)
        
        # Validate and clamp blocked_page to valid range
        blocked_page = max(1, min(blocked_page, total_blocked_pages))
        
        current_blocked_page_users = blocked_users_details[(blocked_page-1)*blocked_users_per_page:blocked_page*blocked_users_per_page]
        
        # Top users by message count (30 users, excluding blocked users)
        user_message_counts = []
        # Include all users who have started the bot
        for chat_id in all_users:
            # Skip blocked users
            if self.memory.is_blocked(chat_id):
                continue
                
            # Get user messages count from user_stats (0 if user hasn't sent any messages)
            user_messages = 0
            if chat_id in self.memory.user_stats:
                user_messages = self.memory.user_stats[chat_id].get("messages", 0)
            
            user_data = self.memory.user_info.get(chat_id, {})
            username = user_data.get("username", "Unknown")
            first_name = user_data.get("first_name", "Unknown")
            last_name = user_data.get("last_name", "")
            full_name = f"{first_name} {last_name}".strip() or "Unknown"
            user_id_info = user_data.get("user_id", "Unknown")
            
            # Get user's current location if available
            location_info = "Not shared"
            try:
                # Try to get location handler and check if user has location data
                from modules.location_features.location_handler import get_location_handler
                location_handler = get_location_handler()
                if chat_id in location_handler.location_data:
                    location_data = location_handler.location_data[chat_id]
                    city = location_data.get("city", "Unknown city")
                    location_info = f"{city} ({location_data['latitude']:.4f}, {location_data['longitude']:.4f})"
            except Exception:
                # If we can't access location handler, just show "Not shared"
                pass
            
            user_message_counts.append({
                "chat_id": chat_id,
                "user_id": user_id_info,
                "username": username,
                "full_name": full_name,
                "messages": user_messages,
                "location": location_info
            })
        
        user_message_counts.sort(key=lambda x: x["messages"], reverse=True)
        top_30_users = user_message_counts[:30]
        
        # Pagination for top users (10 users per page for better UX)
        users_per_page = 10
        total_pages = max(1, (len(top_30_users) + users_per_page - 1) // users_per_page)
        
        # Validate and clamp page to valid range
        page = max(1, min(page, total_pages))
        
        current_page_users = top_30_users[(page-1)*users_per_page:page*users_per_page]
        
        admin_stats_text = (
            f"👑 <b>ADMIN STATISTICS DASHBOARD</b>\n\n"
            f"📊 <b>Overall Statistics:</b>\n"
            f"👥 Total Users: <b>{total_users}</b>\n"
            f"💬 Total Messages: <b>{total_messages}</b>\n"
            f"📝 User Messages: <b>{total_user_messages}</b>\n"
            f"📈 Avg Messages/User: <b>{avg_messages:.1f}</b>\n"
            f"🚫 Blocked Users: <b>{blocked_users_count}</b>\n\n"
            f"🎨 <b>Media Breakdown:</b>\n"
            f"📷 Photos: <b>{total_photos}</b>\n"
            f"🎤 Voice/Audio: <b>{total_voice}</b>\n"
            f"📄 Documents: <b>{total_documents}</b>\n"
            f"🎥 Videos: <b>{total_videos}</b>\n"
            f"🔍 Searches: <b>{total_searches}</b>\n\n"
            f"📑 <b>Document Generation:</b>\n"
            f"📄 PDF Generated: <b>{total_pdf}</b>\n"
            f"📊 Excel Generated: <b>{total_excel}</b>\n"
            f"📝 Word Generated: <b>{total_word}</b>\n"
            f"📽️ PowerPoint Generated: <b>{total_ppt}</b>\n\n"
            f"📊 <b>User Activity Categories:</b>\n"
            f"🔥 Highly Active (20+ msgs): <b>{highly_active}</b>\n"
            f"⚡ Moderately Active (5-19 msgs): <b>{moderately_active}</b>\n"
            f"🌱 Low Activity (1-4 msgs): <b>{low_activity}</b>\n\n"
            f"🧠 <b>Memory System:</b>\n"
            f"💾 Content Memories: <b>{total_content_memories}</b>\n"
            f"📝 History Limit: <b>{Config.MAX_HISTORY}</b> msgs/user\n"
            f"👥 User Limit: <b>{Config.MAX_USERS_IN_MEMORY}</b>\n"
            f"🗓️ Cleanup After: <b>{Config.MAX_INACTIVE_DAYS}</b> days\n\n"
        )
        
        # Add blocked users details with pagination
        if blocked_users_details:
            admin_stats_text += f"🚫 <b>Blocked Users Details (Page {blocked_page}/{total_blocked_pages}):</b>\n"
            for i, user in enumerate(current_blocked_page_users, (blocked_page-1)*blocked_users_per_page + 1):
                username_display = f"@{user['username']}" if user['username'] != "No username" else "No username"
                admin_stats_text += (
                    f"{i}. <b>{user['full_name']}</b> ({username_display})\n"
                    f"   ID: <code>{user['user_id']}</code> | Chat: <code>{user['chat_id']}</code>\n"
                    f"   🕐 Blocked: {user['blocking_time']}\n\n"
                )
            admin_stats_text += "\n"
        
        # Add top users with pagination
        if current_page_users:
            admin_stats_text += f"🏆 <b>Top 30 Users by Messages (Page {page}/{total_pages}):</b>\n"
            for i, user in enumerate(current_page_users, (page-1)*users_per_page + 1):
                username_display = f"@{user['username']}" if user['username'] != "Unknown" else "No username"
                admin_stats_text += (
                    f"{i}. <b>{user['full_name']}</b> ({username_display})\n"
                    f"   ID: <code>{user['user_id']}</code> | Chat: <code>{user['chat_id']}</code> | Messages: <b>{user['messages']}</b>\n"
                    f"   📍 Location: {user['location']}\n\n"
                )
            
            # Add pagination controls if needed
            if total_pages > 1 or total_blocked_pages > 1:
                keyboard = []
                
                # Blocked users pagination
                if total_blocked_pages > 1:
                    blocked_nav_row = []
                    # Previous button for blocked users
                    if blocked_page > 1:
                        blocked_nav_row.append(InlineKeyboardButton("⬅️ Blocked Prev", callback_data=f"admin_stats_blocked_page_{blocked_page-1}"))
                    
                    # Page info for blocked users
                    blocked_nav_row.append(InlineKeyboardButton(f"Blocked {blocked_page}/{total_blocked_pages}", callback_data="admin_stats_blocked_info"))
                    
                    # Next button for blocked users
                    if blocked_page < total_blocked_pages:
                        blocked_nav_row.append(InlineKeyboardButton("Blocked Next ➡️", callback_data=f"admin_stats_blocked_page_{blocked_page+1}"))
                    
                    keyboard.append(blocked_nav_row)
                
                # Regular users pagination
                if total_pages > 1:
                    nav_row = []
                    # Previous button for regular users
                    if page > 1:
                        nav_row.append(InlineKeyboardButton("⬅️ Users Prev", callback_data=f"admin_stats_page_{page-1}"))
                    
                    # Page info for regular users
                    nav_row.append(InlineKeyboardButton(f"Users {page}/{total_pages}", callback_data="admin_stats_info"))
                    
                    # Next button for regular users
                    if page < total_pages:
                        nav_row.append(InlineKeyboardButton("Users Next ➡️", callback_data=f"admin_stats_page_{page+1}"))
                    
                    keyboard.append(nav_row)
                
                reply_markup = InlineKeyboardMarkup(keyboard)
            else:
                reply_markup = None
        else:
            reply_markup = None
        
        admin_stats_text += "<i>🔒 Admin-only information | Updated in real-time</i>"
        
        # Cache the result for better performance (reduced cache time)
        self._admin_stats_cache[cache_key] = (admin_stats_text, reply_markup)
        self._admin_stats_cache_time[cache_key] = current_time
        
        if reply_markup:
            await update.message.reply_text(admin_stats_text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
        else:
            await send_long_message(update, admin_stats_text)
    
    async def handle_admin_stats_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle pagination callbacks for admin stats"""
        if not update.callback_query or not update.effective_user:
            return
            
        query = update.callback_query
        user_id = str(update.effective_user.id)
        admin_ids = [Config.ADMIN_ID.strip()] if Config.ADMIN_ID and Config.ADMIN_ID.strip() else []
        
        if user_id not in admin_ids:
            await query.answer("❌ Access denied", show_alert=True)
            return
        
        if query.data and query.data.startswith("admin_stats_page_"):
            try:
                page = int(query.data.split("_")[-1])
                # Store page in context
                if context.user_data is None:
                    context.user_data = {}
                context.user_data['admin_stats_page'] = page
                
                # Re-call admin stats with new page
                await self.admin_stats_command(update, context)
                await query.answer()
            except (ValueError, IndexError):
                await query.answer("❌ Invalid page", show_alert=True)
        elif query.data and query.data.startswith("admin_stats_blocked_page_"):
            try:
                blocked_page = int(query.data.split("_")[-1])
                # Store blocked page in context
                if context.user_data is None:
                    context.user_data = {}
                context.user_data['admin_stats_blocked_page'] = blocked_page
                
                # Re-call admin stats with new blocked page
                await self.admin_stats_command(update, context)
                await query.answer()
            except (ValueError, IndexError):
                await query.answer("❌ Invalid page", show_alert=True)
        elif query.data and query.data == "admin_stats_info":
            await query.answer("Page navigation", show_alert=False)
        elif query.data and query.data == "admin_stats_blocked_info":
            await query.answer("Blocked users page navigation", show_alert=False)
    
    async def system_monitor_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Monitor system health and performance (admin only)"""
        if not update or not update.message or not update.effective_chat or not update.effective_user:
            return
        
        # Check if user is admin
        admin_ids = [Config.ADMIN_ID.strip()] if Config.ADMIN_ID and Config.ADMIN_ID.strip() else []
        user_id = str(update.effective_user.id)
        
        if user_id not in admin_ids:
            # Hide admin command from non-admin users - no response at all
            return
        
        # Perform cleanup and get metrics
        cleaned_users = self.memory.cleanup_inactive_users()
        
        total_users = len(self.memory.user_history)
        memory_usage = (
            (total_users * 5) +
            (sum(len(history) for history in self.memory.user_history.values()) * 0.5) +
            (sum(len(memories) for memories in self.memory.user_content_memory.values()) * 2)
        ) / 1024
        
        # Check if approaching limits
        user_limit_percent = (total_users / Config.MAX_USERS_IN_MEMORY) * 100
        
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
            f"Foydalanuvchilar: <b>{total_users}</b> / {Config.MAX_USERS_IN_MEMORY} ({user_limit_percent:.1f}%)\n"
            f"Xotira: <b>{memory_usage:.1f} MB</b>\n\n"
            f"<b>🧹 Maintenance:</b>\n"
            f"Faol bo'lmagan foydalanuvchilar tozalandi: <b>{cleaned_users}</b>\n"
            f"Tozalash chegarasi: <b>{Config.MAX_INACTIVE_DAYS} kun</b>\n\n"
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
    
    async def broadcast_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send broadcast message to all users (admin only)"""
        if not update or not update.message or not update.effective_chat or not update.effective_user:
            return
        
        user_id = str(update.effective_user.id)
        admin_ids = [Config.ADMIN_ID.strip()] if Config.ADMIN_ID and Config.ADMIN_ID.strip() else []
        
        if user_id not in admin_ids:
            # Hide admin command from non-admin users - no response
            return
        
        # Extract message text with formatting instructions
        message_text = update.message.text
        if not message_text or len(message_text.split(" ", 1)) < 2:
            await safe_reply(update, f"❓ Iltimos broadcast xabarini kiriting.\n\n<code>/broadcast [xabar matni]</code>")
            return
        
        # Extract the text after the command - this will contain HTML formatting tags if used
        parts = message_text.split(" ", 1)
        broadcast_text = parts[1] if len(parts) > 1 else ""
        
        if not broadcast_text.strip():
            await safe_reply(update, f"❓ Iltimos broadcast xabarini kiriting.\n\n<code>/broadcast [xabar matni]</code>")
            return
        
        # Send broadcast to all users who have started the bot, not just those who sent messages
        # Get all users who have ever interacted with the bot
        all_chat_ids = self.memory.get_all_users()
        
        total_users = len(all_chat_ids)
        success_count = 0
        failed_count = 0
        blocked_count = 0
        
        status_msg = await safe_reply(update, f"📡 <b>Broadcast boshlandi...</b>\n\n📊 Jami foydalanuvchilar: {total_users}")
        
        if not status_msg:
            logger.error("Failed to send broadcast status message")
            return
        
        # Create tasks for concurrent message sending
        tasks = []
        chat_ids = list(all_chat_ids)
        
        for chat_id in chat_ids:
            # Skip blocked users
            if self.memory.is_blocked(chat_id):
                blocked_count += 1
                continue
            
            # Create task for sending message
            task = asyncio.create_task(self.send_broadcast_message(context, chat_id, broadcast_text))
            tasks.append((chat_id, task))
        
        # Process tasks in batches to avoid rate limiting
        batch_size = 20  # Send 20 messages concurrently
        for i in range(0, len(tasks), batch_size):
            batch = tasks[i:i+batch_size]
            batch_results = await asyncio.gather(*[task for _, task in batch], return_exceptions=True)
            
            for j, (chat_id, result) in enumerate(zip([chat_id for chat_id, _ in batch], batch_results)):
                if isinstance(result, Exception):
                    # Check if user blocked the bot
                    if "Forbidden" in str(result) and "bot was blocked by the user" in str(result):
                        self.memory.block_user(chat_id)
                        blocked_count += 1
                        logger.info(f"User {chat_id} has blocked the bot")
                    else:
                        logger.warning(f"Failed to send broadcast to {chat_id}: {result}")
                        failed_count += 1
                else:
                    success_count += 1
            
            # Update status every batch
            processed_count = min(i + batch_size, len(tasks))
            edit_success = await safe_edit_message(
                status_msg,
                f"📡 <b>Broadcast jarayoni...</b>\n\n"
                f"✅ Yuborildi: {success_count}\n"
                f"❌ Xatolik: {failed_count}\n"
                f"🚫 Blocklangan: {blocked_count}\n"
                f"📊 Jarayon: {processed_count + blocked_count}/{total_users}"
            )
            # If editing failed, the message might be invalid, so we stop trying to edit it
            if not edit_success:
                status_msg = None
            
            # Small delay between batches to avoid rate limiting
            await asyncio.sleep(0.1)
        
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
    
    async def send_broadcast_message(self, context, chat_id, broadcast_text):
        """Helper method to send broadcast message to a single user"""
        try:
            # Send the broadcast message with "AQLJON dan yangiliklar" header
            return await context.bot.send_message(
                chat_id=int(chat_id),
                text=f"📢 <b>AQLJON dan yangiliklar:</b>\n\n{broadcast_text}",
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            # If HTML parsing fails, send as plain text
            logger.warning(f"HTML parsing failed: {e}")
            return await context.bot.send_message(
                chat_id=int(chat_id),
                text=f"📢 AQLJON dan yangiliklar:\n\n{broadcast_text}",
                parse_mode=None
            )
    
    async def send_update_message(self, context, chat_id, update_message):
        """Helper method to send update message to a single user"""
        try:
            # Send the hardcoded update message directly WITHOUT any header
            return await context.bot.send_message(
                chat_id=int(chat_id),
                text=update_message,
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            # If HTML parsing fails, send as plain text
            logger.warning(f"HTML parsing failed: {e}")
            return await context.bot.send_message(
                chat_id=int(chat_id),
                text=update_message,
                parse_mode=None
            )
    
    async def update_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send update message to all users (admin only)"""
        if not update or not update.message or not update.effective_chat or not update.effective_user:
            return
        
        # Check if user is admin
        admin_ids = [Config.ADMIN_ID.strip()] if Config.ADMIN_ID and Config.ADMIN_ID.strip() else []
        
        user_id = str(update.effective_user.id)
        
        if user_id not in admin_ids:
            # Hide admin command from non-admin users - no response at all
            return
        
        # Enhanced update message
        update_message = (
            f"🎉🎉🎉 <b>AQLJON KEYINGI BOSQICHGA O'TDI ! 🌟</b> 🚀\n\n"
            f"✨ <b>ENG SO'NGGI YANGILIKLAR BILAN TANISHING:</b>\n\n"
            
            f"📄 <b><i>HUJJAT TAYYORLASH TIZIMI</i></b> 🎉\n"
            f"<b>Endi professional hujjatlar bir necha soniyada:</b>\n"
            f"📊 <b><i>Excel jadvallar</i></b> <u>grafikalar, avtomatik hisobotlar</u> bilan\n"
            f"📝 <b><i>Word hujjatlar</i></b> <u>chiroyli maketlar, professional formatlash</u> bilan\n"
            f"📽️ <b><i>PowerPoint taqdimotlar</i></b> <u>ajoyib dizaynlar, go'zal uslub</u> bilan\n"
            f"📄 <b><i>PDF hisobotlar</i></b> <u>batafsil & chiroyli cover sahifalar</u> bilan\n\n"
            
            f"🌍 <b><i>JOYLASHUV XIZMATLARI</i></b> 🗺️\n"
            f"<b>Endi manzildan foydalanib quyidagilarni sinab ko'ring:</b>\n"
            f"🕌 <b><i>Namoz vaqtlari</i></b> <u>(Hanafiy mazhab)</u>\n"
            f"📍 <b><i>Yaqin-atrofdagi joylar</i></b> <u>30 turdagi manzillar</u>\n"
            f"⭐ <b><i>Sevimli joylaringiz</i></b> <u>Saqlash</u> imkoniyati bilan\n\n"
            
            f"🎨 <b>GO'ZAL DIZAYN:</b>\n"
            f"📈 Kengaytirilgan grafikalar <b>jonli</b> ranglar bilan 🌈\n"
            f"💎 <u>Premium stil</u> barcha hujjat turlarida 💎\n"
            f"✨ Animatsiyalar va vizual effektlar bilan boyitilgan taqdimotlar 🎬\n\n"
            
            f"🔥 <b>AJOYIB FUNKSIYALAR:</b>\n"
            f"📊 <b>Kengaytirilgan statistika</b> - batafsil faoliyat kuzatuvi 📈\n"
            f"📞 <b>Bevosita aloqa</b> - admin bilan muloqot 📲\n"
            f"📷 <b>Media tahlil</b> - rasmlar, audio, video, har turdagi hujjatlarni tushunish 🎥\n\n"
            f"🚀 <b>HOZIROQ SINAB KO'RING VA FARQNI HIS QILING!</b> 💫🌟"
        
        )
        
        # Get all users who have ever interacted with the bot
        all_chat_ids = self.memory.get_all_users()
        
        if not all_chat_ids:
            await safe_reply(update, "❌ Hech qanday foydalanuvchi topilmadi!")
            return
        
        # Send update message with concurrency for better performance
        successful_sends = 0
        failed_sends = 0
        blocked_sends = 0
        
        status_msg = await safe_reply(update, f"📤 {len(all_chat_ids)} ta foydalanuvchiga yangilanish haqida xabar yuborilmoqda...")
        
        if not status_msg:
            logger.error("Failed to send update status message")
            return
        
        # Create tasks for concurrent message sending
        tasks = []
        chat_ids = list(all_chat_ids)
        
        for chat_id in chat_ids:
            # Skip blocked users
            if self.memory.is_blocked(chat_id):
                blocked_sends += 1
                continue
            
            # Create task for sending message
            task = asyncio.create_task(self.send_update_message(context, chat_id, update_message))
            tasks.append((chat_id, task))
        
        # Process tasks in batches to avoid rate limiting
        batch_size = 20  # Send 20 messages concurrently
        for i in range(0, len(tasks), batch_size):
            batch = tasks[i:i+batch_size]
            batch_results = await asyncio.gather(*[task for _, task in batch], return_exceptions=True)
            
            for j, (chat_id, result) in enumerate(zip([chat_id for chat_id, _ in batch], batch_results)):
                if isinstance(result, Exception):
                    # Check if user blocked the bot
                    if "Forbidden" in str(result) and "bot was blocked by the user" in str(result):
                        self.memory.block_user(chat_id)
                        blocked_sends += 1
                        logger.info(f"User {chat_id} has blocked the bot")
                    else:
                        logger.warning(f"Failed to send update to {chat_id}: {result}")
                        failed_sends += 1
                else:
                    successful_sends += 1
            
            # Update status every batch
            processed_count = min(i + batch_size, len(tasks))
            edit_success = await safe_edit_message(
                status_msg,
                f"📤 <b>Yangilanish xabar yuborilmoqda...</b>\n\n"
                f"✅ Yuborildi: {successful_sends}\n"
                f"❌ Xatolik: {failed_sends}\n"
                f"🚫 Blocklangan: {blocked_sends}\n"
                f"📊 Jarayon: {processed_count + blocked_sends}/{len(all_chat_ids)}"
            )
            # If editing failed, the message might be invalid, so we stop trying to edit it
            if not edit_success:
                status_msg = None
            
            # Small delay between batches to avoid rate limiting
            await asyncio.sleep(0.1)
        
        # Final status
        final_text = (
            f"📤 <b>Yangilanish xabar yakunlandi!</b>\n\n"
            f"✅ Muvaffaqiyatli: <b>{successful_sends}</b>\n"
            f"❌ Xatolik: <b>{failed_sends}</b>\n"
            f"🚫 Blocklangan: <b>{blocked_sends}</b>\n"
            f"📊 Jami: <b>{len(all_chat_ids)}</b>\n\n"
            f"<i>🔒 Admin yangilanish yakunlandi</i>"
        )
        
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
    
    async def reply_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Admin can reply to specific users"""
        if not update or not update.message or not update.effective_chat or not update.effective_user:
            return
        
        # Check if user is admin
        admin_ids = [Config.ADMIN_ID.strip()] if Config.ADMIN_ID and Config.ADMIN_ID.strip() else []
        user_id = str(update.effective_user.id)
        
        if user_id not in admin_ids:
            # Hide admin command from non-admin users - no response at all
            return
        
        # Extract reply text
        message_text = update.message.text
        if not message_text or len(message_text.split(" ", 2)) < 3:
            await safe_reply(update, "❓ Iltimos javob yuboring.\n\n<code>/reply [chat_id] [xabar]</code>")
            return
        
        parts = message_text.split(" ", 2)
        target_chat_id = parts[1] if len(parts) > 1 else ""
        admin_reply = parts[2] if len(parts) > 2 else ""
        
        # Mark contact messages as replied
        if target_chat_id in self.memory.user_contact_messages:
            for msg in self.memory.user_contact_messages[target_chat_id]:
                if not msg["replied"]:
                    msg["replied"] = True
        
        # Send reply to user with preserved formatting
        reply_msg = (
            f"📞 <b>AQLJON administratoridan javob:</b>\n\n"
            f"{admin_reply}\n\n"
            f"<i>Kerak bo'lsa /contact bilan yana xabar yubora olasiz.</i>"
        )
        
        # Send message preserving HTML formatting from admin's input
        try:
            await context.bot.send_message(
                chat_id=int(target_chat_id),
                text=reply_msg,
                parse_mode=ParseMode.HTML
            )
            await safe_reply(update, f"✅ Javob yuborildi foydalanuvchiga: {target_chat_id}")
        except Exception as e:
            # If HTML parsing fails, try sending as plain text
            logger.warning(f"HTML parsing failed for reply: {e}")
            try:
                await context.bot.send_message(
                    chat_id=int(target_chat_id),
                    text=reply_msg
                )
                await safe_reply(update, f"✅ Javob yuborildi foydalanuvchiga: {target_chat_id} (formatlashsiz)")
            except Exception as e2:
                logger.error(f"Failed to send reply to user {target_chat_id}: {e2}")
                await safe_reply(update, f"❌ Javob yuborishda xatolik yuz berdi. Foydalanuvchi {target_chat_id} botni bloklagandir.")
        return

    async def contact_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send contact message to admin (users only)"""
        if not update or not update.message or not update.effective_chat or not update.effective_user:
            return
        
        user_id = str(update.effective_user.id)
        admin_ids = [Config.ADMIN_ID.strip()] if Config.ADMIN_ID and Config.ADMIN_ID.strip() else []
        
        # Admin can't use contact command
        if user_id in admin_ids:
            await safe_reply(update, "⚠️ Admin kontakt buyrug'idan foydalana olmaydi. Bevosita xabar yozing.")
            return
        
        # Extract message text
        message_text = update.message.text
        if not message_text or len(message_text.split(" ", 1)) < 2:
            await safe_reply(update, "❓ Adminga yubormoqchi bo'lgan xabaringizni kiriting. Masalan <code>/contact Yordam kerak </code> yoki menyuda 'Aloqa' tugmasini tanlang.")
            return
        
        contact_text = message_text.split(" ", 1)[1]
        chat_id = str(update.effective_chat.id)
        
        # Store contact message
        if chat_id not in self.memory.user_contact_messages:
            self.memory.user_contact_messages[chat_id] = []
        
        contact_message = {
            "message": contact_text,
            "timestamp": time.time(),
            "user_info": self.memory.user_info.get(chat_id, {}),
            "replied": False
        }
        
        self.memory.user_contact_messages[chat_id].append(contact_message)
        
        # Send to admin if admin ID is set
        if Config.ADMIN_ID and Config.ADMIN_ID.strip():
            try:
                user_data = self.memory.user_info.get(chat_id, {})
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
                
                # Send to all admin IDs if there are multiple with concurrency for better performance
                admin_ids = [Config.ADMIN_ID.strip()] if Config.ADMIN_ID and Config.ADMIN_ID.strip() else []
                # Fixed: Properly send messages to all admin IDs
                send_tasks = []
                for admin_id in admin_ids:
                    try:
                        # Create task for sending message
                        task = asyncio.create_task(context.bot.send_message(
                            chat_id=int(admin_id),
                            text=admin_notification,
                            parse_mode=ParseMode.HTML
                        ))
                        send_tasks.append(task)
                    except Exception as e:
                        logger.error(f"Failed to create task for sending contact message to admin {admin_id}: {e}")
                
                # Wait for all messages to be sent
                if send_tasks:
                    try:
                        await asyncio.gather(*send_tasks, return_exceptions=True)
                    except Exception as e:
                        logger.error(f"Error while gathering contact message tasks: {e}")
                
                # Send immediate confirmation to user
                await safe_reply(update, "✅ Xabaringiz adminga yuborildi! Tez orada siz bilan bog'lanadilar.")
                
            except Exception as e:
                logger.error(f"Failed to send contact message to admin: {e}")
                await safe_reply(update, "❌ Xabar yuborishda xatolik yuz berdi. Qaytadan urinib ko'ring.")
        else:
            await safe_reply(update, "⚠️ Admin ID sozlanmagan. Xabar saqlandi, lekin adminga yuborilmadi.")

    async def generate_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle document generation command"""
        if not update or not update.message:
            return
        
        # Show document generation options with enhanced user experience
        if update.message:
            from modules.utils import document_generation_keyboard
            await update.message.reply_text(
                "📑 <b>Hujjatlar tuzish</b>\n\n"
                "Quyidagi hujjat turlaridan birini tanlang:\n"
                "📄 <b>PDF</b> - Professional hisobotlar va maqolalar\n"
                "📊 <b>Excel</b> - Hisobotlar va ma'lumotlar jadvallari\n"
                "📝 <b>Word</b> - Batafsil hujjatlar va taklifnomalar\n"
                "📽️ <b>PowerPoint</b> - Taqdimotlar va slaydlar",
                parse_mode=ParseMode.HTML,
                reply_markup=document_generation_keyboard()
            )
    
    async def location_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /location command"""
        # Import here to avoid circular imports
        from modules.location_features.location_handler import get_location_handler
        location_handler = get_location_handler()
        await location_handler.handle_location_command(update, context)
    
    async def search_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /search command"""
        if not update or not update.message:
            return
            
        # Extract search query from the command
        message_text = update.message.text
        if not message_text or len(message_text.split(" ", 1)) < 2:
            # No search query provided, prompt user to enter one
            from modules.utils import send_fast_reply
            try:
                send_fast_reply(update.message, "🔍 Qidirish uchun so'rov kiriting:\n\nMasalan: <code>/search Python dasturlash</code>")
            except:
                pass  # Silent fail to prevent delays
            chat_id = str(update.effective_chat.id) if update.effective_chat else "unknown"
            self.user_states[chat_id] = "awaiting_search_query"
            return
            
        # Extract the search query after the command
        search_query = message_text.split(" ", 1)[1].strip() if message_text else ""
        if not search_query:
            # Empty search query, prompt user to enter one
            from modules.utils import send_fast_reply
            try:
                send_fast_reply(update.message, "🔍 Qidirish uchun so'rov kiriting:\n\nMasalan: <code>/search Python dasturlash</code>")
            except:
                pass  # Silent fail to prevent delays
            chat_id = str(update.effective_chat.id) if update.effective_chat else "unknown"
            self.user_states[chat_id] = "awaiting_search_query"
            return
            
        # Track search activity
        chat_id = str(update.effective_chat.id) if update.effective_chat else "unknown"
        self.memory.track_user_activity(chat_id, "search_queries", update)
        
        # Send typing indicator for better UX
        from modules.utils import send_typing
        asyncio.create_task(send_typing(update))
        
        # Perform search
        result = await self.search_web(search_query)
        if result:  # Check if result is not None
            from modules.utils import safe_reply
            # Send search results directly without cleaning HTML tags
            await safe_reply(update, f"<b>🔎 Qidiruv natijalari:</b>\n{result}", parse_mode=ParseMode.HTML)
        else:
            from modules.utils import safe_reply
            await safe_reply(update, "❌ Qidiruvda xatolik yuz berdi.")
    
    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle text messages and command processing"""
        try:
            chat_id = str(update.effective_chat.id) if update and update.effective_chat else "unknown"
            message = update.message.text.strip() if update and update.message and update.message.text else ""

            # Handle keyboard button presses for conversational flows - PRIORITY HANDLERS FOR MAXIMUM SPEED
            # These must be at the very beginning for immediate response to keyboard selections
            if message in ["📄 PDF fayl", "📊 Excel fayl", "📝 Word hujjat", "📽️ PowerPoint slayd"]:
                if update.message:
                    # Map button text to response message and state
                    button_responses = {
                        "📄 PDF fayl": ("📄 <b>PDF hujjat tuzish</b>\n\nPDF hujjatingiz uchun mavzu kiriting:", "awaiting_pdf_topic"),
                        "📊 Excel fayl": ("📊 <b>Excel hujjat tuzish</b>\n\nExcel jadvalingiz uchun mavzu kiriting:", "awaiting_excel_topic"),
                        "📝 Word hujjat": ("📝 <b>Word hujjat tuzish</b>\n\nWord hujjatingiz uchun mavzu kiriting:", "awaiting_word_topic"),
                        "📽️ PowerPoint slayd": ("📽️ <b>PowerPoint slaydlar tuzish</b>\n\nPowerPoint taqdimotingiz uchun mavzu kiriting:", "awaiting_ppt_topic")
                    }
                    
                    response_text, state = button_responses[message]
                    
                    # Send immediate response with minimal processing for maximum speed
                    try:
                        # Use fast reply utility for non-blocking execution
                        from modules.utils import send_fast_reply
                        send_fast_reply(update.message, response_text)
                    except:
                        # Silent fail to prevent any delays
                        pass
                    
                    # Allow multiple concurrent requests - don't cancel previous ones
                    # Just set the new state for this specific document type
                    self.user_states[chat_id] = state
                return
                
            elif message == "📞 Aloqa":
                if update.message:
                    # Use fast reply utility for non-blocking execution
                    from modules.utils import send_fast_reply
                    try:
                        send_fast_reply(update.message, "📞 AQLJON adminstratori uchun xabaringizni yozing:")
                    except:
                        pass  # Silent fail to prevent delays
                self.user_states[chat_id] = "awaiting_contact_message"
                return
                
            elif message == "🌍 Joylashuv":
                # Import here to avoid circular imports
                from modules.location_features.location_handler import get_location_handler
                location_handler = get_location_handler()
                await location_handler.handle_location_command(update, context)
                return
                
            elif message == "🔍 Qidiruv":
                if update.message:
                    # Use fast reply utility for non-blocking execution
                    from modules.utils import send_fast_reply
                    try:
                        send_fast_reply(update.message, "🔍 Qidirish uchun so'rov kiriting:")
                    except:
                        pass  # Silent fail to prevent delays
                self.user_states[chat_id] = "awaiting_search_query"
                return
                
            elif message == "📊 Statistika":
                await self.stats_command(update, context)
                return
                
            elif message == "🔄 Qayta ishga tushirish":
                await self.start(update, context)
                return
                
            elif message == "ℹ️ Yordam":
                await self.help_command(update, context)
                return
            
            elif message == "📑 Hujjatlar tuzish":
                # Check if user has recent document content in memory
                chat_id = str(update.effective_chat.id) if update and update.effective_chat else "unknown"
                content_context = self.memory.get_content_context(chat_id)
                
                from modules.utils import document_generation_keyboard
                if update.message:
                    if content_context:
                        # Use fast reply utility for non-blocking execution
                        from modules.utils import send_fast_reply
                        try:
                            send_fast_reply(update.message, 
                                "📑 <b>Hujjatlar tuzish</b>\n\n"
                                "Sizning oldingi hujjatlaringiz asosida yangi hujjat tuzish mumkin.\n"
                                "Quyidagi hujjat turlaridan birini tanlang:",
                                reply_markup=document_generation_keyboard())
                        except:
                            pass
                    else:
                        # Use fast reply utility for non-blocking execution
                        from modules.utils import send_fast_reply
                        try:
                            send_fast_reply(update.message,
                                "📑 <b>Hujjatlar tuzish</b>\n\n"
                                "Quyidagi hujjat turlaridan birini tanlang:",
                                reply_markup=document_generation_keyboard())
                        except:
                            pass
                return
                
            elif message == "🏙️ Shahar bo'yicha qidirish":
                if update.message:
                    # Use fast reply utility for non-blocking execution
                    from modules.utils import send_fast_reply
                    try:
                        send_fast_reply(update.message, "🏙️ Shahar nomini kiriting:")
                    except:
                        pass  # Silent fail to prevent delays
                # Check if user is in favorites flow by checking context.user_data
                if update.effective_chat and context.user_data and context.user_data.get('adding_favorite'):
                    # Set the correct state for favorites flow
                    context.user_data['awaiting_favorite_location'] = True
                else:
                    # Set awaiting_city_name state for general location flow
                    if context.user_data is None:
                        context.user_data = {}
                    context.user_data['awaiting_city_name'] = True
                return
                
            elif message == "🏠 Bosh menyu":
                if update.message:
                    # Use fast reply utility for non-blocking execution
                    from modules.utils import send_fast_reply, main_menu_keyboard
                    try:
                        send_fast_reply(update.message,
                            "🏠 <b>Bosh menyu</b>",
                            reply_markup=main_menu_keyboard())
                    except:
                        pass
                # Clear any pending states
                if chat_id in self.user_states:
                    del self.user_states[chat_id]
                return

            # Handle location service keyboard buttons - these might be missed if user is not in location state
            elif message == "🕋 Namoz vaqtlari":
                # Import here to avoid circular imports
                from modules.location_features.location_handler import get_location_handler
                location_handler = get_location_handler()
                await location_handler.show_prayer_times(update, context)
                return
                
            elif message == "📍 Yaqin-atrofim":
                # Import here to avoid circular imports
                from modules.location_features.location_handler import get_location_handler
                location_handler = get_location_handler()
                await location_handler.show_nearby_places_menu(update, context)
                return
                
            elif message == "⭐ Sevimli joylarim":
                # Import here to avoid circular imports
                from modules.location_features.location_handler import get_location_handler
                location_handler = get_location_handler()
                await location_handler.show_favorites_menu(update, context)
                return
                
            elif message == "⬅️ Orqaga":
                # Import here to avoid circular imports
                from modules.location_features.location_handler import get_location_handler
                from modules.utils import location_initial_keyboard
                location_handler = get_location_handler()
                if update.message:
                    await update.message.reply_text(
                        "🌍 <b>Joylashuv xizmatlari</b>",
                        parse_mode=ParseMode.HTML,
                        reply_markup=location_initial_keyboard()
                    )
                return

            # Check if user is in a conversational flow
            if chat_id in self.user_states:
                state = self.user_states[chat_id]
                
                # Handle contact flow - user has sent their message after being prompted
                if state == "awaiting_contact_message":
                    # Remove user from flow state
                    del self.user_states[chat_id]
                    
                    # Send message to admin
                    if Config.ADMIN_ID and Config.ADMIN_ID.strip():
                        try:
                            user_data = self.memory.user_info.get(chat_id, {})
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
                            admin_ids = [Config.ADMIN_ID.strip()] if Config.ADMIN_ID and Config.ADMIN_ID.strip() else []
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
                    del self.user_states[chat_id]
                    
                    # Track search activity
                    self.memory.track_user_activity(chat_id, "search_queries", update)
                    # Send typing indicator for better UX
                    asyncio.create_task(send_typing(update))
                    result = await self.search_web(message)
                    if result:  # Check if result is not None
                        # Send search results directly without cleaning HTML tags
                        await safe_reply(update, f"<b>🔎 Qidiruv natijalari:</b>\n{result}", parse_mode=ParseMode.HTML)
                    else:
                        await safe_reply(update, "❌ Qidiruvda xatolik yuz berdi.")
                    return

                # Handle document generation flows - user has sent their topic after being prompted
                elif state == "awaiting_pdf_topic":
                    # Remove user from flow state immediately
                    del self.user_states[chat_id]
                    # Generate PDF document with maximum speed
                    await self.doc_generator.generate_pdf(update, context, message)
                    return
                    
                elif state == "awaiting_excel_topic":
                    # Remove user from flow state immediately
                    del self.user_states[chat_id]
                    # Generate Excel document with maximum speed
                    await self.doc_generator.generate_excel(update, context, message)
                    return
                    
                elif state == "awaiting_word_topic":
                    # Remove user from flow state immediately
                    del self.user_states[chat_id]
                    # Generate Word document with maximum speed
                    await self.doc_generator.generate_word(update, context, message)
                    return
                    
                elif state == "awaiting_ppt_topic":
                    # Remove user from flow state immediately
                    del self.user_states[chat_id]
                    # Generate PowerPoint presentation with maximum speed
                    await self.doc_generator.generate_powerpoint(update, context, message)
                    return

            # Handle other keyboard buttons (duplicate handlers removed to prevent conflicts)
            # All keyboard handlers are now at the top for maximum speed

            # Check if user is in a conversational flow (only if not handled by keyboard buttons above)
            # This section is now redundant as all handlers are at the top - keeping for safety


            # Regular chat with AI
            self.memory.add_to_history(chat_id, "user", message)
            
            # Track user activity with character count
            self.memory.track_user_activity(chat_id, "messages", update)
            # Track character count for this message
            if chat_id in self.memory.user_stats:
                self.memory.user_stats[chat_id]["total_characters"] = self.memory.user_stats[chat_id].get("total_characters", 0) + len(message)
            
            # Send typing indicator
            await send_typing(update)
            
            try:
                # Get conversation history
                history = self.memory.get_history(chat_id)
                
                # Generate AI response with context
                messages = [{"role": msg["role"], "parts": [msg["content"]]} for msg in history[-10:]]
                
                # Add content memory context if available
                content_context = self.memory.get_content_context(chat_id)
                
                # Enhanced base instruction with specific guidelines for different types of questions
                base_instruction = (
                    "You are AQLJON, an intelligent Muslim friend who is warm, creative, helpful, and friendly. "
                    "Reply casually with humor and warmth using emojis and formatting. "
                    "Always respond in the SAME language as the user's input.\n\n"
                    
                    "IMPORTANT GUIDELINES:\n"
                    "1. For academic problem-solving (math, physics, chemistry, coding, biology):\n"
                    "   - NEVER give direct answers or solutions if they try and show u their answer many times still not correct and when they then ask u for answer then only tell them the answer with awesome explanation\n"
                    "   - Guide with concepts, understanding, and hints\n"
                    "   - Encourage users to try solving on their own first\n"
                    "   - tell them to think and try again while giving understanding clearly\n\n"
                    
                    "2. For general knowledge questions (history, geography, facts, etc.):\n"
                    "   - You can provide direct answers with clear explanations\n"
                    "   - Keep ur answers short and consice unless detailed answer is requested by user think what's going on u have access to previous content chat history so be smart\n\n"
                    
                    "3. When users ask follow-up questions about previously shared content (images, videos, documents, audio):\n"
                    "   - ALWAYS reference the detailed analysis provided in the 'Previous content user shared' section\n"
                    "   - Provide comprehensive answers based on that content\n"
                    "   - Never say you can't see the content - you have full access to it\n"
                    "   - Be specific and detailed when referencing past content\n"
                 
                    
                    "4. When users request document generation in any language (like 'slayd tuzib ber', 'hujjat yarat', 'make a presentation', etc.):\n"
                    "   - ALWAYS recognize this as a document generation request\n"
                    "   - NEVER say you can't do it or don't understand\n"
                    "   - Guide users to use the proper document generation features\n"
                    "   - Tell them they can use the /generate command or select 'Hujjatlar tuzish' from the keyboard\n"
                    "   - Explain that they can create various document types: PDF reports, Excel spreadsheets, Word documents, and PowerPoint presentations\n"
                    "   - Be enthusiastic and helpful about their document creation needs\n\n"
                    
                    "5. When users ask about your capabilities or what you can do:\n"
                    "   - Respond naturally and conversationally without being robotic\n"
                    "   - NEVER say you don't know what you can do\n"
                    "   - Be positive and encouraging about your abilities u can do tons of stuff u can understand videos, pics, various documents audios etc\n"
                    "   - Guide users to try sending different types of content\n"
                    "   - Keep responses simple and human-like\n\n"
                
                    "   - If user asks for detailed information, provide comprehensive responses\n"
                    "   - If your response is very long, it will be automatically split into multiple messages\n"
                    "   - Never truncate important information - all details should be provided when user asks\n\n"
                    
                    "7. Always keep messages concise and short and to the point unless the user specifically asks for detailed information\n"
                    "8. Never provide illicit, harmful, or inappropriate content\n"
                    "9. Be respectful of Islamic values and principles\n"
                    "10. Maintain a friendly, supportive, and educational tone\n"
                    "11. When referencing past content, be specific and provide detailed information from the analysis\n"
                    "12. Always respond in the SAME language as the user's input - as u  can of course understand any language directly"
                    "13. And NEVER say user that u are chatbot or AI and that u are programmed and ordered to answer like this way. BE a Muslim friend to user"
                )
                
                # Add content context to instruction if available
                full_instruction = base_instruction + content_context
                
                messages.insert(0, {
                    "role": "user", "parts": [full_instruction]
                })
                
                # Generate with timeout and retry logic
                response = await asyncio.wait_for(
                    asyncio.to_thread(lambda: self.doc_generator.model.generate_content(messages)),
                    timeout=Config.PROCESSING_TIMEOUT
                )
                
                reply = response.text.strip() if response and response.text else ""
                
                if reply:  # Only add to history if we got a reply
                    self.memory.add_to_history(chat_id, "model", reply)
                    await send_long_message(update, reply)
                else:
                    if update.message:
                        # Use direct reply for maximum speed
                        try:
                            await update.message.reply_text("⚙️ Hozircha javob bera olmayapman. Biroz kutib, qaytadan urinib ko'ring.", parse_mode=ParseMode.HTML)
                        except:
                            pass  # Silent fail to prevent delays
            except Exception as gemini_error:
                logger.error(f"Gemini processing error: {gemini_error}")
                if update.message:
                    # Use direct reply for maximum speed
                    try:
                        await update.message.reply_text("⚙️ Hozircha javob bera olmayapman. Biroz kutib, qaytadan urinib ko'ring.", parse_mode=ParseMode.HTML)
                    except:
                        pass  # Silent fail to prevent delays
            
        except Exception as e:
            logger.error(f"Unexpected error in handle_text: {e}")
            # Handle the outer exception gracefully
            try:
                if update.message:
                    # Use direct reply for maximum speed
                    try:
                        await update.message.reply_text("⚙️ Kutilmagan xatolik yuz berdi. Biroz kutib, qaytadan urinib ko'ring.", parse_mode=ParseMode.HTML)
                    except:
                        pass  # Silent fail to prevent delays
            except:
                # If we can't send a message, at least log the error
                pass

# Remove the old _send_fast_reply methods since we're now using the utility function
