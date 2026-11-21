"""
Async REST API Backend for A2 TV App.
Powered by aiohttp.web with CORS support and JSON endpoints.
"""

import os
import sys
import time
import json
from aiohttp import web
from config import API_HOST, API_PORT, APP_PACKAGE, CURRENT_APP_VERSION_CODE
from database import db

# CORS Middleware to allow requests from Android WebView
@web.middleware
async def cors_middleware(request, handler):
    if request.method == "OPTIONS":
        response = web.Response(status=200)
    else:
        try:
            response = await handler(request)
        except web.HTTPException as ex:
            response = ex
        except Exception as e:
            response = web.json_response({
                "status": "error",
                "message": str(e)
            }, status=500)

    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Requested-With, X-Admin-Key"
    return response

DEFAULT_MAINTENANCE_MSG = "التطبيق تحت الصيانة حالياً، نعمل على تحسين تجربتك. يرجى المحاولة لاحقاً"

# Endpoints that are always open and NEVER blocked by maintenance
PROTECTED_ENDPOINTS = set()

@web.middleware
async def maintenance_middleware(request, handler):
    # Public API endpoints (/api/categories, /api/channels, /api/app-config) are always accessible
    return await handler(request)

def json_ar(data, status=200):
    return web.json_response(data, status=status, dumps=lambda obj: json.dumps(obj, ensure_ascii=False))

# Routes Handlers
async def handle_health(request):
    return json_ar({
        "status": "ok",
        "healthy": True,
        "service": "A2 TV API & Bot",
        "timestamp": int(time.time())
    })

async def handle_root(request):
    return json_ar({
        "status": "online",
        "service": "A2 TV Backend API & Telegram Bot",
        "version": "2.0.0",
        "package": APP_PACKAGE,
        "endpoints": {
            "health": "/health",
            "app_config": "/api/app-config",
            "channels": "/api/channels",
            "categories": "/api/categories",
            "maintenance": "/api/maintenance",
            "update": "/api/update",
            "channel_apis": "/api/channel-apis"
        }
    })

async def handle_app_config(request):
    """Returns combined app configuration (maintenance, update, and channels overview)."""
    maintenance = db.get_maintenance()
    update_info = db.get_app_update()
    channels = db.get_channels()
    categories = db.get_categories()
    latest_notif = sanitize_notif(db.get_latest_notification())
    sound_info = db.get_notification_sound()
    apis = db.get_channel_apis()

    return json_ar({
        "status": "success",
        "package": APP_PACKAGE,
        "maintenance": maintenance,
        "update": update_info,
        "notification": latest_notif,
        "notification_sound": sanitize_url(sound_info.get("url", "")),
        "notification_sound_name": sound_info.get("name", "افتراضي"),
        "counts": {
            "channels": len(channels),
            "categories": len(categories),
            "apis": len(apis)
        }
    })

from config import API_HOST, API_PORT, APP_PACKAGE, CURRENT_APP_VERSION_CODE, PUBLIC_URL
import os

def sanitize_url(u):
    if not u or not isinstance(u, str):
        return u
    u = u.strip()
    if not u:
        return ""
    if "/static/uploads/" in u:
        fn = u.split("/static/uploads/", 1)[1]
        return f"{PUBLIC_URL}/static/uploads/{fn}"
    if "/uploads/" in u:
        fn = u.split("/uploads/", 1)[1]
        return f"{PUBLIC_URL}/static/uploads/{fn}"
    if u.startswith("/static/"):
        return f"{PUBLIC_URL}{u}"
    if u.startswith("http://0.0.0.0:8080") or u.startswith("http://127.0.0.1:8080"):
        part = u.split(":8080", 1)[1]
        return f"{PUBLIC_URL}{part}"
    for old_host in ["maj83bd-production.up.railway.app"]:
        if old_host in u:
            part = u.split(old_host, 1)[1]
            return f"{PUBLIC_URL}{part}"
    return u

def sanitize_notif(n):
    if not n or not isinstance(n, dict):
        return n
    res = dict(n)
    if "image" in res:
        res["image"] = sanitize_url(res["image"])
    if "sound" in res:
        res["sound"] = sanitize_url(res["sound"])
    return res

async def handle_categories(request):
    """Returns channel categories, optionally filtered by api_id."""
    api_id = request.query.get("api_id", None)
    include_hidden = request.query.get("include_hidden", "false").lower() in ("true", "1")
    categories = db.get_categories(api_id)
    if not include_hidden:
        categories = [c for c in categories if not c.get("hidden", False)]
    
    # Sanitize category image URLs
    for c in categories:
        if c.get("image"):
            c["image"] = sanitize_url(c["image"])

    return json_ar({
        "status": "success",
        "count": len(categories),
        "filter_api": api_id or "all",
        "categories": categories
    })

async def handle_channels(request):
    """Returns all channels or filtered by category, api_id, or search query."""
    category = request.query.get("category", None)
    api_id = request.query.get("api_id", None)
    search_q = request.query.get("q", request.query.get("search", None))
    include_disabled = request.query.get("include_disabled", "false").lower() in ("true", "1")

    if search_q:
        channels = db.search_channels(search_q, category)
    else:
        channels = db.get_channels(category)

    if not include_disabled:
        channels = [c for c in channels if not c.get("disabled", False)]

    if api_id and api_id != "all":
        channels = [c for c in channels if c.get("api_id") == api_id]

    # Sanitize channel logos
    for ch in channels:
        if ch.get("logo"):
            ch["logo"] = sanitize_url(ch["logo"])

    return json_ar({
        "status": "success",
        "filter": category or "all",
        "filter_api": api_id or "all",
        "search": search_q or "",
        "count": len(channels),
        "channels": channels
    })

async def handle_export_m3u(request):
    """Exports all active channels in standard IPTV M3U format."""
    category = request.query.get("category", None)
    m3u_text = db.export_channels_m3u(category)
    return web.Response(
        text=m3u_text,
        content_type="audio/x-mpegurl",
        headers={
            "Content-Disposition": 'attachment; filename="a2tv_playlist.m3u"',
            "Access-Control-Allow-Origin": "*"
        }
    )

async def handle_stats(request):
    """Returns comprehensive channel and category statistics."""
    stats = db.get_channel_stats()
    return json_ar({
        "status": "success",
        "stats": stats
    })

async def handle_maintenance(request):
    """Returns maintenance status."""
    maintenance = db.get_maintenance()
    return json_ar({
        "status": "success",
        "maintenance": maintenance
    })

async def handle_update(request):
    """Checks if there is a new update available for the app."""
    update_info = db.get_app_update()
    try:
        current_v = int(request.query.get("current_version", CURRENT_APP_VERSION_CODE))
    except (ValueError, TypeError):
        current_v = CURRENT_APP_VERSION_CODE

    has_update = update_info.get("enabled", False) and (update_info.get("version_code", 0) > current_v)

    return json_ar({
        "status": "success",
        "current_version": current_v,
        "has_update": has_update,
        "update": update_info
    })

async def handle_channel_apis(request):
    """Returns list of active channel APIs."""
    apis = db.get_channel_apis()
    return json_ar({
        "status": "success",
        "count": len(apis),
        "apis": apis
    })

async def handle_notifications(request):
    """Returns latest push notifications."""
    limit = int(request.query.get("limit", 10))
    notifs = [sanitize_notif(n) for n in db.get_notifications(limit=limit)]
    latest = sanitize_notif(db.get_latest_notification())
    sound_info = db.get_notification_sound()
    return json_ar({
        "status": "success",
        "count": len(notifs),
        "latest": latest,
        "notification_sound": sanitize_url(sound_info.get("url", "")),
        "notifications": notifs
    })

async def handle_fcm_register(request):
    """Registers or updates a client FCM device token."""
    try:
        data = await request.json()
        token = data.get("token", "").strip()
        device_id = data.get("device_id", "").strip()
        model = data.get("model", "").strip()
        version = data.get("version", "").strip()
        platform = data.get("platform", "android").strip()
        if not token:
            return json_ar({"status": "error", "message": "token is required"}, status=400)
        ok, res = db.register_device_token(token, device_id=device_id, model=model, app_version=version, platform=platform)
        return json_ar({"status": "success", "device": res})
    except Exception as e:
        return json_ar({"status": "error", "message": str(e)}, status=500)

async def handle_fcm_unregister(request):
    """Unregisters a client FCM device token."""
    try:
        data = await request.json()
        token = data.get("token", "").strip()
        if not token:
            return json_ar({"status": "error", "message": "token is required"}, status=400)
        ok = db.unregister_device_token(token)
        return json_ar({"status": "success", "unregistered": ok})
    except Exception as e:
        return json_ar({"status": "error", "message": str(e)}, status=500)

async def handle_fcm_stats(request):
    """Returns FCM device registration statistics."""
    from fcm_sender import is_firebase_configured
    tokens = db.get_all_fcm_tokens()
    return json_ar({
        "status": "success",
        "registered_devices": len(tokens),
        "firebase_configured": is_firebase_configured()
    })

# ----------------- Admin API Endpoints (Protected by SECRET_KEY) -----------------

def is_admin_request(request, body_key=None):
    from config import SECRET_KEY
    auth = request.headers.get("Authorization", "").replace("Bearer ", "").strip()
    admin_key = request.headers.get("X-Admin-Key", "").strip()
    query_key = request.query.get("token", "").strip()
    if (auth and auth == SECRET_KEY) or (admin_key and admin_key == SECRET_KEY) or (query_key and query_key == SECRET_KEY):
        return True
    if body_key and body_key == SECRET_KEY:
        return True
    return False

def notify_telegram_admin(text):
    try:
        from bot import bot, ADMIN_ID
        if bot and ADMIN_ID:
            bot.send_message(ADMIN_ID, text)
    except Exception:
        pass

async def handle_admin_verify(request):
    try:
        data = await request.json()
    except Exception:
        data = {}
    key = data.get("key", "")
    if not is_admin_request(request, body_key=key):
        return json_ar({"status": "error", "message": "مفتاح المشرف غير صحيح أو غير مصرح به"}, status=401)
    
    stats = db.get_channel_stats()
    maint = db.get_maintenance()
    update = db.get_app_update()
    return json_ar({
        "status": "success",
        "role": "super_admin",
        "server_version": "2.0.0",
        "maintenance": maint,
        "update": update,
        "stats": stats
    })

async def handle_admin_maintenance(request):
    try:
        data = await request.json()
    except Exception:
        data = {}
    key = data.get("key", "")
    if not is_admin_request(request, body_key=key):
        return json_ar({"status": "error", "message": "غير مصرح به - مفتاح المشرف مطلوب"}, status=401)
    
    enabled = bool(data.get("enabled", False))
    message = data.get("message", "التطبيق قيد الصيانة مؤقتاً")
    telegram_url = data.get("telegram_url", "https://t.me/")
    res = db.set_maintenance(enabled, message=message, admin_id="AppAdmin", theme="dark_purple")
    
    action_str = "تفعيل 🛑" if enabled else "إلغاء تفعيل 🟢"
    notify_telegram_admin(f"🛠️ <b>تنبيه من لوحة تحكم التطبيق</b>:\nتم {action_str} وضع الصيانة!\nالرسالة: {message}")
    return json_ar({
        "status": "success",
        "message": f"تم {action_str} وضع الصيانة بنجاح",
        "maintenance": res
    })

async def handle_admin_notification(request):
    try:
        data = await request.json()
    except Exception:
        data = {}
    key = data.get("key", "")
    if not is_admin_request(request, body_key=key):
        return json_ar({"status": "error", "message": "غير مصرح به - مفتاح المشرف مطلوب"}, status=401)
    
    title = data.get("title", "تنبيه من إدارة التطبيق").strip()
    message = data.get("message", "").strip()
    image = data.get("image", "").strip() or None
    send_fcm = bool(data.get("send_fcm", True))
    
    if not message:
        return json_ar({"status": "error", "message": "نص الإشعار مطلوب"}, status=400)
    
    notif_id = db.add_notification(title, message, image=image)
    
    fcm_result = None
    if send_fcm:
        try:
            from fcm_sender import send_fcm_notification
            fcm_result = send_fcm_notification(title, message, image_url=image)
        except Exception as e:
            fcm_result = {"error": str(e)}
            
    notify_telegram_admin(f"📢 <b>إشعار جديد تم إرساله من لوحة تحكم التطبيق</b>:\n<b>{title}</b>\n{message}")
    return json_ar({
        "status": "success",
        "message": "تم إرسال الإشعار وحفظه بنجاح",
        "notification_id": notif_id,
        "fcm": fcm_result
    })

async def handle_admin_update(request):
    try:
        data = await request.json()
    except Exception:
        data = {}
    key = data.get("key", "")
    if not is_admin_request(request, body_key=key):
        return json_ar({"status": "error", "message": "غير مصرح به - مفتاح المشرف مطلوب"}, status=401)
    
    version_code = int(data.get("version_code", 1))
    version_name = str(data.get("version_name", "1.0")).strip()
    download_url = str(data.get("download_url", "")).strip()
    release_notes = str(data.get("release_notes", "تحديث جديد متوفر للتطبيق")).strip()
    is_force = bool(data.get("is_force", False))
    enabled = bool(data.get("enabled", True))
    
    res = db.set_app_update(version_code=version_code, version_name=version_name,
                            download_url=download_url, release_notes=release_notes,
                            is_force=is_force, enabled=enabled)
                            
    notify_telegram_admin(f"🚀 <b>تحديث جديد للتطبيق من لوحة التحكم</b>:\n• الإصدار: {version_name} ({version_code})\n• إجباري: {'نعم' if is_force else 'اختياري'}\n• الرابط: {download_url}")
    return json_ar({
        "status": "success",
        "message": "تم ضبط التحديث بنجاح",
        "update": res
    })

async def handle_admin_add_channel(request):
    try:
        data = await request.json()
    except Exception:
        data = {}
    key = data.get("key", "")
    if not is_admin_request(request, body_key=key):
        return json_ar({"status": "error", "message": "غير مصرح به - مفتاح المشرف مطلوب"}, status=401)
    
    name = data.get("name", "").strip()
    url = data.get("url", "").strip()
    cat_id = data.get("category", "general").strip()
    cat_name = data.get("category_name", None)
    logo = data.get("logo", "📺").strip()
    quality = data.get("quality", "HD").strip()
    referer = data.get("referer", "").strip()
    useragent = data.get("user_agent", "").strip()
    
    if not name or not url:
        return json_ar({"status": "error", "message": "اسم القناة ورابط البث مطلوبان"}, status=400)
        
    ch = db.add_single_channel(name=name, url=url, category_id=cat_id, category_name=cat_name,
                               logo=logo, quality=quality, referer=referer, useragent=useragent)
    notify_telegram_admin(f"📺 <b>تمت إضافة قناة جديدة من لوحة تحكم التطبيق</b>:\n• الاسم: {name}\n• القسم: {cat_id}\n• الجودة: {quality}")
    return json_ar({
        "status": "success",
        "message": "تمت إضافة القناة بنجاح",
        "channel": ch
    })

async def handle_admin_add_category(request):
    try:
        data = await request.json()
    except Exception:
        data = {}
    key = data.get("key", "")
    if not is_admin_request(request, body_key=key):
        return json_ar({"status": "error", "message": "غير مصرح به - مفتاح المشرف مطلوب"}, status=401)
        
    cid = data.get("id", "").strip()
    name = data.get("name", "").strip()
    icon = data.get("icon", "📁").strip()
    image = data.get("image", "").strip() or None
    
    if not cid or not name:
        return json_ar({"status": "error", "message": "معرف واسم القسم مطلوبان"}, status=400)
        
    cat = db.add_category(cid, name, icon=icon, image=image)
    notify_telegram_admin(f"🗂️ <b>تمت إضافة قسم جديد من لوحة تحكم التطبيق</b>:\n• المعرف: {cid}\n• الاسم: {name}")
    return json_ar({
        "status": "success",
        "message": "تمت إضافة القسم بنجاح",
        "category": cat
    })

async def handle_admin_stats(request):
    if not is_admin_request(request):
        return json_ar({"status": "error", "message": "غير مصرح به - مفتاح المشرف مطلوب"}, status=401)
        
    from fcm_sender import is_firebase_configured
    stats = db.get_channel_stats()
    fcm_count = db.get_fcm_devices_count()
    maint = db.get_maintenance()
    update = db.get_app_update()
    return json_ar({
        "status": "success",
        "stats": stats,
        "fcm_devices": fcm_count,
        "firebase_configured": is_firebase_configured(),
        "maintenance": maint,
        "update": update
    })

def make_app():
    app = web.Application(middlewares=[cors_middleware, maintenance_middleware])
    app.router.add_get("/", handle_root)
    app.router.add_get("/health", handle_health)
    app.router.add_get("/health/", handle_health)
    app.router.add_get("/ping", handle_health)
    app.router.add_get("/api/app-config", handle_app_config)
    app.router.add_get("/api/app-config/", handle_app_config)
    app.router.add_get("/api/config", handle_app_config)
    app.router.add_get("/api/config/", handle_app_config)
    
    app.router.add_get("/api/categories", handle_categories)
    app.router.add_get("/api/categories/", handle_categories)
    
    app.router.add_get("/api/channels", handle_channels)
    app.router.add_get("/api/channels/", handle_channels)

    app.router.add_get("/api/export/m3u", handle_export_m3u)
    app.router.add_get("/api/export/m3u/", handle_export_m3u)

    app.router.add_get("/api/stats", handle_stats)
    app.router.add_get("/api/stats/", handle_stats)
    
    app.router.add_get("/api/maintenance", handle_maintenance)
    app.router.add_get("/api/maintenance/", handle_maintenance)
    
    app.router.add_get("/api/update", handle_update)
    app.router.add_get("/api/update/", handle_update)
    
    app.router.add_get("/api/channel-apis", handle_channel_apis)
    app.router.add_get("/api/channel-apis/", handle_channel_apis)

    app.router.add_get("/api/notifications", handle_notifications)
    app.router.add_get("/api/notifications/", handle_notifications)

    app.router.add_post("/api/fcm/register", handle_fcm_register)
    app.router.add_post("/api/fcm/register/", handle_fcm_register)
    app.router.add_post("/api/fcm/unregister", handle_fcm_unregister)
    app.router.add_post("/api/fcm/unregister/", handle_fcm_unregister)
    app.router.add_get("/api/fcm/stats", handle_fcm_stats)
    app.router.add_get("/api/fcm/stats/", handle_fcm_stats)

    # Admin Protected APIs
    app.router.add_post("/api/admin/verify", handle_admin_verify)
    app.router.add_post("/api/admin/verify/", handle_admin_verify)
    app.router.add_post("/api/admin/maintenance", handle_admin_maintenance)
    app.router.add_post("/api/admin/maintenance/", handle_admin_maintenance)
    app.router.add_post("/api/admin/notification", handle_admin_notification)
    app.router.add_post("/api/admin/notification/", handle_admin_notification)
    app.router.add_post("/api/admin/update", handle_admin_update)
    app.router.add_post("/api/admin/update/", handle_admin_update)
    app.router.add_post("/api/admin/channel/add", handle_admin_add_channel)
    app.router.add_post("/api/admin/channel/add/", handle_admin_add_channel)
    app.router.add_post("/api/admin/category/add", handle_admin_add_category)
    app.router.add_post("/api/admin/category/add/", handle_admin_add_category)
    app.router.add_get("/api/admin/stats", handle_admin_stats)
    app.router.add_get("/api/admin/stats/", handle_admin_stats)

    uploads_dir = os.path.join(os.path.dirname(__file__), "data", "uploads")
    os.makedirs(uploads_dir, exist_ok=True)
    app.router.add_static("/static/uploads/", path=uploads_dir, show_index=False)
    app.router.add_static("/uploads/", path=uploads_dir, show_index=False)

    updates_dir = os.path.join(os.path.dirname(__file__), "data", "updates")
    os.makedirs(updates_dir, exist_ok=True)
    app.router.add_static("/static/", path=updates_dir, show_index=False)

    return app

def run_server(host=None, port=None, handle_signals=True):
    actual_host = host or os.environ.get("API_HOST", "0.0.0.0")
    raw_port = os.environ.get("PORT") or os.environ.get("API_PORT") or port or API_PORT or 8080
    actual_port = int(raw_port)
    print(f"🚀 [A2TV] Starting REST API Web Server on http://{actual_host}:{actual_port} ...")
    app = make_app()
    web.run_app(app, host=actual_host, port=actual_port, handle_signals=handle_signals, print=print)

if __name__ == "__main__":
    import threading
    try:
        from bot import run_bot
        bot_thread = threading.Thread(target=run_bot, name="TelegramBotThread", daemon=True)
        bot_thread.start()
        print("🤖 [A2TV] Telegram Bot started in background thread")
    except Exception as e:
        print(f"⚠️ [A2TV] Failed to start bot in background: {e}")
    run_server(handle_signals=True)
