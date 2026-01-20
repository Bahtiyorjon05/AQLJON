from aiohttp import web
import logging
import json

logger = logging.getLogger(__name__)

async def handle_root(request):
    """Serve a simple status page"""
    try:
        memory_manager = request.app.get('memory_manager')
        
        stats = {
            "status": "online",
            "total_users": len(memory_manager.user_stats) if memory_manager else 0,
            "active_sessions": len(memory_manager.user_history) if memory_manager else 0,
            "blocked_users": len(memory_manager.blocked_users) if memory_manager else 0,
        }
        
        return web.json_response(stats)
    except Exception as e:
        logger.error(f"Error serving dashboard: {e}")
        return web.Response(text="Dashboard Error", status=500)

def setup_dashboard(app, memory_manager):
    """Setup the dashboard routes and context"""
    try:
        app['memory_manager'] = memory_manager
        app.router.add_get('/', handle_root)
        logger.info("Dashboard module initialized")
    except Exception as e:
        logger.error(f"Failed to setup dashboard: {e}")
