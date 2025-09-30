import asyncio
import logging
from typing import Dict, Optional
from telegram import Update
from telegram.ext import ContextTypes
from modules.doc_generation.base_generator import BaseDocumentGenerator
from modules.doc_generation.pdf_generator import PDFGenerator
from modules.doc_generation.excel_generator import ExcelGenerator
from modules.doc_generation.word_generator import WordGenerator
from modules.doc_generation.advanced_ppt_generator import AdvancedPPTGenerator
from modules.utils import send_typing

logger = logging.getLogger(__name__)

class DocumentGenerator:
    """Main document generator facade that maintains backward compatibility.
    
    This class acts as a facade for all document generation functionality,
    coordinating between different document generators and providing a unified interface.
    """
    
    def __init__(self, gemini_model, memory_manager):
        """Initialize the document generator facade.
        
        Args:
            gemini_model: The Gemini AI model instance
            memory_manager: The memory manager instance
        """
        self.model = gemini_model
        self.memory = memory_manager
        # Initialize individual generators lazily to avoid heavy initialization at startup
        self._pdf_generator: Optional[PDFGenerator] = None
        self._excel_generator: Optional[ExcelGenerator] = None
        self._word_generator: Optional[WordGenerator] = None
        self._ppt_generator: Optional[AdvancedPPTGenerator] = None
        # Track active generation tasks per user to prevent duplicate requests of same type
        self.active_tasks: Dict[str, asyncio.Task] = {}
    
    def _get_user_task_key(self, chat_id, doc_type):
        """Generate a unique key for tracking user document generation tasks"""
        return f"{chat_id}_{doc_type}"
    
    def _is_task_active(self, chat_id, doc_type):
        """Check if a document generation task is already active for this user and document type"""
        task_key = self._get_user_task_key(chat_id, doc_type)
        return task_key in self.active_tasks and not self.active_tasks[task_key].done()
    
    def _register_task(self, chat_id, doc_type, task):
        """Register a document generation task for this user and document type"""
        task_key = self._get_user_task_key(chat_id, doc_type)
        # Allow multiple concurrent tasks - don't cancel previous ones
        # Just track this new task
        self.active_tasks[task_key] = task
    
    def _unregister_task(self, chat_id, doc_type):
        """Unregister a completed document generation task"""
        task_key = self._get_user_task_key(chat_id, doc_type)
        if task_key in self.active_tasks:
            del self.active_tasks[task_key]
    
    def _validate_topic(self, topic: str) -> tuple[bool, str]:
        """Validate topic and return (is_valid, cleaned_topic)"""
        if not topic or not str(topic).strip():
            return False, ""
        
        cleaned_topic = str(topic).strip()
        if len(cleaned_topic) < 2:
            return False, cleaned_topic
            
        return True, cleaned_topic
    
    @property
    def pdf_generator(self) -> PDFGenerator:
        """Lazy initialization of PDF generator"""
        if self._pdf_generator is None:
            self._pdf_generator = PDFGenerator(self.model, self.memory)
        return self._pdf_generator
    
    @property
    def excel_generator(self) -> ExcelGenerator:
        """Lazy initialization of Excel generator"""
        if self._excel_generator is None:
            self._excel_generator = ExcelGenerator(self.model, self.memory)
        return self._excel_generator
    
    @property
    def word_generator(self) -> WordGenerator:
        """Lazy initialization of Word generator"""
        if self._word_generator is None:
            self._word_generator = WordGenerator(self.model, self.memory)
        return self._word_generator
    
    @property
    def ppt_generator(self) -> AdvancedPPTGenerator:
        """Lazy initialization of PowerPoint generator"""
        if self._ppt_generator is None:
            self._ppt_generator = AdvancedPPTGenerator(self.model, self.memory)
        return self._ppt_generator
    
    async def generate_pdf(self, update: Update, context: ContextTypes.DEFAULT_TYPE, topic: str, content_context: str = ""):
        """Generate a professional PDF document based on user request.
        
        Args:
            update (Update): The Telegram update object
            context (ContextTypes.DEFAULT_TYPE): The Telegram context object
            topic (str): The document topic
            content_context (str, optional): Additional context for document generation. Defaults to "".
        """
        # Use centralized validation
        is_valid, cleaned_topic = self._validate_topic(topic)
        if not is_valid:
            # Track document generation attempt even for invalid topics
            if update and update.effective_chat:
                chat_id = str(update.effective_chat.id)
                self.memory.track_document_generation(chat_id, "pdf", update)
            if len(cleaned_topic) < 2:
                if update and update.message:
                    from modules.utils import safe_reply
                    from telegram.constants import ParseMode
                    await safe_reply(update, "❌ Iltimos, PDF hujjati uchun to'liq mavzu kiriting (kamida 2 belgi).", parse_mode=ParseMode.HTML)
            else:
                if update and update.message:
                    from modules.utils import safe_reply
                    from telegram.constants import ParseMode
                    await safe_reply(update, "❌ Iltimos, PDF hujjati uchun mavzu kiriting.", parse_mode=ParseMode.HTML)
            return
            
        chat_id = str(update.effective_chat.id) if update.effective_chat else "unknown"
        
        # Send typing indicator
        if update and update.message:
            await send_typing(update)
        
        # Allow multiple concurrent PDF generation requests
        # Don't check if a task is already active - just create a new one
        
        # Track document generation without restriction
        # Create and register the task
        task = asyncio.create_task(self.pdf_generator.generate(update, context, cleaned_topic, content_context))
        self._register_task(chat_id, "pdf", task)
        
        try:
            await task
        except Exception as e:
            logger.error(f"PDF generation task error: {e}")
        finally:
            self._unregister_task(chat_id, "pdf")
    
    async def generate_excel(self, update: Update, context: ContextTypes.DEFAULT_TYPE, topic: str, content_context: str = ""):
        """Generate a professional Excel spreadsheet based on user request.
        
        Args:
            update (Update): The Telegram update object
            context (ContextTypes.DEFAULT_TYPE): The Telegram context object
            topic (str): The document topic
            content_context (str, optional): Additional context for document generation. Defaults to "".
        """
        # Use centralized validation
        is_valid, cleaned_topic = self._validate_topic(topic)
        if not is_valid:
            # Track document generation attempt even for invalid topics
            if update and update.effective_chat:
                chat_id = str(update.effective_chat.id)
                self.memory.track_document_generation(chat_id, "excel", update)
            if len(cleaned_topic) < 2:
                if update and update.message:
                    from modules.utils import safe_reply
                    from telegram.constants import ParseMode
                    await safe_reply(update, "❌ Iltimos, Excel jadvali uchun to'liq mavzu kiriting (kamida 2 belgi).", parse_mode=ParseMode.HTML)
            else:
                if update and update.message:
                    from modules.utils import safe_reply
                    from telegram.constants import ParseMode
                    await safe_reply(update, "❌ Iltimos, Excel jadvali uchun mavzu kiriting.", parse_mode=ParseMode.HTML)
            return
            
        chat_id = str(update.effective_chat.id) if update.effective_chat else "unknown"
        
        # Send typing indicator
        if update and update.message:
            await send_typing(update)
        
        # Allow multiple concurrent Excel generation requests
        # Don't check if a task is already active - just create a new one
        
        # Track document generation without restriction
        # Create and register the task
        task = asyncio.create_task(self.excel_generator.generate(update, context, cleaned_topic, content_context))
        self._register_task(chat_id, "excel", task)
        
        try:
            await task
        except Exception as e:
            logger.error(f"Excel generation task error: {e}")
        finally:
            self._unregister_task(chat_id, "excel")
    
    async def generate_word(self, update: Update, context: ContextTypes.DEFAULT_TYPE, topic: str, content_context: str = ""):
        """Generate a professional Word document based on user request.
        
        Args:
            update (Update): The Telegram update object
            context (ContextTypes.DEFAULT_TYPE): The Telegram context object
            topic (str): The document topic
            content_context (str, optional): Additional context for document generation. Defaults to "".
        """
        # Use centralized validation
        is_valid, cleaned_topic = self._validate_topic(topic)
        if not is_valid:
            # Track document generation attempt even for invalid topics
            if update and update.effective_chat:
                chat_id = str(update.effective_chat.id)
                self.memory.track_document_generation(chat_id, "word", update)
            if len(cleaned_topic) < 2:
                if update and update.message:
                    from modules.utils import safe_reply
                    from telegram.constants import ParseMode
                    await safe_reply(update, "❌ Iltimos, Word hujjati uchun to'liq mavzu kiriting (kamida 2 belgi).", parse_mode=ParseMode.HTML)
            else:
                if update and update.message:
                    from modules.utils import safe_reply
                    from telegram.constants import ParseMode
                    await safe_reply(update, "❌ Iltimos, Word hujjati uchun mavzu kiriting.", parse_mode=ParseMode.HTML)
            return
            
        chat_id = str(update.effective_chat.id) if update.effective_chat else "unknown"
        
        # Send typing indicator
        if update and update.message:
            await send_typing(update)
        
        # Allow multiple concurrent Word generation requests
        # Don't check if a task is already active - just create a new one
        
        # Track document generation without restriction
        # Create and register the task
        task = asyncio.create_task(self.word_generator.generate(update, context, cleaned_topic, content_context))
        self._register_task(chat_id, "word", task)
        
        try:
            await task
        except Exception as e:
            logger.error(f"Word generation task error: {e}")
        finally:
            self._unregister_task(chat_id, "word")
    
    async def generate_powerpoint(self, update: Update, context: ContextTypes.DEFAULT_TYPE, topic: str, content_context: str = ""):
        """Generate a professional PowerPoint presentation based on user request.
        
        Args:
            update (Update): The Telegram update object
            context (ContextTypes.DEFAULT_TYPE): The Telegram context object
            topic (str): The document topic
            content_context (str, optional): Additional context for document generation. Defaults to "".
        """
        # Use centralized validation
        is_valid, cleaned_topic = self._validate_topic(topic)
        if not is_valid:
            # Track document generation attempt even for invalid topics
            if update and update.effective_chat:
                chat_id = str(update.effective_chat.id)
                self.memory.track_document_generation(chat_id, "powerpoint", update)
            if len(cleaned_topic) < 2:
                if update and update.message:
                    from modules.utils import safe_reply
                    from telegram.constants import ParseMode
                    await safe_reply(update, "❌ Iltimos, PowerPoint taqdimoti uchun to'liq mavzu kiriting (kamida 2 belgi).", parse_mode=ParseMode.HTML)
            else:
                if update and update.message:
                    from modules.utils import safe_reply
                    from telegram.constants import ParseMode
                    await safe_reply(update, "❌ Iltimos, PowerPoint taqdimoti uchun mavzu kiriting.", parse_mode=ParseMode.HTML)
            return
            
        chat_id = str(update and update.effective_chat.id) if update and update.effective_chat else "unknown"
        
        # Send typing indicator
        if update and update.message:
            await send_typing(update)
        
        # Allow multiple concurrent PowerPoint generation requests
        # Don't check if a task is already active - just create a new one
        
        # Track document generation without restriction
        # Create and register the task
        task = asyncio.create_task(self.ppt_generator.generate(update, context, cleaned_topic, content_context))
        self._register_task(chat_id, "powerpoint", task)
        
        try:
            await task
        except Exception as e:
            logger.error(f"PowerPoint generation task error: {e}")
        finally:
            self._unregister_task(chat_id, "powerpoint")