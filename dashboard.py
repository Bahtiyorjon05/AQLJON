import os
import asyncio
import logging
from aiohttp import web
import aiohttp_jinja2
import jinja2
from datetime import datetime

logger = logging.getLogger(__name__)

# Basic Admin Password (change via environment variable for security)
ADMIN_PASSWORD = os.getenv("DASHBOARD_PASSWORD", "admin123")

def setup_dashboard(app, memory_manager):
    """Setup the dashboard routes and templates"""
    
    # Setup Jinja2 template loader
    # We'll use a string loader for simplicity so we don't need extra files
    loader = jinja2.DictLoader({
        'index.html': """
<!DOCTYPE html>
<html lang="uz">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AQLJON Dashboard</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { background-color: #f8f9fa; }
        .chat-container { max-height: 600px; overflow-y: auto; background: white; border-radius: 10px; padding: 20px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        .message { margin-bottom: 15px; padding: 10px; border-radius: 10px; max-width: 80%; }
        .message.user { background-color: #e3f2fd; margin-left: auto; text-align: right; }
        .message.bot { background-color: #f1f0f0; margin-right: auto; }
        .timestamp { font-size: 0.8em; color: #888; margin-top: 5px; }
        .user-list { max-height: 600px; overflow-y: auto; }
        .user-item { cursor: pointer; transition: 0.2s; }
        .user-item:hover { background-color: #e9ecef; }
        .user-item.active { background-color: #0d6efd; color: white; }
    </style>
</head>
<body>
    <nav class="navbar navbar-dark bg-dark mb-4">
        <div class="container-fluid">
            <span class="navbar-brand mb-0 h1">🤖 AQLJON Admin Dashboard</span>
            <span class="text-light">Jami foydalanuvchilar: {{ total_users }}</span>
            <a href="/logout" class="btn btn-outline-light btn-sm">Chiqish</a>
        </div>
    </nav>

    <div class="container-fluid">
        <div class="row">
            <!-- User List -->
            <div class="col-md-3 mb-4">
                <div class="card">
                    <div class="card-header">Foydalanuvchilar</div>
                    <ul class="list-group list-group-flush user-list">
                        {% for user in users %}
                        <a href="/?chat_id={{ user.chat_id }}" class="list-group-item list-group-item-action user-item {% if current_chat_id == user.chat_id %}active{% endif %}">
                            <div class="d-flex w-100 justify-content-between">
                                <h6 class="mb-1">{{ user.name }}</h6>
                                <small>{{ user.time }}</small>
                            </div>
                            <small class="text-truncate d-block">{{ user.username }}</small>
                        </a>
                        {% endfor %}
                    </ul>
                </div>
            </div>

            <!-- Chat View -->
            <div class="col-md-9">
                {% if current_chat_id %}
                <div class="card">
                    <div class="card-header d-flex justify-content-between align-items-center">
                        <span>Chat: {{ current_user_name }} ({{ current_chat_id }})</span>
                        <a href="/?chat_id={{ current_chat_id }}" class="btn btn-sm btn-primary">🔄 Yangilash</a>
                    </div>
                    <div class="card-body chat-container">
                        {% if messages %}
                            {% for msg in messages %}
                            <div class="message {{ msg.role }}">
                                <div>
                                    <strong>{% if msg.role == 'user' %}👤 User{% else %}🤖 Bot{% endif %}</strong>
                                    {% if msg.type != 'text' %}
                                    <span class="badge bg-secondary">{{ msg.type }}</span>
                                    {% endif %}
                                </div>
                                <div class="mt-1" style="white-space: pre-wrap;">{{ msg.content }}</div>
                                {% if msg.file_info %}
                                <div class="mt-2 p-2 border rounded bg-light">
                                    <small>📁 File: {{ msg.file_info.file_name }}</small>
                                </div>
                                {% endif %}
                                <div class="timestamp">{{ msg.timestamp }}</div>
                            </div>
                            {% endfor %}
                        {% else %}
                            <div class="text-center text-muted mt-5">
                                <p>Hozircha xabarlar yo'q.</p>
                            </div>
                        {% endif %}
                    </div>
                </div>
                {% else %}
                <div class="alert alert-info text-center">
                    👈 Chap tomondan foydalanuvchini tanlang
                </div>
                {% endif %}
            </div>
        </div>
    </div>
</body>
</html>
        """,
        'login.html': """
<!DOCTYPE html>
<html>
<head>
    <title>Login - AQLJON</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { background-color: #f0f2f5; display: flex; align-items: center; justify-content: center; height: 100vh; }
        .login-card { width: 100%; max-width: 400px; padding: 20px; }
    </style>
</head>
<body>
    <div class="card login-card shadow">
        <div class="card-body">
            <h4 class="card-title text-center mb-4">🔐 Admin Kirish</h4>
            {% if error %}
            <div class="alert alert-danger">{{ error }}</div>
            {% endif %}
            <form method="post" action="/login">
                <div class="mb-3">
                    <label>Parol</label>
                    <input type="password" name="password" class="form-control" required>
                </div>
                <button type="submit" class="btn btn-primary w-100">Kirish</button>
            </form>
        </div>
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

    # Store memory manager in app for access in handlers
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
        response.set_cookie('admin_session', password, max_age=86400) # 1 day
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
    
    # Fetch users list from memory/firestore
    users_list = []
    
    if memory.db:
        # Get users with recent activity
        # Note: In a real large app, you'd want pagination here
        users_ref = memory.db.collection('users').order_by('last_updated', direction='DESCENDING').limit(50)
        docs = users_ref.stream()
        
        for doc in docs:
            data = doc.to_dict()
            info = data.get('info', {})
            name = f"{info.get('first_name', '')} {info.get('last_name', '')}".strip() or "Noma'lum"
            username = f"@{info.get('username')}" if info.get('username') else ""
            
            # Format time
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
                'username': username,
                'time': time_str
            })
    else:
        # Fallback to local memory stats if DB not available (though you said it is)
        for uid, stats in memory.user_stats.items():
            info = memory.user_info.get(uid, {})
            users_list.append({
                'chat_id': uid,
                'name': info.get('first_name', 'User'),
                'username': str(uid),
                'time': 'Local'
            })

    # Fetch chat logs if chat_id selected
    messages = []
    current_user_name = "Unknown"
    
    if chat_id and memory.db:
        # Simple query: fetch logs where chat_id matches, sort by timestamp
        # Note: Firestore needs a composite index for this potentially.
        # Alternatively, query by ID prefix since we used timestamp_chatid as ID? 
        # Better: Query the 'chat_logs' collection where chat_id == selected
        
        logs_ref = memory.db.collection('chat_logs').where('chat_id', '==', chat_id).order_by('timestamp', direction='ASCENDING').limit(100)
        
        try:
            log_docs = logs_ref.stream()
            for doc in log_docs:
                data = doc.to_dict()
                ts = data.get('timestamp')
                ts_str = ""
                if ts:
                    try:
                        ts_str = ts.strftime("%Y-%m-%d %H:%M:%S")
                    except:
                        pass
                
                messages.append({
                    'role': data.get('role', 'user'),
                    'content': data.get('content', ''),
                    'type': data.get('type', 'text'),
                    'timestamp': ts_str,
                    'file_info': data.get('file_info')
                })
                
            # Get user name
            if chat_id in memory.user_info:
                 info = memory.user_info[chat_id]
                 current_user_name = f"{info.get('first_name','')} {info.get('last_name','')}"
                 
        except Exception as e:
            logger.error(f"Error fetching logs: {e}")
            messages.append({'role': 'bot', 'content': f"Error loading logs: {e}", 'type': 'error'})

    context = {
        'total_users': len(users_list),
        'users': users_list,
        'current_chat_id': chat_id,
        'current_user_name': current_user_name,
        'messages': messages
    }
    
    return aiohttp_jinja2.render_template('index.html', request, context)
