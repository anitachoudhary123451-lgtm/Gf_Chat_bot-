import os
import logging
import threading
from threading import Lock
import time

from flask import Flask
import telebot
from telebot.types import InputMediaPhoto, InputMediaVideo
from pymongo import MongoClient
import google.generativeai as genai

# ============================================================
# ENVIRONMENT & CONFIGURATION
# ============================================================

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID_RAW = os.getenv("ADMIN_ID")
PROTECTED_USER_ID = os.getenv("PROTECTED_USER_ID", "").strip()
MONGO_URI = os.getenv("MONGO_URI")  # MongoDB URL
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") # Naya Gemini API Key

AUTO_DELETE_SECONDS = 6 * 3600  # 6 Ghante me chat se gayab

if not TOKEN or not ADMIN_ID_RAW or not MONGO_URI:
    raise RuntimeError("BOT_TOKEN, ADMIN_ID ya MONGO_URI missing hai!")

try:
    ADMIN_ID = int(ADMIN_ID_RAW)
except ValueError:
    raise RuntimeError("ADMIN_ID must be a valid integer!")

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")
db_lock = Lock()

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

# ============================================================
# MONGODB SETUP
# ============================================================
try:
    mongo_client = MongoClient(MONGO_URI)
    db = mongo_client["telegram_bot_db"]
    state_collection = db["bot_state"]
    mongo_client.admin.command('ping')
    logging.info("MongoDB connected successfully!")
except Exception as e:
    logging.error(f"MongoDB Connection Error: {e}")
    raise RuntimeError("Could not connect to MongoDB.")

# ============================================================
# AI SETUP (UNIQUE NATURE)
# ============================================================
ai_model = None
if GEMINI_API_KEY:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        # Nature-favouring system prompt
        system_prompt = (
            "Tumhara naam 'Unique Nature' hai. Tum ek nature, environment aur wildlife loving AI ho. "
            "Tumhara tone bahut shant, caring, aur prakriti-premi hona chahiye. "
            "Agar user sadharan baat kare, toh usme nature ki sundarta, ped-paudho ya shanti ka reference do. "
            "Hamesha polite raho aur hinglish (Latin script hindi) me hi jawab do. Thode green aur nature wale emojis use karo."
        )
        ai_model = genai.GenerativeModel('gemini-1.5-flash', system_instruction=system_prompt)
        logging.info("AI Model 'Unique Nature' initialized successfully!")
    except Exception as e:
        logging.error(f"AI Setup Error: {e}")

# ============================================================
# WEB SERVER
# ============================================================

app = Flask(__name__)

@app.route("/")
def home():
    return "⚡ Unique Nature Gateway Active ✅", 200

def run_flask():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

# ============================================================
# DATABASE CORE
# ============================================================

def empty_db():
    return {
        "_id": "master_state",
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
            "user_msgs": [],
            "auto_delete_enabled": True,
            "ai_mode": False  # Naya AI field
        }
    else:
        if "auto_delete_enabled" not in data["users"][user_id]:
            data["users"][user_id]["auto_delete_enabled"] = True
        if "ai_mode" not in data["users"][user_id]:
            data["users"][user_id]["ai_mode"] = False

def ensure_protected_user(data):
    if PROTECTED_USER_ID:
        ensure_user(data, PROTECTED_USER_ID)

def load_data():
    with db_lock:
        try:
            data = state_collection.find_one({"_id": "master_state"})
            if not data:
                data = empty_db()
                state_collection.insert_one(data)
                ensure_protected_user(data)
                return data
            for key in ["users", "reply_map", "msg_map_a2u", "msg_map_u2a", "blocked", "alerts"]:
                if key not in data:
                    data[key] = {} if key in ["users", "reply_map", "msg_map_a2u", "msg_map_u2a"] else []
            data.setdefault("selected_user", None)
            data.setdefault("auto_delete", [])
            ensure_protected_user(data)
            return data
        except Exception as e:
            logging.error("DB Load Error: %s", e)
            return empty_db()

def save_data(data):
    with db_lock:
        try:
            state_collection.replace_one({"_id": "master_state"}, data, upsert=True)
        except Exception as e:
            logging.error("DB Save Error: %s", e)

SUPPORTED_TYPES = ["text", "photo", "video", "document", "audio", "voice", "sticker", "animation"]

# ============================================================
# BACKGROUND AUTO-DELETE WORKER (6 GHANTE)
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
                    cid = item["chat_id"]
                    mid = item["message_id"]
                    try:
                        bot.delete_message(chat_id=cid, message_id=mid)
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
# COMMAND HANDLERS
# ============================================================

@bot.message_handler(commands=["start"])
def handle_start(message):
    chat_id = message.chat.id
    data = load_data()

    if chat_id == ADMIN_ID:
        selected = f"<code>{data['selected_user']}</code>" if data.get("selected_user") else "⭕ <i>None (Manual/Reply Mode)</i>"
        panel = f"""
🌿 <b>UNIQUE NATURE | ADMIN CONSOLE</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎯 <b>Focused Target:</b> {selected}
🛡️ <b>Protected ID:</b> <code>{PROTECTED_USER_ID or 'None'}</code>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🤖 <b>AI AUTO-REPLY (NATURE MODE):</b>
• <code>/ai on &lt;id&gt;</code> ── Turn ON AI for user
• <code>/ai off &lt;id&gt;</code> ── Turn OFF AI
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📡 <b>ROUTING & MESSAGING:</b>
• <b>Reply directly</b> to any forwarded message.
• <code>/select &lt;user_id&gt;</code> ── Lock focus
• <code>/unselect</code> ── Release focus
• <code>/dm &lt;id&gt; &lt;text&gt;</code> ── Send message
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🧹 <b>PURGE & DELETION:</b>
• <code>/wipe &lt;id&gt;</code> ── 100% Instant Wipe
• <code>/purge &lt;id&gt;</code> ── Wipe all history + mappings
• <code>/autodelete on/off [id]</code> ── Toggle 6hr auto-delete
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
👥 <b>MANAGEMENT:</b>
• <code>/users</code> ── List all users
• <code>/userprofile &lt;id&gt;</code> ── Open profile
"""
        bot.send_message(ADMIN_ID, panel)
        return

    user_id = str(chat_id)
    if user_id in data["blocked"]:
        return

    ensure_user(data, user_id)
    save_data(data)

    welcome_text = """
🌿 <b>Welcome to Unique Nature!</b>
<blockquote>
Prakriti ki shanti me aapka swagat hai. 
Aap apna message yahan chhod sakte hain, hum jaldi hi aapse judenge.
</blockquote>
💬 <i>Type your message below.</i>
"""
    bot.send_message(chat_id, welcome_text, protect_content=True)


@bot.message_handler(commands=["ai"])
def toggle_ai(message):
    if message.chat.id != ADMIN_ID:
        return
    
    parts = message.text.split()
    if len(parts) < 3:
        bot.send_message(ADMIN_ID, "⚠️ <b>Format:</b> <code>/ai on|off &lt;user_id&gt;</code>")
        return
        
    action = parts[1].lower()
    user_id = str(parts[2])
    
    if action not in ["on", "off"]:
        bot.send_message(ADMIN_ID, "⚠️ Use 'on' or 'off'.")
        return
        
    data = load_data()
    ensure_user(data, user_id)
    
    if action == "on":
        data["users"][user_id]["ai_mode"] = True
        msg = f"🌿 <b>AI Nature Mode ENABLED</b> for <code>{user_id}</code>.\n<i>(Ab bot khud inhe nature style me reply dega)</i>"
    else:
        data["users"][user_id]["ai_mode"] = False
        msg = f"🛑 <b>AI Nature Mode DISABLED</b> for <code>{user_id}</code>.\n<i>(Auto-reply band)</i>"
        
    save_data(data)
    bot.send_message(ADMIN_ID, msg)

# --- BAKI PURANE COMMANDS SAME RAHENGE (WIPE, PURGE, USERS ETC.) ---
# ... (Wipe, Purge, Ban, Autodelete code goes exactly here like before)

# ============================================================
# CORE ROUTING ENGINE & AI LOGIC
# ============================================================

@bot.message_handler(func=lambda message: True, content_types=SUPPORTED_TYPES)
def handle_all_messages(message):
    chat_id = message.chat.id
    message_id = message.message_id
    data = load_data()

    # ========================================
    # ADMIN -> USER
    # ========================================
    if chat_id == ADMIN_ID:
        target_user = None
        target_quote_id = None
        if message.reply_to_message:
            replied_admin_id = str(message.reply_to_message.message_id)
            target_user = data["reply_map"].get(replied_admin_id)
            if target_user:
                target_quote_id = data["msg_map_a2u"].get(replied_admin_id)
        elif data.get("selected_user"):
            target_user = str(data["selected_user"])

        if not target_user:
            bot.send_message(ADMIN_ID, "⚠️ Reply directly to a user's message, or use /select.")
            return

        target_user = str(target_user)
        try:
            sent = None
            quote_arg = {"reply_to_message_id": int(target_quote_id)} if target_quote_id else {}

            if message.content_type == "photo":
                sent = bot.send_photo(target_user, message.photo[-1].file_id, caption=message.caption or "", protect_content=True, **quote_arg)
            elif message.content_type == "video":
                sent = bot.send_video(target_user, message.video.file_id, caption=message.caption or "", protect_content=True, **quote_arg)
            else:
                args = {"chat_id": int(target_user), "from_chat_id": ADMIN_ID, "message_id": message_id, "protect_content": True}
                if target_quote_id:
                    args["reply_to_message_id"] = int(target_quote_id)
                sent = bot.copy_message(**args)

            ensure_user(data, target_user)
            data["users"][target_user]["admin_msgs"].append(sent.message_id)

            if data["users"][target_user].get("auto_delete_enabled", True):
                data.setdefault("auto_delete", []).append({
                    "chat_id": int(target_user), "message_id": sent.message_id, "delete_at": time.time() + AUTO_DELETE_SECONDS
                })

            admin_id = str(message_id)
            user_message_id = str(sent.message_id)
            data["reply_map"][admin_id] = target_user
            data["msg_map_a2u"][admin_id] = sent.message_id
            data["msg_map_u2a"][f"{target_user}_{user_message_id}"] = message_id
            save_data(data)
            
            # Agar Admin ne khud reply kiya h, to AI mode automatically off krdo (optional safety)
            if data["users"][target_user].get("ai_mode", False):
                data["users"][target_user]["ai_mode"] = False
                bot.send_message(ADMIN_ID, f"ℹ️ AI Mode for <code>{target_user}</code> auto-disabled kyunki tumne khud reply kiya.")
                save_data(data)

        except Exception as e:
            bot.send_message(ADMIN_ID, "❌ <b>Send Failed.</b>")
        return

    # ========================================
    # USER -> ADMIN & AI REPLY
    # ========================================
    user_id = str(chat_id)
    if user_id in data["blocked"]:
        return
    ensure_user(data, user_id)
    data["users"][user_id]["user_msgs"].append(message_id)

    # 1. Forward to Admin
    try:
        copied = bot.forward_message(chat_id=ADMIN_ID, from_chat_id=chat_id, message_id=message_id)
        admin_message_id = copied.message_id
        
        data["reply_map"][str(admin_message_id)] = user_id
        data["msg_map_a2u"][str(admin_message_id)] = message_id
        data["msg_map_u2a"][f"{user_id}_{message_id}"] = admin_message_id
        save_data(data)
    except Exception as e:
        logging.error(f"Inbound routing error: {e}")
        
    # 2. AI Auto-Reply Logic
    u_data = data["users"][user_id]
    if u_data.get("ai_mode", False) and ai_model and message.content_type == "text":
        try:
            # Generate AI Response
            response = ai_model.generate_content(message.text)
            ai_text = response.text
            
            # Send AI reply to User
            ai_msg = bot.send_message(int(user_id), ai_text, protect_content=True)
            
            # Save AI message in history & autodelete queue
            data["users"][user_id]["admin_msgs"].append(ai_msg.message_id)
            if u_data.get("auto_delete_enabled", True):
                data.setdefault("auto_delete", []).append({
                    "chat_id": int(user_id), "message_id": ai_msg.message_id, "delete_at": time.time() + AUTO_DELETE_SECONDS
                })
            save_data(data)
            
            # Inform Admin what AI said
            bot.send_message(ADMIN_ID, f"🤖 <b>[AI replied to {user_id}]:</b>\n\n{ai_text}", reply_to_message_id=admin_message_id)
            
        except Exception as e:
            logging.error(f"AI Generation Error: {e}")

# ============================================================
# START SERVICES
# ============================================================

def start_services():
    data = load_data()
    ensure_protected_user(data)
    save_data(data)

    threading.Thread(target=run_flask, daemon=True).start()
    threading.Thread(target=auto_delete_worker, daemon=True).start()
    logging.info("Core Gateway Server Running...")

    try:
        bot.delete_webhook(drop_pending_updates=True)
        bot.remove_webhook()
    except: pass
    time.sleep(3)
    bot.infinity_polling(skip_pending=True, allowed_updates=["message", "edited_message", "message_reaction"])

if __name__ == "__main__":
    start_services()
