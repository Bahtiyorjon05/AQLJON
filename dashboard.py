import os
import asyncio
import logging
from aiohttp import web
import aiohttp_jinja2
import jinja2
from datetime import datetime

logger = logging.getLogger(__name__)

# Admin Password
ADMIN_PASSWORD = os.getenv("DASHBOARD_PASSWORD", "ben123!!")

def setup_dashboard(app, memory_manager):
    """Setup the dashboard routes and templates"""
    
    loader = jinja2.DictLoader({
        'index.html': """
<!DOCTYPE html>
<html lang="uz">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AQLJON Dashboard</title>
    
    <!-- Bootstrap & Icons -->
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.1/font/bootstrap-icons.css">
    
    <!-- Google Fonts -->
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&display=swap" rel="stylesheet">

    <style>
        :root {
            --sidebar-width: 320px;
            --primary-color: #0088cc;
            --bg-color: #f0f2f5;
            --sidebar-bg: #ffffff;
            --chat-bg: #e4e9f2;
            --text-primary: #1c1e21;
            --text-secondary: #65676b;
            --border-color: #e9edef;
            --message-out: #e3f2fd;
            --message-in: #ffffff;
            --hover-color: #f5f6f6;
        }

        [data-theme="dark"] {
            --bg-color: #0f0f0f;
            --sidebar-bg: #212121;
            --chat-bg: #0f0f0f;
            --text-primary: #e9edef;
            --text-secondary: #aebac1;
            --border-color: #2f3336;
            --message-out: #005c4b;
            --message-in: #202c33;
            --hover-color: #2a3942;
        }

        body { 
            font-family: 'Inter', sans-serif; 
            background-color: var(--bg-color);
            color: var(--text-primary);
            height: 100vh;
            overflow: hidden;
            transition: background-color 0.3s;
        }

        /* Layout */
        .app-container {
            display: flex;
            height: 100vh;
            max-width: 100%;
            margin: 0 auto;
            background: var(--sidebar-bg);
        }

        /* Sidebar */
        .sidebar {
            width: var(--sidebar-width);
            background: var(--sidebar-bg);
            border-right: 1px solid var(--border-color);
            display: flex;
            flex-direction: column;
            transition: all 0.3s;
        }

        .sidebar-header {
            padding: 16px;
            border-bottom: 1px solid var(--border-color);
            display: flex;
            align-items: center;
            justify-content: space-between;
        }

        .user-list {
            flex: 1;
            overflow-y: auto;
        }

        .user-item {
            padding: 12px 16px;
            display: flex;
            align-items: center;
            gap: 12px;
            cursor: pointer;
            border-bottom: 1px solid transparent;
            transition: background-color 0.2s;
            text-decoration: none;
            color: inherit;
        }

        .user-item:hover {
            background-color: var(--hover-color);
        }

        .user-item.active {
            background-color: rgba(0, 136, 204, 0.1);
            border-left: 3px solid var(--primary-color);
        }

        /* Chat Area */
        .chat-area {
            flex: 1;
            display: flex;
            flex-direction: column;
            background-color: var(--chat-bg);
            background-image: url("https://site-assets.fontawesome.com/assets/img/favicons/mstile-150x150.png");
            background-blend-mode: overlay;
            position: relative;
        }

        .chat-header {
            padding: 10px 20px;
            background: var(--sidebar-bg);
            border-bottom: 1px solid var(--border-color);
            display: flex;
            align-items: center;
            justify-content: space-between;
            height: 64px;
        }

        .chat-messages {
            flex: 1;
            overflow-y: auto;
            padding: 20px;
            display: flex;
            flex-direction: column;
            gap: 8px;
        }

        /* Messages */
        .message {
            max-width: 65%;
            padding: 8px 12px;
            border-radius: 12px;
            font-size: 0.95rem;
            line-height: 1.4;
            position: relative;
            box-shadow: 0 1px 2px rgba(0,0,0,0.08);
        }

        .message.user {
            align-self: flex-end;
            background-color: var(--message-out);
            border-top-right-radius: 2px;
        }

        .message.bot {
            align-self: flex-start;
            background-color: var(--message-in);
            border-top-left-radius: 2px;
        }

        .timestamp {
            font-size: 0.7rem;
            color: var(--text-secondary);
            text-align: right;
            margin-top: 4px;
            display: block;
        }

        /* Components */
        .avatar {
            width: 48px;
            height: 48px;
            border-radius: 50%;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 600;
            font-size: 1.1rem;
            flex-shrink: 0;
        }

        .search-box {
            background: var(--bg-color);
            border: 1px solid var(--border-color);
            color: var(--text-primary);
            border-radius: 8px;
            padding: 8px 12px;
            width: 100%;
        }
        
        .search-box:focus {
            outline: none;
            border-color: var(--primary-color);
        }

        .empty-state {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            height: 100%;
            color: var(--text-secondary);
            text-align: center;
        }

        /* Toggle Switch */
        .theme-toggle {
            cursor: pointer;
            padding: 8px;
            border-radius: 50%;
            transition: background 0.2s;
        }
        .theme-toggle:hover { background: var(--hover-color); }

        /* Scrollbar */
        ::-webkit-scrollbar { width: 6px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: rgba(0,0,0,0.2); border-radius: 3px; }
        ::-webkit-scrollbar-thumb:hover { background: rgba(0,0,0,0.3); }
        
        .badge-file {
            background: rgba(0,0,0,0.05);
            color: var(--text-primary);
            border: 1px solid var(--border-color);
            border-radius: 6px;
            padding: 8px;
            display: flex;
            align-items: center;
            gap: 8px;
            margin-top: 5px;
        }
    </style>
</head>
<body>
    <div class="app-container">
        <!-- Sidebar -->
        <div class="sidebar">
            <div class="sidebar-header">
                <div class="d-flex align-items-center gap-2">
                    <i class="bi bi-robot fs-4 text-primary"></i>
                    <h5 class="m-0 fw-bold">AQLJON</h5>
                </div>
                <div class="d-flex gap-2">
                    <div class="theme-toggle" onclick="toggleTheme()" title="Mavzuni o'zgartirish">
                        <i class="bi bi-moon-stars fs-5"></i>
                    </div>
                    <a href="/logout" class="theme-toggle text-danger" title="Chiqish">
                        <i class="bi bi-box-arrow-right fs-5"></i>
                    </a>
                </div>
            </div>
            
            <div class="p-3">
                <input type="text" class="search-box" id="userSearch" placeholder="Qidirish...">
            </div>

            <div class="user-list" id="userList">
                {% for user in users %}
                <a href="/?chat_id={{ user.chat_id }}" class="user-item {% if current_chat_id == user.chat_id %}active{% endif %}">
                    <div class="avatar position-relative">
                        {{ user.initials }}
                        {% if user.blocked %}
                        <span class="position-absolute top-0 start-100 translate-middle badge rounded-pill bg-danger" style="font-size: 0.5rem; padding: 4px;">
                            <i class="bi bi-slash-circle"></i>
                        </span>
                        {% endif %}
                    </div>
                    <div class="flex-grow-1 overflow-hidden">
                        <div class="d-flex justify-content-between">
                            <span class="fw-semibold text-truncate {% if user.blocked %}text-danger{% endif %}">{{ user.name }}</span>
                            <span class="small text-secondary" style="font-size: 0.75rem">{{ user.time }}</span>
                        </div>
                        <div class="d-flex justify-content-between align-items-center">
                            <span class="small text-secondary text-truncate" style="max-width: 140px;">
                                {{ user.username }}
                            </span>
                            {% if user.blocked %}
                            <span class="badge bg-danger bg-opacity-10 text-danger" style="font-size: 0.6rem">BLOCKED</span>
                            {% endif %}
                        </div>
                    </div>
                </a>
                {% endfor %}
            </div>
        </div>

        <!-- Chat Area -->
        <div class="chat-area">
            {% if current_chat_id %}
            <div class="chat-header">
                <div class="d-flex align-items-center gap-3">
                    <div class="avatar">{{ current_user_initials }}</div>
                    <div>
                        <div class="d-flex align-items-center gap-2">
                            <h6 class="m-0 fw-bold">{{ current_user_name }}</h6>
                            {% if current_user_blocked %}
                            <span class="badge bg-danger">🚫 BLOCKED</span>
                            {% endif %}
                        </div>
                        <span class="small text-secondary">ID: {{ current_chat_id }}</span>
                    </div>
                </div>
                <a href="/?chat_id={{ current_chat_id }}" class="btn btn-icon text-secondary" title="Yangilash">
                    <i class="bi bi-arrow-clockwise fs-4"></i>
                </a>
            </div>

            <div class="chat-messages" id="chatContainer">
                {% if messages %}
                    {% for msg in messages %}
                    <div class="message {{ msg.role }}">
                        {% if msg.type != 'text' %}
                        <div class="d-flex align-items-center gap-2 mb-1">
                            <span class="badge bg-secondary" style="font-size: 0.6rem">{{ msg.type|upper }}</span>
                        </div>
                        {% endif %}
                        
                        <div style="white-space: pre-wrap;">{{ msg.content }}</div>
                        
                        {% if msg.file_info %}
                        <div class="badge-file">
                            {% if msg.type == 'photo' %}
                                <i class="bi bi-image fs-4 text-primary"></i>
                            {% elif msg.type == 'video' %}
                                <i class="bi bi-camera-video fs-4 text-danger"></i>
                            {% elif msg.type == 'audio' %}
                                <i class="bi bi-mic fs-4 text-success"></i>
                            {% else %}
                                <i class="bi bi-file-earmark-text fs-4 text-secondary"></i>
                            {% endif %}
                            
                            <div class="overflow-hidden w-100">
                                <div class="fw-bold text-truncate">{{ msg.file_info.file_name }}</div>
                                <small class="text-secondary opacity-75 d-block mb-1">
                                    {% if msg.type == 'photo' %}Rasm fayl{% elif msg.type == 'video' %}Video fayl{% elif msg.type == 'audio' %}Audio xabar{% else %}Hujjat{% endif %}
                                </small>
                                
                                {% if msg.file_info.file_url %}
                                    {% if msg.type == 'photo' %}
                                    <div class="mt-2">
                                        <a href="{{ msg.file_info.file_url }}" target="_blank">
                                            <img src="{{ msg.file_info.file_url }}" class="img-fluid rounded" style="max-height: 200px; width: auto;" alt="Rasm">
                                        </a>
                                    </div>
                                    {% elif msg.type == 'audio' %}
                                    <div class="mt-2">
                                        <audio controls class="w-100">
                                            <source src="{{ msg.file_info.file_url }}">
                                            Your browser does not support the audio element.
                                        </audio>
                                    </div>
                                    {% elif msg.type == 'video' %}
                                    <div class="mt-2">
                                        <video controls class="w-100 rounded" style="max-height: 240px;">
                                            <source src="{{ msg.file_info.file_url }}">
                                            Your browser does not support the video element.
                                        </video>
                                    </div>
                                    {% else %}
                                    <div class="mt-2">
                                        <a href="{{ msg.file_info.file_url }}" target="_blank" class="btn btn-sm btn-outline-primary">
                                            <i class="bi bi-download me-1"></i> Yuklab olish
                                        </a>
                                    </div>
                                    {% endif %}
                                {% else %}
                                    <small class="text-muted fst-italic">Fayl saqlanmagan</small>
                                {% endif %}
                            </div>
                        </div>
                        {% endif %}
                        
                        <span class="timestamp">
                            {{ msg.timestamp }}
                            {% if msg.role == 'user' %}<i class="bi bi-check2-all ms-1 text-primary"></i>{% endif %}
                        </span>
                    </div>
                    {% endfor %}
                {% else %}
                    <div class="empty-state">
                        <i class="bi bi-chat-dots fs-1 mb-3 opacity-50"></i>
                        <h5>Xabarlar yo'q</h5>
                        <p>Bu foydalanuvchi bilan hali suhbat bo'lmagan.</p>
                    </div>
                {% endif %}
            </div>
            {% else %}
            <div class="empty-state">
                <div class="mb-4">
                    <div class="avatar" style="width: 80px; height: 80px; font-size: 2rem; margin: 0 auto;">
                        <i class="bi bi-robot"></i>
                    </div>
                </div>
                <h3>AQLJON Dashboard</h3>
                <p>Suhbat tarixini ko'rish uchun chap tomondan foydalanuvchini tanlang.</p>
                <div class="mt-4 d-flex gap-3 text-secondary small">
                    <span><i class="bi bi-lock me-1"></i>Secure</span>
                    <span><i class="bi bi-lightning me-1"></i>Real-time</span>
                </div>
            </div>
            {% endif %}
        </div>
    </div>

    <script>
        // Scroll to bottom logic with memory
        const chatContainer = document.getElementById('chatContainer');
        
        // Restore scroll position or go to bottom
        if (chatContainer) {
            const savedScroll = sessionStorage.getItem('chatScroll');
            if (savedScroll && {{ 'true' if current_chat_id else 'false' }}) {
                // If we were viewing this chat, restore position (or if it was near bottom, stick to bottom)
                const isNearBottom = (chatContainer.scrollHeight - chatContainer.scrollTop - chatContainer.clientHeight) < 100;
                if (!isNearBottom) {
                    chatContainer.scrollTop = savedScroll;
                } else {
                    chatContainer.scrollTop = chatContainer.scrollHeight;
                }
            } else {
                chatContainer.scrollTop = chatContainer.scrollHeight;
            }
            
            // Save scroll on change
            chatContainer.addEventListener('scroll', () => {
                sessionStorage.setItem('chatScroll', chatContainer.scrollTop);
            });
        }

        // Theme Toggle Logic
        function toggleTheme() {
            const html = document.documentElement;
            const currentTheme = html.getAttribute('data-theme');
            const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
            html.setAttribute('data-theme', newTheme);
            localStorage.setItem('theme', newTheme);
            updateThemeIcon(newTheme);
        }

        function updateThemeIcon(theme) {
            const icon = document.querySelector('.theme-toggle i');
            if (theme === 'dark') {
                icon.classList.remove('bi-moon-stars');
                icon.classList.add('bi-sun');
            } else {
                icon.classList.remove('bi-sun');
                icon.classList.add('bi-moon-stars');
            }
        }

        // Load saved theme
        const savedTheme = localStorage.getItem('theme') || 'light';
        document.documentElement.setAttribute('data-theme', savedTheme);
        updateThemeIcon(savedTheme);

        // Search Filter
        document.getElementById('userSearch').addEventListener('keyup', function(e) {
            const val = e.target.value.toLowerCase();
            document.querySelectorAll('.user-item').forEach(el => {
                const name = el.innerText.toLowerCase();
                el.style.display = name.includes(val) ? 'flex' : 'none';
            });
        });

        // Auto Refresh Logic (Every 10 seconds)
        {% if current_chat_id %}
        setInterval(() => {
            // Reload page to get new messages
            window.location.reload();
        }, 10000);
        {% endif %}
    </script>
</body>
</html>
        """,
        'login.html': """
<!DOCTYPE html>
<html lang="uz">
<head>
    <title>Login - AQLJON Admin</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { background: #f0f2f5; display: flex; align-items: center; justify-content: center; height: 100vh; font-family: 'Segoe UI', sans-serif; }
        .login-card { width: 100%; max-width: 380px; padding: 40px; background: white; border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.08); text-align: center; }
        .logo { width: 60px; height: 60px; background: #0d6efd; border-radius: 50%; display: flex; align-items: center; justify-content: center; color: white; font-size: 24px; margin: 0 auto 20px; }
    </style>
</head>
<body>
    <div class="login-card">
        <div class="logo">🤖</div>
        <h4 class="mb-4 fw-bold">Admin Panel</h4>
        
        {% if error %}
        <div class="alert alert-danger py-2 mb-3">{{ error }}</div>
        {% endif %}
        
        <form method="post" action="/login">
            <div class="mb-3">
                <input type="password" name="password" class="form-control form-control-lg" placeholder="Parolni kiriting" required style="font-size: 16px;">
            </div>
            <button type="submit" class="btn btn-primary w-100 btn-lg fw-semibold">Kirish</button>
        </form>
    </div>
</body>
</html>
        """
    })
    
    aiohttp_jinja2.setup(app, loader=loader)

    # Routes
    app.router.add_get('/', index)
    app.router.add_get('/login', login_page)
    app.router.add_post('/login', login_post)
    app.router.add_get('/logout', logout)

    # Store memory manager in app
    app['memory'] = memory_manager

async def check_auth(request):
    session = request.cookies.get('admin_session')
    if session == ADMIN_PASSWORD:
        return True
    return False

async def login_page(request):
    return aiohttp_jinja2.render_template('login.html', request, {})

async def login_post(request):
    data = await request.post()
    password = data.get('password')
    
    if password == ADMIN_PASSWORD:
        response = web.HTTPFound('/')
        response.set_cookie('admin_session', password, max_age=86400 * 30) # 30 days
        return response
    
    return aiohttp_jinja2.render_template('login.html', request, {'error': "Noto'g'ri parol!"})

async def logout(request):
    response = web.HTTPFound('/login')
    response.del_cookie('admin_session')
    return response

async def index(request):
    if not await check_auth(request):
        return web.HTTPFound('/login')
    
    memory = request.app['memory']
    chat_id = request.query.get('chat_id')
    
    users_list = []
    
    if memory.db:
        try:
            # Simple fetch without composite sort to avoid index error
            users_ref = memory.db.collection('users')
            # Stream all
            docs = users_ref.stream()
            
            all_users = []
            for doc in docs:
                data = doc.to_dict()
                info = data.get('info', {})
                first_name = info.get('first_name', '') or ''
                last_name = info.get('last_name', '') or ''
                name = f"{first_name} {last_name}".strip() or "Noma'lum"
                initials = (first_name[:1] + last_name[:1]).upper() if name != "Noma'lum" else "?"
                
                updated_at = data.get('last_updated')
                timestamp = 0
                time_str = ""
                if updated_at:
                    try:
                        timestamp = updated_at.timestamp()
                        time_str = updated_at.strftime("%d/%m")
                    except:
                        pass

                all_users.append({
                    'chat_id': doc.id,
                    'name': name,
                    'initials': initials,
                    'username': f"@{info.get('username')}" if info.get('username') else "",
                    'time': time_str,
                    'timestamp': timestamp,
                    'role': 'user',
                    'blocked': data.get('blocked', False)
                })
            
            # Python Sort: Newest active first
            users_list = sorted(all_users, key=lambda x: x['timestamp'], reverse=True)[:100]
            
        except Exception as e:
            logger.error(f"Error fetching users: {e}")
    
    messages = []
    current_user_name = "Tanlanmagan"
    current_user_initials = "?"
    current_user_blocked = False
    
    if chat_id and memory.db:
        # NO COMPLEX SORT IN QUERY to fix index error permanently
        # Fetch logs for this user, then sort in Python
        try:
            logs_ref = memory.db.collection('chat_logs').where('chat_id', '==', chat_id)
            log_docs = logs_ref.stream()
            
            raw_msgs = []
            for doc in log_docs:
                data = doc.to_dict()
                ts = data.get('timestamp')
                timestamp_val = 0
                ts_str = ""
                
                if ts:
                    try:
                        timestamp_val = ts.timestamp()
                        ts_str = ts.strftime("%H:%M | %d-%b")
                    except:
                        pass
                
                raw_msgs.append({
                    'role': data.get('role', 'user'),
                    'content': data.get('content', ''),
                    'type': data.get('type', 'text'),
                    'timestamp_val': timestamp_val,
                    'timestamp': ts_str,
                    'file_info': data.get('file_info')
                })
            
            # Python Sort: Oldest to Newest
            messages = sorted(raw_msgs, key=lambda x: x['timestamp_val'])
                
            # Get user info
            if chat_id in memory.user_info:
                 info = memory.user_info[chat_id]
                 first = info.get('first_name','') or ''
                 last = info.get('last_name','') or ''
                 current_user_name = f"{first} {last}".strip()
                 current_user_initials = (first[:1] + last[:1]).upper()
            
            # Check blocked status
            if chat_id in memory.blocked_users:
                current_user_blocked = True
                 
        except Exception as e:
            logger.error(f"Error fetching logs: {e}")
            messages.append({'role': 'bot', 'content': f"Error: {e}", 'type': 'error'})

    context = {
        'total_users': len(users_list),
        'users': users_list,
        'current_chat_id': chat_id,
        'current_user_name': current_user_name,
        'current_user_initials': current_user_initials,
        'current_user_blocked': current_user_blocked,
        'messages': messages
    }
    
    return aiohttp_jinja2.render_template('index.html', request, context)