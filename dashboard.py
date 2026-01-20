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
<html lang="uz" data-bs-theme="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AQLJON Admin Dashboard</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.1/font/bootstrap-icons.css">
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #212529; }
        .sidebar { height: calc(100vh - 70px); overflow-y: auto; border-right: 1px solid #495057; }
        .main-content { height: calc(100vh - 70px); overflow-y: hidden; display: flex; flex-direction: column; }
        .chat-container { flex-grow: 1; overflow-y: auto; padding: 20px; background-color: #2b3035; }
        .user-item { border-left: 3px solid transparent; transition: all 0.2s; }
        .user-item:hover { background-color: #343a40; border-left-color: #6c757d; }
        .user-item.active { background-color: #343a40; border-left-color: #0d6efd; }
        .message { max-width: 85%; margin-bottom: 15px; padding: 12px 16px; border-radius: 12px; position: relative; }
        .message.user { background-color: #0d6efd; color: white; margin-left: auto; border-bottom-right-radius: 4px; }
        .message.bot { background-color: #343a40; color: #e9ecef; margin-right: auto; border-bottom-left-radius: 4px; border: 1px solid #495057; }
        .timestamp { font-size: 0.75rem; opacity: 0.7; margin-top: 4px; text-align: right; }
        .file-attachment { background: rgba(0,0,0,0.2); padding: 8px; border-radius: 8px; margin-top: 8px; display: flex; align-items: center; gap: 10px; }
        .avatar { width: 40px; height: 40px; border-radius: 50%; background: #6c757d; display: flex; align-items: center; justify-content: center; font-weight: bold; color: white; }
        .navbar-brand { font-weight: 700; letter-spacing: 0.5px; }
        ::-webkit-scrollbar { width: 8px; }
        ::-webkit-scrollbar-track { background: #212529; }
        ::-webkit-scrollbar-thumb { background: #495057; border-radius: 4px; }
        ::-webkit-scrollbar-thumb:hover { background: #6c757d; }
    </style>
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-dark bg-dark border-bottom border-secondary sticky-top" style="height: 70px;">
        <div class="container-fluid px-4">
            <a class="navbar-brand" href="/"><i class="bi bi-robot me-2"></i>AQLJON <span class="text-primary">ADMIN</span></a>
            <div class="d-flex align-items-center gap-3">
                <span class="badge bg-primary rounded-pill"><i class="bi bi-people-fill me-1"></i>{{ total_users }} Users</span>
                <a href="/logout" class="btn btn-outline-danger btn-sm"><i class="bi bi-box-arrow-right me-1"></i>Chiqish</a>
            </div>
        </div>
    </nav>

    <div class="container-fluid">
        <div class="row">
            <!-- Sidebar: User List -->
            <div class="col-md-3 sidebar p-0">
                <div class="p-3 border-bottom border-secondary bg-dark sticky-top">
                    <input type="text" class="form-control form-control-sm bg-dark text-light border-secondary" placeholder="Foydalanuvchi qidirish..." id="userSearch">
                </div>
                <div class="list-group list-group-flush" id="userList">
                    {% for user in users %}
                    <a href="/?chat_id={{ user.chat_id }}" class="list-group-item list-group-item-action bg-dark text-light user-item {% if current_chat_id == user.chat_id %}active{% endif %}">
                        <div class="d-flex align-items-center gap-3">
                            <div class="avatar bg-gradient">{{ user.initials }}</div>
                            <div class="flex-grow-1 overflow-hidden">
                                <div class="d-flex justify-content-between align-items-baseline">
                                    <h6 class="mb-0 text-truncate">{{ user.name }}</h6>
                                    <small class="text-secondary" style="font-size: 0.7rem;">{{ user.time }}</small>
                                </div>
                                <small class="text-secondary text-truncate d-block">{{ user.username }}</small>
                            </div>
                        </div>
                    </a>
                    {% endfor %}
                </div>
            </div>

            <!-- Main Content: Chat View -->
            <div class="col-md-9 main-content p-0">
                {% if current_chat_id %}
                <div class="d-flex justify-content-between align-items-center p-3 border-bottom border-secondary bg-dark">
                    <div class="d-flex align-items-center gap-3">
                        <div class="avatar bg-primary">{{ current_user_initials }}</div>
                        <div>
                            <h5 class="mb-0">{{ current_user_name }}</h5>
                            <small class="text-secondary">ID: {{ current_chat_id }}</small>
                        </div>
                    </div>
                    <a href="/?chat_id={{ current_chat_id }}" class="btn btn-sm btn-outline-primary"><i class="bi bi-arrow-clockwise me-1"></i>Yangilash</a>
                </div>
                
                <div class="chat-container" id="chatContainer">
                    {% if messages %}
                        {% for msg in messages %}
                        <div class="message {{ msg.role }} shadow-sm">
                            <div class="d-flex justify-content-between align-items-center mb-1">
                                <small class="fw-bold" style="font-size: 0.75rem; opacity: 0.8;">
                                    {% if msg.role == 'user' %}Foydalanuvchi{% else %}AQLJON{% endif %}
                                </small>
                                {% if msg.type != 'text' %}
                                <span class="badge bg-light text-dark" style="font-size: 0.6rem;">{{ msg.type|upper }}</span>
                                {% endif %}
                            </div>
                            
                            <div style="white-space: pre-wrap; line-height: 1.5;">{{ msg.content }}</div>
                            
                            {% if msg.file_info %}
                            <div class="file-attachment">
                                <i class="bi bi-file-earmark-text fs-4"></i>
                                <div class="overflow-hidden">
                                    <div class="fw-bold text-truncate">{{ msg.file_info.file_name }}</div>
                                    <small class="text-white-50">Biriktirilgan fayl</small>
                                </div>
                            </div>
                            {% endif %}
                            
                            <div class="timestamp">{{ msg.timestamp }}</div>
                        </div>
                        {% endfor %}
                    {% else %}
                        <div class="d-flex flex-column align-items-center justify-content-center h-100 text-secondary">
                            <i class="bi bi-chat-square-dots fs-1 mb-3"></i>
                            <p>Hozircha xabarlar tarixi mavjud emas.</p>
                        </div>
                    {% endif %}
                </div>
                {% else %}
                <div class="d-flex flex-column align-items-center justify-content-center h-100 text-secondary">
                    <i class="bi bi-arrow-left-circle fs-1 mb-3"></i>
                    <h4>Xush kelibsiz!</h4>
                    <p>Chap tomondan foydalanuvchini tanlang.</p>
                </div>
                {% endif %}
            </div>
        </div>
    </div>

    <script>
        // Auto-scroll to bottom
        const chatContainer = document.getElementById('chatContainer');
        if (chatContainer) {
            chatContainer.scrollTop = chatContainer.scrollHeight;
        }

        // Search functionality
        document.getElementById('userSearch').addEventListener('keyup', function(e) {
            const searchText = e.target.value.toLowerCase();
            const users = document.querySelectorAll('.user-item');
            users.forEach(user => {
                const name = user.innerText.toLowerCase();
                if (name.includes(searchText)) {
                    user.classList.remove('d-none');
                } else {
                    user.classList.add('d-none');
                }
            });
        });
    </script>
</body>
</html>
        """,
        'login.html': """
<!DOCTYPE html>
<html lang="uz" data-bs-theme="dark">
<head>
    <title>Login - AQLJON Admin</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { background-color: #212529; display: flex; align-items: center; justify-content: center; height: 100vh; }
        .login-card { width: 100%; max-width: 400px; padding: 30px; background: #2b3035; border-radius: 15px; border: 1px solid #495057; }
    </style>
</head>
<body>
    <div class="login-card shadow-lg">
        <div class="text-center mb-4">
            <h3 class="fw-bold text-light">🤖 AQLJON</h3>
            <p class="text-secondary">Admin Panelga Kirish</p>
        </div>
        
        {% if error %}
        <div class="alert alert-danger py-2">{{ error }}</div>
        {% endif %}
        
        <form method="post" action="/login">
            <div class="mb-4">
                <label class="form-label text-secondary">Parol</label>
                <input type="password" name="password" class="form-control bg-dark text-light border-secondary form-control-lg" placeholder="••••••••" required>
            </div>
            <button type="submit" class="btn btn-primary w-100 btn-lg">Kirish</button>
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
            users_ref = memory.db.collection('users').order_by('last_updated', direction='DESCENDING').limit(50)
            docs = users_ref.stream()
            
            for doc in docs:
                data = doc.to_dict()
                info = data.get('info', {})
                first_name = info.get('first_name', '') or ''
                last_name = info.get('last_name', '') or ''
                name = f"{first_name} {last_name}".strip() or "Noma'lum"
                initials = (first_name[:1] + last_name[:1]).upper() if name != "Noma'lum" else "?"
                
                updated_at = data.get('last_updated')
                time_str = ""
                if updated_at:
                    try:
                        time_str = updated_at.strftime("%H:%M %d/%m")
                    except:
                        pass

                users_list.append({
                    'chat_id': doc.id,
                    'name': name,
                    'initials': initials,
                    'username': f"@{info.get('username')}" if info.get('username') else "",
                    'time': time_str
                })
        except Exception as e:
            logger.error(f"Error fetching users: {e}")
    
    # Sort users: active chat first, then by time
    # (Firestore already sorted by time, just ensuring stability)

    messages = []
    current_user_name = "Unknown"
    current_user_initials = "?"
    
    if chat_id and memory.db:
        # Optimized query with fallback if index missing
        logs_ref = memory.db.collection('chat_logs').where('chat_id', '==', chat_id).order_by('timestamp', direction='ASCENDING').limit(100)
        
        try:
            log_docs = logs_ref.stream()
            for doc in log_docs:
                data = doc.to_dict()
                ts = data.get('timestamp')
                ts_str = ""
                if ts:
                    try:
                        ts_str = ts.strftime("%H:%M | %d-%b")
                    except:
                        pass
                
                messages.append({
                    'role': data.get('role', 'user'),
                    'content': data.get('content', ''),
                    'type': data.get('type', 'text'),
                    'timestamp': ts_str,
                    'file_info': data.get('file_info')
                })
                
            # Get user info for header
            if chat_id in memory.user_info:
                 info = memory.user_info[chat_id]
                 first = info.get('first_name','') or ''
                 last = info.get('last_name','') or ''
                 current_user_name = f"{first} {last}".strip()
                 current_user_initials = (first[:1] + last[:1]).upper()
                 
        except Exception as e:
            logger.error(f"Error fetching logs: {e}")
            messages.append({'role': 'bot', 'content': f"⚠️ Xatolik: Xabarlarni yuklab bo'lmadi. Index yaratilmoqdami? ({e})", 'type': 'error'})

    context = {
        'total_users': len(users_list),
        'users': users_list,
        'current_chat_id': chat_id,
        'current_user_name': current_user_name,
        'current_user_initials': current_user_initials,
        'messages': messages
    }
    
    return aiohttp_jinja2.render_template('index.html', request, context)