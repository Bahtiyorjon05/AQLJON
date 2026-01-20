import time
import json
import os
from datetime import datetime, timedelta
import firebase_admin
from firebase_admin import credentials, firestore

# ─── 🧠 Enhanced Memory Management ─────────────────────────────────────────────────
class MemoryManager:
    """Manages user memory, history, and statistics"""
    
    def __init__(self, max_history=100, max_content_memory=100, max_users=2000, max_inactive_days=15):
        # Configuration
        self.MAX_HISTORY = max_history
        self.MAX_CONTENT_MEMORY = max_content_memory
        self.MAX_USERS_IN_MEMORY = max_users
        self.MAX_INACTIVE_DAYS = max_inactive_days

        # Initialize Firebase
        self._init_firebase()

        # Initialize data structures
        self.user_history = {}
        self.user_content_memory = {}
        self.user_contact_messages = {}
        self.user_daily_activity = {}

        # Initialize persistent data structures
        self.user_stats = {}
        self.user_info = {}
        self.user_states = {}  # Track user conversational states
        self.blocked_users = set()

        # Batch write optimization - Phase 1 improvement
        self._pending_writes = set()  # Track users needing save
        self._last_batch_save = time.time()
        self.BATCH_SAVE_INTERVAL = 300  # 5 minutes
        self.BATCH_SAVE_THRESHOLD = 50  # Save when 50 users pending

        # Load persistent data from Firestore
        self._load_from_firestore()

        print(f"Loaded {len(self.user_stats)} user stats, {len(self.user_info)} user info, {len(self.blocked_users)} blocked users from Firestore")

    # ─── 💾 Firebase Initialization ─────────────────────────────────────────────────
    def _init_firebase(self):
        """Initialize Firebase connection"""
        try:
            # Check if already initialized
            if firebase_admin._apps:
                self.db = firestore.client()
                print("[OK] Firebase already initialized, reusing connection")
                return

            # Get credentials from environment variable
            firebase_creds_json = os.getenv("FIREBASE_CREDENTIALS")

            if not firebase_creds_json:
                print("[WARNING] FIREBASE_CREDENTIALS not found. Running in local-only mode (data will be lost on restart).")
                self.db = None
                return

            # Parse JSON credentials
            creds_dict = json.loads(firebase_creds_json)
            cred = credentials.Certificate(creds_dict)

            # Initialize Firebase
            firebase_admin.initialize_app(cred)
            self.db = firestore.client()

            print("[OK] Firebase Firestore connected successfully!")

        except Exception as e:
            print(f"[ERROR] Firebase initialization failed: {e}")
            print("[WARNING] Running in local-only mode (data will be lost on restart)")
            self.db = None

    def _load_from_firestore(self):
        """Load all user data from Firestore"""
        if not self.db:
            print("[WARNING] Firestore not available, skipping load")
            return

        try:
            # Load all users from Firestore
            users_ref = self.db.collection('users')
            users = users_ref.stream()

            loaded_count = 0
            for user_doc in users:
                chat_id = user_doc.id
                data = user_doc.to_dict()

                # Load user stats
                if 'stats' in data:
                    self.user_stats[chat_id] = data['stats']

                # Load user info
                if 'info' in data:
                    self.user_info[chat_id] = data['info']

                # Load user conversational states
                if 'state' in data:
                    self.user_states[chat_id] = data['state']

                # Load blocked status
                if data.get('blocked', False):
                    self.blocked_users.add(chat_id)

                loaded_count += 1

            print(f"[OK] Loaded {loaded_count} users from Firestore")

        except Exception as e:
            print(f"[ERROR] Error loading from Firestore: {e}")

    def _save_to_firestore(self, chat_id: str):
        """Save a single user's data to Firestore"""
        if not self.db:
            return False

        try:
            user_ref = self.db.collection('users').document(chat_id)

            # Prepare data
            data = {}

            if chat_id in self.user_stats:
                data['stats'] = self.user_stats[chat_id]

            if chat_id in self.user_info:
                data['info'] = self.user_info[chat_id]
                
            if chat_id in self.user_states:
                data['state'] = self.user_states[chat_id]

            data['blocked'] = chat_id in self.blocked_users
            data['last_updated'] = firestore.SERVER_TIMESTAMP

            # Save to Firestore (merge=True to avoid overwriting existing fields)
            user_ref.set(data, merge=True)

            return True

        except Exception as e:
            print(f"[ERROR] Error saving {chat_id} to Firestore: {e}")
            return False

    def _batch_save_pending(self):
        """Batch save all pending user data to Firestore - Phase 1 optimization"""
        if not self.db or not self._pending_writes:
            return

        try:
            # Use Firestore batch writes for efficiency
            batch = self.db.batch()
            saved_count = 0

            for chat_id in list(self._pending_writes):
                try:
                    user_ref = self.db.collection('users').document(chat_id)

                    # Prepare data
                    data = {}

                    if chat_id in self.user_stats:
                        data['stats'] = self.user_stats[chat_id]

                    if chat_id in self.user_info:
                        data['info'] = self.user_info[chat_id]
                        
                    if chat_id in self.user_states:
                        data['state'] = self.user_states[chat_id]

                    data['blocked'] = chat_id in self.blocked_users
                    data['last_updated'] = firestore.SERVER_TIMESTAMP

                    # Add to batch (max 500 operations per batch)
                    batch.set(user_ref, data, merge=True)
                    saved_count += 1

                    # Commit batch when reaching 500 operations (Firestore limit)
                    if saved_count % 500 == 0:
                        batch.commit()
                        batch = self.db.batch()

                except Exception as e:
                    print(f"Error preparing batch for {chat_id}: {e}")

            # Commit remaining operations (if any were added after last batch commit)
            if saved_count > 0 and saved_count % 500 != 0:
                batch.commit()

            print(f"[OK] Batch saved {saved_count} users to Firestore")

            # Clear pending writes and update timestamp
            self._pending_writes.clear()
            self._last_batch_save = time.time()

        except Exception as e:
            print(f"[ERROR] Error in batch save: {e}")

    def save_persistent_data(self):
        """Save all persistent data to Firestore"""
        if not self.db:
            return False

        try:
            # Save all users in batch
            batch = self.db.batch()
            save_count = 0

            # Combine all chat_ids from stats, info, and blocked users
            all_chat_ids = set()
            all_chat_ids.update(self.user_stats.keys())
            all_chat_ids.update(self.user_info.keys())
            all_chat_ids.update(self.blocked_users)
            all_chat_ids.update(self.user_states.keys())

            for chat_id in all_chat_ids:
                user_ref = self.db.collection('users').document(chat_id)

                # Prepare data
                data = {'last_updated': firestore.SERVER_TIMESTAMP}

                if chat_id in self.user_stats:
                    data['stats'] = self.user_stats[chat_id]

                if chat_id in self.user_info:
                    data['info'] = self.user_info[chat_id]
                    
                if chat_id in self.user_states:
                    data['state'] = self.user_states[chat_id]

                data['blocked'] = chat_id in self.blocked_users

                batch.set(user_ref, data, merge=True)
                save_count += 1

                # Firestore batch limit is 500, commit and start new batch
                if save_count % 450 == 0:
                    batch.commit()
                    batch = self.db.batch()
                    print(f"  💾 Saved batch of {save_count} users...")

            # Commit final batch
            if save_count % 450 != 0:
                batch.commit()

            print(f"[OK] Saved {save_count} users to Firestore")
            return True

        except Exception as e:
            print(f"[ERROR] Error saving to Firestore: {e}")
            return False

    # ─── 📊 User Statistics Tracking ─────────────────────────────────────────────────
    def track_user_activity(self, chat_id: str, activity_type: str, update=None):
        """Track user activity for statistics with daily analytics - NEVER resets existing stats"""
        # Validate input
        if not chat_id or not isinstance(chat_id, str):
            return

        try:
            # Check memory limits before adding new users (but avoid during cleanup)
            if chat_id not in self.user_stats and not hasattr(self, '_in_cleanup'):
                self.check_memory_limits()

            # Initialize user stats ONLY if they don't exist (NEVER reset existing stats)
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
                    "first_interaction": time.time(),  # Set ONCE and NEVER change
                    "last_active": time.time(),
                    "total_characters": 0
                }
            else:
                # CRITICAL: Preserve ALL existing stats - only update last_active time
                # NEVER reset first_interaction or any counters
                self.user_stats[chat_id]["last_active"] = time.time()

                # Ensure first_interaction exists and is never reset
                if "first_interaction" not in self.user_stats[chat_id]:
                    self.user_stats[chat_id]["first_interaction"] = time.time()

                # Ensure all stat counters exist with defaults if missing
                for key in ["messages", "photos", "voice_audio", "documents", "videos",
                           "search_queries", "pdf_generated", "excel_generated",
                           "word_generated", "ppt_generated", "total_characters"]:
                    if key not in self.user_stats[chat_id]:
                        self.user_stats[chat_id][key] = 0

            # Increment activity counter - safely handle missing keys
            if activity_type in self.user_stats[chat_id]:
                self.user_stats[chat_id][activity_type] += 1
            else:
                # If the activity type doesn't exist in stats, add it
                self.user_stats[chat_id][activity_type] = 1

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

            # Optimized batch write - mark user for pending save
            self._pending_writes.add(chat_id)

            # Batch save every 5 minutes OR when 50 users are pending
            if (time.time() - self._last_batch_save > self.BATCH_SAVE_INTERVAL or
                len(self._pending_writes) >= self.BATCH_SAVE_THRESHOLD):
                self._batch_save_pending()

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
        """Remove inactive users' HISTORY and CONTENT ONLY - NEVER TOUCH stats and info for admin panel"""
        try:
            # Set flag to prevent recursion in track_user_activity
            self._in_cleanup = True

            current_time = time.time()
            inactive_threshold = current_time - (self.MAX_INACTIVE_DAYS * 24 * 60 * 60)

            # Find inactive users (excluding blocked users)
            # Create a copy of items to avoid RuntimeError during iteration
            inactive_users = []
            for chat_id in list(self.user_history.keys()):  # Only check users with history
                # Skip blocked users - they should never be cleaned up
                if chat_id in self.blocked_users:
                    continue

                # Get last_active from user_stats if exists
                last_active = 0
                if chat_id in self.user_stats:
                    last_active = self.user_stats[chat_id].get("last_active", 0)
                    # Convert "now" to actual timestamp for comparison
                    if last_active == "now":
                        last_active = current_time
                        self.user_stats[chat_id]["last_active"] = current_time
                    # If last_active is a string (invalid), treat as current time to avoid accidental deletion
                    elif isinstance(last_active, str):
                        last_active = current_time
                        self.user_stats[chat_id]["last_active"] = current_time

                # Only mark as inactive if they haven't been active for MAX_INACTIVE_DAYS
                if last_active > 0 and last_active < inactive_threshold:
                    inactive_users.append(chat_id)

            # Remove inactive users' history and content memory ONLY - NEVER TOUCH stats and info
            removed_count = 0
            for chat_id in inactive_users:
                # Only remove heavy data: history and content memory
                if chat_id in self.user_history:
                    del self.user_history[chat_id]
                    removed_count += 1
                if chat_id in self.user_content_memory:
                    del self.user_content_memory[chat_id]

                # NEVER DELETE user_stats or user_info - these MUST persist forever
                # This ensures all user statistics are visible in admin panel regardless of activity

            if removed_count > 0:
                print(f"Cleaned up {removed_count} inactive users' history (stats/info preserved forever)")

            return removed_count
        except Exception as e:
            print(f"Error during cleanup_inactive_users: {e}")
            return 0
        finally:
            # Always clear the flag
            self._in_cleanup = False
    
    def check_memory_limits(self):
        """Check and enforce memory limits - ONLY remove history and content, NEVER TOUCH stats and info"""
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
                            # Convert string timestamps to current time to avoid accidental deletion
                            if isinstance(last_active, str):
                                last_active = time.time()
                                self.user_stats[chat_id]["last_active"] = last_active

                        user_activity.append((chat_id, last_active))

                    user_activity.sort(key=lambda x: x[1])  # Sort by last_active (oldest first)

                    # Remove oldest users until under limit
                    to_remove = max(0, len(self.user_history) - self.MAX_USERS_IN_MEMORY + 100)  # Remove extra for buffer
                    removed = 0
                    for i in range(min(to_remove, len(user_activity))):
                        chat_id = user_activity[i][0]

                        # ONLY delete history and content_memory, NEVER TOUCH user_stats and user_info
                        if chat_id in self.user_history:
                            del self.user_history[chat_id]
                            removed += 1
                        if chat_id in self.user_content_memory:
                            del self.user_content_memory[chat_id]

                        # NEVER DELETE user_stats or user_info - these MUST persist forever for admin panel

                    print(f"Removed history for {removed} oldest users (stats/info preserved forever)")
        except Exception as e:
            print(f"Error in check_memory_limits: {e}")
        finally:
            # Always clear the flag
            self._in_cleanup = False
        
    # ─── 🧠 Conversation History Management ─────────────────────────────────────────────────
    def log_chat_message(self, chat_id: str, role: str, content: str, msg_type: str = "text", **kwargs):
        """Log chat message to history and track activity"""
        try:
            # Add to conversation history
            self.add_to_history(chat_id, role, content)
            
            # Track activity if it's a user message
            if role == "user":
                self.track_user_activity(chat_id, "messages")
                
        except Exception as e:
            print(f"Error logging chat message for {chat_id}: {e}")

    def upload_to_storage(self, file_path: str, file_name: str, content_type: str):
        """Upload file to Firebase Storage"""
        try:
            from firebase_admin import storage
            bucket = storage.bucket()
            blob = bucket.blob(f"uploads/{file_name}")
            blob.upload_from_filename(file_path, content_type=content_type)
            blob.make_public()
            return blob.public_url
        except Exception as e:
            print(f"Error uploading to storage: {e}")
            return None

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
        """Mark user as blocked - blocked users' stats and info are PERMANENTLY preserved"""
        try:
            if not chat_id or not isinstance(chat_id, str):
                return

            self.blocked_users.add(chat_id)

            # Update last_active to current time when blocking to prevent any cleanup
            if chat_id in self.user_stats:
                self.user_stats[chat_id]["last_active"] = time.time()
            else:
                # If user doesn't have stats yet, create them to ensure they're tracked
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

            # Blocked users MUST be in admin stats - their stats are NEVER deleted
            # Save to Firestore immediately
            self._save_to_firestore(chat_id)
        except Exception as e:
            print(f"Error blocking user {chat_id}: {e}")

    def unblock_user(self, chat_id: str):
        """Unmark user as blocked and restore their activity timestamp - stats always preserved"""
        try:
            if not chat_id or not isinstance(chat_id, str):
                return

            if chat_id in self.blocked_users:
                self.blocked_users.remove(chat_id)

            # Update last_active to current time when unblocking
            if chat_id in self.user_stats:
                self.user_stats[chat_id]["last_active"] = time.time()
            else:
                # If user doesn't have stats, create them
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

            # Stats are ALWAYS preserved regardless of block status
            # Save to Firestore immediately
            self._save_to_firestore(chat_id)
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
                # Count messages from user_stats instead of user_history since history gets cleaned up
                "total_messages": sum(user_stats.get("messages", 0) for user_stats in self.user_stats.values()),
                "total_photos": sum(user_stats.get("photos", 0) for user_stats in self.user_stats.values()),
                "total_voice": sum(user_stats.get("voice_audio", 0) for user_stats in self.user_stats.values()),
                "total_documents": sum(user_stats.get("documents", 0) for user_stats in self.user_stats.values()),
                "total_videos": sum(user_stats.get("videos", 0) for user_stats in self.user_stats.values()),
                "total_searches": sum(user_stats.get("search_queries", 0) for user_stats in self.user_stats.values()),
                "total_pdf": sum(user_stats.get("pdf_generated", 0) for user_stats in self.user_stats.values()),
                "total_excel": sum(user_stats.get("excel_generated", 0) for user_stats in self.user_stats.values()),
                "total_word": sum(user_stats.get("word_generated", 0) for user_stats in self.user_stats.values()),
                "total_ppt": sum(user_stats.get("ppt_generated", 0) for user_stats in self.user_stats.values())
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