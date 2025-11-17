import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, Location
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from modules.utils import safe_reply
from modules.location_features.utils import calculate_distance

logger = logging.getLogger(__name__)

class FavoritesHandler:
    """Handles favorite places functionality with improved UI/UX"""
    
    def __init__(self, location_data, user_favorites):
        self.location_data = location_data
        self.user_favorites = user_favorites
    
    async def show_favorites_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show main favorites menu with better organization"""
        keyboard = [
            [InlineKeyboardButton("➕ Yangi sevimli joy qo'shish", callback_data="favorites_add")],
            [InlineKeyboardButton("📋 Mening sevimlilarim", callback_data="favorites_list")],
            [InlineKeyboardButton("🗑️ Sevimlilarni o'chirish", callback_data="favorites_delete")],
            # Removed categories button as requested
            [InlineKeyboardButton("📊 Statistikalar", callback_data="favorites_stats")],
            [InlineKeyboardButton("⬅️ Orqaga", callback_data="location_menu")]  # This is correct - goes back to location services
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Use the appropriate method to send the message
        if update.callback_query and update.callback_query.message:
            try:
                await update.callback_query.edit_message_text(
                    "⭐ <b>Sevimli joylarim</b>\n\n"
                    "Quyidagi amallardan birini tanlang:",
                    parse_mode=ParseMode.HTML,
                    reply_markup=reply_markup
                )
            except Exception as e:
                if "Message is not modified" in str(e):
                    await update.callback_query.answer("✅ Yangilangan", show_alert=False)
                else:
                    # If we can't edit the message, send a new one
                    if update.effective_message:
                        await update.effective_message.reply_text(
                            "⭐ <b>Sevimli joylarim</b>\n\n"
                            "Quyidagi amallardan birini tanlang:",
                            parse_mode=ParseMode.HTML,
                            reply_markup=reply_markup
                        )
        elif update.message:
            await update.message.reply_text(
                "⭐ <b>Sevimli joylarim</b>\n\n"
                "Quyidagi amallardan birini tanlang:",
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup
            )
        elif update.effective_message:
            # Fallback to effective_message if available
            await update.effective_message.reply_text(
                "⭐ <b>Sevimli joylarim</b>\n\n"
                "Quyidagi amallardan birini tanlang:",
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup
            )
    
    async def add_favorite(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Prompt user to add a new favorite place - ask for location first"""
        query = update.callback_query
        if not query or not query.message:
            return
            
        # Set state to await location
        if context.user_data is None:
            context.user_data = {}
        context.user_data['adding_favorite'] = True
        if 'awaiting_favorite_name' in context.user_data:
            del context.user_data['awaiting_favorite_name']
        if 'awaiting_favorite_location' in context.user_data:
            del context.user_data['awaiting_favorite_location']
        
        # Create keyboard with location options
        keyboard = [
            [KeyboardButton("📍 Mening joylashuvim", request_location=True)],
            [KeyboardButton("🏙️ Shahar bo'yicha qidirish")],
            [KeyboardButton("⬅️ Orqaga")]  # Changed to go back to location menu
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
        
        await query.edit_message_text(
            "⭐ <b>Yangi sevimli joy qo'shish</b>\n\n"
            "Iltimos, sevimli bo'lgan joylashuvingizni yuboring:\n"
            "• 📍 Tugma orqali hozirgi joylashuvingizni yuboring\n"
            "• 🏙️ Shahar nomini kiriting",
            parse_mode=ParseMode.HTML
        )
        
        # Send location options as a separate message
        if update.effective_message:
            await update.effective_message.reply_text(
                "Joylashuvni tanlang:",
                reply_markup=reply_markup
            )
    
    async def save_favorite(self, update: Update, context: ContextTypes.DEFAULT_TYPE, favorite_name: str):
        """Save a new favorite place - this method is now handled in location_handler"""
        # This method is deprecated and handled in location_handler.py
        # Keeping it for backward compatibility
        pass
    
    async def list_favorites(self, update: Update, context: ContextTypes.DEFAULT_TYPE, page=1):
        """List all favorite places with pagination"""
        query = update.callback_query
        if not query or not query.message:
            return
            
        chat_id = str(query.message.chat.id)
        
        # Check if user has favorites
        if chat_id not in self.user_favorites or not self.user_favorites[chat_id]:
            await query.edit_message_text(
                "❌ Sizda hali sevimli joylar yo'q.\n\n"
                "➕ Yangi sevimli joy qo'shish uchun quyidagi tugmani bosing:",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("➕ Yangi sevimli qo'shish", callback_data="favorites_add")],
                    [InlineKeyboardButton("⬅️ Orqaga", callback_data="favorites_menu")]  # Changed to go back to favorites menu
                ])
            )
            return
        
        user_favorites = self.user_favorites[chat_id]
        
        # Pagination settings
        items_per_page = 10
        total_pages = (len(user_favorites) + items_per_page - 1) // items_per_page
        page = max(1, min(page, total_pages))
        
        # Get items for current page
        start_index = (page - 1) * items_per_page
        end_index = min(start_index + items_per_page, len(user_favorites))
        page_favorites = user_favorites[start_index:end_index]
        
        # Show user favorites for current page
        favorites_text = "⭐ <b>Sizning sevimli joylaringiz</b>\n"
        favorites_text += "=" * 30 + "\n\n"
        
        for i, favorite in enumerate(page_favorites, start_index + 1):
            created_date = datetime.fromisoformat(favorite['created_at']).strftime("%Y-%m-%d")
            favorites_text += f"📍 <b>{i}. {favorite['name']}</b>\n"
            # Removed category as requested
            favorites_text += f"   📅 <b>Qo'shilgan:</b> {created_date}\n\n"
        
        # Add footer with pagination info
        favorites_text += f"📄 Sahifa {page}/{total_pages}\n\n"
        
        # Create navigation keyboard
        keyboard = []
        
        # Add action buttons (2 per row) for current page
        for i in range(0, len(page_favorites), 2):
            row = []
            # First button
            favorite_index = start_index + i
            callback_data_1 = f"favorites_view_{favorite_index}"
            row.append(InlineKeyboardButton(f"👁️ {favorite_index+1}-ni ko'rish", callback_data=callback_data_1))
            
            # Second button if exists
            if i + 1 < len(page_favorites):
                favorite_index_2 = start_index + i + 1
                callback_data_2 = f"favorites_view_{favorite_index_2}"
                row.append(InlineKeyboardButton(f"👁️ {favorite_index_2+1}-ni ko'rish", callback_data=callback_data_2))
            
            keyboard.append(row)
        
        # Add pagination controls
        pagination_row = []
        if page > 1:
            pagination_row.append(InlineKeyboardButton("⬅️ Oldingi", callback_data=f"favorites_page_{page-1}"))
        
        # Add page indicator
        pagination_row.append(InlineKeyboardButton(f"{page}/{total_pages}", callback_data="favorites_info"))
        
        if page < total_pages:
            pagination_row.append(InlineKeyboardButton("Keyingi ➡️", callback_data=f"favorites_page_{page+1}"))
        
        if pagination_row:
            keyboard.append(pagination_row)
        
        # Add navigation buttons
        keyboard.append([
            InlineKeyboardButton("➕ Yangi qo'shish", callback_data="favorites_add"),
            InlineKeyboardButton("⬅️ Orqaga", callback_data="favorites_menu")  # Changed to go back to favorites menu
        ])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            favorites_text,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup
        )
    
    async def view_favorite(self, update: Update, context: ContextTypes.DEFAULT_TYPE, favorite_index: int):
        """View details of a specific favorite place"""
        query = update.callback_query
        if not query or not query.message:
            return
            
        chat_id = str(query.message.chat.id)
        
        # Check if user has favorites
        if chat_id not in self.user_favorites or not self.user_favorites[chat_id]:
            await query.answer("❌ Sevimli joylar topilmadi!", show_alert=True)
            return
        
        user_favorites = self.user_favorites[chat_id]
        
        # Check if index is valid
        if favorite_index < 0 or favorite_index >= len(user_favorites):
            await query.answer("❌ Noto'g'ri tanlov!", show_alert=True)
            return
        
        favorite = user_favorites[favorite_index]
        
        # Calculate distance if user location is available
        distance_info = ""
        if chat_id in self.location_data:
            user_location = self.location_data[chat_id]
            user_lat = user_location["latitude"]
            user_lon = user_location["longitude"]
            fav_lat = favorite['latitude']
            fav_lon = favorite['longitude']
            distance = self._calculate_distance(user_lat, user_lon, fav_lat, fav_lon)
            distance_info = f"📏 <b>Masofa:</b> {distance:.2f} km\n"
        
        # Create detailed view
        detail_text = f"📍 <b>{favorite['name']}</b>\n"
        detail_text += "=" * (len(favorite['name']) + 2) + "\n\n"
        
        detail_text += "📋 <b>Asosiy ma'lumotlar:</b>\n"

        # Removed category as requested
        detail_text += f"📅 <b>Qo'shilgan:</b> {datetime.fromisoformat(favorite['created_at']).strftime('%Y-%m-%d')}\n"
        if distance_info:
            detail_text += distance_info
        detail_text += "\n"
        
        detail_text += "🧭 <b>Geografik ma'lumotlar:</b>\n"
        detail_text += f"• <b>Kenglik (latitude):</b> {favorite['latitude']:.6f}\n"
        detail_text += f"• <b>Uzunlik (longitude):</b> {favorite['longitude']:.6f}\n\n"
        
        if favorite.get('notes'):
            detail_text += f"📝 <b>Eslatma:</b> {favorite['notes']}\n\n"
        
        # Add action buttons description
        detail_text += "📋 <b>Mavjud amallar:</b>\n"
        detail_text += "• 🗺️ <b>Xaritada ko'rish</b> - Joylashuvni xaritada ko'rsatish\n"
        detail_text += "• 🧭 <b>Yo'nalish olish</b> - Google Maps orqali yo'nalish olish\n"
        detail_text += "• 🗑️ <b>O'chirish</b> - Ushbu sevimli joyni o'chirish\n"
        detail_text += "• ⬅️ <b>Orqaga</b> - Sevimlilar ro'yxatiga qaytish\n"
        detail_text += "• 🏠 <b>Bosh menyu</b> - Asosiy menyuga qaytish\n\n"
        
        # Add footer
        detail_text += f"🔷 <b>Joy nomi:</b> {favorite['name']}\n"
        detail_text += f"📄 <b>Raqam:</b> {favorite_index + 1}\n\n"
        
        # Add action buttons
        keyboard = [
            [InlineKeyboardButton("🗺️ Xaritada ko'rish", callback_data=f"favorites_map_{favorite_index}")],
            [InlineKeyboardButton("🧭 Yo'nalish olish", callback_data=f"favorites_directions_{favorite_index}")],
            [InlineKeyboardButton("🗑️ O'chirish", callback_data=f"favorites_delete_confirm_{favorite_index}")],
            [InlineKeyboardButton("⬅️ Orqaga", callback_data="favorites_list")],
            [InlineKeyboardButton("🏠 Bosh menyu", callback_data="location_menu")]  # Changed to go back to location menu
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            detail_text,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup
        )
    
    async def show_map(self, update: Update, context: ContextTypes.DEFAULT_TYPE, favorite_index: int):
        """Show favorite place on map"""
        query = update.callback_query
        if not query or not query.message:
            return
            
        chat_id = str(query.message.chat.id)
        
        # Check if user has favorites
        if chat_id not in self.user_favorites or not self.user_favorites[chat_id]:
            await query.answer("❌ Sevimli joylar topilmadi!", show_alert=True)
            return
        
        # Check if location data has expired
        if chat_id in self.location_data:
            location = self.location_data[chat_id]
            if "expires_at" in location:
                expires_at = datetime.fromisoformat(location["expires_at"])
                if datetime.now() > expires_at:
                    await query.answer("📍 Joylashuv ma'lumotlari eskirgan. Iltimos, qaytadan jo'nating!", show_alert=True)
                    return
        
        user_favorites = self.user_favorites[chat_id]
        
        # Check if index is valid
        if favorite_index < 0 or favorite_index >= len(user_favorites):
            await query.answer("❌ Noto'g'ri tanlov!", show_alert=True)
            return
        
        favorite = user_favorites[favorite_index]
        
        # Send location
        location_msg = Location(
            longitude=favorite['longitude'],
            latitude=favorite['latitude']
        )
        
        # Calculate distance if user location is available
        distance_info = ""
        if chat_id in self.location_data:
            user_location = self.location_data[chat_id]
            user_lat = user_location["latitude"]
            user_lon = user_location["longitude"]
            fav_lat = favorite['latitude']
            fav_lon = favorite['longitude']
            distance = self._calculate_distance(user_lat, user_lon, fav_lat, fav_lon)
            distance_info = f"📏 <b>Masofa:</b> {distance:.2f} km\n"
        
        # Create detailed map message
        map_text = f"📍 <b>{favorite['name']}</b> joylashuvi xaritada ko'rsatilgan\n"
        map_text += "=" * (len(favorite['name']) + 20) + "\n\n"
        
        map_text += "🧭 <b>Geografik ma'lumotlar:</b>\n"
        map_text += f"• <b>Kenglik (latitude):</b> {favorite['latitude']:.6f}\n"
        map_text += f"• <b>Uzunlik (longitude):</b> {favorite['longitude']:.6f}\n"
        if distance_info:
            map_text += distance_info
        map_text += "\n"
        
        if favorite.get('notes'):
            map_text += f"📝 <b>Eslatma:</b> {favorite['notes']}\n\n"
        
        map_text += "<i>Xaritada ko'rish uchun yuqoridagi joylashuv xabarini oching</i>\n\n"
        map_text += "<i>Joylashuvni Google Maps ilovasida ochish uchun xabarni bosing</i>\n\n"
        
        # Add footer
        map_text += f"🔷 <b>Joy nomi:</b> {favorite['name']}\n"
        map_text += f"📄 <b>Raqam:</b> {favorite_index + 1}\n\n"
        
        if update.effective_message:
            await update.effective_message.reply_location(location=location_msg)
            await update.effective_message.reply_text(
                map_text,
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⬅️ Orqaga", callback_data=f"favorites_view_{favorite_index}")],
                    [InlineKeyboardButton("🏠 Bosh menyu", callback_data="location_menu")]  # Changed to go back to location menu
                ])
            )
        
        await query.answer(f"📍 {favorite['name']} xaritada ko'rsatildi", show_alert=False)
    
    async def show_directions(self, update: Update, context: ContextTypes.DEFAULT_TYPE, favorite_index: int):
        """Show directions to favorite place"""
        query = update.callback_query
        if not query or not query.message:
            return
            
        chat_id = str(query.message.chat.id)
        
        # Check if user has favorites
        if chat_id not in self.user_favorites or not self.user_favorites[chat_id]:
            await query.answer("❌ Sevimli joylar topilmadi!", show_alert=True)
            return
        
        user_favorites = self.user_favorites[chat_id]
        
        # Check if index is valid
        if favorite_index < 0 or favorite_index >= len(user_favorites):
            await query.answer("❌ Noto'g'ri tanlov!", show_alert=True)
            return
        
        # Check if location data has expired
        if chat_id in self.location_data:
            location = self.location_data[chat_id]
            if "expires_at" in location:
                expires_at = datetime.fromisoformat(location["expires_at"])
                if datetime.now() > expires_at:
                    await query.answer("📍 Joylashuv ma'lumotlari eskirgan. Iltimos, qaytadan jo'natish!", show_alert=True)
                    return
        
        favorite = user_favorites[favorite_index]
        
        # Provide directions link (Google Maps)
        directions_url = f"https://www.google.com/maps/dir/?api=1&destination={favorite['latitude']},{favorite['longitude']}"
        
        # Calculate distance if user location is available
        distance_info = ""
        if chat_id in self.location_data:
            user_location = self.location_data[chat_id]
            user_lat = user_location["latitude"]
            user_lon = user_location["longitude"]
            fav_lat = favorite['latitude']
            fav_lon = favorite['longitude']
            distance = self._calculate_distance(user_lat, user_lon, fav_lat, fav_lon)
            distance_info = f"📏 <b>Masofa:</b> {distance:.2f} km\n"
        
        # Create detailed directions message
        directions_text = f"🧭 <b>{favorite['name']} ga yo'nalish</b>\n"
        directions_text += "=" * (len(favorite['name']) + 15) + "\n\n"
        
        directions_text += "📍 <b>Manzil ma'lumotlari:</b>\n"
        directions_text += f"• <b>Joy nomi:</b> {favorite['name']}\n"
        directions_text += f"• <b>Koordinatalar:</b> {favorite['latitude']:.6f}, {favorite['longitude']:.6f}\n"
        if distance_info:
            directions_text += distance_info
        directions_text += "\n"
        
        if favorite.get('notes'):
            directions_text += f"📝 <b>Eslatma:</b> {favorite['notes']}\n\n"
        
        directions_text += "🧭 <b>Yo'nalish:</b>\n"
        directions_text += f"<a href='{directions_url}'>Google Maps orqali yo'nalish olish</a>\n\n"
        directions_text += "<i>Yo'nalishni ochish uchun havolani bosing</i>\n\n"
        directions_text += "<i>Yo'nalishni Google Maps ilovasida ochish uchun havolani bosing</i>\n\n"
        
        # Add footer
        directions_text += f"🔷 <b>Joy nomi:</b> {favorite['name']}\n"
        directions_text += f"📄 <b>Raqam:</b> {favorite_index + 1}\n\n"
        
        await query.edit_message_text(
            directions_text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Orqaga", callback_data=f"favorites_view_{favorite_index}")],
                [InlineKeyboardButton("🏠 Bosh menyu", callback_data="location_menu")]  # Changed to go back to location menu
            ])
        )
    
    async def delete_favorite_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show menu for deleting favorites"""
        query = update.callback_query
        if not query or not query.message:
            return
            
        chat_id = str(query.message.chat.id)
        
        # Check if user has favorites
        if chat_id not in self.user_favorites or not self.user_favorites[chat_id]:
            await query.edit_message_text(
                "❌ O'chirish uchun sevimli joylaringiz yo'q.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("➕ Yangi sevimli joy qo'shish", callback_data="favorites_add")],
                    [InlineKeyboardButton("⬅️ Orqaga", callback_data="favorites_menu")]  # Changed to go back to favorites menu
                ])
            )
            return
        
        # Show user favorites for deletion
        user_favorites = self.user_favorites[chat_id]
        deletion_text = "🗑️ <b>Sevimli joyni o'chirish</b>\n"
        deletion_text += "=" * 25 + "\n\n"
        deletion_text += "O'chirish uchun sevimli joy tanlang:\n\n"
        
        # Create inline keyboard
        keyboard = []
        
        # Add favorites (2 per row)
        for i in range(0, len(user_favorites), 2):
            row = []
            # First button
            favorite_name_1 = user_favorites[i]['name']
            if len(favorite_name_1) > 15:
                button_text_1 = f"{i+1}. {favorite_name_1[:12]}..."
            else:
                button_text_1 = f"{i+1}. {favorite_name_1}"
            callback_data_1 = f"favorites_delete_confirm_{i}"
            row.append(InlineKeyboardButton(button_text_1, callback_data=callback_data_1))
            
            # Second button if exists
            if i + 1 < len(user_favorites):
                favorite_name_2 = user_favorites[i+1]['name']
                if len(favorite_name_2) > 15:
                    button_text_2 = f"{i+2}. {favorite_name_2[:12]}..."
                else:
                    button_text_2 = f"{i+2}. {favorite_name_2}"
                callback_data_2 = f"favorites_delete_confirm_{i+1}"
                row.append(InlineKeyboardButton(button_text_2, callback_data=callback_data_2))
            
            keyboard.append(row)
        
        # Add cancel button
        keyboard.append([InlineKeyboardButton("❌ Bekor qilish", callback_data="favorites_menu")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            deletion_text,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup
        )
    
    async def confirm_delete(self, update: Update, context: ContextTypes.DEFAULT_TYPE, favorite_index: int):
        """Confirm deletion of a favorite place"""
        query = update.callback_query
        if not query or not query.message:
            return
            
        chat_id = str(query.message.chat.id)
        
        # Check if user has favorites
        if chat_id not in self.user_favorites or not self.user_favorites[chat_id]:
            await query.answer("❌ Sevimli joylar topilmadi!", show_alert=True)
            return
        
        user_favorites = self.user_favorites[chat_id]
        
        # Check if index is valid
        if favorite_index < 0 or favorite_index >= len(user_favorites):
            await query.answer("❌ Noto'g'ri tanlov!", show_alert=True)
            return
        
        favorite = user_favorites[favorite_index]
        
        # Show confirmation
        await query.edit_message_text(
            f"❓ <b>Rostan ham o'chirmoqchimisiz?</b>\n\n"
            f"📍 <b>{favorite['name']}</b>\n\n"
            f"Ushbu amalni bekor qilib bo'lmaydi!",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Ha, o'chir", callback_data=f"favorites_delete_final_{favorite_index}")],
                [InlineKeyboardButton("❌ Yo'q, bekor qil", callback_data="favorites_menu")]  # Changed to go back to favorites menu
            ])
        )
    
    async def delete_favorite(self, update: Update, context: ContextTypes.DEFAULT_TYPE, favorite_index: int):
        """Delete a favorite place"""
        query = update.callback_query
        if not query or not query.message:
            return
            
        chat_id = str(query.message.chat.id)
        
        # Check if user has favorites
        if chat_id not in self.user_favorites or not self.user_favorites[chat_id]:
            await query.answer("❌ Sevimli joylar topilmadi!", show_alert=True)
            return
        
        user_favorites = self.user_favorites[chat_id]
        
        # Check if index is valid
        if favorite_index < 0 or favorite_index >= len(user_favorites):
            await query.answer("❌ Noto'g'ri tanlov!", show_alert=True)
            return
        
        # Delete favorite
        deleted_favorite = user_favorites.pop(favorite_index)
        
        # Remove key if no favorites left
        if not user_favorites:
            del self.user_favorites[chat_id]
        
        # Show confirmation
        await query.edit_message_text(
            f"✅ <b>{deleted_favorite['name']}</b> sevimli joylaringizdan o'chirildi!",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Orqaga", callback_data="favorites_menu")],  # Changed to go back to favorites menu
                [InlineKeyboardButton("🏠 Bosh menyu", callback_data="location_menu")]  # Changed to go back to location menu
            ])
        )
    
    async def show_statistics(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show improved statistics for favorites"""
        query = update.callback_query
        if not query or not query.message:
            return
            
        chat_id = str(query.message.chat.id)
        
        # Check if user has favorites
        if chat_id not in self.user_favorites or not self.user_favorites[chat_id]:
            await query.edit_message_text(
                "📊 <b>Statistikalar</b>\n"
                "==================\n\n"
                "❌ Sizda hali sevimli joylar yo'q.\n\n"
                "➕ Yangi sevimli joy qo'shish uchun quyidagi tugmani bosing:",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("➕ Yangi sevimli qo'shish", callback_data="favorites_add")],
                    [InlineKeyboardButton("⬅️ Orqaga", callback_data="favorites_menu")]  # Changed to go back to favorites menu
                ])
            )
            return
        
        user_favorites = self.user_favorites[chat_id]
        
        # Calculate statistics
        total_favorites = len(user_favorites)
        
        # Date statistics
        dates = [datetime.fromisoformat(fav['created_at']) for fav in user_favorites]
        earliest_date = min(dates).strftime("%Y-%m-%d") if dates else "Noma'lum"
        latest_date = max(dates).strftime("%Y-%m-%d") if dates else "Noma'lum"
        
        # Distance statistics (if user location available)
        distance_stats = ""
        if chat_id in self.location_data:
            user_location = self.location_data[chat_id]
            user_lat = user_location["latitude"]
            user_lon = user_location["longitude"]
            
            distances = []
            for fav in user_favorites:
                fav_lat = fav['latitude']
                fav_lon = fav['longitude']
                distance = self._calculate_distance(user_lat, user_lon, fav_lat, fav_lon)
                distances.append(distance)
            
            if distances:
                avg_distance = sum(distances) / len(distances)
                max_distance = max(distances)
                min_distance = min(distances)
                distance_stats = (
                    f"📏 <b>Masofa statistikasi:</b>\n"
                    f"• O'rtacha masofa: {avg_distance:.2f} km\n"
                    f"• Eng yaqin joy: {min_distance:.2f} km\n"
                    f"• Eng uzoq joy: {max_distance:.2f} km\n\n"
                )
        
        # Create statistics message
        stats_text = "📊 <b>Sevimli joylar statistikasi</b>\n"
        stats_text += "=" * 30 + "\n\n"
        
        stats_text += f"📍 <b>Umumiy statistika:</b>\n"
        stats_text += f"• Jami sevimli joylar: {total_favorites}\n"
        stats_text += f"• Qo'shilgan sana (birinchi): {earliest_date}\n"
        stats_text += f"• Qo'shilgan sana (oxirgi): {latest_date}\n\n"
        
        stats_text += distance_stats
        
        stats_text += "📈 <b>Tavsif:</b>\n"
        stats_text += "Bu statistika sizning sevimli joylaringiz haqida umumiy ma'lumot beradi.\n\n"
        
        # Add navigation buttons
        keyboard = [
            [InlineKeyboardButton("⬅️ Orqaga", callback_data="favorites_menu")],
            [InlineKeyboardButton("🏠 Bosh menyu", callback_data="location_menu")]  # Changed to go back to location menu
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            stats_text,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup
        )
    
    def _calculate_distance(self, lat1, lon1, lat2, lon2):
        """Calculate the distance between two points - delegates to shared utility"""
        return calculate_distance(lat1, lon1, lat2, lon2)