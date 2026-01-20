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

class VideoHandler:
    """Handles video processing for the AQLJON bot"""
    
    def __init__(self, gemini_model, memory_manager: MemoryManager):
        self.model = gemini_model
        self.memory = memory_manager
        # Track active video processing tasks per user
        self.active_tasks = {}
        # Cleanup task will be started by main.py after event loop starts
        self._cleanup_task = None
    
    def _get_user_task_key(self, chat_id, task_id=None):
        """Generate a unique key for tracking user video processing tasks"""
        if task_id:
            return f"{chat_id}_video_{task_id}"
        return f"{chat_id}_video"
    
    def _is_task_active(self, chat_id, task_id=None):
        """Check if a specific video processing task is already active for this user"""
        task_key = self._get_user_task_key(chat_id, task_id)
        return task_key in self.active_tasks and not self.active_tasks[task_key].done()
    
    def _register_task(self, chat_id, task, task_id=None):
        """Register a video processing task for this user"""
        task_key = self._get_user_task_key(chat_id, task_id)
        self.active_tasks[task_key] = task
    
    def _unregister_task(self, chat_id, task_id=None):
        """Unregister a completed video processing task"""
        task_key = self._get_user_task_key(chat_id, task_id)
        if task_key in self.active_tasks:
            del self.active_tasks[task_key]

    async def _cleanup_completed_tasks(self):
        """Periodically clean up completed tasks to prevent memory leaks"""
        while True:
            try:
                await asyncio.sleep(3600)  # Run every hour

                # Find all completed tasks
                completed_keys = [
                    key for key, task in self.active_tasks.items()
                    if task.done()
                ]

                # Remove completed tasks
                for key in completed_keys:
                    del self.active_tasks[key]

                if completed_keys:
                    logger.info(f"🧹 Cleaned up {len(completed_keys)} completed video tasks. Active tasks: {len(self.active_tasks)}")

            except Exception as e:
                logger.error(f"Error in video task cleanup: {e}")

    async def handle_video(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle video uploads and analysis - allow concurrent processing"""
        if not update or not update.message or not update.message.video:
            return
            
        chat_id = str(update.effective_chat.id) if update and update.effective_chat else "unknown"
        
        # Generate a unique task ID for this video processing request
        import time
        task_id = str(int(time.time() * 1000))  # Unique timestamp-based ID
        
        await send_typing(update)
        video = update.message.video
        
        # Check file size
        if video.file_size and video.file_size > Config.MAX_FILE_SIZE:
            await safe_reply(update,
                "❌ <b>Video juda katta!</b>\n\n"
                "🔍 <i>Bot faqat 20MB gacha bo'lgan videolarni tahlil qila oladi.</i>\n\n"
                "💡 <i>Kichikroq video yuboring.</i>",
                parse_mode=ParseMode.HTML
            )
            self.memory.track_user_activity(chat_id, "videos", update)
            return
        
        # Immediate response to user
        analyzing_msg = await safe_reply(update,
            "🎬 <b>Videoni qabul qildim!</b>\n\n"
            "⏳ <i>Qani bir ko'rib chiqay ... Boshqa buyruqlar yuboravering, men parallel ishlayman!</i>",
            parse_mode=ParseMode.HTML
        )
        
        # Process video in background with task tracking
        task = asyncio.create_task(self._process_video_background(
            video, chat_id, analyzing_msg, update, context, task_id
        ))
        self._register_task(chat_id, task, task_id)
        
        # Don't await the task - let it run in background
        # Track activity
        self.memory.track_user_activity(chat_id, "videos", update)
    
    async def _process_video_background(self, video, chat_id: str, analyzing_msg, update: Update, context: ContextTypes.DEFAULT_TYPE, task_id: str):
        """Process video in background with simplified approach"""
        tmp_path = None
        try:
            # Download video file
            file = await context.bot.get_file(video.file_id)
            
            # Create temporary file
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as tmp_file:
                tmp_path = tmp_file.name
            
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
                    raise Exception("Video file download failed or is empty")
                
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
                            "Reply casually with humor and warmth using emojis, bold, italic etc formatting. "
                            "Answer in Uzbek, if user speaks other language use the appropriate language.\n\n"
                            
                            "IMPORTANT GUIDELINES:\n"
                            "1. For academic problem-solving (math, physics, chemistry, coding, biology):\n"
                            "   - NEVER give direct answers or solutions if they try and show u their answer many times still not correct and when they then ask u for answer then only tell them the answer with awesome explanation\n"
                            "   - Guide with concepts, understanding, and hints\n"
                            "   - Encourage users to try solving on their own first\n"
                            "   - Only verify or correct after they've attempted\n"
                            "   - Force them to think and try again while giving understanding clearly\n\n"
                            
                            "2. If the video contains inappropriate, illegal, or harmful content:\n"
                            "   - Don't provide any response about that content\n"
                            "   - Politely redirect to appropriate topics\n"
                            "   - Maintain Islamic values\n\n"
                            
                            "3. Keep your response conversational and natural:\n"
                            "   - Use emojis appropriately to express emotions\n"
                            "   - always answer nicely shortly and to the point unless detailed answer is requested\n\n"
                            
                            "4. When referencing past content:\n"
                            "   - You have access to previous conversations and shared content\n"
                            "   - Reference them naturally when relevant\n"
                            "   - Never say you can't see previous content\n\n"
                            
                            "Here's the context of previous conversations and shared content:\n" + content_context + "\n\n"
                            "never say that u are AI and that u are ordered and programmed to answer like this way. be a Muslim friend to user"
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
                                return candidate.content.parts[0].text.strip() if hasattr(candidate.content.parts[0], 'text') else "🎬 Videoni tahlil qila olmadim."
                            elif hasattr(candidate, 'finish_reason') and candidate.finish_reason == 1:
                                return "🎬 Kechirasiz, videoni tahlil qilishda cheklovga duch keldim. Boshqa video yuboring."
                        return response.text.strip() if response and response.text else "🎬 Videoni tahlil qila olmadim."
                    except Exception as e:
                        logger.error(f"Gemini processing error: {e}")
                        return None
                
                # Run processing with timeout
                try:
                    reply = await asyncio.wait_for(
                        process_with_gemini(),
                        timeout=Config.PROCESSING_TIMEOUT
                    )
                except asyncio.TimeoutError:
                    reply = None
                
                # Upload to Firebase Storage for Dashboard
                file_name = video.file_name if video.file_name else f"video_{video.file_id[:8]}.mp4"
                content_type = video.mime_type if video.mime_type else "video/mp4"
                file_url = None
                try:
                    file_url = await asyncio.to_thread(self.memory.upload_to_storage, tmp_path, file_name, content_type)
                except Exception as e:
                    logger.error(f"Failed to upload video to storage: {e}")

                if reply:
                    # Store video content in memory for future reference with complete details
                    self.memory.store_content_memory(
                        chat_id, 
                        "video", 
                        reply,  # summary
                        file_name,  # file name
                        reply  # full content
                    )
                    
                    self.memory.add_to_history(chat_id, "user", f"[uploaded video: {file_name}]")
                    self.memory.add_to_history(chat_id, "model", reply)
                    
                    # Log to permanent storage for dashboard
                    self.memory.log_chat_message(
                        chat_id=chat_id,
                        role="user",
                        content="[Videoni ko'rish]",
                        msg_type="video",
                        file_info={
                            "file_name": file_name, 
                            "file_id": video.file_id,
                            "file_url": file_url
                        }
                    )
                    self.memory.log_chat_message(
                        chat_id=chat_id,
                        role="bot",
                        content=reply,
                        msg_type="text"
                    )
                    
                    # Update the analyzing message with results
                    await safe_edit_message(
                        analyzing_msg,
                        reply,
                        parse_mode=ParseMode.HTML
                    )
                else:
                    await safe_edit_message(
                        analyzing_msg,
                        "❌ Video tahlilida xatolik yuz berdi. Qaytadan urinib ko'ring.",
                        parse_mode=ParseMode.HTML
                    )
            
            except asyncio.TimeoutError:
                logger.error("Video processing timeout")
                await safe_edit_message(
                    analyzing_msg,
                    "⏰ Video tahlili juda uzoq davom etdi. Iltimos, kichikroq video yuboring.",
                    parse_mode=ParseMode.HTML
                )
            except Exception as processing_error:
                logger.error(f"Video processing error: {processing_error}")
                
                # Provide specific error messages
                error_msg = "❌ Video tahlilida xatolik:"
                if "quota" in str(processing_error).lower():
                    error_msg += "\n📊 API chekloviga yetdik. Biroz kuting va qaytadan urinib ko'ring."
                elif "format" in str(processing_error).lower():
                    error_msg += "\n🎬 Video formati qo'llab-quvvatlanmaydi."
                elif "size" in str(processing_error).lower():
                    error_msg += "\n📏 Video juda katta. 20MB dan kichik video yuboring."
                else:
                    error_msg += "\n🔄 Qaytadan urinib ko'ring yoki boshqa video yuboring."
                
                await safe_edit_message(analyzing_msg, error_msg, parse_mode=ParseMode.HTML)
            
            finally:
                # Always clean up temp file
                try:
                    if tmp_path is not None and os.path.exists(tmp_path):
                        os.unlink(tmp_path)
                except Exception as cleanup_error:
                    logger.warning(f"Failed to cleanup temp file: {cleanup_error}")
                
        except Exception as e:
            logger.error(f"Video handler error: {e}")
            try:
                await safe_edit_message(
                    analyzing_msg,
                    "❌ Video yuklashda xatolik yuz berdi. Iltimos qaytadan urinib ko'ring.",
                    parse_mode=ParseMode.HTML
                )
            except:
                pass
        finally:
            # Unregister the specific task when completed
            self._unregister_task(chat_id, task_id)
