import logging
import aiohttp
import math
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Location
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from modules.utils import safe_reply

logger = logging.getLogger(__name__)

class NearbyHandler:
    """Handles nearby places functionality with improved UI/UX"""
    
    def __init__(self, location_data, cached_data):
        self.location_data = location_data
        self.cached_data = cached_data
        self.OVERPASS_URL = "https://overpass-api.de/api/interpreter"
    
    async def show_nearby_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE, page=1):
        """Show nearby places category menu with pagination"""
        # Define categories with better organization - exactly 30 categories total
        categories = [
            # Page 1 - Food & Dining (10 categories)
            ("☕ Kafelar", "nearby_cafe"),
            ("🍽️ Restoranlar", "nearby_restaurant"),
            ("🍕 Pitsa do'konlar", "nearby_pizza"),
            ("🍔 Fast food", "nearby_fast_food"),
            ("🍦 Shirinliklar", "nearby_confectionery"),
            ("🧋 Choyxonalar", "nearby_tea_shop"),
            ("🍞 Non do'konlari", "nearby_bakery"),
            ("🥡 Takeaway", "nearby_takeaway"),
            ("🛒 Oziq-ovqat do'konlari", "nearby_grocery"),
            ("🏪 Bozorlar", "nearby_marketplace"),
            
            # Page 2 - Shopping & Services (10 categories)
            ("🏪 Supermarketlar", "nearby_supermarket"),
            ("👕 Kiyim do'konlari", "nearby_clothes"),
            ("💻 Elektronika do'konlari", "nearby_electronics"),
            ("📚 Kitob do'konlari", "nearby_books"),
            ("🏦 Banklar", "nearby_bank"),
            ("💇 Salonlar", "nearby_hairdresser"),
            ("📱 Mobil telefon ustalari", "nearby_mobile_phone_repair"),
            ("⛽ Avto zapravkalar", "nearby_fuel"),
            ("🚗 Avtoservis", "nearby_car_service"),
            ("📦 Pochta", "nearby_post_office"),
            
            # Page 3 - Health, Education & Transportation (10 categories)
            ("🏥 Shifokorlar/Klinika", "nearby_doctor"),
            ("⚕️ Dorixonalar", "nearby_pharmacy"),
            ("🏨 Mehmonxonalar", "nearby_hotel"),
            ("🏫 Maktablar", "nearby_school"),
            ("🏢 Universitetlar", "nearby_university"),
            ("🚌 Avtobus bekati", "nearby_bus_stop"),
            ("🚉 Temir yo'l stansiyasi", "nearby_train_station"),
            ("✈️ Aeroportlar", "nearby_aerodrome"),
            ("🚖 Taksi turargohi", "nearby_taxi_stand"),
            ("🚲 Velosiped ijarasi", "nearby_bicycle_rental"),
        ]
        
        # Pagination settings - 3 pages with 10 categories each
        items_per_page = 10
        total_pages = 3  # Fixed to 3 pages as requested
        
        # Adjust page if out of range
        page = max(1, min(page, total_pages))
        
        # Get items for current page
        start_index = (page - 1) * items_per_page
        end_index = min(start_index + items_per_page, len(categories))
        page_categories = categories[start_index:end_index]
        
        # Create message with better formatting
        message_text = "📍 <b>Yaqin-atrofdagi joylar</b>\n"
        message_text += "==============================\n\n"
        message_text += "<i>Qaysi turdagi joylarni qidirmoqchisiz?</i>\n\n"
        
        # Add category headers
        current_category = None
        for i, (category_name, callback_data) in enumerate(page_categories):
            # Determine category group
            if start_index < 10:  # Page 1 - Food & Dining
                category_group = "Food & Dining"
            elif start_index < 20:  # Page 2 - Shopping & Services
                category_group = "Shopping & Services"
            else:  # Page 3 - Health, Education & Transportation
                category_group = "Health, Education & Transportation"
            
            # Add category header if it's a new group
            if i == 0:  # First item on page
                message_text += f"🔷 <b>{category_group}:</b>\n"
            
            message_text += f"   • {category_name}\n"
        
        message_text += "\n"
   
        # Add footer with navigation instructions
        message_text += f"🔷 <b>Jami kategoriyalar:</b> {len(categories)}\n"
        message_text += f"📄 <b>Jami sahifalar:</b> {total_pages}\n\n"
        
        # Create keyboard
        keyboard = []
        
        # Add category buttons (2 per row)
        for i in range(0, len(page_categories), 2):
            row = []
            row.append(InlineKeyboardButton(page_categories[i][0], callback_data=page_categories[i][1]))
            if i + 1 < len(page_categories):
                row.append(InlineKeyboardButton(page_categories[i + 1][0], callback_data=page_categories[i + 1][1]))
            keyboard.append(row)
        
        # Add pagination controls
        pagination_row = []
        if page > 1:
            pagination_row.append(InlineKeyboardButton("⬅️ Oldingi", callback_data=f"nearby_page_{page-1}"))
        
        # Add page indicator
        pagination_row.append(InlineKeyboardButton(f"{page}/{total_pages}", callback_data="nearby_info"))
        
        if page < total_pages:
            pagination_row.append(InlineKeyboardButton("Keyingi ➡️", callback_data=f"nearby_page_{page+1}"))
        
        if pagination_row:
            keyboard.append(pagination_row)
        
        # Add back to main menu button
        keyboard.append([InlineKeyboardButton("🏠 Bosh menyu", callback_data="nearby_menu")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Send or edit message
        if update.callback_query and update.callback_query.message:
            try:
                await update.callback_query.edit_message_text(
                    message_text, 
                    parse_mode=ParseMode.HTML, 
                    reply_markup=reply_markup
                )
            except Exception as e:
                if "Message is not modified" in str(e):
                    await update.callback_query.answer("✅ Yangilangan", show_alert=False)
                else:
                    raise
        elif update.message:
            await update.message.reply_text(
                message_text, 
                parse_mode=ParseMode.HTML, 
                reply_markup=reply_markup
            )
    
    async def search_nearby_places(self, update: Update, context: ContextTypes.DEFAULT_TYPE, place_type: str, page=1):
        """Search for nearby places of a specific type with adaptive radius"""
        query = update.callback_query
        if not query or not query.message:
            return
            
        chat_id = str(query.message.chat.id)
        
        # Check if user has shared location
        if chat_id not in self.location_data:
            await query.answer("📍 Avval joylashuvingizni yuboring!", show_alert=True)
            return
        
        # Check if location data has expired
        location = self.location_data[chat_id]
        if "expires_at" in location:
            expires_at = datetime.fromisoformat(location["expires_at"])
            if datetime.now() > expires_at:
                await query.answer("📍 Joylashuv ma'lumotlari eskirgan. Iltimos, qaytadan jo'natish!", show_alert=True)
                return
        
        location = self.location_data[chat_id]
        user_lat = location["latitude"]
        user_lon = location["longitude"]
        
        # Map place types to display names - all 30 categories
        place_names = {
            "cafe": "Kafelar",
            "restaurant": "Restoranlar",
            "pizza": "Pitsa do'konlar",
            "fast_food": "Fast food",
            "confectionery": "Shirinliklar",
            "tea_shop": "Choyxonalar",
            "bakery": "Non do'konlari",
            "takeaway": "Ovqat olib ketish",
            "grocery": "Oziq-ovqat do'konlari",
            "marketplace": "Bozorlar",
            "supermarket": "Supermarketlar",
            "clothes": "Kiyim do'konlari",
            "electronics": "Elektronika do'konlari",
            "books": "Kitob do'konlari",
            "bank": "Banklar",
            "hairdresser": "Salonlar",
            "mobile_phone_repair": "Mobil telefon ustalari",
            "fuel": "Avto zapravkalar",
            "car_service": "Avtoservis",
            "post_office": "Pochta",
            "doctor": "Shifokorlar/Klinika",
            "pharmacy": "Dorixonalar",
            "hotel": "Mehmonxonalar",
            "school": "Maktablar",
            "university": "Universitetlar",
            "bus_stop": "Avtobus bekati",
            "train_station": "Temir yo'l stansiyasi",
            "aerodrome": "Aeroportlar",
            "taxi_stand": "Taksi turargohi",
            "bicycle_rental": "Velosiped ijarasi",
        }
        
        place_name = place_names.get(place_type, place_type.capitalize())
        
        try:
            await query.answer(f"🔍 {place_name} qidirilmoqda...")
            
            # Check cache first
            cache_key = f"nearby_{chat_id}_{place_type}"
            if cache_key in self.cached_data:
                cached_entry = self.cached_data[cache_key]
                if datetime.now() < cached_entry["expires_at"]:
                    places_with_distance = cached_entry["data"]
                    await self._show_places_list(query, places_with_distance, place_name, page, place_type)
                    return
            
            # Adaptive search radius implementation
            # Start with a smaller radius and increase if needed
            search_radii = [2000, 5000, 10000, 20000]  # 2km, 5km, 10km, 20km
            elements = []
            used_radius = 2000  # Default radius
            
            # Try different radii until we find places or exhaust all options
            for radius in search_radii:
                # Using Overpass API to find nearby places with adaptive search radius
                overpass_query = f"""
                [out:json][timeout:25];
                (
                  node["amenity"="{place_type}"](around:{radius},{user_lat},{user_lon});
                  way["amenity"="{place_type}"](around:{radius},{user_lat},{user_lon});
                  relation["amenity"="{place_type}"](around:{radius},{user_lat},{user_lon});
                  node["shop"="{place_type}"](around:{radius},{user_lat},{user_lon});
                  way["shop"="{place_type}"](around:{radius},{user_lat},{user_lon});
                  node["tourism"="{place_type}"](around:{radius},{user_lat},{user_lon});
                  way["tourism"="{place_type}"](around:{radius},{user_lat},{user_lon});
                );
                out center;
                """
                
                async with aiohttp.ClientSession() as session:
                    async with session.post(self.OVERPASS_URL, data={"data": overpass_query}) as response:
                        if response.status == 200:
                            data = await response.json()
                            elements = data.get("elements", [])
                            
                            # If we found places or this is the largest radius, stop searching
                            if elements or radius == search_radii[-1]:
                                used_radius = radius
                                break
                            # If no places found and this isn't the largest radius, try a larger radius
                            else:
                                continue
                        else:
                            # Try next radius on API error
                            continue
            
            if elements:
                # Process elements
                places_with_distance = []
                for element in elements:
                    tags = element.get("tags", {})
                    name = tags.get("name", "Noma'lum")
                    
                    # Get coordinates
                    if "center" in element:
                        lat = element["center"]["lat"]
                        lon = element["center"]["lon"]
                    else:
                        lat = element["lat"]
                        lon = element["lon"]
                    
                    # Calculate distance
                    distance = self._calculate_distance(user_lat, user_lon, lat, lon)
                    places_with_distance.append((element, name, distance, lat, lon))
                
                # Sort by distance
                places_with_distance.sort(key=lambda x: x[2])
                
                # Cache results with place type
                self.cached_data[cache_key] = {
                    "data": places_with_distance,
                    "expires_at": datetime.now() + timedelta(minutes=10),
                    "place_type": place_type
                }
                
                await self._show_places_list(query, places_with_distance, place_name, page, place_type)
            else:
                error_message = (
                    f"❌ <b>{place_name} topilmadi</b>\n"
                    f"{'=' * (len(place_name) + 15)}\n\n"
                    f"<i>Bu kategoriyada yaqin-atrofda joylar topilmadi.</i>\n"
                    f"<i>Qidiruv radiusi: {used_radius/1000:.1f} km</i>\n\n"
                    f"<i>Maslahatlar:</i>\n"
                    f"• Radiusni kengaytirish\n"
                    f"• Boshqa kategoriyani sinab ko'rish\n"
                    f"• Aniqroq joylashuvni yuborish"
                )
                await query.edit_message_text(
                    error_message,
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Orqaga", callback_data="nearby_menu"), InlineKeyboardButton("🏠 Bosh menyu", callback_data="nearby_menu")]])
                )
        except Exception as e:
            logger.error(f"Yaqin-atrofdagi joylarni qidirishda xatolik: {e}")
            error_message = (
                f"❌ <b>{place_name} topilmadi</b>\n"
                f"{'=' * (len(place_name) + 15)}\n\n"
                f"<i>Xatolik yuz berdi. Keyinroq qayta urinib ko'ring.</i>\n\n"
                f"<i>Maslahatlar:</i>\n"
                f"• Boshqa joyda sinab ko'ring\n"
                f"• Boshqa kategoriyani sinab ko'ring\n"
                f"• Aniqroq joylashuvni yuboring"
            )
            try:
                await query.edit_message_text(
                    error_message,
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Orqaga", callback_data="nearby_menu"), InlineKeyboardButton("🏠 Bosh menyu", callback_data="nearby_menu")]])
                )
            except:
                # If we can't edit the message, just answer the query
                await query.answer("❌ Xatolik yuz berdi. Keyinroq qayta urinib ko'ring.", show_alert=True)
    
    async def _show_places_list(self, query, places_with_distance, place_name, page, place_type):
        """Show list of places with pagination"""
        # Pagination settings
        items_per_page = 10
        total_pages = (len(places_with_distance) + items_per_page - 1) // items_per_page
        page = max(1, min(page, total_pages))
        
        # Get items for current page
        start_index = (page - 1) * items_per_page
        end_index = min(start_index + items_per_page, len(places_with_distance))
        page_places = places_with_distance[start_index:end_index]
        
        # Create message with better formatting
        places_text = f"📍 <b>{place_name}</b>\n"
        places_text += "=" * (len(place_name) + 2) + "\n\n"
        
        for i, (element, name, distance, lat, lon) in enumerate(page_places, start_index + 1):
            # Get additional details for better UI
            tags = element.get("tags", {})
            phone = tags.get("phone", "")
            website = tags.get("website", "")
            
            # Add place info with better formatting
            places_text += f"📍 <b>{i}. {name}</b>\n"
            places_text += f"   📏 <i>Masofa:</i> {distance:.2f} km"
            
            # Add phone if available
            if phone:
                places_text += f"\n   📞 <i>Telefon:</i> {phone}"
            
            # Add website if available
            if website:
                places_text += f"\n   🌐 <i>Vebsayt:</i> {website}"
            
            places_text += "\n\n"
        
        # Add instructions
        places_text += "<i>Qo'shimcha ma'lumot olish uchun quyidagi tugmalardan birini tanlang</i>\n\n"
        places_text += "<i>Har bir tugma mos raqamli joy haqida ma'lumot beradi</i>\n\n"

        # Add footer with category information
        places_text += f"🔷 <b>Kategoriya:</b> {place_name}\n"
        places_text += f"📄 <b>Sahifa:</b> {page}/{total_pages}\n\n"
        
        # Create keyboard
        keyboard = []
        
        # Add place selection buttons (2 per row)
        for i in range(0, len(page_places), 2):
            row = []
            # First button
            place_index = start_index + i
            name_1 = page_places[i][1]
            if len(name_1) > 20:
                button_text_1 = f"{place_index + 1}. {name_1[:17]}..."
            else:
                button_text_1 = f"{place_index + 1}. {name_1}"
            # Include place_type in callback data to identify the correct cache
            callback_data_1 = f"nearby_detail_{place_type}_{place_index}"
            row.append(InlineKeyboardButton(button_text_1, callback_data=callback_data_1))
            
            # Second button if exists
            if i + 1 < len(page_places):
                place_index_2 = start_index + i + 1
                name_2 = page_places[i + 1][1]
                if len(name_2) > 20:
                    button_text_2 = f"{place_index_2 + 1}. {name_2[:17]}..."
                else:
                    button_text_2 = f"{place_index_2 + 1}. {name_2}"
                # Include place_type in callback data to identify the correct cache
                callback_data_2 = f"nearby_detail_{place_type}_{place_index_2}"
                row.append(InlineKeyboardButton(button_text_2, callback_data=callback_data_2))
            
            keyboard.append(row)
        
        # Add pagination controls
        pagination_row = []
        if page > 1:
            pagination_row.append(InlineKeyboardButton("⬅️ Oldingi", callback_data=f"nearby_{place_type}_{page-1}"))
        
        # Add page indicator
        pagination_row.append(InlineKeyboardButton(f"{page}/{total_pages}", callback_data="nearby_info"))
        
        if page < total_pages:
            pagination_row.append(InlineKeyboardButton("Keyingi ➡️", callback_data=f"nearby_{place_type}_{page+1}"))
        
        if pagination_row:
            keyboard.append(pagination_row)
        
        # Add navigation buttons
        keyboard.append([
            InlineKeyboardButton("⬅️ Orqaga", callback_data="nearby_menu"),
            InlineKeyboardButton("🏠 Bosh menyu", callback_data="nearby_menu")
        ])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            places_text,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup
        )
    
    async def show_place_detail(self, update: Update, context: ContextTypes.DEFAULT_TYPE, place_type: str, place_index: int):
        """Show detailed information for a specific place"""
        query = update.callback_query
        if not query or not query.message:
            return
            
        chat_id = str(query.message.chat.id)
        
        # Find cached data for the specific place type
        cache_key = f"nearby_{chat_id}_{place_type}"
        places_with_distance = None
        
        if cache_key in self.cached_data:
            cached_entry = self.cached_data[cache_key]
            if datetime.now() < cached_entry["expires_at"]:
                places_with_distance = cached_entry["data"]
        
        if not places_with_distance:
            await query.answer("❌ Ma'lumotlar topilmadi. Qayta qidiring.", show_alert=True)
            return
        
        # Check if index is valid
        if place_index < 0 or place_index >= len(places_with_distance):
            await query.answer("❌ Noto'g'ri tanlov!", show_alert=True)
            return
        
        element, name, distance, lat, lon = places_with_distance[place_index]
        tags = element.get("tags", {})
        
        # Get details
        phone = tags.get("phone", "Noma'lum")
        website = tags.get("website", "Noma'lum")
        opening_hours = tags.get("opening_hours", "Noma'lum")
        street = tags.get("addr:street", "")
        housenumber = tags.get("addr:housenumber", "")
        city = tags.get("addr:city", "")
        postcode = tags.get("addr:postcode", "")
        
        # Build address
        address_parts = [part for part in [street, housenumber, city, postcode] if part]
        address = ", ".join(address_parts) if address_parts else "Noma'lum"
        
        # Create detailed message with better formatting
        detail_text = f"📍 <b>{name}</b>\n"
        detail_text += "=" * (len(name) + 2) + "\n\n"
        
        # Add location information header
        detail_text += "📍 <b>Joylashuv ma'lumotlari:</b>\n"
        detail_text += f"📏 <b>Masofa:</b> {distance:.2f} km\n"
        if address and address != "Noma'lum":
            detail_text += f"🏠 <b>Manzil:</b> {address}\n"
        detail_text += "\n"
        
        # Add contact information header
        if (phone and phone != "Noma'lum") or (website and website != "Noma'lum") or (opening_hours and opening_hours != "Noma'lum"):
            detail_text += "📱 <b>Aloqa ma'lumotlari:</b>\n"
            if phone and phone != "Noma'lum":
                detail_text += f"• 📞 Telefon: {phone}\n"
            if website and website != "Noma'lum":
                detail_text += f"• 🌐 Vebsayt: {website}\n"
            if opening_hours and opening_hours != "Noma'lum":
                detail_text += f"• 🕒 Ish vaqti: {opening_hours}\n"
            detail_text += "\n"
        
        # Add coordinates information
        detail_text += "🧭 <b>Koordinatalar:</b>\n"
        detail_text += f"• <b>Kenglik (latitude):</b> {lat:.6f}\n"
        detail_text += f"• <b>Uzunlik (longitude):</b> {lon:.6f}\n"
        detail_text += "\n"
        
        # Add additional details if available
        cuisine = tags.get("cuisine", "")
        brand = tags.get("brand", "")
        operator = tags.get("operator", "")
        
        if cuisine or brand or operator:
            detail_text += "📋 <b>Qo'shimcha ma'lumotlar:</b>\n"
            if cuisine:
                detail_text += f"• <b>Ovqat turi:</b> {cuisine}\n"
            if brand:
                detail_text += f"• <b>Brend:</b> {brand}\n"
            if operator:
                detail_text += f"• <b>Operator:</b> {operator}\n"
            detail_text += "\n"
        
        # Add action buttons with better description
        detail_text += "📋 <b>Mavjud amallar:</b>\n"
        detail_text += "<i>Quyidagi tugmalardan birini tanlang:</i>\n\n"
        detail_text += "• 🗺️ <b>Xaritada ko'rish</b> - Joylashuvni xaritada ko'ring\n"
        detail_text += "• 🧭 <b>Yo'nalish olish</b> - Google Maps orqali yo'nalish oling\n"
        detail_text += "• ⬅️ <b>Orqaga</b> - Ro'yxatga qayting\n"
        detail_text += "• 🏠 <b>Bosh menyu</b> - Asosiy menyuga qayting\n\n"
        
        # Add footer with place information
        detail_text += f"🔷 <b>Joy nomi:</b> {name}\n"
        detail_text += f"📄 <b>Raqam:</b> {place_index + 1}\n\n"
        
        # Create keyboard
        keyboard = [
            [InlineKeyboardButton("🗺️ Xaritada ko'rish", callback_data=f"nearby_map_{place_type}_{place_index}")],
            [InlineKeyboardButton("🧭 Yo'nalish olish", callback_data=f"nearby_directions_{place_type}_{place_index}")],
            [InlineKeyboardButton("⬅️ Orqaga", callback_data=f"nearby_{place_type}_1")],
            [InlineKeyboardButton("🏠 Bosh menyu", callback_data="nearby_menu")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            detail_text,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup
        )
    
    async def show_place_map(self, update: Update, context: ContextTypes.DEFAULT_TYPE, place_type: str, place_index: int):
        """Show place on map"""
        query = update.callback_query
        if not query or not query.message:
            return
            
        chat_id = str(query.message.chat.id)
        
        # Find cached data for the specific place type
        cache_key = f"nearby_{chat_id}_{place_type}"
        places_with_distance = None
        
        if cache_key in self.cached_data:
            cached_entry = self.cached_data[cache_key]
            if datetime.now() < cached_entry["expires_at"]:
                places_with_distance = cached_entry["data"]
        
        if not places_with_distance:
            await query.answer("❌ Ma'lumotlar topilmadi. Qayta qidiring.", show_alert=True)
            return
        
        # Check if index is valid
        if place_index < 0 or place_index >= len(places_with_distance):
            await query.answer("❌ Noto'g'ri tanlov!", show_alert=True)
            return
        
        element, name, distance, lat, lon = places_with_distance[place_index]
        
        # Send location
        location_msg = Location(longitude=lon, latitude=lat)
        
        # Create back button callback data
        back_callback = f"nearby_{place_type}_1"
        
        # Get additional details for the map view
        tags = element.get("tags", {})
        phone = tags.get("phone", "Noma'lum")
        website = tags.get("website", "Noma'lum")
        opening_hours = tags.get("opening_hours", "Noma'lum")
        street = tags.get("addr:street", "")
        housenumber = tags.get("addr:housenumber", "")
        city = tags.get("addr:city", "")
        postcode = tags.get("addr:postcode", "")
        
        # Build address
        address_parts = [part for part in [street, housenumber, city, postcode] if part]
        address = ", ".join(address_parts) if address_parts else "Noma'lum"
        
        # Create detailed map message
        map_text = f"📍 <b>{name}</b> joylashuvi xaritada ko'rsatilgan\n"
        map_text += "=" * (len(name) + 20) + "\n\n"
        
        map_text += "📍 <b>Joylashuv ma'lumotlari:</b>\n"
        map_text += f"• <b>Kenglik (latitude):</b> {lat:.6f}\n"
        map_text += f"• <b>Uzunlik (longitude):</b> {lon:.6f}\n"
        if address and address != "Noma'lum":
            map_text += f"• <b>Manzil:</b> {address}\n"
        map_text += "\n"
        
        # Add contact information if available
        if (phone and phone != "Noma'lum") or (website and website != "Noma'lum"):
            map_text += "📱 <b>Aloqa ma'lumotlari:</b>\n"
            if phone and phone != "Noma'lum":
                map_text += f"• 📞 <b>Telefon:</b> {phone}\n"
            if website and website != "Noma'lum":
                map_text += f"• 🌐 <b>Vebsayt:</b> {website}\n"
            if opening_hours and opening_hours != "Noma'lum":
                map_text += f"• 🕒 <b>Ish vaqti:</b> {opening_hours}\n"
            map_text += "\n"
        
        map_text += "<i>Xaritada ko'rish uchun yuqoridagi joylashuv xabarini oching</i>\n\n"
        map_text += "<i>Joylashuvni Google Maps ilovasida ochish uchun xabarni bosing</i>\n\n"
        
        # Add footer with place information
        map_text += f"🔷 <b>Joy nomi:</b> {name}\n"
        map_text += f"📄 <b>Raqam:</b> {place_index + 1}\n\n"
        
        if update.effective_message:
            await update.effective_message.reply_location(location=location_msg)
            await update.effective_message.reply_text(
                map_text,
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Orqaga", callback_data=back_callback), InlineKeyboardButton("🏠 Bosh menyu", callback_data="nearby_menu")]])
            )
        
        await query.answer(f"📍 {name} xaritada ko'rsatildi", show_alert=False)
    
    async def show_directions(self, update: Update, context: ContextTypes.DEFAULT_TYPE, place_type: str, place_index: int):
        """Show directions to place"""
        query = update.callback_query
        if not query or not query.message:
            return
            
        chat_id = str(query.message.chat.id)
        
        # Find cached data for the specific place type
        cache_key = f"nearby_{chat_id}_{place_type}"
        places_with_distance = None
        
        if cache_key in self.cached_data:
            cached_entry = self.cached_data[cache_key]
            if datetime.now() < cached_entry["expires_at"]:
                places_with_distance = cached_entry["data"]
        
        if not places_with_distance:
            await query.answer("❌ Ma'lumotlar topilmadi. Qayta qidiring.", show_alert=True)
            return
        
        # Check if index is valid
        if place_index < 0 or place_index >= len(places_with_distance):
            await query.answer("❌ Noto'g'ri tanlov!", show_alert=True)
            return
        
        element, name, distance, lat, lon = places_with_distance[place_index]
        
        # Check if user has shared location
        if chat_id not in self.location_data:
            await query.answer("📍 Avval joylashuvingizni yuboring!", show_alert=True)
            return
        
        # Check if location data has expired
        location = self.location_data[chat_id]
        if "expires_at" in location:
            expires_at = datetime.fromisoformat(location["expires_at"])
            if datetime.now() > expires_at:
                await query.answer("📍 Joylashuv ma'lumotlari eskirgan. Iltimos, qaytadan jo'natish!", show_alert=True)
                return
        
        location = self.location_data[chat_id]
        user_lat = location["latitude"]
        user_lon = location["longitude"]
        
        # Provide directions link (Google Maps)
        directions_url = f"https://www.google.com/maps/dir/?api=1&origin={user_lat},{user_lon}&destination={lat},{lon}"
        
        # Create back button callback data
        back_callback = f"nearby_{place_type}_1"
        
        # Get additional details for the directions view
        tags = element.get("tags", {})
        phone = tags.get("phone", "")
        website = tags.get("website", "")
        street = tags.get("addr:street", "")
        housenumber = tags.get("addr:housenumber", "")
        city = tags.get("addr:city", "")
        postcode = tags.get("addr:postcode", "")
        
        # Build address
        address_parts = [part for part in [street, housenumber, city, postcode] if part]
        address = ", ".join(address_parts) if address_parts else ""
        
        # Create detailed directions message
        directions_text = f"🧭 <b>{name} ga yo'nalish</b>\n"
        directions_text += "=" * (len(name) + 15) + "\n\n"
        
        directions_text += "📍 <b>Manzil:</b>\n"
        directions_text += f"• <b>Joy nomi:</b> {name}\n"
        if address:
            directions_text += f"• <b>Manzil:</b> {address}\n"
        directions_text += f"• <b>Koordinatalar:</b> {lat:.6f}, {lon:.6f}\n\n"
        
        # Add contact information if available
        if phone or website:
            directions_text += "📱 <b>Aloqa ma'lumotlari:</b>\n"
            if phone:
                directions_text += f"• 📞 <b>Telefon:</b> {phone}\n"
            if website:
                directions_text += f"• 🌐 <b>Vebsayt:</b> {website}\n"
            directions_text += "\n"
        
        directions_text += "🧭 <b>Yo'nalish:</b>\n"
        directions_text += f"<a href='{directions_url}'>Google Maps orqali yo'nalish olish</a>\n\n"
        directions_text += "<i>Yo'nalishni ochish uchun havolani bosing</i>\n\n"
        directions_text += "<i>Yo'nalishni Google Maps ilovasida ochish uchun havolani bosing</i>\n\n"
        
        # Add footer with place information
        directions_text += f"🔷 <b>Joy nomi:</b> {name}\n"
        directions_text += f"📄 <b>Raqam:</b> {place_index + 1}\n\n"
        
        await query.edit_message_text(
            directions_text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Orqaga", callback_data=back_callback), InlineKeyboardButton("🏠 Bosh menyu", callback_data="nearby_menu")]])
        )
    
    def _calculate_distance(self, lat1, lon1, lat2, lon2):
        """Calculate the distance between two points using the haversine formula"""
        R = 6371  # Earth radius in kilometers
        
        # Convert degrees to radians
        lat1_rad = math.radians(lat1)
        lon1_rad = math.radians(lon1)
        lat2_rad = math.radians(lat2)
        lon2_rad = math.radians(lon2)
        
        # Differences in coordinates
        dlat = lat2_rad - lat1_rad
        dlon = lon2_rad - lon1_rad
        
        # Haversine formula
        a = math.sin(dlat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        
        # Distance in kilometers
        distance = R * c
        return distance