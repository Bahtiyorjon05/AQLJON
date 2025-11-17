import asyncio
import tempfile
import logging
import time
import re
import random
from abc import ABC, abstractmethod
from typing import Tuple, Dict, Any, Optional
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from modules.utils import safe_reply, send_typing
from modules.config import Config

logger = logging.getLogger(__name__)

class BaseDocumentGenerator(ABC):
    """Base class for all document generators.
    
    This abstract base class provides common functionality for all document generators,
    including filename generation, validation, styling, and error handling.
    """
    
    def __init__(self, gemini_model, memory_manager):
        self.model = gemini_model
        self.memory = memory_manager
        # Define professional color schemes
        self.color_schemes = {
            'professional': {
                'primary': '#2C3E50',    # Dark blue
                'secondary': '#3498DB',  # Bright blue
                'accent': '#2980B9',     # Strong Blue (replaced red)
                'background': '#ECF0F1', # Light gray
                'text': '#2C3E50',       # Dark blue
                'light_text': '#7F8C8D', # Gray
                'divider': '#BDC3C7',    # Light gray-blue
                'highlight': '#F1C40F',  # Gold (replaced amber)
                'success': '#27AE60',    # Green
                'warning': '#F1C40F',    # Gold (replaced orange)
                'info': '#3498DB'        # Blue
            },
            'energizing': {
                'primary': '#4D74FF',    # Blue
                'secondary': '#2980B9',  # Strong Blue (replaced orange)
                'accent': '#050007',     # Black
                'background': '#EFFFFF', # Light cyan
                'text': '#050007',       # Black
                'light_text': '#7F8C8D', # Gray
                'divider': '#D5DBDB',    # Light gray
                'highlight': '#1ABC9C',  # Turquoise
                'success': '#27AE60',    # Green
                'warning': '#F1C40F',    # Gold (replaced orange)
                'info': '#3498DB'        # Blue
            },
            'corporate': {
                'primary': '#3B4D54',    # Dark gray-blue
                'secondary': '#B9BAB5',  # Light gray
                'accent': '#F1C40F',     # Gold (replaced orange)
                'background': '#FFFFFF', # White
                'text': '#3B4D54',       # Dark gray-blue
                'light_text': '#7F8C8D', # Gray
                'divider': '#ECF0F1',    # Light gray
                'highlight': '#F1C40F',  # Gold (replaced amber)
                'success': '#27AE60',    # Green
                'warning': '#F1C40F',    # Gold (replaced orange)
                'info': '#3498DB'        # Blue
            },
            'modern': {
                'primary': '#2C3E50',      # Deep navy
                'secondary': '#3498DB',    # Bright blue
                'accent': '#2980B9',       # Strong Blue (replaced red)
                'background': '#ECF0F1',   # Light gray
                'text': '#2C3E50',         # Dark navy
                'light_text': '#7F8C8D',   # Gray
                'highlight': '#F1C40F',    # Gold (replaced amber)
                'success': '#27AE60',      # Green
                'warning': '#F1C40F',      # Gold (replaced orange)
                'info': '#3498DB',         # Blue
                'divider': '#BDC3C7',      # Light gray-blue
                'education': '#9B59B6',    # Purple for educational content
                'insight': '#1ABC9C',      # Turquoise for insights
            },
            'elegant': {
                'primary': '#8E44AD',      # Purple
                'secondary': '#9B59B6',    # Light purple
                'accent': '#F1C40F',       # Gold (replaced orange)
                'background': '#F8F9F9',   # Very light gray
                'text': '#2C3E50',         # Dark navy
                'light_text': '#95A5A6',   # Gray
                'highlight': '#1ABC9C',    # Turquoise
                'success': '#27AE60',      # Green
                'warning': '#F1C40F',      # Gold (replaced orange)
                'info': '#3498DB',         # Blue
                'divider': '#D5DBDB',      # Light gray
                'education': '#8E44AD',    # Purple for educational content
                'insight': '#1ABC9C',      # Turquoise for insights
            },
            'vibrant': {
                'primary': '#2980B9',      # Strong Blue (replaced red)
                'secondary': '#F1C40F',    # Gold (replaced orange)
                'accent': '#F1C40F',       # Gold (replaced yellow)
                'background': '#EBF5FB',   # Light blue background (replaced light red)
                'text': '#2C3E50',         # Dark navy
                'light_text': '#95A5A6',   # Gray
                'highlight': '#1ABC9C',    # Turquoise
                'success': '#27AE60',      # Green
                'warning': '#F1C40F',      # Gold (replaced orange)
                'info': '#3498DB',         # Blue
                'divider': '#AED6F1',      # Light blue divider (replaced light gray)
                'education': '#F1C40F',    # Gold for educational content (replaced orange)
                'insight': '#1ABC9C',      # Turquoise for insights
            },
            'natural': {
                'primary': '#27AE60',      # Green
                'secondary': '#1ABC9C',    # Turquoise
                'accent': '#F1C40F',       # Gold (replaced orange)
                'background': '#E8F5E9',   # Light green background
                'text': '#2C3E50',         # Dark navy
                'light_text': '#7F8C8D',   # Gray
                'highlight': '#2ECC71',    # Emerald
                'success': '#27AE60',      # Green
                'warning': '#F1C40F',      # Gold (replaced orange)
                'info': '#3498DB',         # Blue
                'divider': '#A3E4A3',      # Light green divider
                'education': '#16A085',    # Dark turquoise for educational content
                'insight': '#27AE60',      # Green for insights
            },
            'exploratory': {
                'primary': '#3498DB',      # Blue
                'secondary': '#9B59B6',    # Purple
                'accent': '#F1C40F',       # Gold (replaced orange)
                'background': '#EBF5FB',   # Light blue background
                'text': '#2C3E50',         # Dark navy
                'light_text': '#7F8C8D',   # Gray
                'highlight': '#3498DB',    # Blue
                'success': '#27AE60',      # Green
                'warning': '#F1C40F',      # Gold (replaced orange)
                'info': '#3498DB',         # Blue
                'divider': '#AED6F1',      # Light blue divider
                'education': '#2980B9',    # Dark blue for educational content
                'insight': '#8E44AD',      # Purple for insights
            },
            'energetic': {
                'primary': '#2980B9',      # Strong Blue (replaced red)
                'secondary': '#F1C40F',    # Gold (replaced orange)
                'accent': '#3498DB',       # Blue
                'background': '#EBF5FB',   # Light blue background (replaced light red)
                'text': '#2C3E50',         # Dark navy
                'light_text': '#7F8C8D',   # Gray
                'highlight': '#2980B9',    # Strong Blue (replaced red)
                'success': '#27AE60',      # Green
                'warning': '#F1C40F',      # Gold (replaced orange)
                'info': '#3498DB',         # Blue
                'divider': '#AED6F1',      # Light blue divider (replaced light red)
                'education': '#2980B9',    # Strong Blue for educational content (replaced dark red)
                'insight': '#F1C40F',      # Gold for insights (replaced orange)
            },
            'clean': {
                'primary': '#34495E',      # Dark blue-gray
                'secondary': '#1ABC9C',    # Turquoise
                'accent': '#3498DB',       # Blue
                'background': '#FFFFFF',   # White
                'text': '#2C3E50',         # Dark navy
                'light_text': '#95A5A6',   # Gray
                'highlight': '#1ABC9C',    # Turquoise
                'success': '#27AE60',      # Green
                'warning': '#F1C40F',      # Gold (replaced orange)
                'info': '#3498DB',         # Blue
                'divider': '#ECF0F1',      # Light gray
                'education': '#34495E',    # Dark blue-gray for educational content
                'insight': '#1ABC9C',      # Turquoise for insights
            },
            'awesome': {
                'primary': '#2980B9',      # Strong Blue
                'secondary': '#27AE60',    # Emerald Green
                'accent': '#F39C12',       # Vibrant Orange
                'background': '#FFFFFF',   # Clean White
                'text': '#2C3E50',         # Dark navy
                'light_text': '#7F8C8D',   # Gray
                'highlight': '#1ABC9C',    # Turquoise
                'success': '#27AE60',      # Emerald Green
                'warning': '#F39C12',      # Vibrant Orange
                'info': '#3498DB',         # Bright Blue
                'divider': '#BDC3C7',      # Silver
                'education': '#9B59B6',    # Amethyst for educational content
                'insight': '#16A085',      # Green Sea for insights
                'gradient_start': '#3498DB',  # Gradient start (Blue)
                'gradient_end': '#2ECC71',    # Gradient end (Green)
            },
            'stunning': {
                'primary': '#8E44AD',      # Rich Purple
                'secondary': '#3498DB',    # Azure
                'accent': '#E74C3C',       # Alizarin (Red)
                'background': '#ECF0F1',   # Clouds
                'text': '#2C3E50',         # Midnight Blue
                'light_text': '#95A5A6',   # Concrete
                'highlight': '#F1C40F',    # Sunflower
                'success': '#2ECC71',      # Emerald
                'warning': '#E67E22',      # Carrot
                'info': '#3498DB',         # Peter River
                'divider': '#BDC3C7',      # Silver
                'education': '#9B59B6',    # Amethyst
                'insight': '#1ABC9C',      # Turquoise
                'gradient_start': '#8E44AD',  # Purple
                'gradient_end': '#3498DB',    # Blue
            },
            'premium': {
                'primary': '#34495E',      # Wet Asphalt
                'secondary': '#F39C12',    # Orange
                'accent': '#E74C3C',       # Red
                'background': '#FFFFFF',   # White
                'text': '#2C3E50',         # Navy
                'light_text': '#7F8C8D',   # Gray
                'highlight': '#F1C40F',    # Gold
                'success': '#27AE60',      # Nephritis
                'warning': '#D35400',      # Pumpkin
                'info': '#2980B9',         # Belize Hole
                'divider': '#95A5A6',      # Concrete
                'education': '#16A085',    # Green Sea
                'insight': '#C0392B',      # Pomegranate
                'gradient_start': '#34495E',  # Dark
                'gradient_end': '#F39C12',    # Orange
            }
        }
    
    def _sanitize_filename(self, filename: str) -> str:
        """Sanitize filename to ensure it's safe for file systems"""
        # Handle empty or None filename with more robust validation
        if not filename or not str(filename).strip():
            import time
            return f"document_{int(time.time())}"
        
        # Convert to string and clean
        filename = str(filename).strip()
        
        # Additional validation for empty strings after conversion
        if not filename:
            import time
            return f"document_{int(time.time())}"
        
        # Remove or replace invalid characters
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            filename = filename.replace(char, '_')
        
        # Replace spaces with underscores
        filename = filename.replace(' ', '_')
        
        # Limit length and ensure it's not empty
        filename = filename[:50]  # Limit to 50 characters for cleaner names
        if not filename:
            import time
            filename = f"document_{int(time.time())}"
        
        # Ensure it doesn't start or end with spaces or dots
        filename = filename.strip('. ')
        
        # Ensure it starts with a letter or number
        if filename and not (filename[0].isalpha() or filename[0].isdigit()):
            filename = "doc_" + filename
        
        # Additional validation to ensure we have a valid filename
        if not filename or len(filename) < 2:
            import time
            filename = f"document_{int(time.time())}"
        
        # If filename is empty after sanitization, use a generic name
        if not filename:
            import time
            filename = f"document_{int(time.time())}"
        
        return filename
    
    async def _generate_fallback_document(self, topic: str, doc_type: str) -> str:
        """Generate a simple fallback document when primary generation fails.
        
        This method creates a basic document with minimal content as a fallback
        when the primary document generation process fails.
        
        Args:
            topic (str): The document topic
            doc_type (str): The document type
            
        Returns:
            str: A simple document content string
        """
        # Create a simple fallback document
        fallback_content = f"""
# {doc_type.title()} Document: {topic}

## Document Information
- Topic: {topic}
- Document Type: {doc_type.title()}
- Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}

## Content
This is a fallback document generated because the primary generation process failed.

## Note
Please try generating the document again. If the issue persists, contact support.
        """
        return fallback_content
    
    async def _generate_filename(self, topic: str, doc_type: str) -> str:
        """Generate a clean filename by asking Gemini to create a meaningful name based on the topic.
        
        This method implements a multi-level fallback mechanism:
        1. Ask Gemini to generate a meaningful filename
        2. If Gemini fails, create filename from topic
        3. If all else fails, use a generic name with timestamp
        
        Args:
            topic (str): The document topic
            doc_type (str): The document type (PDF, Excel, etc.)
            
        Returns:
            str: A sanitized filename
        """
        # Handle empty or invalid topic
        if not topic or not str(topic).strip():
            import time
            return self._sanitize_filename(f"document_{int(time.time())}")
        
        try:
            # Ask Gemini to create a meaningful filename based on the topic
            filename_prompt = f"""
            Create a concise, meaningful filename (without extension) for a {doc_type} document about '{topic}'.
            The filename should be:
            1. In the SAME LANGUAGE as the user's input '{topic}'
            2. Concise (3-5 words maximum)
            3. Descriptive of the main topic
            4. Using underscores instead of spaces
            5. Without any special characters or file extensions
            6. Without any "Generated by" or similar robotic text
            
    
            Return ONLY the filename, nothing else.
            """
            
            # Generate filename with timeout to prevent blocking
            try:
                filename_response = await asyncio.wait_for(
                    asyncio.to_thread(lambda: self.model.generate_content(filename_prompt)),
                    timeout=Config.PROCESSING_TIMEOUT  # Configurable timeout for filename generation
                )
                filename = filename_response.text if filename_response and filename_response.text else ""
            except asyncio.TimeoutError:
                logger.warning("Filename generation timed out, using fallback method")
                filename = ""
            
            # Clean up the filename
            if filename:
                # Remove any extra text or formatting
                filename = filename.strip().split('\n')[0].strip()
                # Remove any quotes or special formatting
                filename = filename.replace('"', '').replace("'", "").strip()
                
                # If we got a good filename, use it
                if filename and len(filename) > 2:
                    return self._sanitize_filename(filename)
            
            # Fallback: create filename from topic if Gemini failed
            cleaned_topic = str(topic).strip()
            words = cleaned_topic.split()
            if len(words) > 5:
                # Take first 5 words for filename
                filename_base = "_".join(words[:5])
            else:
                # Use the whole topic if it's short
                filename_base = "_".join(words)
            
            # Sanitize and return the filename without adding the document type
            return self._sanitize_filename(filename_base)
                
        except Exception as e:
            logger.warning(f"Filename generation failed: {e}")
            # Fallback to topic-based filename
            try:
                cleaned_topic = str(topic).strip()
                words = cleaned_topic.split()
                if len(words) > 5:
                    # Take first 5 words for filename
                    filename_base = "_".join(words[:5])
                else:
                    # Use the whole topic if it's short
                    filename_base = "_".join(words)
                
                # Sanitize and return the filename without adding the document type
                return self._sanitize_filename(filename_base)
            except Exception as e2:
                logger.error(f"Fallback filename generation failed: {e2}")
                # Absolute last resort - generic name with timestamp
                import time
                return self._sanitize_filename(f"document_{int(time.time())}")
    
    def _get_color_scheme(self, scheme_name='professional') -> Dict[str, str]:
        """Get a color scheme by name.
        
        Args:
            scheme_name (str): The name of the color scheme to retrieve
            
        Returns:
            Dict[str, str]: A dictionary containing color scheme definitions
        """
        return self.color_schemes.get(scheme_name, self.color_schemes['professional'])
    
    def _select_color_scheme_by_topic(self, topic: str, doc_type: str = "general") -> Dict[str, str]:
        """Select a color scheme based on the topic and document type.
        
        Args:
            topic (str): The document topic
            doc_type (str): The document type
            
        Returns:
            Dict[str, str]: A color scheme dictionary
        """
        topic_lower = topic.lower()
        
        # Define topic-based color scheme mappings
        topic_keywords = {
            # Business/Corporate/Finance keywords
            'business': 'professional',
            'corporate': 'professional',
            'finance': 'professional',
            'biznes': 'professional',
            'kompaniya': 'professional',
            'moliya': 'professional',
            
            # Marketing/Creative/Design keywords
            'marketing': 'vibrant',
            'creative': 'vibrant',
            'design': 'vibrant',
            'dizayn': 'vibrant',
            'kreativ': 'vibrant',
            
            # Technology/Tech/Innovation keywords
            'technology': 'modern',
            'tech': 'modern',
            'innovation': 'modern',
            'texnologiya': 'modern',
            'innovatsiya': 'modern',
            
            # Elegant/Luxury keywords
            'elegant': 'elegant',
            'luxury': 'elegant',
            'hashamat': 'elegant',
            
            # Formal/Academic/Education keywords
            'formal': 'professional',
            'academic': 'professional',
            'education': 'elegant',
            'ta\'lim': 'elegant',
            'akademik': 'professional',
            'rasmiy': 'professional',
            'oqituvchi': 'elegant',
            
            # Health/Medical/Wellness keywords
            'health': 'clean',
            'medical': 'clean',
            'wellness': 'natural',
            'salomatlik': 'clean',
            'tibbiy': 'clean',
            'fitnes': 'natural',
            
            # Environment/Sustainability/Green keywords
            'environment': 'natural',
            'sustainability': 'natural',
            'green': 'natural',
            'atrof muhit': 'natural',
            'barqarorlik': 'natural',
            'yashil': 'natural',
            
            # Sports/Recreation/Entertainment keywords
            'sports': 'energetic',
            'recreation': 'energetic',
            'entertainment': 'vibrant',
            'sport': 'energetic',
            'ko\'ngilochar': 'vibrant',
            
            # Travel/Tourism/Adventure keywords
            'travel': 'exploratory',
            'tourism': 'exploratory',
            'adventure': 'exploratory',
            'sayohat': 'exploratory',
            'sarguzasht': 'exploratory',
            
            # Religious/Spiritual keywords
            'religious': 'elegant',
            'spiritual': 'elegant',
            'islamic': 'elegant',
            'muslim': 'elegant',
            'din': 'elegant',
            'ibodat': 'elegant',
            
            # Personal Development/Success keywords
            'success': 'vibrant',
            'motivation': 'vibrant',
            'inspiration': 'vibrant',
            'growth': 'vibrant',
            'development': 'vibrant',
            'muvaffaqiyat': 'vibrant',
            'motivatsiya': 'vibrant',
            'ilhom': 'vibrant',
        }
        
        # Check if any keyword matches the topic
        for keyword, scheme in topic_keywords.items():
            if keyword in topic_lower:
                return self._get_color_scheme(scheme)
        
        # Document type specific mappings
        doc_type_mappings = {
            'pdf': 'professional',
            'excel': 'professional',
            'word': 'professional',
            'powerpoint': 'vibrant',
        }
        
        # Check document type mapping
        if doc_type.lower() in doc_type_mappings:
            return self._get_color_scheme(doc_type_mappings[doc_type.lower()])
        
        # Default to professional scheme
        return self._get_color_scheme('professional')
    
    async def _send_success_message(self, processing_msg, success_text: str) -> None:
        """Send a success message to the user.
        
        Args:
            processing_msg: The processing message to update
            success_text (str): The success message to display to the user
        """
        if processing_msg:
            try:
                await processing_msg.edit_text(success_text, parse_mode=ParseMode.HTML)
            except Exception as e:
                logger.warning(f"Failed to send success message to user: {e}")

    async def _send_processing_message(self, update: Update, message_text: str):
        """Send a processing message to the user with emojis and styling.
        
        Args:
            update (Update): The Telegram update object
            message_text (str): The message text to send
            
        Returns:
            Message: The sent message object
        """
        # Removed send_typing call to improve response time for keyboard button selections
        return await safe_reply(update, message_text, parse_mode=ParseMode.HTML)
    
    async def _track_document_generation(self, update: Update, doc_type: str) -> None:
        """Track document generation in memory manager"""
        if update and update.effective_chat:
            chat_id = str(update.effective_chat.id)
            self.memory.track_document_generation(chat_id, doc_type, update)
    
    def _validate_topic(self, topic: str) -> Tuple[bool, str]:
        """Validate topic and return (is_valid, cleaned_topic).
        
        Args:
            topic (str): The topic to validate
            
        Returns:
            Tuple[bool, str]: A tuple containing (is_valid, cleaned_topic)
        """
        if not topic or not str(topic).strip():
            return False, ""
        
        cleaned_topic = str(topic).strip()
        if len(cleaned_topic) < 2:
            return False, cleaned_topic
            
        return True, cleaned_topic
    
    async def _handle_document_generation_error(self, processing_msg, error_msg: str = "❌ Hujjat yaratishda xatolik. Iltimos, keyinroq qayta urinib ko'ring.", log_msg: Optional[str] = None):
        """Handle document generation errors with centralized error messaging.
        
        Args:
            processing_msg: The processing message to update
            error_msg (str): The error message to display to the user
            log_msg (Optional[str]): Additional message for logging
        """
        if log_msg:
            logger.error(log_msg)
        if processing_msg:
            from telegram.constants import ParseMode
            try:
                await processing_msg.edit_text(error_msg, parse_mode=ParseMode.HTML)
            except Exception as e:
                logger.warning(f"Failed to send error message to user: {e}")
    
    async def _handle_timeout_error(self, processing_msg, error_msg: str = "⏰ Hujjat yaratish vaqti tugadi. Iltimos, keyinroq qayta urinib ko'ring."):
        """Handle timeout errors with centralized error messaging.
        
        Args:
            processing_msg: The processing message to update
            error_msg (str): The timeout error message to display to the user
        """
        if processing_msg:
            from telegram.constants import ParseMode
            try:
                await processing_msg.edit_text(error_msg, parse_mode=ParseMode.HTML)
            except Exception as e:
                logger.warning(f"Failed to send timeout error message to user: {e}")
    
    async def _handle_validation_error(self, update: Update, doc_type: str, error_msg: str, processing_msg = None):
        """Handle validation errors with centralized error messaging.
        
        Args:
            update (Update): The Telegram update object
            doc_type (str): The document type
            error_msg (str): The validation error message to display to the user
            processing_msg: The processing message to update (if any)
        """
        # Track document generation attempt even for invalid topics
        if update and update.effective_chat:
            chat_id = str(update.effective_chat.id)
            self.memory.track_document_generation(chat_id, doc_type, update)
        
        try:
            if processing_msg:
                from telegram.constants import ParseMode
                await processing_msg.edit_text(error_msg, parse_mode=ParseMode.HTML)
            elif update and update.message:
                from modules.utils import safe_reply
                from telegram.constants import ParseMode
                await safe_reply(update, error_msg, parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.warning(f"Failed to send validation error message to user: {e}")

    @abstractmethod
    async def generate(self, update: Update, context: ContextTypes.DEFAULT_TYPE, topic: str, content_context: str = ""):
        """Generate document - to be implemented by subclasses.
        
        Args:
            update (Update): The Telegram update object
            context (ContextTypes.DEFAULT_TYPE): The Telegram context object
            topic (str): The document topic
            content_context (str, optional): Additional context for document generation. Defaults to "".
        """
        pass