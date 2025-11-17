import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from modules.utils import safe_reply, safe_edit_message
from modules.retry_utils import http_get_with_retry
from modules.location_features.utils import calculate_distance, validate_coordinates

logger = logging.getLogger(__name__)

class PrayerTimesHandler:
    """Handles prayer times functionality with improved UI/UX"""
    
    def __init__(self, location_data):
        self.location_data = location_data
        self.ALADHAN_URL = "http://api.aladhan.com/v1"
        self.NOMINATIM_URL = "https://nominatim.openstreetmap.org"
    
    async def show_prayer_times(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show prayer times for user's location"""
        if not update.effective_chat:
            return
            
        chat_id = str(update.effective_chat.id)
        
        # Check if user has shared location
        if chat_id not in self.location_data:
            # Try to get location from message if available
            if update.message and update.message.location:
                location = update.message.location
                # Get location details for city name
                location_info = await self._get_location_info(location.latitude, location.longitude)
                if location_info:
                    self.location_data[chat_id] = {
                        "latitude": location.latitude,
                        "longitude": location.longitude,
                        "city": location_info.get("city", "Noma'lum shahar"),
                        "timestamp": datetime.now().isoformat()
                    }
            else:
                # Offer user options to provide location
                if update.effective_message:
                    keyboard = [[
                        KeyboardButton("📍 Mening joylashuvim", request_location=True),
                        InlineKeyboardButton("🏙️ Shahar qidirish", callback_data="location_search")
                    ]]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    await update.effective_message.reply_text(
                        "📍 Avval joylashuvingizni yuboring yoki shahar nomini kiriting.",
                        reply_markup=reply_markup
                    )
                return
        
        # Check if location data has expired
        location = self.location_data[chat_id]
        if "expires_at" in location:
            expires_at = datetime.fromisoformat(location["expires_at"])
            if datetime.now() > expires_at:
                # Try to get location from message if available
                if update.message and update.message.location:
                    location_msg = update.message.location
                    # Get location details for city name
                    location_info = await self._get_location_info(location_msg.latitude, location_msg.longitude)
                    if location_info:
                        self.location_data[chat_id] = {
                            "latitude": location_msg.latitude,
                            "longitude": location_msg.longitude,
                            "city": location_info.get("city", "Noma'lum shahar"),
                            "timestamp": datetime.now().isoformat(),
                            "expires_at": (datetime.now() + timedelta(hours=24)).isoformat()
                        }
                        location = self.location_data[chat_id]
                else:
                    # Offer user options to provide location
                    if update.effective_message:
                        keyboard = [[
                            KeyboardButton("📍 Mening joylashuvim", request_location=True),
                            InlineKeyboardButton("🏙️ Shahar qidirish", callback_data="location_search")
                        ]]
                        reply_markup = InlineKeyboardMarkup(keyboard)
                        await update.effective_message.reply_text(
                            "📍 Joylashuv ma'lumotlari eskirgan. Iltimos, qaytadan jo'natish!",
                            reply_markup=reply_markup
                        )
                    return
        
        latitude = location["latitude"]
        longitude = location["longitude"]
        
        try:
            # Show processing message
            processing_msg = None
            if update.callback_query and update.callback_query.message:
                # This is a refresh request
                processing_msg = update.callback_query.message
                await update.callback_query.answer("Namoz vaqtlari yangilanmoqda...")
                try:
                    await update.callback_query.edit_message_text("🕋 Namoz vaqtlari hisoblanmoqda...")
                except Exception as e:
                    logger.error(f"Error updating refresh message: {e}")
            else:
                # This is a new request
                processing_msg = await safe_reply(update, "🕋 Namoz vaqtlari hisoblanmoqda...")
            
            # Using Aladhan API for prayer times with Hanafi school (school=1)
            today = datetime.now().strftime("%d-%m-%Y")
            
            # Initialize best_result
            best_result = None
            
            # Use method with Hanafi school (school=1) which affects Asr time calculation
            # In Hanafi school, Asr time is when an object's shadow is twice its length plus the original shadow
            url = f"{self.ALADHAN_URL}/timings/{today}"
            params = {
                "latitude": latitude,
                "longitude": longitude,
                "method": 2,  # ISNA method as default
                "school": 1   # Hanafi school (0 = Shafi, 1 = Hanafi)
            }
            
            data = await http_get_with_retry(url, params=params, timeout=25)
            if data and data.get("code") == 200:
                best_result = data
            
            # If primary method failed, try fallback methods
            if not best_result:
                methods = [
                    {"method": 1, "name": "Karachi"},  # University of Islamic Sciences, Karachi
                    {"method": 3, "name": "MWL"}  # Muslim World League
                ]
                
                for method_info in methods:
                    fallback_params = {
                        "latitude": latitude,
                        "longitude": longitude,
                        "method": method_info["method"],
                        "school": 1  # Still use Hanafi school
                    }
                    
                    fallback_data = await http_get_with_retry(url, params=fallback_params, timeout=25)
                    if fallback_data and fallback_data.get("code") == 200:
                        best_result = fallback_data
                        break
            
            if best_result:
                timings = best_result["data"]["timings"]
                date_info = best_result["data"]["date"]
                readable_date = date_info["readable"]
                hijri_date = date_info["hijri"]
                
                # Format prayer times
                prayer_times = {
                    "Bomdod": timings['Fajr'],
                    "Quyosh": timings['Sunrise'],
                    "Peshin": timings['Dhuhr'],
                    "Asr": timings['Asr'],  # This will now use Hanafi calculation
                    "Shom": timings['Maghrib'],
                    "Xufton": timings['Isha']
                }
                
                # Create message with detailed location information
                city_name = location.get('city', 'Sizning joylashuvingiz')
                prayer_text = f"🕌 <b>{city_name} uchun namoz vaqtlari</b>\n"
                prayer_text += "=" * (len(city_name) + 25) + "\n\n"
                
                prayer_text += "📍 <b>Joylashuv ma'lumotlari:</b>\n"
                prayer_text += f"🏙️ <b>Shahar:</b> {city_name}\n"
                prayer_text += f"🧭 <b>Koordinatalar:</b> {latitude:.6f}, {longitude:.6f}\n\n"
                
                prayer_text += f"📅 <b>Sanada:</b> {readable_date}\n"
                prayer_text += f"🌙 <b>Hijriy sanada:</b> {hijri_date['date']}\n"
                prayer_text += f"📚 <b>Mazhab:</b> Hanafiy\n\n"
                
                prayer_text += "⋆｡ﾟ︎☪︎⋆｡ﾟ︎ <b>Namoz vaqtlari:</b>\n"
                for prayer, time in prayer_times.items():
                    prayer_text += f"🕌<b>{prayer}:</b> {time}\n"
                
                prayer_text += "\n"
                prayer_text += "<i>Yangilash uchun quyidagi tugmani bosing</i>\n\n"
                
                # Add footer with location information
                prayer_text += f"🔷 <b>Joy nomi:</b> {city_name}\n"
                prayer_text += f"📄 <b>Sana:</b> {readable_date}\n\n"
                
                # Add refresh button
                keyboard = [[InlineKeyboardButton("🔄 Yangilash", callback_data="prayer_refresh")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                # Update message based on whether this is a callback query or new message
                if update.callback_query and update.callback_query.message:
                    # This is a refresh request, edit the existing message
                    try:
                        await update.callback_query.edit_message_text(prayer_text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
                    except Exception as e:
                        if "Message is not modified" in str(e):
                            await update.callback_query.answer("✅ Namoz vaqtlari yangilangan", show_alert=False)
                        else:
                            raise
                else:
                    # This is a new request, send the message with inline buttons
                    if processing_msg:
                        await safe_edit_message(processing_msg, prayer_text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
                    else:
                        # Send the message with inline buttons using native Telegram method
                        if update.effective_message:
                            await update.effective_message.reply_text(prayer_text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
                        else:
                            await safe_reply(update, prayer_text, parse_mode=ParseMode.HTML)
            else:
                error_message = "❌ Namoz vaqtlarini hisoblashda xatolik. Keyinroq qayta urinib ko'ring."
                if update.callback_query and update.callback_query.message:
                    await update.callback_query.edit_message_text(error_message)
                    await update.callback_query.answer("❌ Xatolik yuz berdi", show_alert=True)
                elif processing_msg:
                    await safe_edit_message(processing_msg, error_message)
                else:
                    await safe_reply(update, error_message)
        except Exception as e:
            error_message = "❌ Namoz vaqtlarini hisoblashda xatolik. Qaytadan urinib ko'ring."
            logger.error(f"Namoz vaqtlarini olishda xatolik: {e}")
            if update.callback_query and update.callback_query.message:
                await update.callback_query.edit_message_text(error_message)
                await update.callback_query.answer("❌ Xatolik yuz berdi", show_alert=True)
            else:
                await safe_reply(update, error_message)
    
    async def _get_location_info(self, latitude: float, longitude: float):
        """Get location information using Nominatim"""
        try:
            url = f"{self.NOMINATIM_URL}/reverse"
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
            url = f"{self.NOMINATIM_URL}/search"
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
                       location.get("display_name", city_name))

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
            return None
    
    def _calculate_distance(self, lat1, lon1, lat2, lon2):
        """Calculate the distance between two points - delegates to shared utility"""
        return calculate_distance(lat1, lon1, lat2, lon2)