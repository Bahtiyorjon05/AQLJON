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
        # Validate input
        if not chat_id or not isinstance(chat_id, str):
            return
        
        try:
            # Check memory limits before adding new users (but avoid during cleanup)
            if chat_id not in self.user_stats and not hasattr(self, '_in_cleanup'):
                self.check_memory_limits()
        
            # Initialize user stats ONLY if they don't exist (never reset existing stats)
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
            
            # Increment activity counter - safely handle missing keys
            if activity_type in self.user_stats[chat_id]:
                self.user_stats[chat_id][activity_type] += 1
            else:
                # If the activity type doesn't exist in stats, add it
                self.user_stats[chat_id][activity_type] = 1
            
            # Update last active time
            self.user_stats[chat_id]["last_active"] = time.time()
            
            # Ensure user is also in user_info if update is provided
            if update and update.effective_user:
                user = update.effective_user
                # Update user info if it doesn't exist OR update existing info
                self.user_info[chat_id] = {
                    "user_id": user.id,
                    "username": user.username if user.username else None,
                    "first_name": user.first_name if user.first_name else None,
                    "last_name": user.last_name if user.last_name else None,
                    "is_bot": user.is_bot if hasattr(user, 'is_bot') else False,
                    "last_seen": time.time()
                }
            
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
            
            # Safely increment daily activity
            if activity_type in self.user_daily_activity[chat_id][today]:
                self.user_daily_activity[chat_id][today][activity_type] += 1
            else:
                self.user_daily_activity[chat_id][today][activity_type] = 1
        except Exception as e:
            # Log error but don't crash - statistics are not critical
            print(f"Error tracking user activity for {chat_id}: {e}")
    
    def track_document_generation(self, chat_id: str, doc_type: str, update=None):
        """Track document generation statistics"""
        try:
            if not chat_id or not isinstance(chat_id, str):
                return
            
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
        except Exception as e:
            print(f"Error tracking document generation for {chat_id}: {e}")
    
    def get_user_activity_period(self, chat_id: str, days: int) -> dict:
        """Get user activity for the last N days"""
        try:
            if not chat_id or not isinstance(chat_id, str):
                return {
                    "messages": 0,
                    "photos": 0,
                    "voice_audio": 0,
                    "documents": 0,
                    "videos": 0,
                    "search_queries": 0
                }
            
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
        except Exception as e:
            print(f"Error getting user activity period for {chat_id}: {e}")
            return {
                "messages": 0,
                "photos": 0,
                "voice_audio": 0,
                "documents": 0,
                "videos": 0,
                "search_queries": 0
            }
    
    def cleanup_old_daily_activity(self, max_days: int = 30):
        """Clean up daily activity data older than max_days to prevent memory bloat"""
        try:
            cutoff_date = (datetime.now() - timedelta(days=max_days)).strftime("%Y-%m-%d")
            cleaned_count = 0
            
            # Create a copy to avoid RuntimeError during iteration
            for chat_id in list(self.user_daily_activity.keys()):
                if chat_id in self.user_daily_activity:
                    # Remove old dates
                    dates_to_remove = [date for date in self.user_daily_activity[chat_id].keys() if date < cutoff_date]
                    for date in dates_to_remove:
                        try:
                            del self.user_daily_activity[chat_id][date]
                            cleaned_count += 1
                        except KeyError:
                            pass  # Already deleted, skip
                    
                    # Remove empty user entries
                    if not self.user_daily_activity[chat_id]:
                        try:
                            del self.user_daily_activity[chat_id]
                        except KeyError:
                            pass  # Already deleted, skip
            
            if cleaned_count > 0:
                print(f"Cleaned up {cleaned_count} old daily activity records")
            
            return cleaned_count
        except Exception as e:
            print(f"Error in cleanup_old_daily_activity: {e}")
            return 0
    
    # ─── 🧠 Memory Management Functions ─────────────────────────────────────────────────
    def store_content_memory(self, chat_id: str, content_type: str, content_summary: str, file_name: str | None = None, full_content: str | None = None):
        """Store document/audio content for future reference with complete details"""
        try:
            if not chat_id or not isinstance(chat_id, str):
                return
            
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
        except Exception as e:
            print(f"Error storing content memory for {chat_id}: {e}")
    
    def get_content_context(self, chat_id: str) -> str:
        """Get content memory context for AI with complete details"""
        try:
            if not chat_id or not isinstance(chat_id, str):
                return ""
            
            if chat_id not in self.user_content_memory or not self.user_content_memory[chat_id]:
                return ""
            
            context_parts = []
            # Use more content items for better context (last 30 items)
            recent_content = self.user_content_memory[chat_id][-30:]
            
            for item in recent_content:
                item_type = item.get("type", "")
                file_name = item.get("file_name", "unknown")
                full_content = item.get("full_content", "")
                
                if item_type == "document":
                    # Include both file name and full content for documents
                    context_parts.append(f"Document '{file_name}': {full_content}")
                elif item_type == "audio":
                    context_parts.append(f"Audio message: {full_content}")
                elif item_type == "photo":
                    context_parts.append(f"Photo '{file_name}': {full_content}")
                elif item_type == "video":
                    context_parts.append(f"Video '{file_name}': {full_content}")
            
            if context_parts:
                return "\n\nPrevious content user shared (use this context when answering related questions - you have full details of all content):\n" + "\n".join(context_parts)
            return ""
        except Exception as e:
            print(f"Error getting content context for {chat_id}: {e}")
            return ""
    
    def get_specific_content(self, chat_id: str, content_type: str | None = None) -> list:
        """Get specific content items for detailed queries"""
        try:
            if not chat_id or not isinstance(chat_id, str):
                return []
            
            if chat_id not in self.user_content_memory:
                return []
            
            if content_type:
                # Filter by content type if specified
                return [item for item in self.user_content_memory[chat_id] if item.get("type") == content_type]
            else:
                # Return all content
                return self.user_content_memory[chat_id]
        except Exception as e:
            print(f"Error getting specific content for {chat_id}: {e}")
            return []
    
    def cleanup_inactive_users(self):
        """Remove inactive users' HISTORY and CONTENT ONLY - PRESERVE stats and info for admin panel"""
        try:
            # Set flag to prevent recursion in track_user_activity
            self._in_cleanup = True
            
            current_time = time.time()
            inactive_threshold = current_time - (self.MAX_INACTIVE_DAYS * 24 * 60 * 60)
            
            # Find inactive users (excluding blocked users)
            # Create a copy of items to avoid RuntimeError during iteration
            inactive_users = []
            for chat_id, stats in list(self.user_stats.items()):
                # Skip blocked users - they should never be cleaned up
                if chat_id in self.blocked_users:
                    continue
                    
                # Convert "now" to actual timestamp for comparison
                if stats.get("last_active") == "now":
                    stats["last_active"] = current_time
                
                last_active = stats.get("last_active", 0)
                # If last_active is a string (invalid), treat as very old (0) to mark inactive
                if isinstance(last_active, str):
                    last_active = 0
                
                if last_active < inactive_threshold:
                    inactive_users.append(chat_id)
            
            # Remove inactive users' history and content memory ONLY - KEEP stats and info
            removed_count = 0
            for chat_id in inactive_users:
                # Only remove heavy data: history and content memory
                if chat_id in self.user_history:
                    del self.user_history[chat_id]
                    removed_count += 1
                if chat_id in self.user_content_memory:
                    del self.user_content_memory[chat_id]
                
                # DO NOT DELETE user_stats or user_info
                # Keep these for statistics tracking and admin panel visibility
            
            if removed_count > 0:
                print(f"Cleaned up {removed_count} inactive users (history only, stats preserved)")
            
            return removed_count
        except Exception as e:
            print(f"Error during cleanup_inactive_users: {e}")
            return 0
        finally:
            # Always clear the flag
            self._in_cleanup = False
    
    def check_memory_limits(self):
        """Check and enforce memory limits - ONLY remove history and content, PRESERVE stats and info"""
        try:
            # Set flag to prevent recursion
            if hasattr(self, '_in_cleanup') and self._in_cleanup:
                return
            
            self._in_cleanup = True
            
            total_users = len(self.user_history)
            
            # Clean up old daily activity data (keep last 30 days only)
            try:
                self.cleanup_old_daily_activity(max_days=30)
            except Exception as e:
                print(f"Error cleaning up daily activity: {e}")
            
            if total_users > self.MAX_USERS_IN_MEMORY:
                print(f"User limit exceeded: {total_users}/{self.MAX_USERS_IN_MEMORY}")
                cleanup_count = self.cleanup_inactive_users()
                
                # If still over limit, remove oldest users' HISTORY and CONTENT only (excluding blocked users)
                # After cleanup, check if we still have too many users with active history
                if len(self.user_history) > self.MAX_USERS_IN_MEMORY:
                    # Sort by last activity and remove oldest
                    user_activity = []
                    # Create a copy to avoid modification during iteration
                    for chat_id in list(self.user_history.keys()):
                        # Skip blocked users - never remove their data
                        if chat_id in self.blocked_users:
                            continue
                        
                        # Get last active time from stats (with fallback)
                        last_active = 0
                        if chat_id in self.user_stats:
                            last_active = self.user_stats[chat_id].get("last_active", 0)
                            if isinstance(last_active, str):
                                last_active = 0
                        
                        user_activity.append((chat_id, last_active))
                    
                    user_activity.sort(key=lambda x: x[1])  # Sort by last_active (oldest first)
                    
                    # Remove oldest users until under limit
                    to_remove = max(0, len(self.user_history) - self.MAX_USERS_IN_MEMORY + 100)  # Remove extra for buffer
                    removed = 0
                    for i in range(min(to_remove, len(user_activity))):
                        chat_id = user_activity[i][0]
                        
                        # ONLY delete history and content_memory, KEEP user_stats and user_info
                        if chat_id in self.user_history:
                            del self.user_history[chat_id]
                            removed += 1
                        if chat_id in self.user_content_memory:
                            del self.user_content_memory[chat_id]
                        
                        # DO NOT DELETE user_stats or user_info - preserve statistics!
                    
                    print(f"Removed history for {removed} oldest users to maintain memory limits (stats preserved)")
        except Exception as e:
            print(f"Error in check_memory_limits: {e}")
        finally:
            # Always clear the flag
            self._in_cleanup = False
        
    # ─── 🧠 Conversation History Management ─────────────────────────────────────────────────
    def add_to_history(self, chat_id: str, role: str, content: str):
        """Add message to user conversation history"""
        try:
            if not chat_id or not isinstance(chat_id, str):
                return
            
            history = self.user_history.setdefault(chat_id, [])
            history.append({"role": role, "content": content})
            # Keep history within limits
            self.user_history[chat_id] = history[-self.MAX_HISTORY * 2:]
        except Exception as e:
            print(f"Error adding to history for {chat_id}: {e}")
    
    def get_history(self, chat_id: str):
        """Get user conversation history"""
        try:
            if not chat_id or not isinstance(chat_id, str):
                return []
            return self.user_history.get(chat_id, [])
        except Exception as e:
            print(f"Error getting history for {chat_id}: {e}")
            return []
    
    def clear_history(self, chat_id: str):
        """Clear user conversation history"""
        try:
            if not chat_id or not isinstance(chat_id, str):
                return
            if chat_id in self.user_history:
                self.user_history[chat_id] = []
        except Exception as e:
            print(f"Error clearing history for {chat_id}: {e}")
    
    # ─── 🚫 Blocking Management (No Persistence for Heroku) ─────────────────────────
    def block_user(self, chat_id: str):
        """Mark user as blocked - blocked users' stats are NEVER deleted"""
        try:
            if not chat_id or not isinstance(chat_id, str):
                return
            
            self.blocked_users.add(chat_id)
            
            # Update last_active to current time when blocking
            if chat_id in self.user_stats:
                self.user_stats[chat_id]["last_active"] = time.time()
            
            # No file persistence for Heroku deployment
        except Exception as e:
            print(f"Error blocking user {chat_id}: {e}")
    
    def unblock_user(self, chat_id: str):
        """Unmark user as blocked and restore their activity timestamp"""
        try:
            if not chat_id or not isinstance(chat_id, str):
                return
            
            if chat_id in self.blocked_users:
                self.blocked_users.remove(chat_id)
            
            # Update last_active to current time when unblocking
            if chat_id in self.user_stats:
                self.user_stats[chat_id]["last_active"] = time.time()
            
            # No file persistence for Heroku deployment
        except Exception as e:
            print(f"Error unblocking user {chat_id}: {e}")
    
    def is_blocked(self, chat_id: str) -> bool:
        """Check if user is blocked"""
        try:
            if not chat_id or not isinstance(chat_id, str):
                return False
            return chat_id in self.blocked_users
        except Exception as e:
            print(f"Error checking if user {chat_id} is blocked: {e}")
            return False
    
    def get_all_users(self) -> set:
        """Get all unique users who have ever interacted with the bot"""
        try:
            all_users = set()
            all_users.update(self.user_history.keys())
            all_users.update(self.user_info.keys())
            all_users.update(self.user_stats.keys())
            all_users.update(self.user_content_memory.keys())
            return all_users
        except Exception as e:
            print(f"Error getting all users: {e}")
            return set()
    
    def get_user_total_stats(self) -> dict:
        """Get total statistics across all users - used by admin panel"""
        try:
            stats = {
                "total_users": len(self.get_all_users()),
                "blocked_users": len(self.blocked_users),
                "total_messages": sum(len(history) for history in self.user_history.values()),
                "total_photos": sum(stats.get("photos", 0) for stats in self.user_stats.values()),
                "total_voice": sum(stats.get("voice_audio", 0) for stats in self.user_stats.values()),
                "total_documents": sum(stats.get("documents", 0) for stats in self.user_stats.values()),
                "total_videos": sum(stats.get("videos", 0) for stats in self.user_stats.values()),
                "total_searches": sum(stats.get("search_queries", 0) for stats in self.user_stats.values()),
                "total_pdf": sum(stats.get("pdf_generated", 0) for stats in self.user_stats.values()),
                "total_excel": sum(stats.get("excel_generated", 0) for stats in self.user_stats.values()),
                "total_word": sum(stats.get("word_generated", 0) for stats in self.user_stats.values()),
                "total_ppt": sum(stats.get("ppt_generated", 0) for stats in self.user_stats.values())
            }
            return stats
        except Exception as e:
            print(f"Error getting user total stats: {e}")
            # Return safe defaults
            return {
                "total_users": 0,
                "blocked_users": 0,
                "total_messages": 0,
                "total_photos": 0,
                "total_voice": 0,
                "total_documents": 0,
                "total_videos": 0,
                "total_searches": 0,
                "total_pdf": 0,
                "total_excel": 0,
                "total_word": 0,
                "total_ppt": 0
            }