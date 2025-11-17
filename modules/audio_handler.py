import asyncio
import tempfile
import time
import logging
import google.generativeai as genai
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from modules.utils import safe_reply, send_typing, safe_edit_message
from modules.config import Config
from modules.memory import MemoryManager
from modules.retry_utils import generate_content_with_retry, upload_file_with_retry, wait_for_file_active

logger = logging.getLogger(__name__)

class AudioHandler:
    """Handles audio/voice message processing for the AQLJON bot"""

    def __init__(self, gemini_model, memory_manager: MemoryManager):
        self.model = gemini_model
        self.memory = memory_manager
        # Track active audio processing tasks per user
        self.active_tasks = {}
        # Cleanup task will be started by main.py after event loop starts
        self._cleanup_task = None
    
    def _get_user_task_key(self, chat_id, task_id=None):
        """Generate a unique key for tracking user audio processing tasks"""
        if task_id:
            return f"{chat_id}_audio_{task_id}"
        return f"{chat_id}_audio"
    
    def _is_task_active(self, chat_id, task_id=None):
        """Check if a specific audio processing task is already active for this user"""
        task_key = self._get_user_task_key(chat_id, task_id)
        return task_key in self.active_tasks and not self.active_tasks[task_key].done()
    
    def _register_task(self, chat_id, task, task_id=None):
        """Register an audio processing task for this user"""
        task_key = self._get_user_task_key(chat_id, task_id)
        self.active_tasks[task_key] = task
    
    def _unregister_task(self, chat_id, task_id=None):
        """Unregister a completed audio processing task"""
        task_key = self._get_user_task_key(chat_id, task_id)
        if task_key in self.active_tasks:
            del self.active_tasks[task_key]

    async def _cleanup_completed_tasks(self):
        """Periodic cleanup of completed tasks - Phase 1 memory leak fix"""
        while True:
            await asyncio.sleep(3600)  # Run every hour
            try:
                completed = [k for k, v in self.active_tasks.items() if v.done()]
                for key in completed:
                    del self.active_tasks[key]
                if completed:
                    logger.info(f"Cleaned up {len(completed)} completed audio tasks")
            except Exception as e:
                logger.error(f"Error cleaning up audio tasks: {e}")
    
    async def handle_audio(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle audio/voice message uploads and analysis - allow concurrent processing"""
        if not update or not update.message:
            return
            
        # Handle both audio files and voice messages
        audio = update.message.audio if update.message.audio else None
        voice = update.message.voice if update.message.voice else None
        
        # Must have either audio or voice
        if not audio and not voice:
            return
            
        chat_id = str(update.effective_chat.id) if update and update.effective_chat else "unknown"
        
        # Generate a unique task ID for this audio processing request
        import time
        task_id = str(int(time.time() * 1000))  # Unique timestamp-based ID
        
        # Show typing indicator for both audio and voice messages
        await send_typing(update)
        
        # Check file size
        media = audio or voice
        file_size = getattr(media, 'file_size', 0)
        if file_size and file_size > Config.MAX_FILE_SIZE:
            await safe_reply(update, 
                "❌ <b>Audio juda katta!</b>\n\n"
                "🔍 <i>Bot faqat 20MB gacha bo'lgan audio xabarlarni tahlil qila oladi.</i>\n\n"
                "💡 <i>Kichikroq audio xabar yuboring.</i>",
                parse_mode=ParseMode.HTML
            )
            self.memory.track_user_activity(chat_id, "voice_audio", update)
            return
        
        # Show analyzing message for both audio files and voice messages
        analyzing_msg = await safe_reply(update,
            "🎤 <b>Ovozli xabaringizni qabul qildim!</b>\n\n"
            "⏳ <i>Eshityapman...</i>",
            parse_mode=ParseMode.HTML
        )
        
        # Process audio/voice in background with task tracking
        task = asyncio.create_task(self._process_audio_voice_background(
            media, chat_id, analyzing_msg, update, context, task_id
        ))
        self._register_task(chat_id, task, task_id)
        
        # Don't await the task - let it run in background
        # Track activity
        self.memory.track_user_activity(chat_id, "voice_audio", update)
    
    async def _process_audio_voice_background(self, media, chat_id: str, analyzing_msg, update: Update, context: ContextTypes.DEFAULT_TYPE, task_id: str):
        """Process audio/voice messages in background with improved error handling"""
        import os
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
                    timeout=Config.DOWNLOAD_TIMEOUT
                )
                
                # Wait a moment for file to be fully written
                await asyncio.sleep(0.5)
                
                # Check if file exists and has content
                if not os.path.exists(tmp_path) or os.path.getsize(tmp_path) == 0:
                    raise Exception("Audio file download failed or is empty")
                
                # Process with Gemini using retry logic
                async def process_with_gemini():
                    try:
                        # Upload to Gemini with retry
                        uploaded = await upload_file_with_retry(tmp_path)

                        # Wait for file to be in ACTIVE state with retry logic
                        uploaded = await wait_for_file_active(uploaded, timeout=30)
                        
                        # Generate response with user context
                        content_context = self.memory.get_content_context(chat_id)
                        instruction = (
                            "You are AQLJON, an intelligent Muslim friend who is warm, creative, helpful, and friendly. "
                            "Always respond as a friend, never mention you are an AI or use other names. "
                            "Reply casually with humor and warmth using emojis and formatting different font styles bold italic uppercase lowercase etc. "
                            "Answer in the same language the user spoke in the audio, otherwise answer in Uzbek.\n\n"
                            "Don't repeat what user said or ask the user to repeat. and dont be robotic and dont give robotic descriptions"
                            "IMPORTANT GUIDELINES:\n"
                            "1. if user asks u to solve academic problem-solving (math, physics, chemistry, coding, biology):\n"
                            "   - NEVER give direct answers or solutions if they try and show u their answer many times still not correct and when they then ask u for answer then only tell them the answer with awesome explanation\n"
                            "   - Guide with concepts, understanding, and hints\n"
                            "   - Encourage users to try solving on their own first\n"
                            "   - Only verify or correct after they've attempted\n"
                            "   - tell them to think and try again while giving understanding clearly up to the point\n\n"
                            
                            "2. If user said u inappropriate, illegal, or harmful content:\n"
                            "   - Don't provide any response about that content\n"
                            "   - Politely redirect to appropriate topics\n"
                            "   - Maintain Islamic values\n\n"
                            
                            "3. Keep your response conversational and natural:\n"
                            "   - Speak like a friend having a casual conversation\n"
                            "   - Use emojis, bold, italic different formatting appropriately to express emotions\n"
                            "   - give short concise answers always unless user asked u to give detailed asnwer\n\n"
                            
                            "4. When referencing past content:\n"
                            "   - You have access to previous conversations and shared content\n"
                            "   - Reference them naturally when relevant\n"
                            "   - Never say you can't see previous content\n\n"
                            
                            "Here's the context of previous conversations and shared content:\n" + content_context + "\n\n"
                            
                            "never say to user that u are programmed to answer like this way"
                        )

                        # Generate content with retry logic
                        response = await generate_content_with_retry(
                            self.model,
                            [
                                {"role": "user", "parts": [instruction]},
                                {"role": "user", "parts": [uploaded]}
                            ]
                        )
                        
                        # Better validation of Gemini response
                        if response and hasattr(response, 'candidates') and response.candidates:
                            candidate = response.candidates[0]
                            if hasattr(candidate, 'content') and candidate.content and hasattr(candidate.content, 'parts') and candidate.content.parts:
                                return candidate.content.parts[0].text.strip() if hasattr(candidate.content.parts[0], 'text') else "🎤 Audio xabarni tahlil qila olmadim."
                            elif hasattr(candidate, 'finish_reason') and candidate.finish_reason == 1:
                                return "🎤 Kechirasiz, audio xabarni tahlil qilishda cheklovga duch keldim. Boshqa audio xabar yuboring."
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
                        process_with_gemini(),
                        timeout=Config.PROCESSING_TIMEOUT
                    )
                except asyncio.TimeoutError:
                    reply = None
                
                if reply:
                    # Store audio content in memory for future reference with complete details
                    file_name = getattr(media, 'file_name', f"audio_{media.file_id[:8]}{suffix}")
                    self.memory.store_content_memory(
                        chat_id, 
                        "audio", 
                        reply,  # summary
                        file_name,  # file name
                        reply  # full content
                    )
                    
                    self.memory.add_to_history(chat_id, "user", f"[uploaded audio: {file_name}]" if hasattr(media, 'file_name') else "[sent voice message 🎤]")
                    self.memory.add_to_history(chat_id, "model", reply)
                    
                    # Send response directly if no analyzing message was shown (for voice messages)
                    if analyzing_msg is None:
                        from modules.utils import send_long_message
                        await send_long_message(update, reply)
                    else:
                        # Update the analyzing message with results (for audio files)
                        await safe_edit_message(
                            analyzing_msg,
                            reply,
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
                        await safe_reply(update, 
                            "❌ <b>Audio xabar tahlilida xatolik yuz berdi</b>\n\n"
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
                    error_msg += "📊 API chekloviga yetdim. Biroz kuting va qaytadan urinib ko'ring.\n"
                elif "format" in error_str:
                    error_msg += "🎤 Audio formati qo'llab-quvvatlanmaydi.\n"
                elif "size" in error_str:
                    error_msg += "📏 Audio juda katta. Iltimos, 20MB dan kichik audio xabar yuboring.\n"
                elif "ssl" in error_str and "wrong_version_number" in error_str:
                    error_msg += "🔒 Tarmoq xavfsizlik xatosi. Qaytadan urinib ko'ring.\n"
                else:
                    error_msg += "🔄 Qaytadan urinib ko'ring yoki boshqa audio xabar yuboring.\n"
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
                except Exception as e:
                    logger.error(f"Failed to edit error message: {e}")
            else:
                try:
                    await safe_reply(update, error_msg, parse_mode=ParseMode.HTML)
                except Exception as e:
                    logger.error(f"Failed to send error message: {e}")
        finally:
            # Unregister the specific task when completed
            self._unregister_task(chat_id, task_id)