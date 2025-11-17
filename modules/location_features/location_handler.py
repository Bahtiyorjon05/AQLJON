import asyncio
import logging
from datetime import datetime, timedelta
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup, Location
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from modules.utils import safe_reply, safe_edit_message
from modules.retry_utils import http_get_with_retry
from modules.location_features.utils import validate_city_name, validate_coordinates
from .favorites import FavoritesHandler
from .nearby import NearbyHandler
from .prayer_times import PrayerTimesHandler

logger = logging.getLogger(__name__)

# Global instance to maintain state across interactions
_location_handler_instance = None

def get_location_handler():
    """Get or create a singleton instance of LocationFeatureHandler"""
    global _location_handler_instance
    if _location_handler_instance is None:
        _location_handler_instance = LocationFeatureHandler()
    return _location_handler_instance

class LocationFeatureHandler:
    """Main handler for all location-based features with improved organization"""
    
    def __init__(self):
        # Shared data structures
        self.location_data = {}  # In-memory storage for user locations
        self.user_favorites = {}  # In-memory storage for user favorite places
        self.cached_data = {}  # Cache for API responses
        
        # Initialize feature handlers
        self.favorites_handler = FavoritesHandler(self.location_data, self.user_favorites)
        self.nearby_handler = NearbyHandler(self.location_data, self.cached_data)
        self.prayer_handler = PrayerTimesHandler(self.location_data)
    
    # ─── LOCATION MANAGEMENT ──────────────────────────────────────────────────────
    
    async def handle_location_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /location command to show location menu"""
        if not update.message or not update.effective_chat:
            return
        
        from modules.utils import location_initial_keyboard
        await update.message.reply_text(
            "🌍 <b>Joylashuv xizmatlari</b>\n\n"
            "Joylashuvingizni ulashish uchun quyidagi variantlardan birini tanlang:",
            parse_mode=ParseMode.HTML,
            reply_markup=location_initial_keyboard()
        )
    
    def _main_location_keyboard(self):
        """Create main location menu keyboard - ONLY 3 options as requested"""
        return ReplyKeyboardMarkup(
            [
                [KeyboardButton("📍 Mening joylashuvim", request_location=True)],
                [KeyboardButton("🏙️ Shahar bo'yicha qidirish")],
                [KeyboardButton("🏠 Bosh menyu")]
            ],
            resize_keyboard=True, one_time_keyboard=False,
        )
    
    def _location_services_keyboard(self):
        """Create location services menu keyboard after location is provided"""
        return ReplyKeyboardMarkup(
            [
                [KeyboardButton("📍 Mening joylashuvim", request_location=True)],
                [KeyboardButton("🏙️ Shahar bo'yicha qidirish"), KeyboardButton("🕋 Namoz vaqtlari")],
                [KeyboardButton("📍 Yaqin-atrofim"), KeyboardButton("⭐ Sevimli joylarim")],
                [KeyboardButton("🏠 Bosh menyu")]
            ],
            resize_keyboard=True, one_time_keyboard=False,
        )
    
    async def handle_location_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle location messages from users"""
        if not update.message or not update.message.location or not update.effective_chat:
            return
        
        chat_id = str(update.effective_chat.id)
        location = update.message.location
        
        # Check if we're in favorite location mode
        if context.user_data and context.user_data.get('adding_favorite'):
            await self.handle_favorite_location(update, context, location)
            return
        
        # Check location accuracy and warn user if needed
        accuracy_indicator = "✅"
        accuracy_message = ""
        if location.horizontal_accuracy:
            if location.horizontal_accuracy > 1000:  # Poor accuracy
                accuracy_indicator = "❌"
                accuracy_message = "\n⚠️ Diqqat: Joylashuvingiz aniqliki past. Aniqroq aniqlik uchun ochiq havoda bo'ling."
            elif location.horizontal_accuracy > 100:  # Medium accuracy
                accuracy_indicator = "⚠️"
                accuracy_message = "\n⚠️ Joylashuvingiz aniqliki o'rtacha."
        
        # Get location details
        location_info = await self._get_location_info(location.latitude, location.longitude)
        
        # Store user location with expiration
        city_name = "Noma'lum shahar"
        if location_info is not None:
            city_name = location_info.get("city", "Noma'lum shahar")
        
        self.location_data[chat_id] = {
            "latitude": location.latitude,
            "longitude": location.longitude,
            "horizontal_accuracy": location.horizontal_accuracy,
            "city": city_name,
            "timestamp": datetime.now().isoformat(),
            "expires_at": (datetime.now() + timedelta(hours=24)).isoformat()
        }
        
        # Show detailed location information
        await self.show_detailed_location_info(update, context, location, location_info, accuracy_message)

    async def show_detailed_location_info(self, update: Update, context: ContextTypes.DEFAULT_TYPE, location, location_info, accuracy_message):
        """Show detailed information about the user's location"""
        # Format location details
        lat = location.latitude
        lon = location.longitude
        accuracy = location.horizontal_accuracy if location.horizontal_accuracy else "Noma'lum"
        
        # Get location details
        city = location_info.get("city", "Noma'lum shahar") if location_info else "Noma'lum shahar"
        country = location_info.get("country", "Noma'lum mamlakat") if location_info else "Noma'lum mamlakat"
        state = location_info.get("state", "") if location_info else ""
        display_name = location_info.get("display_name", f"Koordinatalar: {lat:.4f}, {lon:.4f}") if location_info else f"Koordinatalar: {lat:.4f}, {lon:.4f}"
        
        # Create detailed message with improved formatting
        location_details = f"📍 <b>Sizning joylashuvingiz</b>\n"
        location_details += "=" * 30 + "\n\n"
        
        location_details += f"🌍 <b>Geografik ma'lumotlar:</b>\n"
        location_details += f"• <b>Kenglik (latitude):</b> {lat:.6f}\n"
        location_details += f"• <b>Uzunlik (longitude):</b> {lon:.6f}\n"
        location_details += f"• <b>Aniqlik:</b> {accuracy} metr\n\n"
        
        location_details += f"🏙️ <b>Manzil ma'lumotlari:</b>\n"
        location_details += f"• <b>Shahar:</b> {city}\n"
        if state:
            location_details += f"• <b>Viloyat:</b> {state}\n"
        location_details += f"• <b>Mamlakat:</b> {country}\n\n"
        
        location_details += f"📌 <b>To'liq manzil:</b>\n"
        location_details += f"{display_name}\n\n"
        
        # Add accuracy warning if needed
        if accuracy_message:
            location_details += f"{accuracy_message}\n\n"
        
        location_details += "📋 <b>Mavjud xizmatlar:</b>\n"
        location_details += "Endi quyidagi joylashuvga asoslangan xizmatlardan foydalanishingiz mumkin:\n"
        location_details += "• 🕋 <b>Namoz vaqtlari</b> - Namoz vaqtlarini biling\n"
        location_details += "• 📍 <b>Yaqin-atrofim</b> - Yonizdagi joylarni toping\n"
        location_details += "• ⭐ <b>Sevimli joylarim</b> - O'z sevgan joylaringizni saqlang\n\n"
        
        # Add timestamp for freshness indicator
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        location_details += f"🕒 <b>Ma'lumotlar yangilangan vaqti:</b> {timestamp}\n"
        
        # Send location on map and detailed information
        if update.message:
            # Send location on map
            location_msg = Location(longitude=lon, latitude=lat)
            await update.message.reply_location(location=location_msg)
            
            # Check if we're in the middle of adding a favorite
            if context.user_data and context.user_data.get('adding_favorite'):
                # Don't show location services keyboard, just show the location info
                await update.message.reply_text(
                    location_details,
                    parse_mode=ParseMode.HTML
                )
            elif context.user_data and context.user_data.get('awaiting_favorite_name'):
                # We're waiting for the favorite name, don't show location services keyboard
                await update.message.reply_text(
                    location_details,
                    parse_mode=ParseMode.HTML
                )
            else:
                # Send detailed information with location services keyboard (without location input options)
                from modules.utils import location_services_keyboard
                await update.message.reply_text(
                    location_details,
                    parse_mode=ParseMode.HTML,
                    reply_markup=location_services_keyboard()
                )

    async def handle_favorite_location(self, update: Update, context: ContextTypes.DEFAULT_TYPE, location):
        """Handle location for favorite creation"""
        if not update.effective_chat:
            return
        
        # Get location details
        location_info = await self._get_location_info(location.latitude, location.longitude)
        
        # Store temporary location info
        chat_id = str(update.effective_chat.id)
        if context.user_data is None:
            context.user_data = {}
        context.user_data['temp_favorite_location'] = {
            "latitude": location.latitude,
            "longitude": location.longitude,
            "city": location_info.get("city", "Noma'lum shahar") if location_info is not None else "Noma'lum shahar",
            "timestamp": datetime.now().isoformat()
        }
        
        # Ask for favorite name
        context.user_data['awaiting_favorite_name'] = True
        # Remove the adding_favorite flag since we're now waiting for the name
        if 'adding_favorite' in context.user_data:
            del context.user_data['adding_favorite']
        
        # Show simple keyboard with just the back option
        if update.message:
            await update.message.reply_text(
                "⭐ Iltimos, ushbu joy uchun nom kiriting:",
                reply_markup=ReplyKeyboardMarkup(
                    [[KeyboardButton("⬅️ Orqaga")]],
                    resize_keyboard=True,
                    one_time_keyboard=True
                )
            )
    
    async def handle_text_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle text messages related to location features"""
        if not update.message or not update.message.text or not update.effective_chat:
            return
        
        chat_id = str(update.effective_chat.id)
        text = update.message.text.strip()
        
        # Initialize user_data if it doesn't exist
        if context.user_data is None:
            context.user_data = {}
        
        # Handle user states for location features
        if context.user_data.get('awaiting_city_name'):
            del context.user_data['awaiting_city_name']
            await self.handle_city_search(update, context, text)
            return
        elif context.user_data.get('awaiting_favorite_name'):
            # Check if user pressed back button while entering favorite name
            if text == "⬅️ Orqaga":
                # Clear the state and show the favorites menu
                del context.user_data['awaiting_favorite_name']
                if 'temp_favorite_location' in context.user_data:
                    del context.user_data['temp_favorite_location']
                await self.favorites_handler.show_favorites_menu(update, context)
                return
            else:
                # Save the favorite with the entered name
                del context.user_data['awaiting_favorite_name']
                await self.save_favorite_with_location(update, context, text)
                return
        elif context.user_data.get('awaiting_favorite_location'):
            # Handle city name for favorite location
            del context.user_data['awaiting_favorite_location']
            await self.handle_favorite_city_search(update, context, text)
            return

        
        # Handle location menu options
        if text == "🏙️ Shahar bo'yicha qidirish":
            await safe_reply(update, "🏙️ Iltimos, shahar nomini kiriting:")
            # Check if user is in favorites flow
            if context.user_data.get('adding_favorite'):
                # User is in favorites flow, set the appropriate state
                context.user_data['awaiting_favorite_location'] = True
            else:
                # User is in general location flow, set awaiting_city_name state
                context.user_data['awaiting_city_name'] = True
            return  # Important: return immediately after setting state
        elif text == "🕋 Namoz vaqtlari":
            await self.prayer_handler.show_prayer_times(update, context)
            return
        elif text == "📍 Yaqin-atrofim":
            await self.nearby_handler.show_nearby_menu(update, context)
            return
        elif text == "⭐ Sevimli joylarim":
            await self.favorites_handler.show_favorites_menu(update, context)
            return
        elif text == "⬅️ Orqaga":  # Added back button handling
            from modules.utils import location_initial_keyboard
            if update.message:
                await update.message.reply_text(
                    "🌍 <b>Joylashuv xizmatlari</b>",
                    parse_mode=ParseMode.HTML,
                    reply_markup=location_initial_keyboard()
                )
            return
        elif text == "🏠 Bosh menyu":
            from modules.utils import main_menu_keyboard
            if update.message:
                await update.message.reply_text(
                    "🏠 <b>Bosh menyu</b>",
                    parse_mode=ParseMode.HTML,
                    reply_markup=main_menu_keyboard()
                )
            return
        
        # If we reach here, it's an unexpected text message in location context
        # Send a helpful message and show the location menu again
        from modules.utils import location_initial_keyboard
        if update.message:
            await update.message.reply_text(
                "❌ Kechirasiz, bu buyruq tushunarsiz.\n\n"
                "Iltimos, quyidagi variantlardan birini tanlang:",
                parse_mode=ParseMode.HTML,
                reply_markup=location_initial_keyboard()
            )
    
    async def show_prayer_times(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show prayer times"""
        await self.prayer_handler.show_prayer_times(update, context)
    
    async def show_nearby_places_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE, page=1):
        """Show nearby places menu"""
        await self.nearby_handler.show_nearby_menu(update, context, page)
    
    async def show_favorites_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show favorites menu"""
        await self.favorites_handler.show_favorites_menu(update, context)
    
    async def handle_city_search(self, update: Update, context: ContextTypes.DEFAULT_TYPE, city_name: str):
        """Handle city search by name"""
        if not update.effective_chat:
            return

        # Validate city name
        is_valid, cleaned_city = validate_city_name(city_name)
        if not is_valid:
            if update.effective_message:
                await update.effective_message.reply_text(
                    "❌ Noto'g'ri shahar nomi. Iltimos, kamida 2 belgili nom kiriting.",
                    parse_mode=ParseMode.HTML
                )
            return

        try:
            # Show processing message
            processing_msg = await safe_reply(update, "🏙️ Shahar qidirilmoqda...")

            # Using Nominatim for geocoding
            location_info = await self._get_location_info_by_name(cleaned_city)
            
            if location_info:
                # Store location with expiration
                chat_id = str(update.effective_chat.id)
                self.location_data[chat_id] = {
                    "latitude": location_info["latitude"],
                    "longitude": location_info["longitude"],
                    "city": location_info.get("city", city_name) if location_info is not None else city_name,
                    "timestamp": datetime.now().isoformat(),
                    "expires_at": (datetime.now() + timedelta(hours=24)).isoformat()
                }
                
                # Update processing message with more details
                if processing_msg:
                    state_text = location_info.get('state', "Noma'lum")
                    await safe_edit_message(processing_msg, f"✅ {city_name} topildi!\n\n"
                                                          f"🏙️ <b>Shahar:</b> {location_info['city']}\n"
                                                          f"🌍 <b>Mamlakat:</b> {location_info['country']}\n"
                                                          f"🏛️ <b>Viloyat:</b> {state_text}",
                                                          parse_mode=ParseMode.HTML)
                
                # Show detailed location information for searched city
                fake_location = type('Location', (), {
                    'latitude': location_info["latitude"],
                    'longitude': location_info["longitude"],
                    'horizontal_accuracy': None
                })()
                await self.show_detailed_location_info(update, context, fake_location, location_info, "")
            else:
                error_message = (f"❌ {city_name} topilmadi. Iltimos, boshqa nom kiriting.\n\n"
                               f"<i>Maslahatlar:</i>\n"
                               f"• Shahar nomini to'liq yozing\n"
                               f"• Boshqa tilga tarjima qilib ko'ring\n"
                               f"• Atrofdagi katta shaharlarni sinab ko'ring")
                if processing_msg:
                    await safe_edit_message(processing_msg, error_message, parse_mode=ParseMode.HTML)
                else:
                    if update.effective_message:
                        await update.effective_message.reply_text(error_message, parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.error(f"Shahar qidirishda xatolik: {e}")
            error_message = ("❌ Shahar qidirishda xatolik. Qaytadan urinib ko'ring.\n\n"
                           f"<i>Xato tavsifi:</i> {str(e)[:100]}...")
            if update.effective_message:
                await update.effective_message.reply_text(error_message, parse_mode=ParseMode.HTML)
    
    async def _get_location_info(self, latitude: float, longitude: float):
        """Get location information using Nominatim"""
        try:
            NOMINATIM_URL = "https://nominatim.openstreetmap.org"
            
            url = f"{NOMINATIM_URL}/reverse"
            params = {
                "format": "json",
                "lat": latitude,
                "lon": longitude,
                "accept-language": "uz"
            }
            
            headers = {
                "User-Agent": "AQLJON-bot/1.0 (https://t.me/AQLJON_bot)"
            }
            
            data = await http_get_with_retry(url, params=params, headers=headers, timeout=15)
            if data:
                address = data.get("address", {})

                city = (address.get("city") or
                       address.get("town") or
                       address.get("village") or
                       "Noma'lum shahar")

                country = address.get("country", "Noma'lum mamlakat")
                state = address.get("state", "")
                display_name = data.get("display_name", "Noma'lum joylashuv")

                return {
                    "city": city,
                    "country": country,
                    "state": state,
                    "display_name": display_name,
                    "latitude": latitude,
                    "longitude": longitude
                }
        except Exception as e:
            logger.error(f"Nominatimdan joylashuv ma'lumotlarini olishda xatolik: {e}")
            return {
                "city": "Noma'lum shahar",
                "country": "Noma'lum mamlakat",
                "state": "",
                "display_name": f"Koordinatalar: {latitude:.4f}, {longitude:.4f}",
                "latitude": latitude,
                "longitude": longitude
            }
    
    async def _get_location_info_by_name(self, city_name: str):
        """Get location information by city name using Nominatim"""
        try:
            NOMINATIM_URL = "https://nominatim.openstreetmap.org"
            
            url = f"{NOMINATIM_URL}/search"
            params = {
                "format": "json",
                "q": city_name,
                "addressdetails": 1,
                "limit": 5
            }
            
            headers = {
                "User-Agent": "AQLJON-bot/1.0 (https://t.me/AQLJON_bot)"
            }
            
            data = await http_get_with_retry(url, params=params, headers=headers, timeout=15)
            if data and len(data) > 0:
                # Get the most relevant result
                location = data[0]
                lat = float(location["lat"])
                lon = float(location["lon"])

                # Validate coordinates
                if not validate_coordinates(lat, lon):
                    logger.error(f"Invalid coordinates from Nominatim: {lat}, {lon}")
                    return None

                address = location.get("address", {})
                city = (address.get("city") or
                       address.get("town") or
                       address.get("village") or
                       city_name)

                country = address.get("country", "Noma'lum mamlakat")
                state = address.get("state", "")

                return {
                    "city": city,
                    "country": country,
                    "state": state,
                    "display_name": location.get("display_name", city_name),
                    "latitude": lat,
                    "longitude": lon
                }
        except Exception as e:
            logger.error(f"Nominatimdan shahar ma'lumotlarini olishda xatolik: {e}")
            return {
                "city": "Noma'lum shahar",
                "country": "Noma'lum mamlakat",
                "state": "",
                "display_name": f"Koordinatalar: Noma'lum",
                "latitude": 0.0,
                "longitude": 0.0
            }
    
    # ─── CALLBACK QUERY HANDLING ──────────────────────────────────────────────────
    
    async def handle_callback_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle callback queries from inline buttons"""
        if not update.callback_query:
            return
        
        query = update.callback_query
        await query.answer()  # Remove loading indication
        
        # Initialize user_data if it doesn't exist
        if context.user_data is None:
            context.user_data = {}
        
        try:
            # Handle different callback actions
            if query.data == "prayer_refresh":
                await self.prayer_handler.show_prayer_times(update, context)
            elif query.data == "location_search":
                # Prompt for city name
                if query.message:
                    await safe_edit_message(query.message, "🏙️ Iltimos, shahar nomini kiriting:")
                context.user_data['awaiting_city_name'] = True
            
            # Nearby places handling
            elif query.data == "nearby_menu":
                await self.nearby_handler.show_nearby_menu(update, context)
            elif query.data and query.data.startswith("nearby_page_"):
                try:
                    page_num = int(query.data.split("_")[-1])
                    await self.nearby_handler.show_nearby_menu(update, context, page=page_num)
                except (ValueError, IndexError):
                    await query.answer("❌ Noto'g'ri sahifa", show_alert=True)
            elif query.data and query.data.startswith("nearby_"):
                parts = query.data.split("_")
                if len(parts) >= 2:
                    # Handle different callback patterns more precisely
                    if len(parts) >= 4 and parts[0] == "nearby" and parts[1] == "detail":
                        # Format: nearby_detail_{place_type}_{place_index} or nearby_detail_{part1}_{part2}_{place_index}
                        # Extract place_type and place_index
                        if len(parts) == 5:  # nearby_detail_fast_food_0
                            detail_place_type = f"{parts[2]}_{parts[3]}"
                            place_index = int(parts[4]) if parts[4].isdigit() else 0
                        else:  # nearby_detail_cafe_0
                            detail_place_type = parts[2]
                            place_index = int(parts[3]) if parts[3].isdigit() else 0
                        await self.nearby_handler.show_place_detail(update, context, detail_place_type, place_index)
                    elif len(parts) >= 4 and parts[0] == "nearby" and parts[1] == "map":
                        # Format: nearby_map_{place_type}_{place_index}
                        if len(parts) == 5:  # nearby_map_fast_food_0
                            map_place_type = f"{parts[2]}_{parts[3]}"
                            place_index = int(parts[4]) if parts[4].isdigit() else 0
                        else:  # nearby_map_cafe_0
                            map_place_type = parts[2]
                            place_index = int(parts[3]) if parts[3].isdigit() else 0
                        await self.nearby_handler.show_place_map(update, context, map_place_type, place_index)
                    elif len(parts) >= 4 and parts[0] == "nearby" and parts[1] == "directions":
                        # Format: nearby_directions_{place_type}_{place_index}
                        if len(parts) == 5:  # nearby_directions_fast_food_0
                            directions_place_type = f"{parts[2]}_{parts[3]}"
                            place_index = int(parts[4]) if parts[4].isdigit() else 0
                        else:  # nearby_directions_cafe_0
                            directions_place_type = parts[2]
                            place_index = int(parts[3]) if parts[3].isdigit() else 0
                        await self.nearby_handler.show_directions(update, context, directions_place_type, place_index)
                    elif len(parts) >= 2 and parts[0] == "nearby" and parts[1] not in ["page", "menu", "info", "search"]:
                        # This is a place type selection or pagination for specific place types
                        # Check if it's pagination: nearby_{place_type}_{page}
                        if len(parts) >= 3 and parts[-1].isdigit():
                            # Format: nearby_{place_type}_{page}
                            if len(parts) == 3:  # nearby_fast_food_2
                                place_type = parts[1]
                                page = int(parts[2]) if parts[2].isdigit() else 1
                            else:  # Handle cases with underscores like nearby_fast_food_2
                                # Combine all middle parts as place_type except the last digit part
                                place_type = "_".join(parts[1:-1])
                                page = int(parts[-1]) if parts[-1].isdigit() else 1
                            await self.nearby_handler.search_nearby_places(update, context, place_type, page)
                        else:
                            # This is a place type selection, could be with underscores
                            # Format: nearby_fast_food or nearby_cafe
                            place_type = "_".join(parts[1:])  # Join all parts after "nearby" with underscores
                                
                            if place_type in ["cafe", "restaurant", "pizza", "fast_food", "confectionery", "tea_shop", 
                                            "bakery", "takeaway", "grocery", "marketplace", "supermarket", "books", 
                                            "clothes", "electronics", "bank", "hairdresser", "mobile_phone_repair", 
                                            "fuel", "car_service", "post_office", "doctor", "pharmacy", "hotel", 
                                            "school", "university", "bus_stop", "train_station", "aerodrome", 
                                            "taxi_stand", "bicycle_rental"]:
                                await self.nearby_handler.search_nearby_places(update, context, place_type, 1)
                    elif len(parts) >= 3 and parts[1] == "page":
                        # Handle pagination: nearby_page_2
                        page_num = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 1
                        await self.nearby_handler.show_nearby_menu(update, context, page=page_num)
                    elif parts[1] == "menu":
                        # Back to nearby menu
                        await self.nearby_handler.show_nearby_menu(update, context)
                    elif parts[1] == "info":
                        await query.answer("Sahifa raqami", show_alert=False)
                    elif len(parts) >= 3 and parts[1] == "search":
                        # Handle search with place type and page
                        search_place_type = parts[2]
                        page = 1
                        if len(parts) > 3 and parts[3].isdigit():
                            page = int(parts[3])
                        await self.nearby_handler.search_nearby_places(update, context, search_place_type, page)
            
            # Favorites handling
            elif query.data == "favorites_add":
                await self.favorites_handler.add_favorite(update, context)
            elif query.data == "favorites_list":
                await self.favorites_handler.list_favorites(update, context)
            elif query.data == "favorites_delete":
                await self.favorites_handler.delete_favorite_menu(update, context)
            elif query.data == "favorites_menu":
                await self.favorites_handler.show_favorites_menu(update, context)
            elif query.data == "favorites_stats":
                await self.favorites_handler.show_statistics(update, context)
            elif query.data and query.data.startswith("favorites_"):
                parts = query.data.split("_")
                if len(parts) >= 3:
                    action = parts[1]
                    
                    if action == "view":
                        index = int(parts[2]) if parts[2].isdigit() else 0
                        await self.favorites_handler.view_favorite(update, context, index)
                    elif action == "map":
                        index = int(parts[2]) if parts[2].isdigit() else 0
                        await self.favorites_handler.show_map(update, context, index)
                    elif action == "directions":
                        index = int(parts[2]) if parts[2].isdigit() else 0
                        await self.favorites_handler.show_directions(update, context, index)
                    elif action == "delete" and len(parts) >= 4:
                        # Handle delete actions with proper index parsing
                        if parts[2] == "confirm":
                            index = int(parts[3]) if parts[3].isdigit() else 0
                            await self.favorites_handler.confirm_delete(update, context, index)
                        elif parts[2] == "final":
                            index = int(parts[3]) if parts[3].isdigit() else 0
                            await self.favorites_handler.delete_favorite(update, context, index)
                    elif action == "page":
                        # Handle pagination for favorites
                        page = int(parts[2]) if parts[2].isdigit() else 1
                        await self.favorites_handler.list_favorites(update, context, page)
                    elif action in ["add", "list", "menu", "stats"]:
                        # Handle simple favorites actions
                        if action == "add":
                            await self.favorites_handler.add_favorite(update, context)
                        elif action == "list":
                            await self.favorites_handler.list_favorites(update, context)
                        elif action == "menu":
                            await self.favorites_handler.show_favorites_menu(update, context)
                        elif action == "stats":
                            await self.favorites_handler.show_statistics(update, context)
            
            # Location menu handling
            elif query.data == "location_menu":
                # Show location services keyboard
                from modules.utils import location_services_keyboard
                if query.message:
                    await safe_edit_message(
                        query.message,
                        "🌍 <b>Joylashuv xizmatlari</b>\n\n"
                        "Endi quyidagi joylashuv xizmatlaridan foydalanishingiz mumkin:",
                        parse_mode=ParseMode.HTML
                    )
                # Send location services keyboard separately
                if update.effective_message:
                    await update.effective_message.reply_text(
                        "Joylashuv xizmatlari", 
                        reply_markup=location_services_keyboard()
                    )
            
            # Main menu
            elif query.data == "main_menu":
                from modules.utils import main_menu_keyboard
                if query.message:
                    await safe_edit_message(
                        query.message,
                        "🏠 <b>Bosh menyu</b>",
                        parse_mode=ParseMode.HTML
                    )
                # Send main menu keyboard separately
                if update.effective_message:
                    await update.effective_message.reply_text(
                        "Bosh menyu", 
                        reply_markup=main_menu_keyboard()
                    )
            
        except Exception as e:
            logger.error(f"Callback query handlingda xatolik: {e}")
            await query.answer("❌ Xatolik yuz berdi. Qaytadan urinib ko'ring.", show_alert=True)

    async def handle_favorite_city_search(self, update: Update, context: ContextTypes.DEFAULT_TYPE, city_name: str):
        """Handle city search for favorite location"""
        if not update.effective_chat:
            return
        
        try:
            # Show processing message
            processing_msg = await safe_reply(update, "🏙️ Shahar qidirilmoqda...")
            
            # Using Nominatim for geocoding
            location_info = await self._get_location_info_by_name(city_name)
            
            if location_info:
                # Store temporary location info
                chat_id = str(update.effective_chat.id)
                if context.user_data is None:
                    context.user_data = {}
                context.user_data['temp_favorite_location'] = {
                    "latitude": location_info["latitude"],
                    "longitude": location_info["longitude"],
                    "city": location_info.get("city", city_name) if location_info is not None else city_name,
                    "timestamp": datetime.now().isoformat()
                }
                
                # Update processing message
                if processing_msg:
                    await safe_edit_message(processing_msg, f"✅ {city_name} topildi!")
                
                # Automatically use city name as favorite name instead of asking user
                favorite_name = location_info.get("city", city_name) if location_info is not None else city_name
                await self.save_favorite_with_location(update, context, favorite_name)
                
                # Remove the adding_favorite and awaiting_favorite_location flags
                if 'adding_favorite' in context.user_data:
                    del context.user_data['adding_favorite']
                if 'awaiting_favorite_location' in context.user_data:
                    del context.user_data['awaiting_favorite_location']
                
    
            else:
                if processing_msg:
                    await safe_edit_message(processing_msg, f"❌ {city_name} topilmadi. Iltimos, boshqa nom kiriting.")
                else:
                    if update.effective_message:
                        await update.effective_message.reply_text(f"❌ {city_name} topilmadi. Iltimos, boshqa nom kiriting.")
        except Exception as e:
            logger.error(f"Shahar qidirishda xatolik: {e}")
            if update.effective_message:
                await update.effective_message.reply_text("❌ Shahar qidirishda xatolik. Qaytadan urinib ko'ring.")

    async def save_favorite_with_location(self, update: Update, context: ContextTypes.DEFAULT_TYPE, favorite_name: str):
        """Save a new favorite place with location"""
        if not update.effective_chat:
            return
            
        chat_id = str(update.effective_chat.id)
        
        # Check if we have temporary location info
        if context.user_data is None or 'temp_favorite_location' not in context.user_data:
            if update.effective_message:
                await update.effective_message.reply_text("❌ Xatolik yuz berdi. Iltimos, qaytadan urinib ko'ring.")
            return
        
        # Get location info
        location_info = context.user_data['temp_favorite_location']
        del context.user_data['temp_favorite_location']
        
        # Create favorite object
        favorite = {
            "id": f"fav_{int(datetime.now().timestamp())}",
            "name": favorite_name,
            "latitude": location_info["latitude"],
            "longitude": location_info["longitude"],
            "created_at": datetime.now().isoformat(),
            "category": "Umumiy",
            "notes": ""
        }
        
        # Store favorite
        if chat_id not in self.user_favorites:
            self.user_favorites[chat_id] = []
        self.user_favorites[chat_id].append(favorite)
        
        # Send confirmation with detailed location info
        lat = location_info["latitude"]
        lon = location_info["longitude"]
        city = location_info.get("city", "Noma'lum shahar")
        
        confirmation_message = f"✅ <b>Sevimli joyingiz saqlandi!</b>\n\n"
        confirmation_message += f"⭐ <b>Nom:</b> {favorite_name}\n"
        confirmation_message += f"🏙️ <b>Shahar:</b> {city}\n"
        confirmation_message += f"📍 <b>Koordinatalar:</b>\n"
        confirmation_message += f"• <b>Kenglik:</b> {lat:.6f}\n"
        confirmation_message += f"• <b>Uzunlik:</b> {lon:.6f}\n\n"
        confirmation_message += "Endi bu joyga tezda qaytish uchun 'Sevimli joylarim' menyusidan foydalanishingiz mumkin."
        
        if update.effective_message:
            await update.effective_message.reply_text(
                confirmation_message,
                parse_mode=ParseMode.HTML
            )
        
        # Show favorites menu with appropriate keyboard
        await self.favorites_handler.show_favorites_menu(update, context)

   