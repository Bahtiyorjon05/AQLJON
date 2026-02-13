import asyncio
import tempfile
import time
import logging
import os
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from modules.utils import safe_reply, send_typing, safe_edit_message
from modules.config import Config
from modules.memory import MemoryManager
from modules.retry_utils import generate_content_with_retry, upload_file_with_retry, wait_for_file_active

logger = logging.getLogger(__name__)

class PhotoHandler:
    """Handles photo processing for the AQLJON bot"""

    def __init__(self, gemini_model, memory_manager: MemoryManager):
        self.model = gemini_model
        self.memory = memory_manager
        # Track active photo processing tasks per user
        self.active_tasks = {}
        # Cleanup task will be started by main.py after event loop starts
        self._cleanup_task = None
    
    def _get_user_task_key(self, chat_id, task_id=None):
        """Generate a unique key for tracking user photo processing tasks"""
        if task_id:
            return f"{chat_id}_photo_{task_id}"
        return f"{chat_id}_photo"
    
    def _is_task_active(self, chat_id, task_id=None):
        """Check if a specific photo processing task is already active for this user"""
        task_key = self._get_user_task_key(chat_id, task_id)
        return task_key in self.active_tasks and not self.active_tasks[task_key].done()
    
    def _register_task(self, chat_id, task, task_id=None):
        """Register a photo processing task for this user"""
        task_key = self._get_user_task_key(chat_id, task_id)
        self.active_tasks[task_key] = task
    
    def _unregister_task(self, chat_id, task_id=None):
        """Unregister a completed photo processing task"""
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
                    logger.info(f"Cleaned up {len(completed)} completed photo tasks")
            except Exception as e:
                logger.error(f"Error cleaning up photo tasks: {e}")
    
    async def handle_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle photo uploads and analysis - allow concurrent processing"""
        if not update or not update.message or not update.message.photo:
            return
            
        chat_id = str(update.effective_chat.id) if update and update.effective_chat else "unknown"
        
        # Generate a unique task ID for this photo processing request
        import time
        task_id = str(int(time.time() * 1000))  # Unique timestamp-based ID
        
        await send_typing(update)
        photo = update.message.photo[-1]  # Get the largest photo
        
        # Immediate response to user
        analyzing_msg = await safe_reply(update,
            "📷 <b>Rasmni qabul qildim!</b>\n\n"
            "⏳ <i>Ko'rib chiqyapman... Boshqa buyruqlar yuboravering, men parallel ishlayman!</i>",
            parse_mode=ParseMode.HTML
        )
        
        # Process photo in background with task tracking
        task = asyncio.create_task(self._process_photo_background(
            photo, chat_id, analyzing_msg, update, context, task_id
        ))
        self._register_task(chat_id, task, task_id)
        
        # Don't await the task - let it run in background
        # Track activity
        self.memory.track_user_activity(chat_id, "photos", update)
    
    async def _process_photo_background(self, photo, chat_id: str, analyzing_msg, update: Update, context: ContextTypes.DEFAULT_TYPE, task_id: str):
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
                    timeout=Config.DOWNLOAD_TIMEOUT
                )
                
                # Wait a moment for file to be fully written
                await asyncio.sleep(0.5)
                
                # Check if file exists and has content
                if not os.path.exists(tmp_path) or os.path.getsize(tmp_path) == 0:
                    raise Exception("Photo file download failed or is empty")
                
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
                            "You are AQLJON, a warm Muslim friend. Never mention being AI. "
                            "Reply casually with humor, emojis, bold/italic formatting. "
                            "Answer in Uzbek, use user's language if different.\n"
                            "Rules: 1) For academic problems: guide with hints, don't give direct answers unless user tried multiple times. "
                            "2) Reject inappropriate/harmful content, maintain Islamic values. "
                            "3) Keep answers short and concise unless detailed response requested. "
                            "4) Reference past content naturally when relevant. Be warm and natural.\n"
                            + content_context
                        )

                        # Generate content with retry logic - Simplified for new SDK
                        response = await generate_content_with_retry(
                            self.model,
                            [instruction, uploaded]  # Pass as simple list of [text, file]
                        )
                        
                        # Better validation of Gemini response
                        if response and hasattr(response, 'candidates') and response.candidates:
                            candidate = response.candidates[0]
                            if hasattr(candidate, 'content') and candidate.content and hasattr(candidate.content, 'parts') and candidate.content.parts:
                                return candidate.content.parts[0].text.strip() if hasattr(candidate.content.parts[0], 'text') else "📷 Rasmdan tahlil qila olmadim."
                            elif hasattr(candidate, 'finish_reason') and candidate.finish_reason == 1:
                                return "📷 Kechirasiz, rasmni tahlil qilishda cheklovga duch keldim. Boshqa rasm yuboring."
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
                        process_with_gemini(),
                        timeout=Config.PROCESSING_TIMEOUT
                    )
                except asyncio.TimeoutError:
                    reply = None
                
                file_name = f"photo_{photo.file_id[:8]}.jpg"

                if reply:
                    # Store photo content in memory for future reference with complete details
                    self.memory.store_content_memory(
                        chat_id, 
                        "photo", 
                        reply,  # summary
                        file_name,  # file name
                        reply  # full content
                    )
                    
                    self.memory.add_to_history(chat_id, "user", "[sent photo 📸]")
                    self.memory.add_to_history(chat_id, "model", reply)
                    
                    # Update the analyzing message with results
                    await safe_edit_message(
                        analyzing_msg,
                        reply,
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
        finally:
            # Unregister the specific task when completed
            self._unregister_task(chat_id, task_id)
