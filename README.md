# 🤖 AQLJON - Advanced Gemini Telegram Bot

A **production-ready** AI chatbot built with [Google Gemini 2.5 Flash](https://ai.google.dev) and `python-telegram-bot`.  
Features **queue-based media processing**, **admin system**, **memory management**, and **deadlock prevention** for Railway deployment!

> ⚡ **Railway-optimized** with advanced features - handles massive user loads without crashing!

---

## ✨ Core Features

### 🧠 **AI Capabilities**
- 💬 **Smart Conversations** - Advanced memory system with context preservation
- 🤖 **Google Gemini 2.5 Flash** - Latest AI model with retry logic
- 🧠 **Persistent Memory** - Remembers documents, photos, audio, videos across conversations
- 📄 **Document Analysis** - Educational analysis with lessons and insights
- 📸 **Image Analysis** - Warm, friendly photo understanding
- 🎤 **Voice & Audio** - Natural voice message processing
- 🎬 **Video Analysis** - Comprehensive video content understanding
- 🔍 **Web Search** - Integrated internet search via Serper API

### 🚀 **Production Features**
- 📊 **Queue Management** - Sequential media processing (prevents crashes)
- 🛡️ **Deadlock Prevention** - Railway-optimized concurrent upload limits
- 🔒 **Admin System** - Full admin commands with user management
- 📨 **Contact System** - Users can contact admin, admin can reply
- 📈 **Advanced Statistics** - Comprehensive user analytics
- 🧹 **Memory Management** - Automatic cleanup of inactive users
- ⚙️ **Error Resilience** - Multi-layer retry mechanisms
- 🔄 **Auto-Recovery** - Graceful handling of API failures

---

## 🧱 Advanced Tech Stack

| Technology             | Purpose                          | Version |
|------------------------|----------------------------------|----------|
| `python-telegram-bot`  | Telegram Bot API client         | 22.1     |
| `google-generativeai`  | Gemini 2.5 Flash AI model       | 0.8.3    |
| `httpx`                | Async HTTP client                | 0.28.1   |
| `tenacity`             | Retry handling & resilience     | 9.0.0    |
| `aiofiles`             | Async file operations            | 24.1.0   |
| `python-dotenv`        | Environment configuration        | 1.0.0    |
| `Pillow`               | Image processing support         | 10.2.0   |

---

## 🚀 Quick Setup Guide

### 1. 🔑 Configure Environment

```bash
# Copy the example config
cp .env.example .env

# Edit .env with your actual API keys
# Required: TELEGRAM_BOT_TOKEN and GEMINI_API_KEY
# Optional: SERPER_API_KEY (for web search)
```

### 2. 📦 Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. 🚀 Launch the Bot

```bash
python bot.py
```

### 4. 📱 Advanced Deployment

#### Railway Deployment:
1. Fork this repository on GitHub
2. Create a new Railway project
3. Connect your GitHub repository
4. Add environment variables in Railway dashboard
5. Deploy automatically!

#### Docker Deployment:
```bash
# Build the image
docker build -t gemini-bot .

# Run with environment file
docker run --env-file .env gemini-bot
```

---

## 🎯 Command Reference

### 🔵 User Commands
| Command | Description | Example |
|---------|-------------|---------|
| `/start` | Initialize/restart bot | `/start` |
| `/help` | Show detailed help menu | `/help` |
| `/search [query]` | Search the internet | `/search AI news 2024` |
| `/stats` | View your usage statistics | `/stats` |
| `/contact [message]` | Send message to admin | `/contact Need help with bot` |

### 👑 Admin Commands (Admin Only)
| Command | Description | Example |
|---------|-------------|---------|
| `/adminstats` | Comprehensive admin statistics | `/adminstats` |
| `/broadcast [message]` | Send message to all users | `/broadcast Important update!` |
| `/reply [user_id] [message]` | Reply to user contact | `/reply 123456789 Thanks for feedback` |

## 🎨 Response Styles

- **friendly** (default) - Warm and conversational
- **professional** - Formal and business-like  
- **casual** - Relaxed and informal
- **creative** - Imaginative and artistic

---

## 📞 Contact & Admin System

### 👥 For Users:
- **Contact Admin**: Use `/contact [your message]` to send messages directly to admin
- **Get Help**: Admin will receive your message with your profile info
- **Receive Replies**: Admin can respond directly to your contact messages
- **Example**: `/contact I need help with document analysis`

### 👑 For Admins:
- **View Statistics**: `/adminstats` shows comprehensive bot statistics with top 20 users
- **User Analytics**: Detailed user data including message counts, media usage, and profile info
- **Broadcast Messages**: `/broadcast [message]` sends announcements to all bot users
- **Reply to Contacts**: `/reply [user_id] [message]` responds to user contact messages
- **System Monitoring**: Track queue management, memory usage, and performance metrics

### 🔐 Admin Setup:
1. Get your Telegram User ID (send `/start` to @userinfobot)
2. Set `ADMIN_ID=your_user_id` in environment variables
3. Admin commands are automatically hidden from regular users
4. Only verified admins can access administrative functionality

---

## 🚀 Railway Deployment Features

### 🏗️ Production Optimizations:
- **Deadlock Prevention** - Advanced semaphore controls prevent Railway crashes
- **Queue Management** - Sequential media processing (max 2 concurrent uploads)
- **Memory Limits** - Auto-cleanup of inactive users after 30 days
- **Error Recovery** - Multi-layer retry mechanisms with timeout controls
- **Resource Management** - ThreadPoolExecutor with safe worker limits
- **File Size Validation** - Pre-upload file size checking

### 📈 Performance Metrics:
- **Max Users in Memory**: 2,000 active users
- **Max History per User**: 40 messages (20 conversations)
- **Max Content Memory**: 50 items per user
- **Upload Timeout**: 20-30 seconds (depending on file type)
- **API Timeout**: 15-25 seconds (with retry logic)

---

## 📊 Supported Content Types & File Limits

- ✅ **Text Messages** - Natural conversation with unlimited length
- ✅ **Images** - Photo analysis and description (any size)
- ✅ **Voice Messages** - Audio processing and response (any size)
- ✅ **Audio Files** - Music, sounds, podcasts analysis (any size)
- ✅ **Documents** - File analysis (PDF, DOCX, TXT, etc.) - **Max: 20MB**
- ✅ **Videos** - Video content analysis and description - **Max: 25MB**
- ✅ **URLs** - Web page content analysis
- ✅ **Commands** - Interactive bot controls

### 🚀 Advanced Processing Features
- **Sequential Media Processing** - Handles multiple files one by one to prevent crashes
- **Queue Management** - Up to 5 pending media files per user
- **Smart Memory** - Remembers previous documents, photos, and conversations
- **Error Recovery** - Automatic retry with graceful fallbacks

---

## 🔧 Configuration

### Required Environment Variables:
```env
TELEGRAM_BOT_TOKEN=your_token_here     # Get from @BotFather
GEMINI_API_KEY=your_api_key_here       # Get from Google AI Studio
```

### Optional Environment Variables:
```env
SERPER_API_KEY=your_serper_key_here    # For web search functionality
ADMIN_ID=your_telegram_user_id_here    # For admin commands access
```

### Bot Capabilities:
- **Memory Management**: 30 messages per user with intelligent pruning
- **File Size Limits**: 
  - Documents: 20MB maximum
  - Videos: 25MB maximum
  - Photos/Audio: No size limit
- **Queue System**: Sequential processing prevents Railway deadlocks
- **Admin System**: Full administrative controls and statistics
- **Contact System**: Users can contact admin, admin can reply
- **Response Time**: Optimized with retry logic and async processing
- **Error Recovery**: Multi-layer error handling with graceful fallbacks
- **Auto-Cleanup**: Inactive users removed after 30 days

---

## 🏗️ Architecture Highlights

- **Event-Driven Design** - Asynchronous message processing
- **Queue Management System** - Sequential media processing per user
- **Deadlock Prevention** - Railway-optimized with semaphore controls
- **Memory Management** - Smart conversation context preservation with auto-cleanup
- **Admin Authentication** - Secure admin-only command visibility
- **Contact System** - Bidirectional user-admin communication
- **Error Resilience** - Multi-layer retry mechanisms with timeout controls
- **Type Safety** - Full type annotations for reliability
- **Modular Structure** - Clean, maintainable codebase
- **Performance Optimized** - Efficient async operations with concurrent upload limits

---

## 🤝 Contributing

We welcome contributions! Please feel free to submit pull requests, report bugs, or suggest new features.

### Development Setup:
```bash
git clone <your-repo>
cd gemini-chatbot
pip install -r requirements.txt
cp .env.example .env
# Configure your .env file
python bot.py
```

---

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

---

## 🙏 Acknowledgments

- **Google Gemini AI** - For powerful 2.5 Flash language processing
- **Telegram Bot API** - For seamless messaging platform
- **Python Telegram Bot Library** - For excellent async framework
- **Railway** - For reliable cloud deployment platform
- **Serper API** - For integrated web search capabilities
- **Open Source Community** - For inspiration and collaboration

### 📝 Features Summary:
✅ **Smart AI Conversations** with memory
✅ **Media Analysis** (photos, videos, documents, audio)
✅ **Web Search** integration
✅ **Admin System** with comprehensive statistics
✅ **Contact System** for user-admin communication
✅ **Queue Management** for crash prevention
✅ **Railway-Optimized** for production deployment
✅ **Memory Management** with auto-cleanup
✅ **Error Recovery** with retry mechanisms

**Built with ❤️ for the AI community!**