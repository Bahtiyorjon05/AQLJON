import asyncio
import tempfile
import logging
import os
import platform
import math
import io
from typing import Dict
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from modules.doc_generation.base_generator import BaseDocumentGenerator
from modules.config import Config
from modules.utils import safe_reply, send_typing
from modules.retry_utils import generate_content_with_retry
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.pagesizes import A4, letter
from reportlab.lib.colors import HexColor, black, white, Color
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY, TA_RIGHT
from reportlab.lib.units import inch, cm
from reportlab.platypus import Image as ReportLabImage
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.graphics.shapes import Drawing, Line, Rect, Circle
from reportlab.lib.styles import ListStyle
import random

logger = logging.getLogger(__name__)

class PDFGenerator(BaseDocumentGenerator):
    """Handles PDF document generation with enhanced styling and professional themes.
    
    This class generates professional PDF documents with advanced styling, Unicode support,
    and theme-based color schemes. It supports various document types and automatically
    selects appropriate fonts for better emoji and special character display.
    """
    
    def __init__(self, gemini_model, memory_manager):
        """Initialize the PDF generator.
        
        Args:
            gemini_model: The Gemini AI model instance
            memory_manager: The memory manager instance
        """
        super().__init__(gemini_model, memory_manager)
        self._register_emoji_fonts()
    
    def _register_emoji_fonts(self):
        """Register emoji-supporting fonts for better emoji display in PDFs with enhanced Unicode support"""
        try:
            # Try to register common emoji-supporting fonts based on the operating system
            system = platform.system()
            
            if system == "Windows":
                # Windows emoji fonts - ordered by priority for Unicode support
                # Segoe UI Symbol is particularly good for Arabic and religious symbols
                # DejaVu Sans is prioritized for excellent apostrophe and Unicode support
                unicode_fonts = [
                    ("DejaVuSans", "C:/Windows/Fonts/DejaVuSans.ttf"),
                    ("DejaVuSans-Bold", "C:/Windows/Fonts/DejaVuSans-Bold.ttf"),
                    ("Segoe UI Symbol", "C:/Windows/Fonts/seguisym.ttf"),
                    ("Arial Unicode MS", "C:/Windows/Fonts/ARIALUNI.TTF"),
                    ("Segoe UI", "C:/Windows/Fonts/segoeui.ttf"),
                    ("Segoe UI Emoji", "C:/Windows/Fonts/seguiemj.ttf"),
                    ("Microsoft Sans Serif", "C:/Windows/Fonts/micross.ttf"),
                    ("Tahoma", "C:/Windows/Fonts/tahoma.ttf"),
                    # Additional fonts for better Unicode support
                    ("Times New Roman", "C:/Windows/Fonts/times.ttf"),
                    # Add Noto fonts for comprehensive Unicode support including Arabic
                    ("NotoSans", "C:/Windows/Fonts/NotoSans-Regular.ttf"),
                    ("NotoSansArabic", "C:/Windows/Fonts/NotoSansArabic-Regular.ttf"),
                    ("NotoSansArabic-Bold", "C:/Windows/Fonts/NotoSansArabic-Bold.ttf"),
                ]
            elif system == "Darwin":  # macOS
                # macOS emoji fonts
                unicode_fonts = [
                    ("DejaVuSans", "/System/Library/Fonts/DejaVuSans.ttf"),
                    ("DejaVuSans-Bold", "/System/Library/Fonts/DejaVuSans-Bold.ttf"),
                    ("Apple Symbols", "/System/Library/Fonts/Apple Symbols.ttf"),
                    ("Arial Unicode MS", "/System/Library/Fonts/Arial Unicode.ttf"),
                    ("Apple Color Emoji", "/System/Library/Fonts/Apple Color Emoji.ttc"),
                    ("Helvetica", "/System/Library/Fonts/Helvetica.ttc"),
                    ("Times New Roman", "/System/Library/Fonts/Times New Roman.ttf"),
                    # Additional fonts for better Unicode support
                    ("Menlo", "/System/Library/Fonts/Menlo.ttc"),
                    # Add Noto fonts for comprehensive Unicode support including Arabic
                    ("NotoSans", "/System/Library/Fonts/NotoSans-Regular.ttf"),
                    ("NotoSansArabic", "/System/Library/Fonts/NotoSansArabic-Regular.ttf"),
                    ("NotoSansArabic-Bold", "/System/Library/Fonts/NotoSansArabic-Bold.ttf"),
                ]
            else:  # Linux and others
                # Common Linux emoji fonts
                unicode_fonts = [
                    ("DejaVuSans", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
                    ("DejaVuSans-Bold", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
                    ("Noto Sans", "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf"),
                    ("Noto Color Emoji", "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"),
                    ("Noto Emoji", "/usr/share/fonts/truetype/noto/NotoEmoji-Regular.ttf"),
                    ("Arial Unicode MS", "/usr/share/fonts/truetype/arphic/arialuni.ttf"),
                    ("DejaVu Sans", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
                    ("Liberation Sans", "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
                    # Additional fonts for better Unicode support
                    ("FreeSans", "/usr/share/fonts/truetype/freefont/FreeSans.ttf"),
                    # Add Arabic support fonts
                    ("NotoSansArabic", "/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf"),
                    ("NotoSansArabic-Bold", "/usr/share/fonts/truetype/noto/NotoSansArabic-Bold.ttf"),
                ]
            
            # Try to register available Unicode fonts
            registered_fonts = []
            for font_name, font_path in unicode_fonts:
                try:
                    if os.path.exists(font_path):
                        pdfmetrics.registerFont(TTFont(font_name, font_path))
                        registered_fonts.append(font_name)
                        logger.info(f"Registered Unicode font: {font_name} ({font_path})")
                    # Suppress warnings for missing fonts as they're not critical and just clutter logs
                    # else:
                    #     logger.warning(f"Font not found: {font_name} ({font_path})")
                except Exception as e:
                    # Suppress font registration warnings as they're not critical and just clutter logs
                    # logger.warning(f"Could not register font {font_name}: {e}")
                    pass
            
            # Store the registered fonts for later use
            self.unicode_fonts = registered_fonts
            
            # If no Unicode fonts were registered, use a fallback approach
            if not registered_fonts:
                # Suppress warning as it's not critical and just clutters logs
                # logger.warning("No Unicode fonts found, using fallback approach")
                self.unicode_fonts = []
                
        except Exception as e:
            # Suppress error logging for font registration as it's not critical
            # logger.error(f"Error registering Unicode fonts: {e}")
            self.unicode_fonts = []

    def _get_best_unicode_font(self):
        """Get the best font for Unicode character support, prioritizing those that support religious symbols and apostrophes"""
        if not self.unicode_fonts:
            # Try to register DejaVu fonts as fallback if available - DejaVu has excellent apostrophe support
            try:
                import reportlab.rl_config as rl_config
                rl_config.TTFSearchPath.append('/usr/share/fonts/truetype/dejavu')
                rl_config.TTFSearchPath.append('C:/Windows/Fonts')
                rl_config.TTFSearchPath.append('/System/Library/Fonts')
                
                # Try to register DejaVu fonts specifically for Unicode support
                dejavu_path = None
                for path in ['/usr/share/fonts/truetype/dejavu', 'C:/Windows/Fonts', '/System/Library/Fonts']:
                    dejavu_regular = os.path.join(path, 'DejaVuSans.ttf')
                    dejavu_bold = os.path.join(path, 'DejaVuSans-Bold.ttf')
                    if os.path.exists(dejavu_regular):
                        dejavu_path = path
                        break
                
                if dejavu_path:
                    regular_font = os.path.join(dejavu_path, 'DejaVuSans.ttf')
                    bold_font = os.path.join(dejavu_path, 'DejaVuSans-Bold.ttf')
                    
                    if os.path.exists(regular_font):
                        pdfmetrics.registerFont(TTFont('DejaVuSans', regular_font))
                        # Also register with a simpler name for compatibility
                        pdfmetrics.registerFont(TTFont('DejaVu', regular_font))
                    if os.path.exists(bold_font):
                        pdfmetrics.registerFont(TTFont('DejaVuSans-Bold', bold_font))
                        # Also register with a simpler name for compatibility
                        pdfmetrics.registerFont(TTFont('DejaVu-Bold', bold_font))
                    
                    return 'DejaVuSans', 'DejaVuSans-Bold'
            except Exception as e:
                # Suppress font registration warnings as they're not critical and just clutter logs
                # logger.warning(f"Could not register DejaVu fonts: {e}")
                pass
            
            # Fallback to Helvetica with UTF-8 support
            return 'Helvetica', 'Helvetica-Bold'
        
        # Priority order for fonts that support the Prophet Muhammad symbol (ﷺ - U+FDFA) and special characters
        # DejaVu Sans is known to have excellent Unicode support including apostrophes
        # Noto Sans Arabic is specifically designed for Arabic script including religious symbols
        priority_fonts = [
            'NotoSansArabic',      # Best for Arabic script and religious symbols
            'DejaVuSans',          # Excellent general Unicode support including apostrophes
            'DejaVu Sans',         # Alternative name
            'Segoe UI Symbol',     # Good for religious symbols on Windows
            'Arial Unicode MS',    # Extensive Unicode coverage
            'Noto Sans',           # Google's comprehensive Unicode font
            'Segoe UI',            # Windows default with good Unicode support
            'Apple Symbols',       # macOS symbols
            'Liberation Sans',     # Cross-platform font with good Unicode support
        ]
        
        for font in priority_fonts:
            if font in self.unicode_fonts:
                # Check for bold variant
                bold_variants = [
                    f"{font}-Bold", 
                    f"{font} Bold", 
                    f"{font}_Bold", 
                    'DejaVuSans-Bold', 
                    'DejaVu Bold',
                    'NotoSansArabic-Bold'  # Arabic bold variant
                ]
                bold_font = font  # Default to same font if no bold variant found
                
                for bold_variant in bold_variants:
                    if bold_variant in self.unicode_fonts:
                        bold_font = bold_variant
                        break
                
                return font, bold_font
        
        # Fallback to first registered font
        main_font = self.unicode_fonts[0] if self.unicode_fonts else 'Helvetica'
        return main_font, main_font
    
    def _get_theme_colors(self, theme_name='modern'):
        """Get a comprehensive color palette for a specific theme"""
        themes = {
            'modern': {
                'primary': HexColor('#2C3E50'),      # Deep navy
                'secondary': HexColor('#3498DB'),    # Bright blue
                'accent': HexColor('#E74C3C'),       # Vibrant red
                'background': HexColor('#ECF0F1'),   # Light gray
                'text': HexColor('#2C3E50'),         # Dark navy
                'light_text': HexColor('#7F8C8D'),   # Gray
                'highlight': HexColor('#F39C12'),    # Amber
                'success': HexColor('#27AE60'),      # Green
                'warning': HexColor('#F39C12'),      # Orange
                'info': HexColor('#3498DB'),         # Blue
                'divider': HexColor('#BDC3C7'),      # Light gray-blue
                'education': HexColor('#9B59B6'),    # Purple for educational content
                'insight': HexColor('#1ABC9C'),      # Turquoise for insights
                'quote': HexColor('#8E44AD'),        # Deep purple for quotes
                'code': HexColor('#F39C12'),         # Amber for code blocks
                'link': HexColor('#3498DB'),         # Blue for links
            },
            'elegant': {
                'primary': HexColor('#8E44AD'),      # Purple
                'secondary': HexColor('#9B59B6'),    # Light purple
                'accent': HexColor('#E67E22'),       # Orange
                'background': HexColor('#F8F9F9'),   # Very light gray
                'text': HexColor('#2C3E50'),         # Dark navy
                'light_text': HexColor('#95A5A6'),   # Gray
                'highlight': HexColor('#1ABC9C'),    # Turquoise
                'success': HexColor('#27AE60'),      # Green
                'warning': HexColor('#F39C12'),      # Orange
                'info': HexColor('#3498DB'),         # Blue
                'divider': HexColor('#D5DBDB'),      # Light gray
                'education': HexColor('#8E44AD'),    # Purple for educational content
                'insight': HexColor('#1ABC9C'),      # Turquoise for insights
                'quote': HexColor('#9B59B6'),        # Light purple for quotes
                'code': HexColor('#E67E22'),         # Orange for code blocks
                'link': HexColor('#9B59B6'),         # Light purple for links
            },
            'vibrant': {
                'primary': HexColor('#E74C3C'),      # Red
                'secondary': HexColor('#E67E22'),    # Orange
                'accent': HexColor('#F1C40F'),       # Yellow
                'background': HexColor('#FDEDEC'),   # Light red background
                'text': HexColor('#2C3E50'),         # Dark navy
                'light_text': HexColor('#95A5A6'),   # Gray
                'highlight': HexColor('#1ABC9C'),    # Turquoise
                'success': HexColor('#27AE60'),      # Green
                'warning': HexColor('#F39C12'),      # Orange
                'info': HexColor('#3498DB'),         # Blue
                'divider': HexColor('#EBEDEF'),      # Light gray
                'education': HexColor('#E67E22'),    # Orange for educational content
                'insight': HexColor('#1ABC9C'),      # Turquoise for insights
                'quote': HexColor('#E74C3C'),        # Red for quotes
                'code': HexColor('#F1C40F'),         # Yellow for code blocks
                'link': HexColor('#E67E22'),         # Orange for links
            },
            'professional': {
                'primary': HexColor('#1F3A93'),      # Deep blue
                'secondary': HexColor('#3498DB'),    # Bright blue
                'accent': HexColor('#26A65B'),       # Green
                'background': HexColor('#F8F9F9'),   # Very light gray
                'text': HexColor('#2C3E50'),         # Dark navy
                'light_text': HexColor('#7F8C8D'),   # Gray
                'highlight': HexColor('#F39C12'),    # Amber
                'success': HexColor('#27AE60'),      # Green
                'warning': HexColor('#F39C12'),      # Orange
                'info': HexColor('#3498DB'),         # Blue
                'divider': HexColor('#D5DBDB'),      # Light gray
                'education': HexColor('#1F3A93'),    # Deep blue for educational content
                'insight': HexColor('#26A65B'),      # Green for insights
                'quote': HexColor('#1F3A93'),        # Deep blue for quotes
                'code': HexColor('#F39C12'),         # Amber for code blocks
                'link': HexColor('#3498DB'),         # Blue for links
            },
            'corporate': {
                'primary': HexColor('#2C3E50'),      # Charcoal
                'secondary': HexColor('#34495E'),    # Dark blue-gray
                'accent': HexColor('#16A085'),       # Teal
                'background': HexColor('#FFFFFF'),   # White
                'text': HexColor('#2C3E50'),         # Charcoal
                'light_text': HexColor('#95A5A6'),   # Gray
                'highlight': HexColor('#F39C12'),    # Amber
                'success': HexColor('#27AE60'),      # Green
                'warning': HexColor('#F39C12'),      # Orange
                'info': HexColor('#3498DB'),         # Blue
                'divider': HexColor('#ECF0F1'),      # Light gray
                'education': HexColor('#2C3E50'),    # Charcoal for educational content
                'insight': HexColor('#16A085'),      # Teal for insights
                'quote': HexColor('#34495E'),        # Dark blue-gray for quotes
                'code': HexColor('#16A085'),         # Teal for code blocks
                'link': HexColor('#3498DB'),         # Blue for links
            },
            'creative': {
                'primary': HexColor('#9B59B6'),      # Purple
                'secondary': HexColor('#3498DB'),    # Blue
                'accent': HexColor('#E74C3C'),       # Red
                'background': HexColor('#F9F5FF'),   # Light purple background
                'text': HexColor('#2C3E50'),         # Dark navy
                'light_text': HexColor('#7F8C8D'),   # Gray
                'highlight': HexColor('#F1C40F'),    # Yellow
                'success': HexColor('#27AE60'),      # Green
                'warning': HexColor('#E67E22'),      # Orange
                'info': HexColor('#3498DB'),         # Blue
                'divider': HexColor('#D5DBDB'),      # Light gray
                'education': HexColor('#9B59B6'),    # Purple for educational content
                'insight': HexColor('#1ABC9C'),      # Turquoise for insights
                'quote': HexColor('#9B59B6'),        # Purple for quotes
                'code': HexColor('#F1C40F'),         # Yellow for code blocks
                'link': HexColor('#9B59B6'),         # Purple for links
            },
            'minimalist': {
                'primary': HexColor('#2C3E50'),      # Dark navy
                'secondary': HexColor('#7F8C8D'),    # Gray
                'accent': HexColor('#3498DB'),       # Blue
                'background': HexColor('#FFFFFF'),   # White
                'text': HexColor('#2C3E50'),         # Dark navy
                'light_text': HexColor('#BDC3C7'),   # Light gray
                'highlight': HexColor('#3498DB'),    # Blue
                'success': HexColor('#27AE60'),      # Green
                'warning': HexColor('#F39C12'),      # Orange
                'info': HexColor('#3498DB'),         # Blue
                'divider': HexColor('#ECF0F1'),      # Light gray
                'education': HexColor('#2C3E50'),    # Dark navy for educational content
                'insight': HexColor('#7F8C8D'),      # Gray for insights
                'quote': HexColor('#7F8C8D'),        # Gray for quotes
                'code': HexColor('#3498DB'),         # Blue for code blocks
                'link': HexColor('#3498DB'),         # Blue for links
            }
        }
        return themes.get(theme_name, themes['modern'])
    
    def _create_decorative_elements(self, story, colors, element_type='header'):
        """Create decorative elements for visual enhancement"""
        # Note: These decorative elements are purely visual and do not affect text rendering or Unicode support
        if element_type == 'header':
            # Create a decorative header with gradient geometric shapes
            d = Drawing(400, 30)
            # Add gradient circles for visual interest
            for i in range(7):
                x = 20 + i * 60
                size = 5 + (i % 3) * 2  # Varying sizes
                # Use different colors from the scheme
                color_options = [colors['primary'], colors['secondary'], colors['accent']]
                circle = Circle(x, 15, size, fillColor=color_options[i % len(color_options)], strokeColor=colors['divider'])
                d.add(circle)
            story.append(d)
            story.append(Spacer(1, 15))
        elif element_type == 'divider':
            # Create a decorative divider with gradient effect
            d = Drawing(400, 15)
            # Create a gradient line effect
            for i in range(20):
                x = i * 20
                line = Line(x, 7, x + 10, 7, strokeColor=colors['divider'], strokeWidth=1)
                d.add(line)
            story.append(d)
            story.append(Spacer(1, 20))
        elif element_type == 'footer':
            # Create a decorative footer with wave pattern
            d = Drawing(400, 25)
            # Create a wave pattern using simple calculations instead of math.sin
            points = []
            for i in range(41):
                x = i * 10
                # Create a wave-like pattern using modulo arithmetic
                y = 12 + 5 * (i % 4 - 2) * 0.5  # Simple wave approximation
                points.append((x, y))
            # Draw the wave
            for i in range(len(points) - 1):
                line = Line(points[i][0], points[i][1], points[i+1][0], points[i+1][1], 
                           strokeColor=colors['secondary'], strokeWidth=2)
                d.add(line)
            story.append(d)
            story.append(Spacer(1, 15))
        elif element_type == 'sidebar':
            # Create a decorative sidebar element
            d = Drawing(20, 400)
            # Add vertical decorative lines
            for i in range(20):
                y = i * 20
                line = Line(5, y, 15, y, strokeColor=colors['divider'], strokeWidth=1)
                d.add(line)
                # Add small circles at intersection points
                if i % 2 == 0:
                    circle = Circle(10, y, 2, fillColor=colors['accent'], strokeColor=colors['divider'])
                    d.add(circle)
            story.append(d)
        elif element_type == 'corner':
            # Create decorative corner elements
            d = Drawing(50, 50)
            # Create a decorative corner pattern
            for i in range(5):
                size = 40 - i * 8
                rect = Rect(5 + i * 4, 5 + i * 4, size, size)
                rect.strokeColor = colors['divider']
                rect.strokeWidth = 0.5
                rect.fillColor = None
                d.add(rect)
            story.append(d)
    
    def _add_cover_page(self, story, title, topic, colors):
        """Add an awesome cover page with visual elements"""
        # Add decorative header with gradient effect
        self._create_decorative_elements(story, colors, 'header')
        
        # Add spacing
        story.append(Spacer(1, 20))
        
        # Add large title with awesome styling
        # Get the best Unicode font for cover page as well
        main_font, bold_font = self._get_best_unicode_font()
        title_style = ParagraphStyle(
            'CoverTitle',
            fontSize=44,
            fontName=bold_font,
            textColor=colors['primary'],
            alignment=TA_CENTER,
            spaceAfter=30,
            leading=48,
            encoding='utf-8',  # Explicitly set UTF-8 encoding
            backColor=colors['background']  # Add background color
        )
        story.append(Paragraph(title, title_style))
        
        # Add decorative divider with enhanced styling
        self._create_decorative_elements(story, colors, 'divider')
        
        # Add document info with educational focus
        info_style = ParagraphStyle(
            'CoverInfo',
            fontSize=12,
            fontName=main_font,
            textColor=colors['light_text'],
            alignment=TA_CENTER,
            spaceAfter=10,
            leading=16,
            encoding='utf-8',  # Explicitly set UTF-8 encoding
            borderColor=colors['divider'],
            borderWidth=0.5
        )
        story.append(Paragraph(f"Prepared on: {self._get_current_date()}", info_style))
        # Remove the robotic "Educational Document with Learning Takeaways" text
        # story.append(Paragraph("📚 Educational Document with Learning Takeaways", info_style))
        
        # Add decorative footer
        self._create_decorative_elements(story, colors, 'footer')
        
        # Add page break
        story.append(PageBreak())
    
    def _add_table_of_contents_placeholder(self, story, colors):
        """Add a table of contents placeholder with styling"""
        # Add section header
        # Get the best Unicode font for TOC as well
        _, bold_font = self._get_best_unicode_font()
        toc_header_style = ParagraphStyle(
            'TOCHeader',
            fontSize=24,
            fontName=bold_font,
            textColor=colors['primary'],
            alignment=TA_CENTER,
            spaceAfter=25,
            leading=30,
            encoding='utf-8'  # Explicitly set UTF-8 encoding
        )
        story.append(Paragraph("📋 Table of Contents", toc_header_style))
        
        # Add note
        main_font, _ = self._get_best_unicode_font()
        note_style = ParagraphStyle(
            'TOCNote',
            fontSize=12,
            fontName=main_font,
            textColor=colors['light_text'],
            alignment=TA_CENTER,
            spaceAfter=30,
            leading=16,
            encoding='utf-8'  # Explicitly set UTF-8 encoding
        )
      
        # Add decorative divider
        self._create_decorative_elements(story, colors, 'divider')
        
        story.append(Spacer(1, 30))
    
    async def generate(self, update: Update, context: ContextTypes.DEFAULT_TYPE, topic: str, content_context: str = ""):
        """Generate a professional PDF document based on user request"""
        # Validate topic using centralized validation
        is_valid, cleaned_topic = self._validate_topic(topic)
        if not is_valid:
            await self._track_document_generation(update, "pdf")
            if len(cleaned_topic) < 2:
                processing_msg = await self._send_processing_message(update, "<b>❌ PDF hujjat yaratishda xatolik.</b>\n\nMavzu juda qisqa.")
                if processing_msg:
                    await processing_msg.edit_text("❌ Iltimos, PDF hujjati uchun to'liq mavzu kiriting (kamida 2 belgi).", parse_mode=ParseMode.HTML)
            else:
                processing_msg = await self._send_processing_message(update, "<b>❌ PDF hujjat yaratishda xatolik.</b>\n\nIltimos, mavzu kiriting.")
                if processing_msg:
                    await processing_msg.edit_text("❌ Iltimos, PDF hujjati uchun mavzu kiriting.", parse_mode=ParseMode.HTML)
            return
        
        # Track document generation
        await self._track_document_generation(update, "pdf")
        
        # Initialize processing_msg to avoid unbound variable error
        processing_msg = None
        
        # Send immediate processing message for better user experience
        try:
            from modules.utils import send_fast_reply
            if update.message:
                send_fast_reply(update.message, "<b>📄 PDF hujjatni tuzyapman. Biroz kutib turing... ⏳</b>")
                # Send typing indicator
                await send_typing(update)
        except:
            # Fallback if fast reply fails
            processing_msg = await self._send_processing_message(update, f"<b>📄 PDF hujjatni tuzyapman. Biroz kutib turing... ⏳</b>")
            # Send typing indicator
            await send_typing(update)
        
        try:
            # Generate filename using centralized method
            filename = await self._generate_filename(cleaned_topic, "PDF")
            
            # Generate content with Gemini using enhanced prompt for visual, data-driven content
            # Gemini will automatically detect the language from the user's input
            prompt = f"""
            You are AQLJON, an intelligent assistant who creates exceptional, professionally formatted PDF documents.
            Create a professional PDF document about '{cleaned_topic}' in the SAME LANGUAGE as the user's input.

            {"Use the following context from previous documents the user shared to inform your content:" + content_context if content_context else ""}

            CRITICAL: Structure your response for MAXIMUM VISUAL IMPACT with data, tables, and charts:

            1. CONTENT STRUCTURE:
               - Main title (#): Compelling, professional title
               - 4-6 major sections (##): Clear, descriptive headings
               - 2-3 subsections (###) per major section
               - Mix of text, data, and visual elements

            2. INCLUDE DATA FOR VISUALIZATION:
               For any data-heavy sections, provide:
               - Comparison data (e.g., "Feature A: 85%, Feature B: 65%, Feature C: 92%")
               - Timeline data (e.g., "2020: 100K, 2021: 150K, 2022: 200K, 2023: 280K")
               - Category breakdowns (e.g., "Type 1: 40%, Type 2: 35%, Type 3: 25%")
               - Rankings or top items with numbers
               - Process steps with time estimates or percentages

            3. SUGGEST TABLES (mark with [TABLE]):
               For structured data, use this format:
               [TABLE: Comparison of Options]
               | Feature | Option A | Option B | Option C |
               | Cost | $100 | $150 | $200 |
               | Speed | Fast | Medium | Slow |
               | Quality | High | Medium | High |

            4. SUGGEST CHARTS (mark with [CHART]):
               [CHART: Bar - Market Share by Company]
               Data: Company A: 35%, Company B: 28%, Company C: 22%, Company D: 15%

               [CHART: Line - Growth Over Time]
               Data: 2020: 100, 2021: 150, 2022: 225, 2023: 340

               [CHART: Pie - Budget Distribution]
               Data: Marketing: 30%, Development: 40%, Operations: 20%, Other: 10%

            5. VISUAL ELEMENTS:
               - Add emojis strategically for section markers
               - Use <quote>text</quote> for important quotes
               - Mark key insights with 💡 or 🔑
               - Use 📊 for data-heavy sections
               - Use 📈 for growth/trend sections

            6. CONTENT GUIDELINES:
               - Medium-detailed coverage (not too brief, not overly detailed)
               - Include real numbers, statistics, and data points
               - Provide actionable insights and practical advice
               - Add case studies or examples with specific metrics
               - Include comparisons using tables or data

            7. ACADEMIC CONTENT RULES:
               If topic relates to academic problems (math, physics, chemistry, coding):
               - NEVER provide direct solutions
               - Guide with concepts, hints, and understanding
               - Use diagrams and visual explanations
               - Include practice problems with hints only

            8. FORMATTING:
               - Use # for main title
               - Use ## for major sections
               - Use ### for subsections
               - Use - for bullet points
               - Use 1. 2. 3. for numbered steps
               - Mark tables with [TABLE: Title]
               - Mark charts with [CHART: Type - Title]

            9. LANGUAGE:
               - ALL content in SAME LANGUAGE as '{cleaned_topic}'
               - Conversational and engaging, not robotic
               - Professional but human-like tone
               - No "Generated by" or similar phrases

            Example format:
            # Engaging Professional Title

            ## Introduction
            Brief overview with key statistics (e.g., "Industry grew by 45% in 2023")

            ## Market Analysis
            [TABLE: Market Comparison]
            | Metric | 2022 | 2023 | Change |
            | Revenue | $1.2B | $1.8B | +50% |

            [CHART: Bar - Revenue by Quarter]
            Data: Q1: 400M, Q2: 450M, Q3: 480M, Q4: 470M

            ## Key Insights
            💡 Insight 1: Market shows strong growth trajectory
            📊 Data point: 78% of companies report increased adoption

            <quote>Important industry quote here</quote>
            """
            
            try:
                response = await generate_content_with_retry(
                    self.model,
                    prompt,
                    timeout=Config.PROCESSING_TIMEOUT * 2  # Double timeout for document generation
                )
                content = response.text if response and response.text else f"Error generating content for {cleaned_topic}."
            except asyncio.TimeoutError:
                logger.warning("PDF content generation timed out, using fallback content")
                content = f"# {cleaned_topic}\n\nProfessional PDF document on {cleaned_topic}.\n\nGenerated by AQLJON."
            except Exception as e:
                logger.error(f"PDF content generation failed after retries: {e}")
                content = f"# {cleaned_topic}\n\nProfessional PDF document on {cleaned_topic}.\n\nGenerated by AQLJON."
            
            # Create PDF in temporary file - offload to separate thread to avoid blocking asyncio
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
                tmp_path = tmp_file.name
            
            try:
                # Offload PDF creation to a separate thread to avoid blocking the asyncio event loop
                await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(
                        None, 
                        self._create_pdf_document, 
                        content, tmp_path, cleaned_topic, filename
                    ),
                    timeout=Config.PROCESSING_TIMEOUT  # Configurable timeout for PDF creation
                )
                
                # Send PDF to user
                if update.message:
                    with open(tmp_path, 'rb') as pdf_file:
                        await update.message.reply_document(
                            document=pdf_file,
                            filename=f"{filename}.pdf",
                            caption=f"📄 <b>'{filename}' mavzusida professional PDF hujjat</b>\n📁 Fayl nomi: {filename}.pdf",
                            parse_mode=ParseMode.HTML
                        )
                
                # Send success message
                try:
                    from modules.utils import send_fast_reply
                    if update.message:
                        send_fast_reply(update.message, f"✅ <b>'{filename}' nomli PDF hujjat muvaffaqiyatli tuzildi va yuborildi!</b>\n📥 Chiroyli dizayn va did bilan tuzilgan faylingizdan zavqlaning!", parse_mode=ParseMode.HTML)
                except:
                    # Fallback if fast reply fails
                    if processing_msg is not None:
                        await processing_msg.edit_text(f"✅ <b>'{filename}' nomli PDF hujjat muvaffaqiyatli tuzildi va yuborildi!</b>\n📥 Chiroyli dizayn va did bilan tuzilgan faylingizdan zavqlaning!", parse_mode=ParseMode.HTML)
            
            finally:
                # Clean up temporary file
                try:
                    import os
                    if os.path.exists(tmp_path):
                        os.unlink(tmp_path)
                except Exception as e:
                    logger.warning(f"Failed to cleanup temp file: {e}")
        
        except Exception as e:
            logger.error(f"PDF generation error: {e}")
            # Send error message to user
            try:
                from modules.utils import send_fast_reply
                if update.message:
                    send_fast_reply(update.message, "❌ PDF hujjat yaratishda xatolik. Iltimos, keyinroq qayta urinib ko'ring.", parse_mode=ParseMode.HTML)
            except:
                # Fallback if fast reply fails
                if processing_msg:
                    await processing_msg.edit_text("❌ PDF hujjat yaratishda xatolik. Iltimos, keyinroq qayta urinib ko'ring.", parse_mode=ParseMode.HTML)
    
    def _create_pdf_document(self, content, tmp_path, topic, filename):
        """Create PDF document in a separate thread to avoid blocking asyncio"""
        try:
            # Create professional PDF document
            buffer = io.BytesIO()
            doc = SimpleDocTemplate(buffer, pagesize=A4, 
                                   topMargin=72, bottomMargin=72,
                                   leftMargin=72, rightMargin=72)
            
            # Get styles
            styles = getSampleStyleSheet()
            
            # Get the best Unicode font for better emoji and special character support
            main_font, bold_font = self._get_best_unicode_font()
            
            # Update styles with Unicode font support and better formatting
            # Create enhanced normal style with better formatting
            normal_style = ParagraphStyle(
                'CustomNormal',
                parent=styles['Normal'],
                fontName=main_font,
                fontSize=14,  # Increased font size for better readability
                leading=24,   # Increased leading for better line spacing
                spaceAfter=18,  # Increased spacing after paragraph
                spaceBefore=10,  # Added spacing before paragraph
                alignment=TA_JUSTIFY,
                textColor=HexColor('#263238'),  # Darker text color for better readability
                wordWrap='LTR',     # Left-to-right word wrapping for better Unicode support
                encoding='utf-8',   # Explicitly set UTF-8 encoding
                allowWidows=0,      # Prevent widows
                allowOrphans=0,     # Prevent orphans
                hyphenationLang='',  # Disable hyphenation that might break Unicode
                backColor=HexColor('#FFFFFF'),
                firstLineIndent=0,   # No first line indent for cleaner look
                borderWidth=0.3,
                borderColor=HexColor('#CFD8DC'),  # Light blue-gray border
                borderPadding=8,
                borderRadius=2,  # Slight rounding for modern look
                shadowColor=HexColor('#ECEFF1'),  # Light shadow for depth
                shadowOffset=0.5,
                wordBreak='normal',  # Normal word breaking for Unicode characters
                splitLongWords=True,  # Allow splitting long words for better line wrapping
            )
            
            # Create enhanced bullet style with better formatting
            bullet_style = ParagraphStyle(
                'CustomBullet',
                parent=styles['Bullet'],
                fontName=main_font,
                fontSize=14,  # Increased font size
                leading=24,   # Increased leading for better line spacing
                spaceAfter=14,  # Increased spacing after bullet point
                spaceBefore=8,  # Added spacing before bullet point
                leftIndent=40,  # Increased left indent
                alignment=TA_LEFT,
                textColor=HexColor('#263238'),  # Dark text color
                wordWrap='LTR',     # Left-to-right word wrapping for better Unicode support
                encoding='utf-8',   # Explicitly set UTF-8 encoding
                allowWidows=0,      # Prevent widows
                allowOrphans=0,      # Prevent orphans
                backColor=HexColor('#FFFFFF'),
                firstLineIndent=0,
                borderWidth=0.4,
                borderColor=HexColor('#B0BEC5'),  # Blue-gray border
                borderPadding=5,
                borderRadius=2,  # Slight rounding
                shadowColor=HexColor('#ECEFF1'),  # Light shadow
                shadowOffset=0.5,
                wordBreak='normal',  # Normal word breaking for Unicode characters
                splitLongWords=True,  # Allow splitting long words for better line wrapping
            )
            
            # Create enhanced list style with better formatting
            list_style = ParagraphStyle(
                'CustomList',
                parent=styles['Normal'],
                fontName=main_font,
                fontSize=14,  # Increased font size
                leading=22,   # Increased leading for better line spacing
                spaceAfter=12,  # Increased spacing after list item
                spaceBefore=6,  # Added spacing before list item
                leftIndent=35,  # Increased left indent
                alignment=TA_LEFT,
                textColor=HexColor('#2C3E50'),
                wordWrap='LTR',     # Left-to-right word wrapping for better Unicode support
                encoding='utf-8',   # Explicitly set UTF-8 encoding
                allowWidows=0,      # Prevent widows
                allowOrphans=0,      # Prevent orphans
                backColor=HexColor('#FFFFFF'),
                firstLineIndent=0,
                borderWidth=0.3,
                borderColor=HexColor('#ECF0F1'),
                borderPadding=3,
                wordBreak='normal',  # Normal word breaking for Unicode characters
                splitLongWords=True,  # Allow splitting long words for better line wrapping
            )
            
            # Create enhanced bold style with better visual appeal
            bold_style = ParagraphStyle(
                'CustomBold',
                parent=normal_style,
                fontName=bold_font,
                fontSize=15,  # Slightly larger font for emphasis
                leading=24,   # Increased leading for better spacing
                textColor=HexColor('#1A237E'),  # Deeper blue for better visibility
                wordWrap='LTR',
                encoding='utf-8',
                borderWidth=0.5,
                borderColor=HexColor('#E8EAF6'),  # Light blue border
                borderPadding=4,
                backColor=HexColor('#F5F7FF'),   # Light blue background for emphasis
                spaceAfter=16,
                spaceBefore=8,
                allowWidows=0,
                allowOrphans=0,
                borderRadius=3,  # Slight rounding for modern look
                wordBreak='normal',  # Normal word breaking for Unicode characters
                splitLongWords=True,  # Allow splitting long words for better line wrapping
            )
            
            # Create enhanced italic style with better visual appeal
            italic_style = ParagraphStyle(
                'CustomItalic',
                parent=normal_style,
                fontName='Times-Italic' if 'Times' in main_font else main_font,
                fontSize=14,
                leading=22,
                textColor=HexColor('#455A64'),  # Dark gray for subtle emphasis
                wordWrap='LTR',
                encoding='utf-8',
                borderWidth=0.3,
                borderColor=HexColor('#ECEFF1'),  # Very light gray border
                borderPadding=3,
                backColor=HexColor('#FAFAFA'),   # Very light gray background
                spaceAfter=14,
                spaceBefore=6,
                allowWidows=0,
                allowOrphans=0,
                firstLineIndent=5,  # Small indent for italic text
                leftIndent=5,
                rightIndent=5,
                wordBreak='normal',  # Normal word breaking for Unicode characters
                splitLongWords=True,  # Allow splitting long words for better line wrapping
            )
            
            # Create enhanced heading styles with better visual appeal
            heading1_style = ParagraphStyle(
                'CustomHeading1',
                parent=styles['Heading1'],
                fontName=bold_font,
                fontSize=26,  # Increased font size
                leading=34,   # Increased leading for better spacing
                spaceAfter=28,  # Increased spacing after heading
                spaceBefore=35,  # Increased spacing before heading
                alignment=TA_LEFT,
                textColor=HexColor('#1976D2'),  # Vibrant blue for headings
                backColor=HexColor('#E3F2FD'),  # Light blue background
                encoding='utf-8',   # Explicitly set UTF-8 encoding
                wordWrap='LTR',     # Left-to-right word wrapping for better Unicode support
                allowWidows=0,      # Prevent widows
                allowOrphans=0,      # Prevent orphans
                borderColor=HexColor('#64B5F6'),  # Medium blue border
                borderWidth=1.5,
                borderPadding=15,  # Increased padding
                borderRadius=6,    # Rounded corners
                shadowColor=HexColor('#BBDEFB'),  # Light blue shadow
                shadowOffset=1.5,
                wordBreak='normal',  # Normal word breaking for Unicode characters
                splitLongWords=True,  # Allow splitting long words for better line wrapping
            )
            
            heading2_style = ParagraphStyle(
                'CustomHeading2',
                parent=styles['Heading2'],
                fontName=bold_font,
                fontSize=22,  # Increased font size
                leading=30,   # Increased leading for better spacing
                spaceAfter=24,  # Increased spacing after heading
                spaceBefore=28,  # Increased spacing before heading
                alignment=TA_LEFT,
                textColor=HexColor('#388E3C'),  # Green for subheadings
                backColor=HexColor('#E8F5E9'),  # Light green background
                encoding='utf-8',   # Explicitly set UTF-8 encoding
                wordWrap='LTR',     # Left-to-right word wrapping for better Unicode support
                allowWidows=0,      # Prevent widows
                allowOrphans=0,      # Prevent orphans
                borderColor=HexColor('#81C784'),  # Medium green border
                borderWidth=1.2,
                borderPadding=12,  # Increased padding
                borderRadius=5,    # Rounded corners
                shadowColor=HexColor('#A5D6A7'),  # Light green shadow
                shadowOffset=1.2,
                wordBreak='normal',  # Normal word breaking for Unicode characters
                splitLongWords=True,  # Allow splitting long words for better line wrapping
            )
            
            title_style = ParagraphStyle(
                'CustomTitle',
                parent=styles['Title'],
                fontName=bold_font,
                fontSize=36,       # Larger title font
                leading=44,        # Increased leading for better spacing
                spaceAfter=40,     # Increased spacing after title
                alignment=TA_CENTER,
                textColor=HexColor('#0D47A1'),  # Deep blue for title
                backColor=HexColor('#FFFFFF'),  # White background
                encoding='utf-8',   # Explicitly set UTF-8 encoding
                wordWrap='LTR',     # Left-to-right word wrapping
                allowWidows=0,      # Prevent widows
                allowOrphans=0,     # Prevent orphans
                borderColor=HexColor('#1976D2'),  # Blue border
                borderWidth=2.5,
                borderPadding=25,   # Increased padding
                borderRadius=10,    # More rounded corners
                shadowColor=HexColor('#64B5F6'),  # Blue shadow
                shadowOffset=2.5,
                wordBreak='normal',  # Normal word breaking for Unicode characters
                splitLongWords=True,  # Allow splitting long words for better line wrapping
            )
            
            # Parse the content to extract sections
            sections = self._parse_pdf_content(content)
            
            # Create story for PDF document
            story = []
            
            # Select a theme based on the topic
            theme_colors = self._select_color_scheme_by_topic(topic, "pdf")  # Use topic-based theme selection
            
            # Add cover page with awesome styling
            if sections and len(sections) > 0:
                self._add_cover_page(story, sections[0]['title'], topic, theme_colors)
            
            # Add table of contents placeholder
            self._add_table_of_contents_placeholder(story, theme_colors)
            
            # Add content sections with enhanced styling
            for i, section in enumerate(sections):
                self._add_content_section(story, section, {
                    'Title': title_style,
                    'Heading1': heading1_style,
                    'Heading2': heading2_style,
                    'Normal': normal_style,
                    'Bullet': bullet_style,
                    'Bold': bold_style,
                    'Italic': italic_style
                }, theme_colors, i == 0)
            
            # Add decorative footer
            self._create_decorative_elements(story, theme_colors, 'footer')
            
            # Build PDF document with UTF-8 encoding and page numbers/headers
            doc.build(story,
                     onFirstPage=lambda canvas, doc: self._add_page_header_footer(canvas, doc, filename, True),
                     onLaterPages=lambda canvas, doc: self._add_page_header_footer(canvas, doc, filename, False))
            pdf_data = buffer.getvalue()
            buffer.close()

            # Write PDF data to temporary file
            with open(tmp_path, 'wb') as f:
                f.write(pdf_data)
                
        except Exception as e:
            logger.error(f"Error creating PDF document: {e}")
            raise
    
    def _parse_pdf_content(self, content):
        """Parse the PDF content into sections with better structure"""
        sections = []
        lines = content.strip().split('\n')
        
        current_section = None
        in_list = False
        
        for line in lines:
            line = line.strip()
            
            # Skip empty lines
            if not line:
                continue
            
            # Check for main title (#)
            if line.startswith('# ') and not line.startswith('##'):
                # Save previous section if exists
                if current_section:
                    sections.append(current_section)
                
                # Start new section
                current_section = {
                    'title': line[2:],  # Remove '# ' prefix
                    'level': 1,
                    'content': []
                }
                in_list = False
                continue
            
            # Check for section headers (##)
            if line.startswith('## '):
                # Save previous section if exists
                if current_section:
                    sections.append(current_section)
                
                # Start new section
                current_section = {
                    'title': line[3:],  # Remove '## ' prefix
                    'level': 2,
                    'content': []
                }
                in_list = False
                continue
            
            # Check for subsection headers (###)
            if line.startswith('### '):
                # Save previous section if exists
                if current_section:
                    sections.append(current_section)
                
                # Start new section
                current_section = {
                    'title': line[4:],  # Remove '### ' prefix
                    'level': 3,
                    'content': []
                }
                in_list = False
                continue
            
            # Handle list items
            if line.startswith('- ') or line.startswith('* ') or (line[0].isdigit() and len(line) > 1 and line[1] == '.'):
                if current_section:
                    # Add list marker to distinguish from regular paragraphs
                    current_section['content'].append(f"LIST_ITEM:{line}")
                in_list = True
                continue
            
            # Handle regular paragraphs
            if current_section:
                current_section['content'].append(line)
            in_list = False
        
        # Add the last section
        if current_section:
            sections.append(current_section)
        
        # If no sections were parsed, create a default structure
        if not sections:
            sections = [
                {
                    'title': 'Professional Document',
                    'level': 1,
                    'content': [content[:100] + "..." if len(content) > 100 else content]
                }
            ]
        
        return sections
    
    def _add_content_section(self, story, section, styles, colors, is_first=False):
        """Add a content section to the PDF story with appropriate styling"""
        # Add section header with appropriate style based on level
        if section['level'] == 1:
            header_style = styles['Title']
        elif section['level'] == 2:
            header_style = styles['Heading1']
        else:  # level 3
            header_style = styles['Heading2']
        
        # Add header
        story.append(Paragraph(section['title'], header_style))
        story.append(Spacer(1, 15))  # Increased spacing
        
        # Add decorative divider for sections
        if section['level'] <= 2:  # Only for main sections
            self._create_decorative_elements(story, colors, 'divider')
        
        # Add content
        for item in section['content']:
            if item.startswith("LIST_ITEM:"):
                # Handle list items
                list_item = item[10:]  # Remove LIST_ITEM: prefix
                # Process formatting in list items
                formatted_item = self._process_text_formatting(list_item, styles)
                story.append(Paragraph(formatted_item, styles.get('CustomList', styles['Bullet'])))
            else:
                # Handle regular paragraphs with special styling for educational content
                if "💡" in item or "🔑" in item or "📘" in item:
                    # Create a special style for insights with enhanced visual appeal
                    insight_style = ParagraphStyle(
                        'InsightStyle',
                        parent=styles['Normal'],
                        textColor=colors.get('insight', colors['primary']),
                        fontName=styles['Normal'].fontName,
                        fontSize=15,
                        leading=24,  # Increased leading
                        spaceAfter=20,  # Increased spacing
                        spaceBefore=12,  # Added spacing before
                        wordWrap='LTR',
                        encoding='utf-8',
                        backColor=HexColor('#F1F8E9'),  # Light green background
                        borderColor=HexColor('#7CB342'),  # Green border
                        borderWidth=1.5,
                        borderPadding=15,  # Increased padding
                        leftIndent=20,
                        rightIndent=20,
                        borderRadius=6,  # Rounded corners
                        shadowColor=HexColor('#AED581'),  # Light green shadow
                        shadowOffset=1.2
                    )
                    # Process formatting in insight content
                    formatted_item = self._process_text_formatting(item, styles)
                    story.append(Paragraph(formatted_item, insight_style))
                elif "🎓" in item or "📚" in item or "📖" in item:
                    # Create a special style for educational content with enhanced visual appeal
                    education_style = ParagraphStyle(
                        'EducationStyle',
                        parent=styles['Normal'],
                        textColor=colors.get('education', colors['primary']),
                        fontName=styles['Normal'].fontName,
                        fontSize=15,
                        leading=24,  # Increased leading
                        spaceAfter=20,  # Increased spacing
                        spaceBefore=12,  # Added spacing before
                        wordWrap='LTR',
                        encoding='utf-8',
                        backColor=HexColor('#E3F2FD'),  # Light blue background
                        borderColor=HexColor('#1976D2'),  # Blue border
                        borderWidth=1.5,
                        borderPadding=15,  # Increased padding
                        leftIndent=20,
                        rightIndent=20,
                        borderRadius=6,  # Rounded corners
                        shadowColor=HexColor('#64B5F6'),  # Light blue shadow
                        shadowOffset=1.2
                    )
                    # Process formatting in educational content
                    formatted_item = self._process_text_formatting(item, styles)
                    story.append(Paragraph(formatted_item, education_style))
                elif "<quote>" in item:
                    # Create a special style for quotes with enhanced visual appeal
                    quote_style = ParagraphStyle(
                        'QuoteStyle',
                        parent=styles['Normal'],
                        textColor=colors.get('quote', colors['primary']),
                        fontName=styles['Normal'].fontName,
                        fontSize=15,
                        leading=24,  # Increased leading
                        spaceAfter=20,  # Increased spacing
                        spaceBefore=12,  # Added spacing before
                        wordWrap='LTR',
                        encoding='utf-8',
                        backColor=HexColor('#FFF3E0'),  # Light orange background
                        borderColor=HexColor('#EF6C00'),  # Orange border
                        borderWidth=1.8,
                        borderPadding=20,  # Increased padding
                        firstLineIndent=35,  # Increased indent
                        leftIndent=25,
                        rightIndent=25,
                        borderRadius=7,  # More rounded corners
                        shadowColor=HexColor('#FFCC80'),  # Light orange shadow
                        shadowOffset=1.5
                    )
                    # Remove quote markers for cleaner display
                    clean_item = item.replace("<quote>", "").replace("</quote>", "")
                    # Process formatting in quote content
                    formatted_item = self._process_text_formatting(clean_item, styles)
                    story.append(Paragraph(formatted_item, quote_style))
                elif "```" in item:
                    # Create a special style for code blocks with enhanced visual appeal
                    code_style = ParagraphStyle(
                        'CodeStyle',
                        parent=styles['Normal'],
                        textColor=colors.get('code', colors['primary']),
                        fontName='Courier',  # Monospace font for code
                        fontSize=13,
                        leading=20,  # Increased leading
                        spaceAfter=20,  # Increased spacing
                        spaceBefore=12,  # Added spacing before
                        wordWrap='LTR',
                        encoding='utf-8',
                        backColor=HexColor('#F5F5F5'),  # Light gray background
                        borderColor=HexColor('#757575'),  # Gray border
                        borderWidth=2,
                        borderPadding=20,  # Increased padding
                        leftIndent=30,
                        rightIndent=30,
                        borderRadius=5,  # Rounded corners
                        shadowColor=HexColor('#BDBDBD'),  # Gray shadow
                        shadowOffset=1.3
                    )
                    # Remove code markers for cleaner display
                    clean_item = item.replace("```", "")
                    # Process formatting in code content
                    formatted_item = self._process_text_formatting(clean_item, styles)
                    story.append(Paragraph(formatted_item, code_style))
                else:
                    # Handle regular paragraphs with formatting processing
                    formatted_item = self._process_text_formatting(item, styles)
                    story.append(Paragraph(formatted_item, styles['Normal']))
        
        # Add spacing after section
        story.append(Spacer(1, 20))  # Increased spacing
    
    def _process_text_formatting(self, text, styles):
        """Process text to add bold, italic, and other formatting support with emoji preservation"""
        # Handle emojis first to preserve them through formatting
        # Emojis should work with our Unicode font support
        
        # Handle bold text (enclosed in **) - process all occurrences at once
        # We need to be careful not to process ** that are part of *** or more
        parts = text.split('**')
        processed_parts = []
        for i, part in enumerate(parts):
            if i % 2 == 1 and part:  # Bold parts (odd indices) that are not empty
                # Apply bold style using ReportLab tags
                processed_parts.append(f"<b>{part}</b>")
            else:
                processed_parts.append(part)
        text = ''.join(processed_parts)
        
        # Handle underline text (enclosed in __) - process all occurrences at once
        parts = text.split('__')
        processed_parts = []
        for i, part in enumerate(parts):
            if i % 2 == 1 and part:  # Underline parts (odd indices) that are not empty
                # Apply underline style using ReportLab tags
                processed_parts.append(f"<u>{part}</u>")
            else:
                processed_parts.append(part)
        text = ''.join(processed_parts)
        
        # Handle italic text (enclosed in *) - process all occurrences at once
        # We need to be careful to avoid processing * that are part of ** markers or apostrophes
        # Only process single asterisks that are not part of double asterisks or apostrophes
        # Use regex to properly identify italic markers vs apostrophes
        import re
        
        # First, temporarily replace apostrophes to avoid confusion
        # Handle common contractions
        text = re.sub(r"\bdon't\b", "DONT_REPLACE", text)
        text = re.sub(r"\bcan't\b", "CANT_REPLACE", text)
        text = re.sub(r"\bwon't\b", "WONT_REPLACE", text)
        text = re.sub(r"\bshouldn't\b", "SHOULDNT_REPLACE", text)
        text = re.sub(r"\bcouldn't\b", "COULDNT_REPLACE", text)
        text = re.sub(r"\baren't\b", "ARENT_REPLACE", text)
        text = re.sub(r"\bisn't\b", "ISNT_REPLACE", text)
        text = re.sub(r"\bhasn't\b", "HASNT_REPLACE", text)
        text = re.sub(r"\bhaven't\b", "HAVENT_REPLACE", text)
        text = re.sub(r"\bhadn't\b", "HADNT_REPLACE", text)
        text = re.sub(r"\bdoesn't\b", "DOESNT_REPLACE", text)
        text = re.sub(r"\bdidn't\b", "DIDNT_REPLACE", text)
        text = re.sub(r"\bwouldn't\b", "WOULDNT_REPLACE", text)
        text = re.sub(r"\bmustn't\b", "MUSTNT_REPLACE", text)
        text = re.sub(r"\bshan't\b", "SHANT_REPLACE", text)
        text = re.sub(r"\bneedn't\b", "NEEDNT_REPLACE", text)
        text = re.sub(r"\blet's\b", "LETS_REPLACE", text)
        text = re.sub(r"\byou're\b", "YOURE_REPLACE", text)
        text = re.sub(r"\bwe're\b", "WERE_REPLACE", text)
        text = re.sub(r"\bthey're\b", "THEYRE_REPLACE", text)
        text = re.sub(r"\bit's\b", "ITS_REPLACE", text)
        text = re.sub(r"\bhe's\b", "HES_REPLACE", text)
        text = re.sub(r"\bshe's\b", "SHES_REPLACE", text)
        text = re.sub(r"\bthat's\b", "THATS_REPLACE", text)
        text = re.sub(r"\bwhat's\b", "WHATS_REPLACE", text)
        text = re.sub(r"\bwhere's\b", "WHERES_REPLACE", text)
        text = re.sub(r"\bwho's\b", "WHOS_REPLACE", text)
        text = re.sub(r"\bhow's\b", "HOWS_REPLACE", text)
        text = re.sub(r"\bI'm\b", "IM_REPLACE", text)
        text = re.sub(r"\bI've\b", "IVE_REPLACE", text)
        text = re.sub(r"\bI'll\b", "ILL_REPLACE", text)
        text = re.sub(r"\bI'd\b", "ID_REPLACE", text)
        text = re.sub(r"\byou've\b", "YOUVE_REPLACE", text)
        text = re.sub(r"\byou'll\b", "YOULL_REPLACE", text)
        text = re.sub(r"\byou'd\b", "YOUD_REPLACE", text)
        text = re.sub(r"\bwe've\b", "WEVE_REPLACE", text)
        text = re.sub(r"\bwe'll\b", "WELL_REPLACE", text)
        text = re.sub(r"\bwe'd\b", "WED_REPLACE", text)
        text = re.sub(r"\bthey've\b", "THEYVE_REPLACE", text)
        text = re.sub(r"\bthey'll\b", "THEYLL_REPLACE", text)
        text = re.sub(r"\bthey'd\b", "THEYD_REPLACE", text)
        text = re.sub(r"\bhe've\b", "HEVE_REPLACE", text)
        text = re.sub(r"\bhe'll\b", "HELL_REPLACE", text)
        text = re.sub(r"\bhe'd\b", "HED_REPLACE", text)
        text = re.sub(r"\bshe've\b", "SHEVE_REPLACE", text)
        text = re.sub(r"\bshe'll\b", "SHELL_REPLACE", text)
        text = re.sub(r"\bshe'd\b", "SHED_REPLACE", text)
        text = re.sub(r"\bit've\b", "ITVE_REPLACE", text)
        text = re.sub(r"\bit'll\b", "ITLL_REPLACE", text)
        text = re.sub(r"\bit'd\b", "ITD_REPLACE", text)
        text = re.sub(r"\bthat've\b", "THATVE_REPLACE", text)
        text = re.sub(r"\bthat'll\b", "THATLL_REPLACE", text)
        text = re.sub(r"\bthat'd\b", "THATD_REPLACE", text)
        text = re.sub(r"\bwho've\b", "WHOVE_REPLACE", text)
        text = re.sub(r"\bwho'll\b", "WHOLL_REPLACE", text)
        text = re.sub(r"\bwho'd\b", "WHOD_REPLACE", text)
        text = re.sub(r"\bwhat've\b", "WHATVE_REPLACE", text)
        text = re.sub(r"\bwhat'll\b", "WHATLL_REPLACE", text)
        text = re.sub(r"\bwhat'd\b", "WHATD_REPLACE", text)
        text = re.sub(r"\bwhere've\b", "WHEREVE_REPLACE", text)
        text = re.sub(r"\bwhere'll\b", "WHERELL_REPLACE", text)
        text = re.sub(r"\bwhere'd\b", "WHERED_REPLACE", text)
        text = re.sub(r"\bwhen've\b", "WHENVE_REPLACE", text)
        text = re.sub(r"\bwhen'll\b", "WHENLL_REPLACE", text)
        text = re.sub(r"\bwhen'd\b", "WHEND_REPLACE", text)
        text = re.sub(r"\bwhy've\b", "WHYVE_REPLACE", text)
        text = re.sub(r"\bwhy'll\b", "WHYLL_REPLACE", text)
        text = re.sub(r"\bwhy'd\b", "WHYD_REPLACE", text)
        text = re.sub(r"\bhow've\b", "HOWVE_REPLACE", text)
        text = re.sub(r"\bhow'll\b", "HOWLL_REPLACE", text)
        text = re.sub(r"\bhow'd\b", "HOWD_REPLACE", text)
        
        # Handle special Unicode characters that might be problematic
        # Replace problematic apostrophe variants with standard apostrophe
        text = text.replace("’", "'")  # Right single quotation mark
        text = text.replace("‘", "'")  # Left single quotation mark
        text = text.replace("`", "'")  # Grave accent
        text = text.replace("՚", "'")  # Armenian apostrophe
        text = text.replace("＇", "'")  # Fullwidth apostrophe
        
        # Now process italics - find *text* patterns that are not part of **text**
        # Use negative lookbehind and lookahead to avoid matching ** patterns
        def replace_italic(match):
            return f"<i>{match.group(1)}</i>"
        
        # Match *text* but not **text** or text* or *text patterns
        text = re.sub(r'(?<!\*)\*([^\*]+?)\*(?!\*)', replace_italic, text)
        
        # Restore apostrophes
        text = text.replace("DONT_REPLACE", "don't")
        text = text.replace("CANT_REPLACE", "can't")
        text = text.replace("WONT_REPLACE", "won't")
        text = text.replace("SHOULDNT_REPLACE", "shouldn't")
        text = text.replace("COULDNT_REPLACE", "couldn't")
        text = text.replace("ARENT_REPLACE", "aren't")
        text = text.replace("ISNT_REPLACE", "isn't")
        text = text.replace("HASNT_REPLACE", "hasn't")
        text = text.replace("HAVENT_REPLACE", "haven't")
        text = text.replace("HADNT_REPLACE", "hadn't")
        text = text.replace("DOESNT_REPLACE", "doesn't")
        text = text.replace("DIDNT_REPLACE", "didn't")
        text = text.replace("WOULDNT_REPLACE", "wouldn't")
        text = text.replace("MUSTNT_REPLACE", "mustn't")
        text = text.replace("SHANT_REPLACE", "shan't")
        text = text.replace("NEEDNT_REPLACE", "needn't")
        text = text.replace("LETS_REPLACE", "let's")
        text = text.replace("YOURE_REPLACE", "you're")
        text = text.replace("WERE_REPLACE", "we're")
        text = text.replace("THEYRE_REPLACE", "they're")
        text = text.replace("ITS_REPLACE", "it's")
        text = text.replace("HES_REPLACE", "he's")
        text = text.replace("SHES_REPLACE", "she's")
        text = text.replace("THATS_REPLACE", "that's")
        text = text.replace("WHATS_REPLACE", "what's")
        text = text.replace("WHERES_REPLACE", "where's")
        text = text.replace("WHOS_REPLACE", "who's")
        text = text.replace("HOWS_REPLACE", "how's")
        text = text.replace("IM_REPLACE", "I'm")
        text = text.replace("IVE_REPLACE", "I've")
        text = text.replace("ILL_REPLACE", "I'll")
        text = text.replace("ID_REPLACE", "I'd")
        text = text.replace("YOUVE_REPLACE", "you've")
        text = text.replace("YOULL_REPLACE", "you'll")
        text = text.replace("YOUD_REPLACE", "you'd")
        text = text.replace("WEVE_REPLACE", "we've")
        text = text.replace("WELL_REPLACE", "we'll")
        text = text.replace("WED_REPLACE", "we'd")
        text = text.replace("THEYVE_REPLACE", "they've")
        text = text.replace("THEYLL_REPLACE", "they'll")
        text = text.replace("THEYD_REPLACE", "they'd")
        text = text.replace("HEVE_REPLACE", "he've")
        text = text.replace("HELL_REPLACE", "he'll")
        text = text.replace("HED_REPLACE", "he'd")
        text = text.replace("SHEVE_REPLACE", "she've")
        text = text.replace("SHELL_REPLACE", "she'll")
        text = text.replace("SHED_REPLACE", "she'd")
        text = text.replace("ITVE_REPLACE", "it've")
        text = text.replace("ITLL_REPLACE", "it'll")
        text = text.replace("ITD_REPLACE", "it'd")
        text = text.replace("THATVE_REPLACE", "that've")
        text = text.replace("THATLL_REPLACE", "that'll")
        text = text.replace("THATD_REPLACE", "that'd")
        text = text.replace("WHOVE_REPLACE", "who've")
        text = text.replace("WHOLL_REPLACE", "who'll")
        text = text.replace("WHOD_REPLACE", "who'd")
        text = text.replace("WHATVE_REPLACE", "what've")
        text = text.replace("WHATLL_REPLACE", "what'll")
        text = text.replace("WHATD_REPLACE", "what'd")
        text = text.replace("WHEREVE_REPLACE", "where've")
        text = text.replace("WHERELL_REPLACE", "where'll")
        text = text.replace("WHERED_REPLACE", "where'd")
        text = text.replace("WHENVE_REPLACE", "when've")
        text = text.replace("WHENLL_REPLACE", "when'll")
        text = text.replace("WHEND_REPLACE", "when'd")
        text = text.replace("WHYVE_REPLACE", "why've")
        text = text.replace("WHYLL_REPLACE", "why'll")
        text = text.replace("WHYD_REPLACE", "why'd")
        text = text.replace("HOWVE_REPLACE", "how've")
        text = text.replace("HOWLL_REPLACE", "how'll")
        text = text.replace("HOWD_REPLACE", "how'd")
        
        # Ensure emojis are properly encoded and preserved
        # Emojis should work with our Unicode font support
        return text
    
    def _get_current_date(self):
        """Get current date in a formatted string"""
        from datetime import datetime
        return datetime.now().strftime("%B %d, %Y")
    
    def _select_color_scheme_by_topic(self, topic: str, doc_type: str = "pdf") -> Dict[str, str]:
        """Select a color scheme based on the topic and document type"""
        topic_lower = topic.lower()
        
        # Define topic-based color scheme mappings with both English and Uzbek keywords
        # Extended with more diverse keywords for better theme selection
        topic_keywords = {
            # Business/Corporate/Finance keywords (Professional theme)
            'business': 'professional',
            'corporate': 'professional',
            'finance': 'professional',
            'investment': 'professional',
            'market': 'professional',
            'economy': 'professional',
            'strategy': 'professional',
            'plan': 'professional',
            'biznes': 'professional',  # Uzbek for business
            'kompaniya': 'professional',  # Uzbek for company
            'moliya': 'professional',  # Uzbek for finance
            'investitsiya': 'professional',  # Uzbek for investment
            'bozor': 'professional',  # Uzbek for market
            'iqtisod': 'professional',  # Uzbek for economy
            'strategiya': 'professional',  # Uzbek for strategy
            'reja': 'professional',  # Uzbek for plan
            
            # Marketing/Creative/Design keywords (Creative theme)
            'marketing': 'creative',
            'creative': 'creative',
            'design': 'creative',
            'branding': 'creative',
            'advertising': 'creative',
            'campaign': 'creative',
            'promotion': 'creative',
            'dizayn': 'creative',  # Uzbek for design
            'kreativ': 'creative',  # Uzbek for creative
            'brend': 'creative',  # Uzbek for brand
            'reklama': 'creative',  # Uzbek for advertising
            'kampaniya': 'creative',  # Uzbek for campaign
            
            # Technology/Tech/Innovation keywords (Modern theme)
            'technology': 'modern',
            'tech': 'modern',
            'innovation': 'modern',
            'digital': 'modern',
            'software': 'modern',
            'programming': 'modern',
            'ai': 'modern',
            'artificial': 'modern',
            'machine': 'modern',
            'robot': 'modern',
            'internet': 'modern',
            'web': 'modern',
            'app': 'modern',
            'mobile': 'modern',
            'cloud': 'modern',
            'blockchain': 'modern',
            'crypto': 'modern',
            'virtual': 'modern',
            'texnologiya': 'modern',  # Uzbek for technology
            'innovatsiya': 'modern',  # Uzbek for innovation
            'dastur': 'modern',  # Uzbek for software
            'dasturlash': 'modern',  # Uzbek for programming
            'sun\'iy': 'modern',  # Uzbek for artificial
            'mashina': 'modern',  # Uzbek for machine
            
            # Elegant/Luxury keywords (Elegant theme)
            'elegant': 'elegant',
            'luxury': 'elegant',
            'premium': 'elegant',
            'exclusive': 'elegant',
            'high-end': 'elegant',
            'sophisticated': 'elegant',
            'hashamat': 'elegant',  # Uzbek for luxury
            'elegent': 'elegant',  # Alternative spelling
            'premium': 'elegant',  # Uzbek for premium
            'eksklyuziv': 'elegant',  # Uzbek for exclusive
            
            # Formal/Academic/Education keywords (Professional theme)
            'formal': 'professional',
            'academic': 'professional',
            'education': 'professional',
            'study': 'professional',
            'research': 'professional',
            'scholar': 'professional',
            'university': 'professional',
            'college': 'professional',
            'course': 'professional',
            'lecture': 'professional',
            'ta\'lim': 'professional',  # Uzbek for education
            'akademik': 'professional',  # Uzbek for academic
            'rasmiy': 'professional',  # Uzbek for formal
            'tadqiqot': 'professional',  # Uzbek for research
            'universitet': 'professional',  # Uzbek for university
            'kurs': 'professional',  # Uzbek for course
            
            # Scientific/Technical keywords (Modern theme)
            'science': 'modern',
            'scientific': 'modern',
            'biology': 'modern',
            'chemistry': 'modern',
            'physics': 'modern',
            'mathematics': 'modern',
            'math': 'modern',
            'engineering': 'modern',
            'biologiya': 'modern',  # Uzbek for biology
            'kimyo': 'modern',  # Uzbek for chemistry
            'fizika': 'modern',  # Uzbek for physics
            'matematika': 'modern',  # Uzbek for mathematics
            'muhandislik': 'modern',  # Uzbek for engineering
            
            # Medical/Health keywords (Professional theme)
            'medical': 'professional',
            'health': 'professional',
            'medicine': 'professional',
            'doctor': 'professional',
            'hospital': 'professional',
            'patient': 'professional',
            'therapy': 'professional',
            'treatment': 'professional',
            'salomatlik': 'professional',  # Uzbek for health
            'tibbiy': 'professional',  # Uzbek for medical
            'shifokor': 'professional',  # Uzbek for doctor
            'kasalxona': 'professional',  # Uzbek for hospital
            
            # Legal/Law keywords (Professional theme)
            'legal': 'professional',
            'law': 'professional',
            'court': 'professional',
            'justice': 'professional',
            'contract': 'professional',
            'rights': 'professional',
            'regulation': 'professional',
            'huquq': 'professional',  # Uzbek for law
            'sud': 'professional',  # Uzbek for court
            'adolat': 'professional',  # Uzbek for justice
            'shartnoma': 'professional',  # Uzbek for contract
            
            # Religious/Spiritual keywords (Elegant theme)
            'religion': 'elegant',
            'spiritual': 'elegant',
            'faith': 'elegant',
            'prayer': 'elegant',
            'worship': 'elegant',
            'bible': 'elegant',
            'quran': 'elegant',
            'allah': 'elegant',
            'prophet': 'elegant',
            'sahoba': 'elegant',
            'companion': 'elegant',
            'mosque': 'elegant',
            'church': 'elegant',
            'temple': 'elegant',
            'dua': 'elegant',  # Uzbek for prayer
            'ibodat': 'elegant',  # Uzbek for worship
            'paygamber': 'elegant',  # Uzbek for prophet
            'sahoba': 'elegant',  # Uzbek for companion
            'masjid': 'elegant',  # Uzbek for mosque
            
            # Personal Development/Success keywords (Vibrant theme)
            'success': 'vibrant',
            'motivation': 'vibrant',
            'inspiration': 'vibrant',
            'growth': 'vibrant',
            'development': 'vibrant',
            'achievement': 'vibrant',
            'goal': 'vibrant',
            'dream': 'vibrant',
            'ambition': 'vibrant',
            'muvaffaqiyat': 'vibrant',  # Uzbek for success
            'motivatsiya': 'vibrant',  # Uzbek for motivation
            'ilhom': 'vibrant',  # Uzbek for inspiration
            'rivojlanish': 'vibrant',  # Uzbek for development
            'maqsad': 'vibrant',  # Uzbek for goal
            'tush': 'vibrant',  # Uzbek for dream
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

    def _add_page_header_footer(self, canvas, doc, filename, is_first_page):
        """Add professional headers and footers with page numbers to PDF pages"""
        try:
            from datetime import datetime

            canvas.saveState()

            # Get page size
            width, height = A4

            # Set font for header/footer
            main_font, bold_font = self._get_best_unicode_font()

            if not is_first_page:
                # Add header line
                canvas.setStrokeColor(HexColor('#3498DB'))
                canvas.setLineWidth(1)
                canvas.line(50, height - 50, width - 50, height - 50)

                # Add document title in header
                canvas.setFont(main_font, 9)
                canvas.setFillColor(HexColor('#2C3E50'))
                canvas.drawString(60, height - 45, filename[:60])  # Truncate long titles

            # Add footer line
            canvas.setStrokeColor(HexColor('#3498DB'))
            canvas.setLineWidth(0.5)
            canvas.line(50, 50, width - 50, 50)

            # Add page number (centered)
            page_num = canvas.getPageNumber()
            canvas.setFont(bold_font, 9)
            canvas.setFillColor(HexColor('#2C3E50'))
            page_text = f"Page {page_num}"
            text_width = canvas.stringWidth(page_text, bold_font, 9)
            canvas.drawString((width - text_width) / 2, 35, page_text)

            # Add generation date on the right
            canvas.setFont(main_font, 8)
            canvas.setFillColor(HexColor('#7F8C8D'))
            date_text = datetime.now().strftime("%Y-%m-%d")
            date_width = canvas.stringWidth(date_text, main_font, 8)
            canvas.drawRightString(width - 60, 35, date_text)

            # Add "AQLJON" branding on the left
            canvas.setFont(bold_font, 8)
            canvas.setFillColor(HexColor('#3498DB'))
            canvas.drawString(60, 35, "AQLJON")

            canvas.restoreState()

        except Exception as e:
            logger.warning(f"Error adding page header/footer: {e}")
            # Fallback - just add simple page number
            try:
                canvas.saveState()
                canvas.setFont('Helvetica', 9)
                page_num = canvas.getPageNumber()
                canvas.drawCentredString(A4[0] / 2, 30, f"Page {page_num}")
                canvas.restoreState()
            except:
                pass  # If even fallback fails, skip headers/footers
