"""
Telegram Bot Control Panel for Ahmed Al Ali TV App (A2 TV).
Modern, ultra-clean, streamlined control panel:
1. إضافة قسم (مع تحديد الاسم والشعار) - يظهر أول قسم في التطبيق مباشرة.
2. إضافة قناة داخل قسم (الاسم، الشعار، ورابط البث).
3. مسح قناة داخل قسم (حذف فوري للقناة).
4. تعديل قناة داخل قسم (تعديل الاسم، الشعار، والرابط).
5. عرض وتصفح الأقسام والقنوات.
"""

import os
import re
import json
import time
import telebot
from telebot import types
from datetime import datetime

from config import BOT_TOKEN, ADMIN_ID, API_HOST, API_PORT, PUBLIC_URL, APP_PACKAGE, CURRENT_APP_VERSION_CODE, logger
from database import db

# Initialize TeleBot
BOT_INITIALIZED = False
if BOT_TOKEN and ":" in BOT_TOKEN and BOT_TOKEN != "YOUR_TELEGRAM_BOT_TOKEN_HERE":
    try:
        bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")
        BOT_INITIALIZED = True
    except Exception as e:
        logger.error("Failed to initialize TeleBot: %s", e)
        bot = telebot.TeleBot("123456789:AAFakeTokenForValidationPlaceholderUntilReal", parse_mode="HTML")
else:
    bot = telebot.TeleBot("123456789:AAFakeTokenForValidationPlaceholderUntilReal", parse_mode="HTML")

# Paths for uploaded assets
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
UPLOADS_DIR = os.path.join(DATA_DIR, "uploads")
UPDATES_DIR = os.path.join(DATA_DIR, "updates")
os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(UPDATES_DIR, exist_ok=True)

# State management for multi-step wizards
user_states = {}

def get_user_id(msg_or_call):
    if hasattr(msg_or_call, "from_user") and msg_or_call.from_user:
        return msg_or_call.from_user.id
    return msg_or_call.chat.id

def is_admin(user_id):
    return db.is_admin(user_id)

def cancel_keyboard():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("❌ إلغاء والعودة للرئيسية", callback_data="main_menu"))
    return kb

def back_keyboard(callback_target="main_menu"):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🔙 رجوع", callback_data=callback_target))
    return kb

# ----------------- Main Dashboard Keyboard -----------------

def main_dashboard_keyboard(user_id=None):
    """
    Clean, focused keyboard with the 4 essential operations:
    - إضافة قسم
    - إضافة قناة داخل قسم
    - تعديل قناة داخل قسم
    - مسح قناة داخل قسم
    - عرض وإدارة الأقسام
    """
    kb = types.InlineKeyboardMarkup(row_width=2)
    b_add_cat = types.InlineKeyboardButton("➕ إضافة قسم", callback_data="btn_add_cat")
    b_add_ch = types.InlineKeyboardButton("📺 إضافة قناة داخل قسم", callback_data="btn_add_ch_select")
    b_edit_ch = types.InlineKeyboardButton("✏️ تعديل قناة داخل قسم", callback_data="btn_edit_ch_select")
    b_del_ch = types.InlineKeyboardButton("🗑️ مسح قناة داخل قسم", callback_data="btn_del_ch_select")
    b_browse = types.InlineKeyboardButton("🗂️ عرض وإدارة الأقسام والقنوات", callback_data="cat_p_1")

    kb.row(b_add_cat)
    kb.row(b_add_ch)
    kb.row(b_edit_ch, b_del_ch)
    kb.row(b_browse)
    return kb

def render_welcome_text():
    cats = db.get_categories()
    chs = db.get_channels()
    return (
        "👋 <b>أهلاً بك في لوحة تحكم تطبيق أحمد ال علي TV</b> 🚀\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 الإحصائيات: <b>{len(cats)}</b> باقة وقسم | <b>{len(chs)}</b> قناة مباشرة\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "اختر الإجراء المطلوب من الأزرار أدناه:\n\n"
        "➕ <b>إضافة قسم:</b> إنشاء قسم جديد مع اسمه وشعاره.\n"
        "📺 <b>إضافة قناة داخل قسم:</b> اسم، شعار، ورابط البث.\n"
        "✏️ <b>تعديل قناة داخل قسم:</b> تعديل الاسم أو الشعار أو الرابط.\n"
        "🗑️ <b>مسح قناة داخل قسم:</b> حذف القناة نهائياً من التطبيق.\n"
        "🗂️ <b>عرض وإدارة الأقسام:</b> استعراض كافة الأقسام وقنواتها.\n\n"
        "⚡ <i>ملاحظة: أي قسم جديد تضيفه سيظهر أول شيء في التطبيق تلقائياً!</i>"
    )

# ----------------- Command Handlers -----------------

@bot.message_handler(commands=['start', 'panel', 'admin', 'menu'])
def handle_start(message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        text = (
            "⛔ <b>عذراً، هذه اللوحة مخصصة لإدارة تطبيق أحمد ال علي TV فقط.</b>\n"
            f"معرفك الخاص: <code>{user_id}</code>\n"
            "تواصل مع الإدارة للحصول على الصلاحيات."
        )
        bot.send_message(message.chat.id, text)
        return

    user_states.pop(user_id, None)
    bot.send_message(message.chat.id, render_welcome_text(), reply_markup=main_dashboard_keyboard(user_id))

# ----------------- Category Picker Generators -----------------

def render_categories_picker(action_prefix, prompt_title, page=1, page_size=8):
    paged = db.get_categories_paged(page=page, page_size=page_size)
    cats = paged["items"]
    cur_page = paged["page"]
    total_pages = paged["total_pages"]
    total_items = paged["total_items"]

    kb = types.InlineKeyboardMarkup(row_width=1)
    if not cats:
        kb.add(types.InlineKeyboardButton("➕ أنشئ قسماً جديداً أولاً", callback_data="btn_add_cat"))
    else:
        for c in cats:
            cid = c["id"]
            cname = c.get("name", cid)
            icon = c.get("icon", "📁")
            ch_count = len(db.get_channels(cid))
            kb.add(types.InlineKeyboardButton(f"{icon} {cname} ({ch_count} قناة)", callback_data=f"{action_prefix}_{cid}"))

    # Pagination buttons
    nav_row = []
    if cur_page > 1:
        nav_row.append(types.InlineKeyboardButton("➡️ السابق", callback_data=f"catpick_{action_prefix}_{cur_page - 1}"))
    nav_row.append(types.InlineKeyboardButton(f"📄 {cur_page} / {total_pages}", callback_data="noop"))
    if cur_page < total_pages:
        nav_row.append(types.InlineKeyboardButton("التالي ⬅️", callback_data=f"catpick_{action_prefix}_{cur_page + 1}"))
    if len(nav_row) > 1:
        kb.row(*nav_row)

    kb.add(types.InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="main_menu"))
    text = (
        f"{prompt_title}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"اختر القسم المطلوب:"
    )
    return text, kb

# ----------------- Channel Picker Generators -----------------

def render_channels_picker(category_id, action_prefix, prompt_title, page=1, page_size=8):
    cat_obj = db.get_category(category_id)
    cat_name = cat_obj.get("name", category_id) if cat_obj else category_id
    icon = cat_obj.get("icon", "📁") if cat_obj else "📁"

    paged = db.get_channels_by_category_paged(category_id=category_id, page=page, page_size=page_size)
    channels = paged["items"]
    cur_page = paged["page"]
    total_pages = paged["total_pages"]
    total_items = paged["total_items"]

    kb = types.InlineKeyboardMarkup(row_width=1)
    for ch in channels:
        chid = ch["id"]
        chname = ch.get("name", "قناة بدون اسم")
        qual = ch.get("quality", "FHD")
        dis = " [معطلة]" if ch.get("disabled", False) else ""
        kb.add(types.InlineKeyboardButton(f"📺 {chname} ({qual}){dis}", callback_data=f"{action_prefix}_{chid}"))

    nav_row = []
    if cur_page > 1:
        nav_row.append(types.InlineKeyboardButton("➡️ السابق", callback_data=f"chpick_{action_prefix}_{category_id}_{cur_page - 1}"))
    nav_row.append(types.InlineKeyboardButton(f"📄 {cur_page} / {total_pages}", callback_data="noop"))
    if cur_page < total_pages:
        nav_row.append(types.InlineKeyboardButton("التالي ⬅️", callback_data=f"chpick_{action_prefix}_{category_id}_{cur_page + 1}"))
    if len(nav_row) > 1:
        kb.row(*nav_row)

    # Back buttons
    if "editch" in action_prefix:
        kb.add(types.InlineKeyboardButton("🔙 رجوع لاختيار قسم آخر", callback_data="btn_edit_ch_select"))
    elif "delch" in action_prefix:
        kb.add(types.InlineKeyboardButton("🔙 رجوع لاختيار قسم آخر", callback_data="btn_del_ch_select"))
    else:
        kb.add(types.InlineKeyboardButton("🔙 رجوع لتفاصيل القسم", callback_data=f"cat_view_{category_id}"))
    kb.add(types.InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="main_menu"))

    if total_items == 0:
        text = (
            f"{prompt_title}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📁 القسم: <b>{icon} {cat_name}</b>\n\n"
            f"⚠️ <b>لا توجد أي قنوات داخل هذا القسم حالياً!</b>"
        )
    else:
        text = (
            f"{prompt_title}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📁 القسم: <b>{icon} {cat_name}</b>\n"
            f"إجمالي القنوات: <b>{total_items}</b> قناة (صفحة {cur_page} من {total_pages})\n\n"
            f"اضغط على القناة المطلوبة:"
        )
    return text, kb

# ----------------- Channel Edit View Generator -----------------

def render_channel_edit_view(chid):
    ch = db.get_channel(chid)
    if not ch:
        return "⚠️ القناة غير موجودة أو تم حذفها مسبقاً.", cancel_keyboard()

    cat_id = ch.get("category", "general")
    cat_name = ch.get("categoryName", cat_id)
    logo = ch.get("logo", "📺")
    logo_display = "🖼️ صورة مخصصة" if str(logo).startswith("http") else str(logo)

    text = (
        f"📺 <b>تفاصيل وتعديل القناة</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🏷️ الاسم: <b>{ch.get('name')}</b>\n"
        f"📁 القسم: <b>{cat_name}</b>\n"
        f"🖼️ الشعار: <b>{logo_display}</b>\n"
        f"⚙️ الجودة: <b>{ch.get('quality', 'FHD')}</b>\n"
        f"🔗 رابط البث المباشر:\n<code>{ch.get('url')}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"اختر التعديل المطلوب:"
    )

    kb = types.InlineKeyboardMarkup(row_width=2)
    b_name = types.InlineKeyboardButton("✏️ تعديل الاسم", callback_data=f"ch_edname_{chid}")
    b_logo = types.InlineKeyboardButton("🖼️ تعديل الشعار", callback_data=f"ch_edlogo_{chid}")
    b_url = types.InlineKeyboardButton("🔗 تعديل رابط البث", callback_data=f"ch_edurl_{chid}")
    b_qual = types.InlineKeyboardButton("⚙️ تعديل الجودة", callback_data=f"ch_edqual_{chid}")
    b_del = types.InlineKeyboardButton("🗑️ مسح هذه القناة", callback_data=f"ch_del_ask_{chid}")
    b_back = types.InlineKeyboardButton(f"🔙 رجوع لقنوات {cat_name}", callback_data=f"ch_cat_{cat_id}_1")
    b_home = types.InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="main_menu")

    kb.row(b_name, b_logo)
    kb.row(b_url, b_qual)
    kb.row(b_del)
    kb.row(b_back, b_home)
    return text, kb

# ----------------- Categories Browsing View -----------------

def render_categories_page(page=1, search_query="", page_size=8):
    paged = db.get_categories_paged(page=page, page_size=page_size, search_query=search_query)
    cats = paged["items"]
    cur_page = paged["page"]
    total_pages = paged["total_pages"]
    total_items = paged["total_items"]

    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.row(
        types.InlineKeyboardButton("➕ إضافة قسم جديد", callback_data="btn_add_cat"),
        types.InlineKeyboardButton("🔍 بحث عن قسم", callback_data="cat_search_prompt")
    )

    if search_query:
        kb.add(types.InlineKeyboardButton("❌ إلغاء البحث وعرض الكل", callback_data="cat_p_1"))

    for c in cats:
        cid = c["id"]
        cname = c.get("name", cid)
        icon = c.get("icon", "📁")
        ch_count = len(db.get_channels(cid))
        hidden_mark = " [مخفي]" if c.get("hidden", False) else ""
        btn_text = f"{icon} {cname} ({ch_count} قناة){hidden_mark}"
        kb.add(types.InlineKeyboardButton(btn_text, callback_data=f"cat_view_{cid}"))

    nav_row = []
    if cur_page > 1:
        prev_call = f"cat_p_{cur_page - 1}" if not search_query else f"cat_s_{cur_page - 1}_{search_query}"
        nav_row.append(types.InlineKeyboardButton("➡️ السابق", callback_data=prev_call))
    nav_row.append(types.InlineKeyboardButton(f"📄 {cur_page} / {total_pages}", callback_data="noop"))
    if cur_page < total_pages:
        next_call = f"cat_p_{cur_page + 1}" if not search_query else f"cat_s_{cur_page + 1}_{search_query}"
        nav_row.append(types.InlineKeyboardButton("التالي ⬅️", callback_data=next_call))
    if len(nav_row) > 1:
        kb.row(*nav_row)

    kb.add(types.InlineKeyboardButton("🏠 العودة للقائمة الرئيسية", callback_data="main_menu"))

    search_status = f"\n🔍 نتيجة البحث عن: <b>«{search_query}»</b>" if search_query else ""
    if total_items == 0:
        text = (
            f"🗂️ <b>إدارة أقسام تطبيق أحمد ال علي TV</b>{search_status}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⚠️ <b>لا توجد أي أقسام حالياً.</b>\n\n"
            f"اضغط على زر ➕ <b>إضافة قسم جديد</b> لإنشاء أول قسم."
        )
    else:
        text = (
            f"🗂️ <b>إدارة وتصفح الأقسام والقنوات</b>{search_status}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"إجمالي الأقسام: <b>{total_items}</b> قسم (صفحة {cur_page} من {total_pages})\n\n"
            f"اضغط على أي قسم لعرض قنواته أو إدارته وتعديله:"
        )
    return text, kb

# ----------------- Callback Query Router -----------------

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    user_id = call.from_user.id
    if not is_admin(user_id):
        bot.answer_callback_query(call.id, "⚠️ غير مصرح لك باستخدام هذه اللوحة!", show_alert=True)
        return

    data = call.data
    chat_id = call.message.chat.id
    msg_id = call.message.message_id

    # 1. Main Navigation
    if data == "main_menu":
        user_states.pop(user_id, None)
        try:
            bot.edit_message_text(render_welcome_text(), chat_id, msg_id, reply_markup=main_dashboard_keyboard(user_id))
        except Exception:
            bot.send_message(chat_id, render_welcome_text(), reply_markup=main_dashboard_keyboard(user_id))
        bot.answer_callback_query(call.id)
        return

    if data == "noop":
        bot.answer_callback_query(call.id)
        return

    # 2. Add Category Wizard
    if data == "btn_add_cat" or data == "cat_add":
        user_states[user_id] = {"action": "wait_cat_name", "data": {}}
        prompt = (
            "📁 <b>إضافة قسم جديد</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "<b>الخطوة 1 من 2:</b> أرسل الآن <b>اسم القسم الجديد</b> (مثال: قنوات رياضية VIP أو بي إن سبورتس):"
        )
        bot.edit_message_text(prompt, chat_id, msg_id, reply_markup=cancel_keyboard())
        bot.answer_callback_query(call.id)
        return

    # 3. Add Channel Flow
    if data == "btn_add_ch_select":
        text, kb = render_categories_picker(
            action_prefix="ch_add_in",
            prompt_title="📺 <b>إضافة قناة داخل قسم</b>"
        )
        bot.edit_message_text(text, chat_id, msg_id, reply_markup=kb)
        bot.answer_callback_query(call.id)
        return

    if data.startswith("catpick_ch_add_in_"):
        page = int(data.split("_")[-1])
        text, kb = render_categories_picker(action_prefix="ch_add_in", prompt_title="📺 <b>إضافة قناة داخل قسم</b>", page=page)
        bot.edit_message_text(text, chat_id, msg_id, reply_markup=kb)
        bot.answer_callback_query(call.id)
        return

    if data.startswith("ch_add_in_"):
        cat_id = data[len("ch_add_in_"):]
        cat = db.get_category(cat_id)
        cat_name = cat.get("name", cat_id) if cat else "عام"
        user_states[user_id] = {
            "action": "wait_ch_add_name",
            "data": {"category_id": cat_id, "category_name": cat_name}
        }
        text = (
            f"📺 <b>إضافة قناة داخل قسم «{cat_name}»</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"<b>الخطوة 1 من 3:</b> أرسل الآن <b>اسم القناة</b> (مثال: beIN Sports 1 HD):\n\n"
            f"💡 <i>أو أرسل الصيغة السريعة بسطر واحد:</i>\n"
            f"<code>اسم القناة | رابط البث | الجودة</code>"
        )
        bot.edit_message_text(text, chat_id, msg_id, reply_markup=cancel_keyboard())
        bot.answer_callback_query(call.id)
        return

    # 4. Edit Channel Flow
    if data == "btn_edit_ch_select":
        text, kb = render_categories_picker(
            action_prefix="ch_pickedit_cat",
            prompt_title="✏️ <b>تعديل قناة داخل قسم</b>"
        )
        bot.edit_message_text(text, chat_id, msg_id, reply_markup=kb)
        bot.answer_callback_query(call.id)
        return

    if data.startswith("catpick_ch_pickedit_cat_"):
        page = int(data.split("_")[-1])
        text, kb = render_categories_picker(action_prefix="ch_pickedit_cat", prompt_title="✏️ <b>تعديل قناة داخل قسم</b>", page=page)
        bot.edit_message_text(text, chat_id, msg_id, reply_markup=kb)
        bot.answer_callback_query(call.id)
        return

    if data.startswith("ch_pickedit_cat_"):
        cid = data[len("ch_pickedit_cat_"):]
        text, kb = render_channels_picker(category_id=cid, action_prefix="ch_view", prompt_title="✏️ <b>اختر القناة المطلوب تعديلها</b>")
        bot.edit_message_text(text, chat_id, msg_id, reply_markup=kb)
        bot.answer_callback_query(call.id)
        return

    # 5. Delete Channel Flow
    if data == "btn_del_ch_select":
        text, kb = render_categories_picker(
            action_prefix="ch_pickdel_cat",
            prompt_title="🗑️ <b>مسح قناة داخل قسم</b>"
        )
        bot.edit_message_text(text, chat_id, msg_id, reply_markup=kb)
        bot.answer_callback_query(call.id)
        return

    if data.startswith("catpick_ch_pickdel_cat_"):
        page = int(data.split("_")[-1])
        text, kb = render_categories_picker(action_prefix="ch_pickdel_cat", prompt_title="🗑️ <b>مسح قناة داخل قسم</b>", page=page)
        bot.edit_message_text(text, chat_id, msg_id, reply_markup=kb)
        bot.answer_callback_query(call.id)
        return

    if data.startswith("ch_pickdel_cat_"):
        cid = data[len("ch_pickdel_cat_"):]
        text, kb = render_channels_picker(category_id=cid, action_prefix="ch_del_ask", prompt_title="🗑️ <b>اختر القناة المطلوب مسحها</b>")
        bot.edit_message_text(text, chat_id, msg_id, reply_markup=kb)
        bot.answer_callback_query(call.id)
        return

    # Delete Channel Confirmation
    if data.startswith("ch_del_ask_"):
        chid = data[len("ch_del_ask_"):]
        ch = db.get_channel(chid)
        if not ch:
            bot.answer_callback_query(call.id, "⚠️ القناة غير موجودة", show_alert=True)
            return

        cat_id = ch.get("category", "general")
        cat_name = ch.get("categoryName", cat_id)
        ch_name = ch.get("name", "هذه القناة")

        text = (
            f"⚠️ <b>تأكيد مسح القناة نهائياً</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"هل أنت متأكد من مسح قناة «<b>{ch_name}</b>» نهائياً من قسم «<b>{cat_name}</b>»؟\n"
            f"سيتم حذف القناة فوراً من تطبيق أحمد ال علي TV!"
        )
        kb = types.InlineKeyboardMarkup(row_width=1)
        kb.add(types.InlineKeyboardButton("🗑️ نعم، احذف القناة الآن", callback_data=f"ch_del_confirmed_{chid}"))
        kb.add(types.InlineKeyboardButton("❌ تراجع وإلغاء", callback_data=f"ch_view_{chid}"))

        bot.edit_message_text(text, chat_id, msg_id, reply_markup=kb)
        bot.answer_callback_query(call.id)
        return

    if data.startswith("ch_del_confirmed_"):
        chid = data[len("ch_del_confirmed_"):]
        ch = db.get_channel(chid)
        cat_id = ch.get("category", "general") if ch else "general"
        db.delete_channel(chid)
        bot.answer_callback_query(call.id, "تم مسح القناة بنجاح 🗑️", show_alert=True)

        text, kb = render_channels_picker(category_id=cat_id, action_prefix="ch_view", prompt_title="📺 <b>قنوات القسم بعد المسح</b>")
        try:
            bot.edit_message_text(text, chat_id, msg_id, reply_markup=kb)
        except Exception:
            pass
        return

    if data.startswith("ch_del_"):
        # Alias for direct delete
        chid = data[len("ch_del_"):]
        call.data = f"ch_del_ask_{chid}"
        handle_callbacks(call)
        return

    # 6. View & Edit Channel Details
    if data.startswith("ch_view_"):
        chid = data[len("ch_view_"):]
        text, kb = render_channel_edit_view(chid)
        try:
            bot.edit_message_text(text, chat_id, msg_id, reply_markup=kb)
        except Exception:
            pass
        bot.answer_callback_query(call.id)
        return

    # Edit Channel Name
    if data.startswith("ch_edname_"):
        chid = data[len("ch_edname_"):]
        ch = db.get_channel(chid)
        ch_name = ch.get("name", "") if ch else ""
        user_states[user_id] = {"action": "wait_ch_new_name", "data": {"chid": chid}}
        text = (
            f"✏️ <b>تعديل اسم القناة</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"الاسم الحالي: <b>{ch_name}</b>\n\n"
            f"أرسل الآن <b>الاسم الجديد</b> للقناة:"
        )
        bot.edit_message_text(text, chat_id, msg_id, reply_markup=cancel_keyboard())
        bot.answer_callback_query(call.id)
        return

    # Edit Channel Logo
    if data.startswith("ch_edlogo_"):
        chid = data[len("ch_edlogo_"):]
        ch = db.get_channel(chid)
        ch_name = ch.get("name", "") if ch else ""
        user_states[user_id] = {"action": "wait_ch_new_logo", "data": {"chid": chid}}
        text = (
            f"🖼️ <b>تعديل شعار القناة: {ch_name}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"أرسل الآن <b>شعار القناة الجديد</b>:\n"
            f"• يمكنك إرسال صورة مباشرة 📸\n"
            f"• أو رابط صورة مباشر (URL)\n"
            f"• أو إيموجي (مثل: ⚽، 📺)\n"
            f"• أو اكتب 'تخطي' للشعار الافتراضي 📺"
        )
        bot.edit_message_text(text, chat_id, msg_id, reply_markup=cancel_keyboard())
        bot.answer_callback_query(call.id)
        return

    # Edit Channel Stream URL
    if data.startswith("ch_edurl_"):
        chid = data[len("ch_edurl_"):]
        ch = db.get_channel(chid)
        ch_name = ch.get("name", "") if ch else ""
        curr_url = ch.get("url", "") if ch else ""
        user_states[user_id] = {"action": "wait_ch_new_url", "data": {"chid": chid}}
        text = (
            f"🔗 <b>تعديل رابط بث القناة: {ch_name}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"الرابط الحالي:\n<code>{curr_url}</code>\n\n"
            f"أرسل الآن <b>رابط البث المباشر الجديد</b> (يدعم HLS, M3U8, MPD, MP4):"
        )
        bot.edit_message_text(text, chat_id, msg_id, reply_markup=cancel_keyboard())
        bot.answer_callback_query(call.id)
        return

    # Edit Channel Quality
    if data.startswith("ch_edqual_"):
        chid = data[len("ch_edqual_"):]
        kb = types.InlineKeyboardMarkup(row_width=3)
        for q in ["4K", "FHD", "HD", "SD", "LOW"]:
            kb.add(types.InlineKeyboardButton(q, callback_data=f"ch_setqual_{chid}:{q}"))
        kb.add(types.InlineKeyboardButton("🔙 إلغاء والعودة للقناة", callback_data=f"ch_view_{chid}"))
        bot.edit_message_text("⚙️ <b>اختر الجودة المطلوبة للقناة:</b>", chat_id, msg_id, reply_markup=kb)
        bot.answer_callback_query(call.id)
        return

    if data.startswith("ch_setqual_"):
        raw_payload = data[len("ch_setqual_"):]
        chid, qual = raw_payload.split(":", 1) if ":" in raw_payload else (raw_payload, "FHD")
        db.update_channel_basic(chid, quality=qual)
        bot.answer_callback_query(call.id, f"تم ضبط الجودة إلى {qual} بنجاح ✅", show_alert=True)
        call.data = f"ch_view_{chid}"
        handle_callbacks(call)
        return

    # 7. Categories Management & Browsing
    if data.startswith("cat_p_"):
        page = int(data.split("_")[2])
        text, kb = render_categories_page(page=page)
        bot.edit_message_text(text, chat_id, msg_id, reply_markup=kb)
        bot.answer_callback_query(call.id)
        return

    if data.startswith("cat_s_"):
        parts = data.split("_", 3)
        page = int(parts[2])
        q = parts[3]
        text, kb = render_categories_page(page=page, search_query=q)
        bot.edit_message_text(text, chat_id, msg_id, reply_markup=kb)
        bot.answer_callback_query(call.id)
        return

    if data == "cat_search_prompt":
        user_states[user_id] = {"action": "wait_cat_search"}
        bot.edit_message_text("🔍 <b>أرسل الآن اسم القسم الذي تريد البحث عنه:</b>", chat_id, msg_id, reply_markup=cancel_keyboard())
        bot.answer_callback_query(call.id)
        return

    if data.startswith("cat_view_"):
        cid = data[len("cat_view_"):]
        c = db.get_category(cid)
        if not c:
            bot.answer_callback_query(call.id, "⚠️ القسم غير موجود", show_alert=True)
            return

        ch_in_cat = db.get_channels(cid)
        banner_info = f"🖼️ الشعار/الصورة: <b>موجود ✅</b>\n" if c.get("image") else f"🎨 الأيقونة: <b>{c.get('icon', '📁')}</b>\n"

        text = (
            f"📁 <b>تفاصيل القسم: {c.get('icon', '📁')} {c.get('name')}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🆔 المعرف البرمجي: <code>{cid}</code>\n"
            f"{banner_info}"
            f"📺 عدد القنوات بداخله: <b>{len(ch_in_cat)}</b> قناة\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"اختر الإجراء المطلوب:"
        )

        kb = types.InlineKeyboardMarkup(row_width=2)
        kb.row(
            types.InlineKeyboardButton(f"📺 قنوات هذا القسم ({len(ch_in_cat)})", callback_data=f"ch_cat_{cid}_1"),
            types.InlineKeyboardButton("➕ إضافة قناة هنا", callback_data=f"ch_add_in_{cid}")
        )
        kb.row(
            types.InlineKeyboardButton("✏️ تعديل اسم القسم", callback_data=f"cat_edname_{cid}"),
            types.InlineKeyboardButton("🖼️ تغيير الشعار والأيقونة", callback_data=f"cat_edicon_{cid}")
        )
        kb.row(
            types.InlineKeyboardButton("🗑️ حذف هذا القسم", callback_data=f"cat_del_{cid}")
        )
        kb.add(types.InlineKeyboardButton("🔙 رجوع لقائمة الأقسام", callback_data="cat_p_1"))
        kb.add(types.InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="main_menu"))

        bot.edit_message_text(text, chat_id, msg_id, reply_markup=kb)
        bot.answer_callback_query(call.id)
        return

    if data.startswith("ch_cat_"):
        raw_payload = data[len("ch_cat_"):]
        parts = raw_payload.rsplit("_", 1)
        cid = parts[0]
        page = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 1
        text, kb = render_channels_picker(category_id=cid, action_prefix="ch_view", prompt_title="📺 <b>قنوات هذا القسم</b>", page=page)
        bot.edit_message_text(text, chat_id, msg_id, reply_markup=kb)
        bot.answer_callback_query(call.id)
        return

    # Edit Category Name & Icon
    if data.startswith("cat_edname_"):
        cid = data[len("cat_edname_"):]
        user_states[user_id] = {"action": "wait_cat_new_name", "data": {"cid": cid}}
        bot.edit_message_text("✏️ <b>أرسل الآن الاسم الجديد للقسم:</b>", chat_id, msg_id, reply_markup=cancel_keyboard())
        bot.answer_callback_query(call.id)
        return

    if data.startswith("cat_edicon_"):
        cid = data[len("cat_edicon_"):]
        user_states[user_id] = {"action": "wait_cat_new_icon", "data": {"cid": cid}}
        text = (
            "🖼️ <b>تغيير شعار وأيقونة القسم</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "أرسل الآن صورة الشعار كصورة 📸\n"
            "أو أرسل رابط صورة مباشر (URL)\n"
            "أو أرسل إيموجي (مثل: ⚽، 🎬، 🕋، 📺):"
        )
        bot.edit_message_text(text, chat_id, msg_id, reply_markup=cancel_keyboard())
        bot.answer_callback_query(call.id)
        return

    # Delete Category
    if data.startswith("cat_del_"):
        cid = data[len("cat_del_"):]
        c = db.get_category(cid)
        ch_cnt = len(db.get_channels(cid))
        kb = types.InlineKeyboardMarkup(row_width=1)
        kb.add(types.InlineKeyboardButton("🗑️ نعم، احذف القسم وقنواته نهائياً", callback_data=f"cat_del_confirm_{cid}"))
        kb.add(types.InlineKeyboardButton("❌ تراجع وإلغاء", callback_data=f"cat_view_{cid}"))

        text = (
            f"⚠️ <b>هل أنت متأكد من حذف القسم «{c.get('name', cid) if c else cid}»؟</b>\n"
            f"يحتوي هذا القسم على <b>{ch_cnt}</b> قناة.\n"
            f"سيتم حذف القسم وكافة قنواته من التطبيق!"
        )
        bot.edit_message_text(text, chat_id, msg_id, reply_markup=kb)
        bot.answer_callback_query(call.id)
        return

    if data.startswith("cat_del_confirm_"):
        cid = data[len("cat_del_confirm_"):]
        db.delete_category(cid, delete_channels=True)
        bot.answer_callback_query(call.id, "تم حذف القسم وقنواته بنجاح 🗑️", show_alert=True)
        text, kb = render_categories_page(page=1)
        bot.edit_message_text(text, chat_id, msg_id, reply_markup=kb)
        return

# ----------------- Message Handler for Wizards -----------------

@bot.message_handler(content_types=['text', 'photo', 'document'])
def handle_text_messages(message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        return

    state = user_states.get(user_id)
    if not state:
        return

    action = state.get("action")
    raw_text = message.text.strip() if message.text else ""

    # 1. Search Category
    if action == "wait_cat_search":
        user_states.pop(user_id, None)
        text, kb = render_categories_page(page=1, search_query=raw_text)
        bot.reply_to(message, text, reply_markup=kb)
        return

    # 2. Add Category Wizard
    if action == "wait_cat_name":
        if len(raw_text) < 2:
            bot.reply_to(message, "⚠️ اسم القسم قصير جداً. يرجى إدخال اسم واضح للقسم:")
            return
        state["data"]["name"] = raw_text
        state["action"] = "wait_cat_icon"
        text = (
            f"📁 تم حفظ اسم القسم: <b>{raw_text}</b>\n\n"
            f"<b>الخطوة 2 من 2:</b> أرسل الآن <b>شعار أو أيقونة القسم</b>:\n"
            f"• يمكنك إرسال صورة الشعار مباشرة 📸\n"
            f"• أو إرسال رابط صورة مباشر (URL)\n"
            f"• أو إرسال إيموجي (مثل: ⚽، 🎬، 📺، 🏆، 🕋)\n"
            f"• أو اكتب <b>تخطي</b> لاستخدام الأيقونة الافتراضية 📁"
        )
        bot.reply_to(message, text, reply_markup=cancel_keyboard())
        return

    if action == "wait_cat_icon":
        cat_name = state["data"]["name"]
        icon = "📁"
        image_url = ""
        file_id = None
        if message.photo:
            file_id = message.photo[-1].file_id
        elif message.document and message.document.mime_type and message.document.mime_type.startswith("image/"):
            file_id = message.document.file_id

        if file_id:
            try:
                file_info = bot.get_file(file_id)
                down = bot.download_file(file_info.file_path)
                fn = f"cat_{int(time.time())}.jpg"
                save_path = os.path.join(UPLOADS_DIR, fn)
                with open(save_path, "wb") as f:
                    f.write(down)
                image_url = f"{PUBLIC_URL}/static/uploads/{fn}"
                icon = "🖼️"
            except Exception as e:
                logger.error("Failed to download category logo: %s", e)
                bot.reply_to(message, f"⚠️ خطأ أثناء تنزيل الصورة: {e}\nيرجى إعادة المحاولة أو إرسال رابط.")
                return
        elif raw_text.startswith("http://") or raw_text.startswith("https://"):
            image_url = raw_text.strip()
            icon = "🖼️"
        elif raw_text.strip().lower() in ["تخطي", "بدون", "لا يوجد", "skip", "none"]:
            icon = "📁"
            image_url = ""
        elif raw_text:
            icon = raw_text.strip()[:6]

        # Generate unique safe ID
        clean_id = re.sub(r'[^a-zA-Z0-9]+', '_', cat_name).strip('_').lower()
        if not clean_id or len(clean_id) < 2:
            import hashlib
            clean_id = f"cat_{hashlib.md5(cat_name.encode('utf-8')).hexdigest()[:6]}"
        cat_id = clean_id

        res = db.add_category(cat_id, cat_name, icon=icon, image=image_url)
        user_states.pop(user_id, None)

        kb = types.InlineKeyboardMarkup(row_width=1)
        kb.add(types.InlineKeyboardButton(f"➕ إضافة قنوات داخل «{cat_name}» الآن", callback_data=f"ch_add_in_{cat_id}"))
        kb.add(types.InlineKeyboardButton("🗂️ عرض قائمة الأقسام", callback_data="cat_p_1"))
        kb.add(types.InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="main_menu"))

        logo_status = "صورة مخصصة ✅" if image_url else icon
        success_text = (
            f"🎉 <b>تم إنشاء القسم بنجاح ووضعه في أول القائمة!</b> 🚀\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📁 اسم القسم: <b>{icon} {cat_name}</b>\n"
            f"🆔 المعرف البرمجي: <code>{cat_id}</code>\n"
            f"🖼️ الشعار: <b>{logo_status}</b>\n\n"
            f"⚡ <b>سيظهر هذا القسم أول شيء في تطبيق أحمد ال علي TV تلقائياً!</b>"
        )
        bot.reply_to(message, success_text, reply_markup=kb)
        return

    # Edit Category Name & Icon
    if action == "wait_cat_new_name":
        cid = state["data"]["cid"]
        if len(raw_text) < 2:
            bot.reply_to(message, "⚠️ اسم القسم قصير جداً. يرجى إدخال اسم واضح:")
            return
        db.update_category(cid, new_name=raw_text)
        user_states.pop(user_id, None)
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("📁 عرض القسم بعد التعديل", callback_data=f"cat_view_{cid}"))
        kb.add(types.InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="main_menu"))
        bot.reply_to(message, f"✅ <b>تم تعديل اسم القسم إلى:</b> <b>{raw_text}</b> بنجاح!", reply_markup=kb)
        return

    if action == "wait_cat_new_icon":
        cid = state["data"]["cid"]
        icon = None
        image_url = None
        file_id = None
        if message.photo:
            file_id = message.photo[-1].file_id
        elif message.document and message.document.mime_type and message.document.mime_type.startswith("image/"):
            file_id = message.document.file_id

        if file_id:
            try:
                file_info = bot.get_file(file_id)
                down = bot.download_file(file_info.file_path)
                fn = f"cat_{int(time.time())}.jpg"
                save_path = os.path.join(UPLOADS_DIR, fn)
                with open(save_path, "wb") as f:
                    f.write(down)
                image_url = f"{PUBLIC_URL}/static/uploads/{fn}"
                icon = "🖼️"
            except Exception as e:
                bot.reply_to(message, f"⚠️ خطأ أثناء تنزيل الصورة: {e}")
                return
        elif raw_text.startswith("http://") or raw_text.startswith("https://"):
            image_url = raw_text.strip()
            icon = "🖼️"
        elif raw_text.strip().lower() in ["حذف", "ازالة", "إزالة", "clear", "remove", "none", "بدون"]:
            image_url = ""
            icon = "📁"
        elif raw_text:
            icon = raw_text.strip()[:6]

        db.update_category(cid, new_icon=icon, new_image=image_url)
        user_states.pop(user_id, None)
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("📁 عرض القسم بعد التحديث", callback_data=f"cat_view_{cid}"))
        kb.add(types.InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="main_menu"))
        bot.reply_to(message, "✅ <b>تم تحديث شعار وأيقونة القسم بنجاح!</b>", reply_markup=kb)
        return

    # 3. Add Channel Wizard
    if action == "wait_ch_add_name":
        d = state["data"]
        cat_id = d["category_id"]
        cat_name = d["category_name"]

        # Fast 1-line format: Name | URL | Quality
        if "|" in raw_text:
            parts = [p.strip() for p in raw_text.split("|")]
            ch_name = parts[0]
            ch_url = parts[1]
            ch_qual = parts[2] if len(parts) > 2 else "FHD"

            ch = db.add_single_channel(name=ch_name, url=ch_url, category_id=cat_id, category_name=cat_name, quality=ch_qual)
            user_states.pop(user_id, None)

            kb = types.InlineKeyboardMarkup(row_width=1)
            kb.add(types.InlineKeyboardButton(f"➕ إضافة قناة أخرى في «{cat_name}»", callback_data=f"ch_add_in_{cat_id}"))
            kb.add(types.InlineKeyboardButton(f"📺 قنوات «{cat_name}»", callback_data=f"ch_cat_{cat_id}_1"))
            kb.add(types.InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="main_menu"))

            text = (
                f"🎉 <b>تمت إضافة القناة بنجاح!</b> 🚀\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📺 القناة: <b>{ch['name']}</b>\n"
                f"📁 القسم: <b>{cat_name}</b>\n"
                f"⚙️ الجودة: <b>{ch.get('quality', 'FHD')}</b>\n"
                f"🔗 الرابط:\n<code>{ch['url']}</code>\n\n"
                f"⚡ تظهر القناة فوراً في تطبيق أحمد ال علي TV!"
            )
            bot.reply_to(message, text, reply_markup=kb)
            return

        if len(raw_text) < 2:
            bot.reply_to(message, "⚠️ اسم القناة قصير جداً. يرجى إدخال اسم صحيح:")
            return

        state["data"]["name"] = raw_text
        state["action"] = "wait_ch_add_logo"
        prompt = (
            f"📺 تم حفظ اسم القناة: <b>{raw_text}</b>\n\n"
            f"<b>الخطوة 2 من 3:</b> أرسل الآن <b>شعار أو أيقونة القناة</b>:\n"
            f"• يمكنك إرسال صورة الشعار مباشرة 📸\n"
            f"• أو إرسال رابط صورة مباشر (URL)\n"
            f"• أو إرسال إيموجي (مثل: ⚽، 📺)\n"
            f"• أو اكتب <b>تخطي</b> لاستخدام الشعار الافتراضي 📺"
        )
        bot.reply_to(message, prompt, reply_markup=cancel_keyboard())
        return

    if action == "wait_ch_add_logo":
        logo_val = "📺"
        file_id = None
        if message.photo:
            file_id = message.photo[-1].file_id
        elif message.document and message.document.mime_type and message.document.mime_type.startswith("image/"):
            file_id = message.document.file_id

        if file_id:
            try:
                file_info = bot.get_file(file_id)
                down = bot.download_file(file_info.file_path)
                fn = f"ch_{int(time.time())}.jpg"
                save_path = os.path.join(UPLOADS_DIR, fn)
                with open(save_path, "wb") as f:
                    f.write(down)
                logo_val = f"{PUBLIC_URL}/static/uploads/{fn}"
            except Exception as e:
                bot.reply_to(message, f"⚠️ خطأ أثناء تنزيل الصورة: {e}")
                return
        elif raw_text.startswith("http://") or raw_text.startswith("https://"):
            logo_val = raw_text.strip()
        elif raw_text.strip().lower() in ["تخطي", "بدون", "لا يوجد", "skip", "none"]:
            logo_val = "📺"
        elif raw_text:
            logo_val = raw_text.strip()[:6]

        state["data"]["logo"] = logo_val
        state["action"] = "wait_ch_add_url"
        prompt = (
            f"🖼️ تم حفظ الشعار بنجاح!\n\n"
            f"<b>الخطوة 3 من 3:</b> أرسل الآن <b>رابط البث المباشر (Stream URL)</b>:\n"
            f"(يدعم روابط HLS, M3U8, MPD, MP4, TS وروابط السيرفرات المباشرة)"
        )
        bot.reply_to(message, prompt, reply_markup=cancel_keyboard())
        return

    if action == "wait_ch_add_url":
        if not (raw_text.startswith("http://") or raw_text.startswith("https://") or raw_text.startswith("rtmp://")):
            bot.reply_to(message, "⚠️ يرجى إرسال رابط بث مباشر صحيح يبدأ بـ http:// أو https://")
            return

        d = state["data"]
        cat_id = d["category_id"]
        cat_name = d["category_name"]
        ch_name = d["name"]
        ch_logo = d.get("logo", "📺")

        ch = db.add_single_channel(
            name=ch_name,
            url=raw_text,
            category_id=cat_id,
            category_name=cat_name,
            logo=ch_logo,
            quality="FHD"
        )
        user_states.pop(user_id, None)

        kb = types.InlineKeyboardMarkup(row_width=1)
        kb.add(types.InlineKeyboardButton(f"➕ إضافة قناة أخرى في «{cat_name}»", callback_data=f"ch_add_in_{cat_id}"))
        kb.add(types.InlineKeyboardButton(f"📺 قنوات «{cat_name}»", callback_data=f"ch_cat_{cat_id}_1"))
        kb.add(types.InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="main_menu"))

        logo_display = "صورة مخصصة ✅" if str(ch_logo).startswith("http") else str(ch_logo)
        text = (
            f"🎉 <b>تمت إضافة القناة بنجاح!</b> 🚀\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📺 القناة: <b>{ch['name']}</b>\n"
            f"📁 القسم: <b>{cat_name}</b>\n"
            f"🖼️ الشعار: <b>{logo_display}</b>\n"
            f"⚙️ الجودة: <b>{ch.get('quality', 'FHD')}</b>\n"
            f"🔗 الرابط:\n<code>{ch['url']}</code>\n\n"
            f"⚡ <b>تظهر القناة فوراً وتعمل داخل تطبيق أحمد ال علي TV!</b>"
        )
        bot.reply_to(message, text, reply_markup=kb)
        return

    # 4. Edit Channel Wizards
    if action == "wait_ch_new_name":
        chid = state["data"]["chid"]
        if len(raw_text) < 2:
            bot.reply_to(message, "⚠️ اسم القناة قصير جداً. يرجى إدخال اسم صحيح:")
            return
        db.update_channel_basic(chid, name=raw_text)
        user_states.pop(user_id, None)
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("📺 عرض تفاصيل القناة", callback_data=f"ch_view_{chid}"))
        kb.add(types.InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="main_menu"))
        bot.reply_to(message, f"✅ <b>تم تعديل اسم القناة إلى:</b> <b>{raw_text}</b> بنجاح!", reply_markup=kb)
        return

    if action == "wait_ch_new_url":
        chid = state["data"]["chid"]
        if not (raw_text.startswith("http://") or raw_text.startswith("https://") or raw_text.startswith("rtmp://")):
            bot.reply_to(message, "⚠️ يرجى إرسال رابط بث مباشر صحيح يبدأ بـ http:// أو https://")
            return
        db.update_channel_basic(chid, url=raw_text)
        user_states.pop(user_id, None)
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("📺 عرض تفاصيل القناة", callback_data=f"ch_view_{chid}"))
        kb.add(types.InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="main_menu"))
        bot.reply_to(message, "✅ <b>تم تعديل رابط بث القناة بنجاح!</b>\nسيتم تشغيل الرابط الجديد فوراً في التطبيق.", reply_markup=kb)
        return

    if action == "wait_ch_new_logo":
        chid = state["data"]["chid"]
        logo_val = "📺"
        file_id = None
        if message.photo:
            file_id = message.photo[-1].file_id
        elif message.document and message.document.mime_type and message.document.mime_type.startswith("image/"):
            file_id = message.document.file_id

        if file_id:
            try:
                file_info = bot.get_file(file_id)
                down = bot.download_file(file_info.file_path)
                fn = f"ch_{int(time.time())}.jpg"
                save_path = os.path.join(UPLOADS_DIR, fn)
                with open(save_path, "wb") as f:
                    f.write(down)
                logo_val = f"{PUBLIC_URL}/static/uploads/{fn}"
            except Exception as e:
                bot.reply_to(message, f"⚠️ خطأ أثناء تحميل الصورة: {e}")
                return
        elif raw_text.startswith("http://") or raw_text.startswith("https://"):
            logo_val = raw_text.strip()
        elif raw_text.strip().lower() in ["حذف", "ازالة", "إزالة", "clear", "remove", "none", "بدون"]:
            logo_val = "📺"
        elif raw_text:
            logo_val = raw_text.strip()[:6]

        db.update_channel_basic(chid, logo=logo_val)
        user_states.pop(user_id, None)
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("📺 عرض تفاصيل القناة", callback_data=f"ch_view_{chid}"))
        kb.add(types.InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="main_menu"))
        bot.reply_to(message, "✅ <b>تم تحديث شعار القناة بنجاح!</b>", reply_markup=kb)
        return

def start_bot_polling():
    if not BOT_INITIALIZED:
        logger.warning("Bot token not configured properly, polling skipped.")
        return
    logger.info("Starting Telegram Bot Polling with clean modern UI...")
    bot.infinity_polling(timeout=20, long_polling_timeout=20)

run_bot = start_bot_polling

if __name__ == "__main__":
    start_bot_polling()
