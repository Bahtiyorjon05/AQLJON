# 🤖 Gemini Advanced Telegram Bot

An **ultra-enhanced** AI chatbot built with [Google Gemini 2.5 Flash](https://ai.google.dev) and `python-telegram-bot`.  
Features advanced memory management, document processing, URL analysis, and comprehensive error handling!

> ⚡ **Production-ready** with awesome features - deploy on [Railway](https://railway.app) or any Python server!

---

## ✨ Enhanced Features

- 💬 **Smart Conversations** - Advanced memory system with context preservation
- 🤖 **Google Gemini Integration** - Latest AI model with retry logic
- 🧠 **Intelligent Memory** - Per-user conversation history with smart pruning
- 📄 **Document Analysis** - Upload and analyze any document type
- 🌐 **URL Processing** - Analyze web pages and content
- 🎤 **Voice & Audio** - Process voice messages naturally
- 📸 **Image Analysis** - Advanced photo understanding
- 🔍 **Web Search** - Integrated internet search capability
- 🎨 **Custom Styles** - Adjustable response personalities
- 📊 **Usage Statistics** - Track your bot interactions
- 🛡️ **Robust Error Handling** - Comprehensive retry mechanisms
- ⚙️ **Type Safety** - Full type hints for reliability
- 🚀 **Production Ready** - Optimized for deployment

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

| Command | Description | Example |
|---------|-------------|---------|
| `/start` | Initialize/restart bot | `/start` |
| `/help` | Show detailed help menu | `/help` |
| `/search [query]` | Search the internet | `/search AI news 2024` |
| `/style [style]` | Change response style | `/style professional` |
| `/stats` | View usage statistics | `/stats` |
| `/settings` | Bot configuration | `/settings` |

## 🎨 Response Styles

- **friendly** (default) - Warm and conversational
- **professional** - Formal and business-like  
- **casual** - Relaxed and informal
- **creative** - Imaginative and artistic

## 📊 Supported Content Types

- ✅ **Text Messages** - Natural conversation
- ✅ **Images** - Photo analysis and description
- ✅ **Voice Messages** - Audio processing and response
- ✅ **Documents** - File analysis (PDF, DOCX, TXT, etc.)
- ✅ **URLs** - Web page content analysis
- ✅ **Commands** - Interactive bot controls

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
```

### Bot Capabilities:
- **Memory Limit**: 30 messages per user with smart pruning
- **File Size Limit**: 20MB for document uploads
- **Response Time**: Optimized with retry logic and async processing
- **Error Recovery**: Comprehensive error handling with graceful fallbacks

---

## 🏗️ Architecture Highlights

- **Event-Driven Design** - Asynchronous message processing
- **Memory Management** - Smart conversation context preservation
- **Error Resilience** - Multi-layer retry mechanisms
- **Type Safety** - Full type annotations for reliability
- **Modular Structure** - Clean, maintainable codebase
- **Performance Optimized** - Efficient async operations

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

- Google Gemini AI for powerful language processing
- Telegram Bot API for seamless messaging
- Python Telegram Bot library for excellent framework

**Built with ❤️ for the AI community!**