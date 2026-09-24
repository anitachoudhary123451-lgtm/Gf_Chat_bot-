import os
import json
import logging
import threading
from threading import Lock
import time

from flask import Flask
import telebot

# ============================================================
# ENVIRONMENT & CONFIGURATION
# ============================================================

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID_RAW = os.getenv("ADMIN_ID")
PROTECTED_USER_ID = os.getenv("PROTECTED_USER_ID", "").strip()

DATA_FILE = "bot_data.json"
AUTO_DELETE_SECONDS = 6 * 3600  # 6 Ghante (21600 seconds)

if not TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is not set!")

if not ADMIN_ID_RAW:
    raise RuntimeError("ADMIN_ID environment variable is not set!")

try:
    ADMIN_ID = int(ADMIN_ID_RAW)
except ValueError:
    raise RuntimeError("ADMIN_ID must be a valid integer!")

bot = telebot.TeleBot(
    TOKEN,
    parse_mode="HTML"
)

db_lock = Lock()

# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

# ============================================================
# WEB SERVER / KEEP ALIVE
# ============================================================

app = Flask(__name__)

@app.route("/")
def home():
    return "⚡ Gateway Service Active ✅", 200

def run_flask():
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 10000))
    )

# ============================================================
# DATABASE CORE
# ============================================================

def empty_db():
    return {
        "users": {},
        "reply_map": {},
        "msg_map_a2u": {},
        "msg_map_u2a": {},
        "blocked": [],
        "alerts": [],
        "selected_user": None,
        "auto_delete": []
    }

def ensure_user(data, user_id):
    user_id = str(user_id)
    if user_id not in data["users"]:
        data["users"][user_id] = {
            "admin_msgs": [],
            "user_msgs": []
        }

def ensure_protected_user(data):
    if PROTECTED_USER_ID:
        ensure_user(data, PROTECTED_USER_ID)

def load_data():
    with db_lock:
        if not os.path.exists(DATA_FILE):
            data = empty_db()
            ensure_protected_user(data)
            return data

        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

            for key in ["users", "reply_map", "msg_map_a2u", "msg_map_u2a", "blocked", "alerts"]:
                if key not in data:
                    if key in ["users", "reply_map", "msg_map_a2u", "msg_map_u2a"]:
                        data[key] = {}
                    else:
                        data[key] = []

            data.setdefault("selected_user", None)
            data.setdefault("auto_delete", [])
            ensure_protected_user(data)
            return data

        except Exception as e:
            logging.error("DB Load Error: %s", e)
            data = empty_db()
            ensure_protected_user(data)
            return data

def save_data(data):
    with db_lock:
        temp_file = DATA_FILE + ".tmp"
        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(temp_file, DATA_FILE)
        except Exception as e:
            logging.error("DB Save Error: %s", e)

SUPPORTED_TYPES = [
    "text", "photo", "video", "document",
    "audio", "voice", "sticker", "animation"
]

# ============================================================
# BACKGROUND AUTO-DELETE WORKER (6 GHANTE TIMER)
# ============================================================

def auto_delete_worker():
    while True:
        try:
            time.sleep(15)
            now = time.time()
            data = load_data()
            queue = data.get("auto_delete", [])
            if not queue:
                continue

            remaining = []
            modified = False

            for item in queue:
                if now >= item.get("delete_at", 0):
                    try:
                        bot.delete_message(chat_id=item["chat_id"], message_id=item["message_id"])
                    except Exception:
                        pass
                    modified = True
                else:
                    remaining.append(item)

            if modified:
                data["auto_delete"] = remaining
                save_data(data)

        except Exception as e:
            logging.error("Auto delete worker error: %s", e)

# ============================================================
# START COMMAND
# ============================================================

@bot.message_handler(commands=["start"])
def handle_start(message):
    chat_id = message.chat.id
    data = load_data()

    if chat_id == ADMIN_ID:
        selected = (f"<code>{data['selected_user']}</code>" if data.get("selected_user") else "⭕ <i>None (Manual/Reply Mode)</i>")
        protected_label = f"<code>{PROTECTED_USER_ID}</code>" if PROTECTED_USER_ID else "<i>None</i>"
        panel = f"""
🎛️ <b>CONTROL CONSOLE | ADMIN</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎯 <b>Focused Target:</b> {selected}
🛡️ <b>Protected User ID:</b> {protected_label}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📡 <b>ROUTING & MESSAGING:</b>
• <b>Reply directly</b> to any forwarded user message to quote-reply.
• <code>/select &lt;user_id&gt;</code>
  └─ Lock focus to a specific user
• <code>/unselect</code>
  └─ Release locked focus
• <code>/dm &lt;id&gt; &lt;text&gt;</code>
  └─ Send standalone message (copy protected)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🧹 <b>PURGE & DELETION:</b>
• <code>/wipe &lt;id&gt;</code>
  └─ <b>100% Instant Wipe:</b> User chat screen se user + admin messages gayab
• <code>/clearall &lt;id&gt;</code>
  └─ Delete Admin messages from user chat
• <code>/purge &lt;id&gt;</code>
  └─ Wipe known user + admin messages & mappings
• <code>/resetdb</code>
  └─ Reset database and session mappings
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
👥 <b>MANAGEMENT:</b>
• <code>/users</code>
  └─ List all users
• <code>/userprofile &lt;id&gt;</code>
  └─ Open Telegram profile
• <code>/ban &lt;id&gt;</code>
  └─ Block user
• <code>/unban &lt;id&gt;</code>
  └─ Restore user access
• <code>/alert &lt;id&gt;</code>
  └─ Toggle priority flag
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔒 <i>User Protection: Screenshot, screen record, save aur forward sab locked hai. Admin messages 6 hrs me auto-delete hote hain.</i>
"""
        bot.send_message(ADMIN_ID, panel)
        return

    user_id = str(chat_id)
    if user_id in data["blocked"]:
        return

    ensure_user(data, user_id)
    save_data(data)

    welcome_text = """
🔒 <b>ENCRYPTED SECURE CHANNEL</b>
<blockquote>
Aapka direct communication session establish ho chuka hai.
Aap yahan apna koi bhi message, photo,
video ya document bhej sakte hain.
Hamaari team aapse isi chat me connect karegi.
</blockquote>
💬 <i>Apna sandesh niche type karke send karein.</i>
"""
    bot.send_message(chat_id, welcome_text, protect_content=True)

# ============================================================
# COMMAND HANDLERS
# ============================================================

@bot.message_handler(commands=["wipe"])
def wipe_chat(message):
    if message.chat.id != ADMIN_ID:
        return
    try:
        user_id = message.text.split()[1]
    except IndexError:
        data = load_data()
        user_id = data.get("selected_user")
        if not user_id:
            bot.send_message(ADMIN_ID, "⚠️ <b>Format:</b> <code>/wipe &lt;user_id&gt;</code>")
            return

    user_id = str(user_id)
    data = load_data()
    if user_id not in data["users"]:
        bot.send_message(ADMIN_ID, "⚠️ User history not found.")
        return

    user_msgs = list(data["users"][user_id].get("user_msgs", []))
    admin_msgs = list(data["users"][user_id].get("admin_msgs", []))
    total = 0

    # User ke khud ke messages user chat se delete
    for msg_id in user_msgs:
        try:
            bot.delete_message(chat_id=int(user_id), message_id=int(msg_id))
            total += 1
        except Exception:
            pass

    # Admin ke messages user chat se delete
    for msg_id in admin_msgs:
        try:
            bot.delete_message(chat_id=int(user_id), message_id=int(msg_id))
            total += 1
        except Exception:
            pass

    data["users"][user_id]["user_msgs"] = []
    data["users"][user_id]["admin_msgs"] = []
    data["auto_delete"] = [x for x in data.get("auto_delete", []) if str(x.get("chat_id")) != user_id]
    save_data(data)
    bot.send_message(ADMIN_ID, f"🧹 <b>100% Wiped:</b> User <code>{user_id}</code> ki screen se <b>{total}</b> messages delete kar diye gaye.")

@bot.message_handler(commands=["select"])
def select_user(message):
    if message.chat.id != ADMIN_ID: return
    try: user_id = message.text.split()[1]
    except IndexError:
        bot.send_message(ADMIN_ID, "⚠️ <b>Format:</b> <code>/select &lt;user_id&gt;</code>"); return
    data = load_data()
    ensure_user(data, user_id)
    data["selected_user"] = str(user_id)
    save_data(data)
    bot.send_message(ADMIN_ID, f"🎯 <b>Focus Locked:</b> <code>{user_id}</code>")

@bot.message_handler(commands=["unselect"])
def unselect_user(message):
    if message.chat.id != ADMIN_ID: return
    data = load_data()
    data["selected_user"] = None
    save_data(data)
    bot.send_message(ADMIN_ID, "🎯 <b>Focus Released.</b> Manual/Reply mode active.")

@bot.message_handler(commands=["dm"])
def direct_message(message):
    if message.chat.id != ADMIN_ID: return
    try:
        parts = message.text.split(" ", 2)
        user_id = parts[1]
        text = parts[2]
    except IndexError:
        bot.send_message(ADMIN_ID, "⚠️ <b>Format:</b> <code>/dm &lt;user_id&gt; &lt;text&gt;</code>"); return
    data = load_data()
    if user_id in data["blocked"]:
        bot.send_message(ADMIN_ID, "⛔ User is blocked."); return
    try:
        # User side screenshot/save/forward locked
        sent = bot.send_message(int(user_id), text, protect_content=True)
        ensure_user(data, user_id)
        data["users"][user_id]["admin_msgs"].append(sent.message_id)

        # 6-Hour Auto Delete
        data.setdefault("auto_delete", []).append({
            "chat_id": int(user_id),
            "message_id": sent.message_id,
            "delete_at": time.time() + AUTO_DELETE_SECONDS
        })

        admin_message_id = str(message.message_id)
        data["reply_map"][admin_message_id] = str(user_id)
        data["msg_map_a2u"][admin_message_id] = sent.message_id
        data["msg_map_u2a"][f"{user_id}_{sent.message_id}"] = message.message_id
        save_data(data)
        bot.send_message(ADMIN_ID, f"✅ <b>Sent to</b> <code>{user_id}</code> (Protected + Auto-deletes in 6 hrs)")
    except Exception as e:
        logging.error("DM delivery error: %s", e)
        bot.send_message(ADMIN_ID, "❌ <b>Delivery failed.</b>")

@bot.message_handler(commands=["clearall"])
def clear_admin_messages(message):
    if message.chat.id != ADMIN_ID: return
    try: user_id = message.text.split()[1]
    except IndexError:
        data = load_data()
        user_id = data.get("selected_user")
        if not user_id:
            bot.send_message(ADMIN_ID, "⚠️ <b>Format:</b> <code>/clearall &lt;user_id&gt;</code>"); return
    user_id = str(user_id)
    data = load_data()
    if user_id not in data["users"]:
        bot.send_message(ADMIN_ID, "⚠️ No message history found."); return
    admin_msgs = data["users"][user_id].get("admin_msgs", [])
    count = 0
    for msg_id in admin_msgs:
        try: bot.delete_message(chat_id=int(user_id), message_id=int(msg_id)); count += 1
        except Exception: pass
    data["users"][user_id]["admin_msgs"] = []
    save_data(data)
    bot.send_message(ADMIN_ID, f"🧹 <b>Cleared:</b> {count} Admin messages deleted from <code>{user_id}</code>'s chat.")

@bot.message_handler(commands=["purge"])
def purge_chat(message):
    if message.chat.id != ADMIN_ID: return
    try: user_id = message.text.split()[1]
    except IndexError:
        bot.send_message(ADMIN_ID, "⚠️ <b>Format:</b> <code>/purge &lt;user_id&gt;</code>"); return
    user_id = str(user_id)
    data = load_data()
    if user_id not in data["users"]:
        bot.send_message(ADMIN_ID, "⚠️ User history not found."); return
    user_data = data["users"][user_id]
    user_msgs = list(user_data.get("user_msgs", []))
    admin_msgs = list(user_data.get("admin_msgs", []))
    total = 0
    for msg_id in user_msgs:
        try: bot.delete_message(chat_id=int(user_id), message_id=int(msg_id)); total += 1
        except Exception: pass
    for msg_id in admin_msgs:
        try: bot.delete_message(chat_id=int(user_id), message_id=int(msg_id)); total += 1
        except Exception: pass
    reply_map = data.get("reply_map", {})
    msg_map_a2u = data.get("msg_map_a2u", {})
    msg_map_u2a = data.get("msg_map_u2a", {})
    for admin_id, mapped_user in list(reply_map.items()):
        if str(mapped_user) == user_id:
            reply_map.pop(admin_id, None); msg_map_a2u.pop(admin_id, None)
    prefix = f"{user_id}_"
    for key in list(msg_map_u2a.keys()):
        if key.startswith(prefix): msg_map_u2a.pop(key, None)
    data["users"][user_id] = {"admin_msgs": [], "user_msgs": []}
    data["auto_delete"] = [x for x in data.get("auto_delete", []) if str(x.get("chat_id")) != user_id]
    save_data(data)
    bot.send_message(ADMIN_ID, f"💥 <b>Purge completed.</b>\n\n👤 User: <code>{user_id}</code>\n🗑 Deleted known messages: <b>{total}</b>\n🧹 Routing mappings cleared.")

@bot.message_handler(commands=["resetdb"])
def reset_database(message):
    if message.chat.id != ADMIN_ID: return
    data = empty_db()
    ensure_protected_user(data)
    save_data(data)
    bot.send_message(ADMIN_ID, "♻️ <b>Database Reset:</b> All state logs and mappings cleared.")

@bot.message_handler(commands=["users"])
def list_users(message):
    if message.chat.id != ADMIN_ID: return
    data = load_data()
    users_dict = data.get("users", {})
    if not users_dict:
        bot.send_message(ADMIN_ID, "👥 <b>No registered users found.</b>"); return
    text = "📊 <b>USER DIRECTORY</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    for i, user_id in enumerate(users_dict.keys(), 1):
        if user_id in data["blocked"]: status = "⛔ [Banned]"
        elif user_id in data["alerts"]: status = "🚨 [Flagged]"
        elif user_id == PROTECTED_USER_ID: status = "🛡️ [Protected]"
        else: status = "🟢 [Active]"
        text += f"{i}. <code>{user_id}</code> ── {status}\n"
    bot.send_message(ADMIN_ID, text)

@bot.message_handler(commands=["ban"])
def ban_user(message):
    if message.chat.id != ADMIN_ID: return
    try: user_id = message.text.split()[1]
    except IndexError: bot.send_message(ADMIN_ID, "⚠️ <b>Format:</b> <code>/ban &lt;user_id&gt;</code>"); return
    user_id = str(user_id)
    data = load_data()
    if user_id not in data["blocked"]:
        data["blocked"].append(user_id); save_data(data)
        bot.send_message(ADMIN_ID, f"⛔ User <code>{user_id}</code> is now blocked.")
    else: bot.send_message(ADMIN_ID, "⚠️ User is already blocked.")

@bot.message_handler(commands=["unban"])
def unban_user(message):
    if message.chat.id != ADMIN_ID: return
    try: user_id = message.text.split()[1]
    except IndexError: bot.send_message(ADMIN_ID, "⚠️ <b>Format:</b> <code>/unban &lt;user_id&gt;</code>"); return
    user_id = str(user_id)
    data = load_data()
    if user_id in data["blocked"]:
        data["blocked"].remove(user_id); save_data(data)
        bot.send_message(ADMIN_ID, f"✅ User <code>{user_id}</code> unblocked.")
    else: bot.send_message(ADMIN_ID, "⚠️ User is not blocked.")

@bot.message_handler(commands=["alert"])
def toggle_alert(message):
    if message.chat.id != ADMIN_ID: return
    try: user_id = message.text.split()[1]
    except IndexError: bot.send_message(ADMIN_ID, "⚠️ <b>Format:</b> <code>/alert &lt;user_id&gt;</code>"); return
    user_id = str(user_id)
    data = load_data()
    if user_id not in data["alerts"]:
        data["alerts"].append(user_id); save_data(data)
        bot.send_message(ADMIN_ID, f"🚨 Alert flag ADDED to <code>{user_id}</code>.")
    else:
        data["alerts"].remove(user_id); save_data(data)
        bot.send_message(ADMIN_ID, f"🏳️ Alert flag REMOVED from <code>{user_id}</code>.")

@bot.message_handler(commands=["userprofile"])
def user_profile(message):
    if message.chat.id != ADMIN_ID: return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.send_message(ADMIN_ID, "⚠️ <b>Format:</b> <code>/userprofile &lt;user_id&gt;</code>"); return
    user_id = parts[1].strip()
    if not user_id.lstrip("-").isdigit():
        bot.send_message(ADMIN_ID, "⚠️ Invalid Chat ID."); return
    data = load_data()
    if user_id not in data.get("users", {}):
        if user_id == PROTECTED_USER_ID:
            ensure_protected_user(data); save_data(data)
        else:
            bot.send_message(ADMIN_ID, f"⚠️ User <code>{user_id}</code> is not registered."); return
    u = data["users"].get(user_id, {})
    if user_id in data["blocked"]: status = "⛔ Banned"
    elif user_id in data["alerts"]: status = "🚨 Alert"
    elif user_id == PROTECTED_USER_ID: status = "🛡️ Protected"
    else: status = "🟢 Active"
    link = f"tg://user?id={user_id}"
    text = (f"👤 <b>USER PROFILE</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n🆔 <b>Chat ID:</b> <code>{user_id}</code>\n📊 <b>Status:</b> {status}\n💬 <b>User Messages:</b> {len(u.get('user_msgs', []))}\n📨 <b>Admin Messages:</b> {len(u.get('admin_msgs', []))}\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n<a href=\"{link}\">🔗 OPEN TELEGRAM PROFILE</a>")
    bot.send_message(ADMIN_ID, text, disable_web_page_preview=True)

# ============================================================
# CORE ROUTING ENGINE - ASYMMETRIC PROTECTION
# ============================================================

@bot.message_handler(func=lambda message: True, content_types=SUPPORTED_TYPES)
def handle_all_messages(message):
    chat_id = message.chat.id
    message_id = message.message_id
    data = load_data()

    # ========================================================
    # ADMIN -> USER (COPY MODE + PROTECT_CONTENT = ADMIN 100% HIDE, USER BLOCKED FROM SAVING/RECORDING)
    # ========================================================
    if chat_id == ADMIN_ID:
        target_user = None
        target_quote_id = None
        if message.reply_to_message:
            replied_admin_id = str(message.reply_to_message.message_id)
            target_user = data["reply_map"].get(replied_admin_id)
            if target_user: target_quote_id = data["msg_map_a2u"].get(replied_admin_id)
        elif data.get("selected_user"):
            target_user = str(data["selected_user"])

        if not target_user:
            bot.send_message(ADMIN_ID, "⚠️ <b>Action Required:</b> Reply directly to a user's forwarded message, or use <code>/select &lt;user_id&gt;</code>."); return

        target_user = str(target_user)
        if target_user in data["blocked"]:
            bot.send_message(ADMIN_ID, "⛔ Delivery failed: User is blocked."); return

        try:
            # User ko copy karke bhejenge taaki admin hide rahe + protect_content se user screenshot/recording na le sake
            args = {
                "chat_id": int(target_user),
                "from_chat_id": ADMIN_ID,
                "message_id": message_id,
                "protect_content": True
            }
            if target_quote_id:
                args["reply_to_message_id"] = int(target_quote_id)

            sent = bot.copy_message(**args)

            ensure_user(data, target_user)
            data["users"][target_user]["admin_msgs"].append(sent.message_id)

            # Auto-Delete in 6 hours queue
            data.setdefault("auto_delete", []).append({
                "chat_id": int(target_user),
                "message_id": sent.message_id,
                "delete_at": time.time() + AUTO_DELETE_SECONDS
            })

            admin_id = str(message_id)
            user_message_id = str(sent.message_id)
            data["reply_map"][admin_id] = target_user
            data["msg_map_a2u"][admin_id] = sent.message_id
            data["msg_map_u2a"][f"{target_user}_{user_message_id}"] = message_id
            save_data(data)
        except Exception as e:
            logging.error("Admin -> User routing error: %s", e)
            bot.send_message(ADMIN_ID, "❌ <b>Send Failed.</b>")
        return

    # ========================================================
    # USER -> ADMIN (FORWARD MODE = ADMIN KO DIRECT PROFILE DIKHEGI, NO RESTRICTION ON ADMIN)
    # ========================================================
    user_id = str(chat_id)
    if user_id in data["blocked"]: return
    ensure_user(data, user_id)
    data["users"][user_id]["user_msgs"].append(message_id)

    reply_to_admin_msg_id = None
    if message.reply_to_message:
        replied_user_msg_id = message.reply_to_message.message_id
        lookup_key = f"{user_id}_{replied_user_msg_id}"
        reply_to_admin_msg_id = data["msg_map_u2a"].get(lookup_key)

    try:
        # bot.forward_message use hoga: Admin ko sender ki actual profile dikhegi
        # Koi protect_content nahi lagega taaki admin screenshot, save ya screen recording aaram se kar sake
        copied = bot.forward_message(chat_id=ADMIN_ID, from_chat_id=chat_id, message_id=message_id)
        admin_message_id = copied.message_id

        if reply_to_admin_msg_id:
            try:
                bot.copy_message(chat_id=ADMIN_ID, from_chat_id=chat_id, message_id=message_id, reply_to_message_id=int(reply_to_admin_msg_id))
                try:
                    bot.delete_message(chat_id=ADMIN_ID, message_id=admin_message_id)
                    admin_message_id = admin_message_id + 1
                except Exception: pass
            except Exception: pass

        data["reply_map"][str(admin_message_id)] = user_id
        data["msg_map_a2u"][str(admin_message_id)] = message_id
        data["msg_map_u2a"][f"{user_id}_{message_id}"] = admin_message_id

        if user_id in data["alerts"]:
            try: bot.send_message(ADMIN_ID, f"🚨 <b>ALERT: Flagged User Active</b>\n👤 <code>{user_id}</code>", reply_to_message_id=admin_message_id)
            except Exception: pass

        save_data(data)
    except Exception as e:
        logging.error("Inbound routing error: %s", e)

# ============================================================
# REACTION & EDIT SYNC
# ============================================================

def _reaction_to_payload(reaction):
    try:
        if reaction.type == "emoji": return {"type": "emoji", "emoji": reaction.emoji}
        if reaction.type == "custom_emoji": return {"type": "custom_emoji", "custom_emoji_id": reaction.custom_emoji_id}
    except Exception: pass
    return None

def _mirror_reaction_to_other_side(source_chat_id, source_message_id, reaction_items, is_user_side):
    data = load_data()
    source_message_id = int(source_message_id)
    if is_user_side:
        user_id = str(source_chat_id)
        counterpart = data["msg_map_u2a"].get(f"{user_id}_{source_message_id}")
        target_chat_id = ADMIN_ID
    else:
        counterpart = data["msg_map_a2u"].get(str(source_message_id))
        target_user = data["reply_map"].get(str(source_message_id))
        if not target_user: return
        target_chat_id = int(target_user)
    if not counterpart: return
    try: bot.set_message_reaction(chat_id=target_chat_id, message_id=int(counterpart), reaction=[])
    except Exception as e: logging.warning("Could not clear mirrored reaction: %s", e)
    if not reaction_items: return
    for item in reaction_items:
        payload = _reaction_to_payload(item)
        if not payload: continue
        try: bot.set_message_reaction(chat_id=target_chat_id, message_id=int(counterpart), reaction=[payload]); break
        except Exception as e: logging.warning("Could not mirror reaction: %s", e)

if hasattr(bot, "message_reaction_handler"):
    @bot.message_reaction_handler(func=lambda reaction: True)
    def handle_message_reaction(reaction):
        try:
            is_user = (reaction.chat.id != ADMIN_ID)
            new_reaction = getattr(reaction, "new_reaction", None) or []
            _mirror_reaction_to_other_side(source_chat_id=reaction.chat.id, source_message_id=reaction.message_id, reaction_items=new_reaction, is_user_side=is_user)
        except Exception as e: logging.error("Reaction sync error: %s", e)

@bot.edited_message_handler(func=lambda message: True, content_types=SUPPORTED_TYPES)
def handle_edits(message):
    chat_id = message.chat.id
    message_id = message.message_id
    data = load_data()
    if chat_id == ADMIN_ID:
        user_target_msg_id = data["msg_map_a2u"].get(str(message_id))
        target_user = data["reply_map"].get(str(message_id))
        if user_target_msg_id and target_user:
            try:
                if message.content_type == "text": bot.edit_message_text(message.text, int(target_user), int(user_target_msg_id))
            except Exception: pass
        return
    user_id = str(chat_id)
    admin_ref_id = data["msg_map_u2a"].get(f"{user_id}_{message_id}")
    if admin_ref_id:
        try:
            if message.content_type == "text": bot.send_message(ADMIN_ID, f"✏️ <b>[User Edited Message]</b>\n\n{message.text}", reply_to_message_id=int(admin_ref_id))
        except Exception: pass

# ============================================================
# START SERVICES
# ============================================================

def start_services():
    data = load_data()
    ensure_protected_user(data)
    save_data(data)

    threading.Thread(target=run_flask, daemon=True).start()
    threading.Thread(target=auto_delete_worker, daemon=True).start()
    logging.info("Core Gateway Server Running with Auto-Delete Worker...")

    try:
        bot.delete_webhook(drop_pending_updates=True)
        bot.remove_webhook()
        logging.info("Webhook cleared, waiting 3 sec...")
    except Exception as e:
        logging.warning(f"Webhook clear warning: {e}")

    time.sleep(3)

    bot.infinity_polling(
        skip_pending=True,
        timeout=20,
        long_polling_timeout=20,
        allowed_updates=["message", "edited_message", "message_reaction"]
    )

if __name__ == "__main__":
    try: start_services()
    except Exception as e: logging.exception("Fatal Service Error: %s", e)
