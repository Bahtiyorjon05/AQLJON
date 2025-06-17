# 🤖 Gemini Telegram Bot

A fast, friendly AI chatbot built with [Google Gemini 2 Flash](https://ai.google.dev) and `python-telegram-bot`.  
No database needed. HTML answers. Works like a memory bot.

> ⚡ Built for easy deployment on [Railway](https://railway.app) or any Python server!

---

## ✨ Features

- 💬 Telegram bot with persistent per-user memory (in RAM)
- 🤖 Google Gemini Flash AI integration
- 🧠 Stores chat history for better replies
- 🧾 HTML responses with bold/italic/emoji
- ⚙️ Easy config via `.env` file
- 🚀 No Redis or database needed (deploy anywhere)

---

## 🧱 Tech Stack

| Tech               | Purpose                          |
|--------------------|----------------------------------|
| `python-telegram-bot` | Telegram Bot API client         |
| `google-generativeai` | Gemini 2.0 Flash AI model       |
| `tenacity`         | Retry handling for Gemini        |
| `dotenv`           | Config from `.env` file          |
| `asyncio`          | Fast async message handling      |

---

## 🚀 Quickstart (Local)

### 1. 🔑 Setup `.env`

Create a `.env` file:

```env
TELEGRAM_BOT_TOKEN=your-telegram-token-here
GEMINI_API_KEY=your-gemini-api-key-here
```

### 2. 📦 Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. 🚀 Run the Bot

```bash
python bot.py
```

### 4. 📱 Deploy to Railway

1. Create a new Railway project
2. Connect your GitHub repository
3. Add the required environment variables
4. Deploy and set up the webhook

---

## 📝 License

This project is licensed under the MIT License - see the LICENSE file for details.
