# AQLJON - Intelligent Muslim Assistant Bot

[![Python](https://img.shields.io/badge/Python-3.11-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)
[![Telegram](https://img.shields.io/badge/Telegram-Bot-blue)](https://core.telegram.org/bots)
[![Heroku](https://img.shields.io/badge/Deploy-Heroku-purple)](https://heroku.com)

AQLJON is an advanced, multilingual Telegram bot powered by Google Gemini AI that serves as an intelligent Muslim assistant. It can process various media types, generate professional documents, provide location-based services, and maintain contextual conversations with users.

## 🌟 Key Features

### 🤖 AI-Powered Conversations
- Natural, contextual conversations with memory of previous interactions
- Multilingual support with automatic language detection
- Islamic values and principles integration
- Academic guidance without direct answers (encourages learning)

### 📁 Document Generation
Professional document creation in multiple formats:
- **PDF Documents**: Richly formatted reports with cover pages, tables of contents, and visual elements
- **Excel Spreadsheets**: Data-rich tables with charts, conditional formatting, and summary statistics
- **Word Documents**: Structured documents with professional styling and formatting
- **PowerPoint Presentations**: Visually appealing slides with themes, animations, and graphics

### 📱 Media Processing
Advanced analysis of various media types:
- **Audio/Voice Messages**: Transcription and intelligent response
- **Images/Photos**: Detailed visual analysis with summary and comprehensive description
- **Videos**: Content understanding and contextual responses
- **Documents**: Text extraction and analysis from various file formats

### 🌍 Location Services
- **Prayer Times**: Accurate prayer times based on user location
- **Nearby Places**: Find points of interest including mosques, parks, restaurants, and more (30+ categories)
- **Favorite Locations**: Save and manage your favorite places
- **Geocoding**: City and location information lookup
- **Direction Services**: Get directions to any place via Google Maps

### 📊 Analytics & Statistics
- Comprehensive user activity tracking
- Document generation statistics
- Media processing analytics
- Admin dashboard with detailed insights and pagination
- User location tracking in admin statistics

## 🏗️ Architecture

### Core Components
```
AQLJON/
├── main.py                 # Application entry point
├── modules/
│   ├── audio_handler.py    # Audio/voice message processing
│   ├── video_handler.py    # Video processing
│   ├── pic_handler.py      # Image/photo analysis
│   ├── doc_handler.py      # Document file processing
│   ├── location_features/  # Location-based services
│   │   ├── __init__.py          # Package initialization
│   │   ├── location_handler.py  # Main location handler
│   │   ├── prayer_times.py      # Prayer times calculation
│   │   ├── nearby.py            # Nearby places search
│   │   └── favorites.py         # Favorite locations management
│   ├── command_handlers.py # Command processing
│   ├── memory.py           # User memory management
│   ├── config.py           # Configuration management
│   ├── utils.py            # Utility functions
│   └── doc_generation/     # Document generation system
│       ├── __init__.py              # Package initialization
│       ├── document_generator.py      # Main facade
│       ├── base_generator.py          # Base class
│       ├── pdf_generator.py           # PDF generation
│       ├── excel_generator.py         # Excel generation
│       ├── word_generator.py          # Word document generation
│       └── advanced_ppt_generator.py  # PowerPoint generation
├── requirements.txt        # Python dependencies
├── .env.example           # Environment variables template
└── init_project.py        # Project initialization script
```

### System Design

#### 1. **Modular Architecture**
The bot follows a modular design pattern with separate handlers for different functionalities:
- Each media type has its dedicated handler
- Document generation is separated into specialized modules
- Location features are organized in a dedicated folder
- Memory management is centralized
- Configuration is externalized

#### 2. **Concurrent Processing**
- Non-blocking operations using asyncio
- Background task processing for time-intensive operations
- Concurrent user handling for better scalability

#### 3. **Memory Management**
- Conversation history tracking
- Content memory for media analysis context
- User statistics and activity tracking
- Automatic cleanup of inactive users

#### 4. **Error Handling**
- Comprehensive exception handling
- Graceful degradation on failures
- Retry mechanisms for transient errors
- User-friendly error messages

## 🚀 Getting Started

### Prerequisites
- Python 3.11 (required for python-telegram-bot compatibility)
- Telegram Bot Token (get from [@BotFather](https://t.me/BotFather))
- Google Gemini API Key (get from [Google AI Studio](https://makersuite.google.com/app/apikey))
- Serper API Key (optional, for web search - get from [Serper.dev](https://serper.dev))

### Quick Start (Local Development)

1. **Clone the repository:**
```bash
git clone https://github.com/Bahtiyorjon05/AQLJON.git
cd AQLJON
```

2. **Create Python 3.11 virtual environment:**
```bash
# Windows
py -3.11 -m venv .venv311
.venv311\Scripts\activate.bat

# Linux/Mac
python3.11 -m venv .venv311
source .venv311/bin/activate
```

3. **Install dependencies:**
```bash
pip install -r requirements.txt
```

4. **Configure environment variables:**
```bash
# Copy the example file
cp .env.example .env

# Edit .env with your API keys:
# - TELEGRAM_BOT_TOKEN (required)
# - GEMINI_API_KEY (required)
# - ADMIN_ID (optional - your Telegram user ID)
# - SERPER_API_KEY (optional - for web search)
```

5. **Run the bot:**
```bash
python main.py
```

### 🚀 Deploy to Heroku (Recommended for Production)

#### One-Click Deploy
[![Deploy](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy)

#### Manual Heroku Deployment

1. **Prerequisites:**
   - [Heroku CLI](https://devcenter.heroku.com/articles/heroku-cli) installed
   - Heroku account created

2. **Login to Heroku:**
```bash
heroku login
```

3. **Create a new Heroku app:**
```bash
heroku create your-aqljon-bot
```

4. **Set environment variables:**
```bash
heroku config:set TELEGRAM_BOT_TOKEN="your_telegram_bot_token"
heroku config:set GEMINI_API_KEY="your_gemini_api_key"
heroku config:set ADMIN_ID="your_telegram_user_id"
heroku config:set SERPER_API_KEY="your_serper_api_key"  # Optional
```

5. **Deploy to Heroku:**
```bash
git push heroku main
```

6. **Start the bot:**
```bash
heroku ps:scale worker=1
```

7. **Check logs:**
```bash
heroku logs --tail
```

#### Heroku Configuration Notes
- ✅ Python 3.11.0 is specified in `runtime.txt`
- ✅ `Procfile` configured with worker dyno
- ✅ All dependencies in `requirements.txt`
- ✅ In-memory storage (no database required)
- ✅ Automatic cleanup of inactive users

### Environment Variables
```env
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
GEMINI_API_KEY=your_gemini_api_key
SERPER_API_KEY=your_serper_api_key  
ADMIN_ID=your_telegram_user_id      
```

## 📖 Usage Guide

### Basic Commands
- `/start` - Initialize the bot and show main menu
- `/help` - Display help and available commands
- `/stats` - View personal usage statistics
- `/contact` - Send a message to the administrator
- `/search [so'z]` - Search the web for information
- `/generate` - Access document generation features
- `/location` - Access location-based services

### Admin Commands
- `/adminstats` - Comprehensive system statistics with pagination
- `/monitor` - System health monitoring
- `/broadcast` - Send messages to all users
- `/update` - Notify users of system updates
- `/reply` - Respond to user contact messages

### Interactive Features
- Send any text message for conversation
- Upload images for visual analysis
- Send voice messages for audio processing
- Share documents for content extraction
- Send videos for content understanding
- Share location for prayer times and nearby places

### Document Generation
Access through the `/generate` command or "Hujjat yaratish" menu option:
1. **PDF Generation** - Create professional reports and documents
2. **Excel Generation** - Generate data tables with charts and statistics
3. **Word Generation** - Create formatted documents with styling
4. **PowerPoint Generation** - Build presentation slides with themes

### Location Services
Access through the `/location` command or "Joylashuv" menu option:
1. **Share Current Location** - Send your current GPS coordinates
2. **Search by City** - Find locations by city name
3. **Prayer Times** - Get accurate prayer times for your location
4. **Nearby Places** - Discover 30+ categories of nearby points of interest
5. **Favorite Places** - Save and manage your favorite locations

## 🔧 Technical Implementation

### AI Integration
- **Google Gemini**: Primary AI engine for content generation and media analysis
- **Prompt Engineering**: Sophisticated prompting techniques for consistent, high-quality responses
- **Context Management**: Maintains conversation context and user history

### Media Processing
- **File Handling**: Secure temporary file management with cleanup
- **Format Support**: Multiple audio, image, video, and document formats
- **Size Limits**: Configurable file size restrictions
- **Timeout Handling**: Proper timeout management for long operations

### Document Generation
- **PDF**: ReportLab library for professional PDF creation
- **Excel**: openpyxl for advanced spreadsheet features
- **Word**: python-docx for document formatting
- **PowerPoint**: python-pptx for presentation creation

### Location Services
- **Nominatim**: Geocoding and reverse geocoding
- **Aladhan API**: Prayer times calculation
- **Overpass API**: Points of interest search
- **Google Maps**: Directions and location sharing

### Memory Management
- **User History**: Conversation context preservation
- **Content Memory**: Media analysis storage for future reference
- **Statistics Tracking**: Usage analytics and metrics
- **Automatic Cleanup**: Inactive user data management

## 🎨 Design Principles

### User Experience
- **Multilingual Support**: Automatic language detection and response
- **Intuitive Interface**: Keyboard-based navigation
- **Progressive Disclosure**: Step-by-step workflows
- **Visual Feedback**: Processing indicators and status updates

### Technical Excellence
- **Scalability**: Concurrent processing and efficient memory management
- **Reliability**: Comprehensive error handling and retry mechanisms
- **Maintainability**: Modular code structure with clear separation of concerns
- **Security**: Secure API key management and file handling

### Islamic Values
- **Respectful Content**: Adherence to Islamic principles
- **Educational Focus**: Guidance over direct answers for academic topics
- **Cultural Sensitivity**: Appropriate content and language

## 📈 Analytics & Monitoring

### User Statistics
- Message counts and engagement metrics
- Media processing statistics
- Document generation tracking
- Search activity monitoring

### Admin Features
- `/adminstats` - Comprehensive system statistics with pagination for top users
- `/monitor` - System health monitoring
- `/broadcast` - Send messages to all users
- `/update` - Notify users of system updates
- `/reply` - Respond to user contact messages

### Enhanced Admin Dashboard
The admin dashboard now includes:
- **Top User Tracking**: See the top 25 most active users with pagination
- **User Location Data**: View current location information for users who have shared it
- **Detailed Statistics**: Comprehensive breakdown of all bot activities
- **Blocked Users Management**: Track and manage blocked users
- **System Health Monitoring**: Real-time system performance metrics

## 🔒 Privacy & Security

### Data Handling
- **Minimal Data Storage**: Only essential information retained
- **Automatic Cleanup**: Inactive user data removal
- **Secure Storage**: Environment variable-based configuration
- **No Personal Data**: No storage of personal information beyond what's necessary

### Compliance
- **Telegram Privacy**: Adherence to Telegram's privacy guidelines
- **Data Minimization**: Only collect necessary information
- **User Control**: Users can block the bot to stop data collection

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🛠️ Recent Improvements

### Enhanced Privacy & Security
- Removed phone numbers from all user statistics and admin displays
- Improved blocked user handling in admin stats
- Enhanced data minimization practices

### Improved Admin Features
- Better HTML formatting preservation in broadcast and reply commands
- Enhanced admin stats dashboard with improved pagination
- Dedicated blocked users list with blocking time information

### Bug Fixes & Performance
- Fixed back button handling in favorites feature
- Improved document generation reliability
- Enhanced error handling across all modules

## 🙏 Acknowledgments

- Google Gemini AI for powering the intelligent features
- Python Telegram Bot library for Telegram integration
- ReportLab, openpyxl, python-docx, and python-pptx for document generation
- OpenStreetMap and related APIs for location services
- All contributors and users who help improve the project

## 📞 Support

For support, feature requests, or bug reports, please:
1. Open an issue on GitHub
2. Contact the administrator through the bot's `/contact` command
3. Join our community (if available)

---

*Made with ❤️ for the Muslim community*