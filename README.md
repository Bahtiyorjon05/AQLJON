# 🤖 Gemini-Powered Telegram Bot

A feature-rich Telegram bot powered by Google's Gemini 2.0 Flash API with memory and rich text formatting.

## ✨ Features

- 🧠 **Conversation Memory** - Remembers chat history and context
- 💬 **Rich Text Formatting** - Supports bold, italic, underline, and emojis
- 🚀 **Fast Response Times** - Optimized for quick replies
- 💾 **Redis Caching** - Efficient response caching to reduce API usage
- ⚡ **Rate Limiting** - Protects against spam and excessive usage
- 🔄 **Error Handling** - Robust retry mechanisms and error recovery
- 🌐 **24/7 Deployment** - Ready for continuous operation on Railway

## 🛠️ Setup

### Prerequisites

- Python 3.9+
- Redis server
- Google Gemini API Token

### Environment Variables

Create a `.env` file with the following variables:

```
GEMINI_API_KEY=your_gemini_api_key
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
REDIS_URL=your_redis_url (optional, defaults to localhost)
```

### Installation

1. Clone the repository
2. Install dependencies: `pip install -r requirements.txt`
3. Run the bot locally: `python bot_fixed.py`

> **Note:** We've created a fixed version (`bot_fixed.py`) that uses python-telegram-bot v13.15 for better compatibility. The requirements.txt has been updated accordingly.

## 🚀 Deployment

### Railway Deployment

This bot is configured for deployment on [Railway](https://railway.app/):

1. Create a new Railway project
2. Connect your GitHub repository
3. Add the required environment variables
4. Deploy and set up the webhook

## 📝 License

This project is licensed under the MIT License - see the LICENSE file for details.
