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
    # GEMINI_API_KEYS accepts a comma-separated pool of free-tier keys that are
    # rotated when one runs out of quota. GEMINI_API_KEY stays supported as a
    # single-key shorthand, and both may be set together.
    GEMINI_KEYS = [
        key.strip()
        for key in (
            (os.getenv("GEMINI_API_KEY") or "") + "," + (os.getenv("GEMINI_API_KEYS") or "")
        ).split(",")
        if key.strip()
    ]
    # De-duplicated while preserving order, so a key listed in both vars is
    # not counted twice in the rotation.
    GEMINI_KEYS = list(dict.fromkeys(GEMINI_KEYS))
    GEMINI_KEY = GEMINI_KEYS[0] if GEMINI_KEYS else None
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    GEMINI_MODEL_FALLBACK = os.getenv("GEMINI_MODEL_FALLBACK", "gemini-2.5-flash")
    SERPER_KEY = os.getenv("SERPER_API_KEY")
    
    # Memory Management
    MAX_HISTORY = 100
    MAX_CONTENT_MEMORY = 150
    MAX_USERS_IN_MEMORY = 2000
    MAX_INACTIVE_DAYS = 15  # Back to 15 days for proper cleanup
    
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
        if not cls.GEMINI_KEYS:
            raise ValueError("GEMINI_API_KEY (or GEMINI_API_KEYS) environment variable not set")
        return True
