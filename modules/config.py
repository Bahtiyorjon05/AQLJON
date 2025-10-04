import os
from dotenv import load_dotenv

# ─── 🔐 Load Environment Variables ─────────────────────────────
load_dotenv()

class Config:
    """Configuration class for the AQLJON bot"""
    
    # Telegram Bot Configuration
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    ADMIN_ID = os.getenv("ADMIN_ID")
    
    # AI Configuration
    GEMINI_KEY = os.getenv("GEMINI_API_KEY")
    SERPER_KEY = os.getenv("SERPER_API_KEY")
    
    # Memory Management
    MAX_HISTORY = 100
    MAX_CONTENT_MEMORY = 150
    MAX_USERS_IN_MEMORY = 2000
    MAX_INACTIVE_DAYS = 15  # Changed from 10 to 15 days
    
    # File Processing
    MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB limit
    
    # Timeouts
    DOWNLOAD_TIMEOUT = 90
    PROCESSING_TIMEOUT = 240  # Increased for better media processing
    NETWORK_TIMEOUT = 45
    
    @classmethod
    def validate(cls):
        """Validate required configuration"""
        if not cls.TELEGRAM_TOKEN:
            raise ValueError("TELEGRAM_BOT_TOKEN environment variable not set")
        if not cls.GEMINI_KEY:
            raise ValueError("GEMINI_API_KEY environment variable not set")
        return True