import time
import json
import os
from datetime import datetime, timedelta

# ─── 🧠 Enhanced Memory Management ─────────────────────────────────────────────────
class MemoryManager:
    """Manages user memory, history, and statistics"""
    
    def __init__(self, max_history=100, max_content_memory=100, max_users=2000, max_inactive_days=10):
        self.user_history = {}
        self.user_content_memory = {}
        self.user_stats = {}
        self.user_info = {}
        self.user_contact_messages = {}
        self.user_daily_activity = {}
        self.blocked_users = set()
        
        # Configuration
        self.MAX_HISTORY = max_history
        self.MAX_CONTENT_MEMORY = max_content_memory
        self.MAX_USERS_IN_MEMORY = max_users
        self.MAX_INACTIVE_DAYS = max_inactive_days
        
        # No file persistence for Heroku deployment
    
    # ─── 📊 User Statistics Tracking ─────────────────────────────────────────────────
    def track_user_activity(self, chat_id: str, activity_type: str, update=None):
        """Track user activity for statistics with daily analytics"""
        # Check memory limits before adding new users
        if chat_id not in self.user_stats:
            self.check_memory_limits()
        
        if chat_id not in self.user_stats:
            self.user_stats[chat_id] = {
                "messages": 0,
                "photos": 0,
                "voice_audio": 0,
                "documents": 0,
                "videos": 0,
                "search_queries": 0,
                "pdf_generated": 0,
                "excel_generated": 0,
                "word_generated": 0,
                "ppt_generated": 0,
                "first_interaction": time.time(),
                "last_active": time.time(),
                "total_characters": 0
            }
        
        self.user_stats[chat_id][activity_type] += 1
        self.user_stats[chat_id]["last_active"] = time.time()
        
        # Track daily activity for analytics
        today = datetime.now().strftime("%Y-%m-%d")
        if chat_id not in self.user_daily_activity:
            self.user_daily_activity[chat_id] = {}
        
        if today not in self.user_daily_activity[chat_id]:
            self.user_daily_activity[chat_id][today] = {
                "messages": 0,
                "photos": 0,
                "voice_audio": 0,
                "documents": 0,
                "videos": 0,
                "search_queries": 0,
                "pdf_generated": 0,
                "excel_generated": 0,
                "word_generated": 0,
                "ppt_generated": 0
            }
        
        self.user_daily_activity[chat_id][today][activity_type] += 1
        
        # Store user information if available
        if update and update.effective_user:
            user = update.effective_user
            
            self.user_info[chat_id] = {
                "user_id": user.id,
                "username": user.username if user.username else None,
                "first_name": user.first_name if user.first_name else None,
                "last_name": user.last_name if user.last_name else None,
                "is_bot": user.is_bot if hasattr(user, 'is_bot') else False,
                "last_seen": time.time()
            }
    
    def track_document_generation(self, chat_id: str, doc_type: str, update=None):
        """Track document generation statistics"""
        # Map document types to stats keys
        doc_type_map = {
            "pdf": "pdf_generated",
            "excel": "excel_generated",
            "word": "word_generated",
            "powerpoint": "ppt_generated"
        }
        
        stat_key = doc_type_map.get(doc_type.lower(), None)
        if stat_key:
            self.track_user_activity(chat_id, stat_key, update)
    
    def get_user_activity_period(self, chat_id: str, days: int) -> dict:
        """Get user activity for the last N days"""
        activity = {
            "messages": 0,
            "photos": 0,
            "voice_audio": 0,
            "documents": 0,
            "videos": 0,
            "search_queries": 0
        }
        
        if chat_id not in self.user_daily_activity:
            return activity
        
        # Calculate date range
        today = datetime.now()
        for i in range(days):
            check_date = (today - timedelta(days=i)).strftime("%Y-%m-%d")
            if check_date in self.user_daily_activity[chat_id]:
                day_activity = self.user_daily_activity[chat_id][check_date]
                for key in activity.keys():
                    activity[key] += day_activity.get(key, 0)
        
        return activity
    
    # ─── 🧠 Memory Management Functions ─────────────────────────────────────────────────
    def store_content_memory(self, chat_id: str, content_type: str, content_summary: str, file_name: str | None = None, full_content: str | None = None):
        """Store document/audio content for future reference with complete details"""
        if chat_id not in self.user_content_memory:
            self.user_content_memory[chat_id] = []
        
        # Store both summary and full content for better context
        memory_item = {
            "type": content_type,
            "summary": content_summary,
            "full_content": full_content if full_content else content_summary,  # Store full content if available
            "file_name": file_name if file_name else "unknown",
            "timestamp": "just now",
            "stored_at": time.time()  # Add timestamp for better tracking
        }
        
        self.user_content_memory[chat_id].append(memory_item)
        
        # Keep more content memories (increase from 30 to 50 for better context)
        if len(self.user_content_memory[chat_id]) > 50:
            self.user_content_memory[chat_id] = self.user_content_memory[chat_id][-50:]
    
    def get_content_context(self, chat_id: str) -> str:
        """Get content memory context for AI with complete details"""
        if chat_id not in self.user_content_memory or not self.user_content_memory[chat_id]:
            return ""
        
        context_parts = []
        # Use more content items for better context (last 30 items)
        recent_content = self.user_content_memory[chat_id][-30:]
        
        for item in recent_content:
            if item["type"] == "document":
                # Include both file name and full content for documents
                context_parts.append(f"Document '{item['file_name']}': {item['full_content']}")
            elif item["type"] == "audio":
                context_parts.append(f"Audio message: {item['full_content']}")
            elif item["type"] == "photo":
                context_parts.append(f"Photo '{item['file_name']}': {item['full_content']}")
            elif item["type"] == "video":
                context_parts.append(f"Video '{item['file_name']}': {item['full_content']}")
        
        if context_parts:
            return "\n\nPrevious content user shared (use this context when answering related questions - you have full details of all content):\n" + "\n".join(context_parts)
        return ""
    
    def get_specific_content(self, chat_id: str, content_type: str | None = None) -> list:
        """Get specific content items for detailed queries"""
        if chat_id not in self.user_content_memory:
            return []
        
        if content_type:
            # Filter by content type if specified
            return [item for item in self.user_content_memory[chat_id] if item["type"] == content_type]
        else:
            # Return all content
            return self.user_content_memory[chat_id]
    
    def cleanup_inactive_users(self):
        """Remove inactive users to prevent memory overflow"""
        current_time = time.time()
        inactive_threshold = current_time - (self.MAX_INACTIVE_DAYS * 24 * 60 * 60)
        
        # Find inactive users (excluding blocked users)
        inactive_users = []
        for chat_id, stats in self.user_stats.items():
            # Skip blocked users - they should never be cleaned up
            if chat_id in self.blocked_users:
                continue
                
            # Convert "now" to actual timestamp for comparison
            if stats.get("last_active") == "now":
                stats["last_active"] = current_time
            
            last_active = stats.get("last_active", 0)
            if isinstance(last_active, str):
                last_active = current_time
            
            if last_active < inactive_threshold:
                inactive_users.append(chat_id)
        
        # Remove inactive users
        removed_count = 0
        for chat_id in inactive_users:
            if chat_id in self.user_history:
                del self.user_history[chat_id]
            if chat_id in self.user_content_memory:
                del self.user_content_memory[chat_id]
            if chat_id in self.user_stats:
                del self.user_stats[chat_id]
            if chat_id in self.user_info:
                del self.user_info[chat_id]
            removed_count += 1
        
        if removed_count > 0:
            print(f"Cleaned up {removed_count} inactive users")
        
        return removed_count
    
    def check_memory_limits(self):
        """Check and enforce memory limits"""
        total_users = len(self.user_history)
        
        if total_users > self.MAX_USERS_IN_MEMORY:
            print(f"User limit exceeded: {total_users}/{self.MAX_USERS_IN_MEMORY}")
            cleanup_count = self.cleanup_inactive_users()
            
            # If still over limit, remove oldest users (excluding blocked users)
            if len(self.user_history) > self.MAX_USERS_IN_MEMORY:
                # Sort by last activity and remove oldest
                user_activity = []
                for chat_id, stats in self.user_stats.items():
                    # Skip blocked users
                    if chat_id in self.blocked_users:
                        continue
                        
                    last_active = stats.get("last_active", 0)
                    if isinstance(last_active, str):
                        last_active = 0
                    user_activity.append((chat_id, last_active))
                
                user_activity.sort(key=lambda x: x[1])  # Sort by last_active (oldest first)
                
                # Remove oldest users until under limit
                to_remove = len(self.user_history) - self.MAX_USERS_IN_MEMORY + 100  # Remove extra for buffer
                for i in range(min(to_remove, len(user_activity))):
                    chat_id = user_activity[i][0]
                    if chat_id in self.user_history:
                        del self.user_history[chat_id]
                    if chat_id in self.user_content_memory:
                        del self.user_content_memory[chat_id]
                    if chat_id in self.user_stats:
                        del self.user_stats[chat_id]
                    if chat_id in self.user_info:
                        del self.user_info[chat_id]
                
                print(f"Removed {to_remove} oldest users to maintain memory limits")
        
    # ─── 🧠 Conversation History Management ─────────────────────────────────────────────────
    def add_to_history(self, chat_id: str, role: str, content: str):
        """Add message to user conversation history"""
        history = self.user_history.setdefault(chat_id, [])
        history.append({"role": role, "content": content})
        # Keep history within limits
        self.user_history[chat_id] = history[-self.MAX_HISTORY * 2:]
    
    def get_history(self, chat_id: str):
        """Get user conversation history"""
        return self.user_history.get(chat_id, [])
    
    def clear_history(self, chat_id: str):
        """Clear user conversation history"""
        if chat_id in self.user_history:
            self.user_history[chat_id] = []
    
    # ─── 🚫 Blocking Management (No Persistence for Heroku) ─────────────────────────
    def block_user(self, chat_id: str):
        """Mark user as blocked"""
        self.blocked_users.add(chat_id)
        # No file persistence for Heroku deployment
    
    def unblock_user(self, chat_id: str):
        """Unmark user as blocked"""
        if chat_id in self.blocked_users:
            self.blocked_users.remove(chat_id)
        # No file persistence for Heroku deployment
    
    def is_blocked(self, chat_id: str) -> bool:
        """Check if user is blocked"""
        return chat_id in self.blocked_users