import os
import json
import logging
import threading
from threading import Lock
import time
from functools import wraps
from flask import Flask
import telebot

# ============================================================
# CONFIGURATION
# ============================================================

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID_RAW = os.getenv("ADMIN_ID")
PROTECTED_USER_ID = os.getenv("PROTECTED_USER_ID", "").strip()
DATA_FILE = "stealth_session.json"
AUTO_DELETE_SECONDS = 6 * 3600  # 6 Ghante (21600 seconds)

if not TOKEN or not ADMIN_ID_RAW:
    raise RuntimeError("BOT_TOKEN ya ADMIN_ID set nahi hai!")

try:
    ADMIN_ID = int(ADMIN_ID_RAW)
except ValueError:
    raise RuntimeError("ADMIN_ID ek valid integer hona chahiye!")

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")
db_lock = Lock()

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s")

# ============================================================
# FLASK SERVER (KEEP ALIVE)
# ============================================================

app = Flask(__name__)

@app.route("/")
def home():
    return "⚡ [SECURE_STEALTH_RELAY_ACTIVE]", 200

def run_web():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

# ============================================================
# DATABASE STATE & PROTECTED USER
# ============================================================

def empty_db():
    return {
        "reply_map": {},      # {admin_msg_id: user_chat_id}
        "admin_msgs": {},     # {user_id: [msg_id, ...]}
        "user_msgs": {},      # {user_id: [msg_id, ...]}
        "auto_delete": []     # [{"chat_id": int, "message_id": int, "delete_at": float}]
    }

def ensure_user(data, user_id):
    user_id = str(user_id)
    data.setdefault("admin_msgs", {}).setdefault(user_id, [])
    data.setdefault("user_msgs", {}).setdefault(user_id, [])

def ensure_protected_user(data):
    if PROTECTED_USER_ID:
        ensure_user(data, PROTECTED_USER_ID)

def get_db():
    with db_lock:
        if not os.path.exists(DATA_FILE):
            data = empty_db()
            ensure_protected_user(data)
            return data
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            for k in ["reply_map", "admin_msgs", "user_msgs"]:
                data.setdefault(k, {})
            data.setdefault("auto_delete", [])
            ensure_protected_user(data)
            return data
        except Exception:
            data = empty_db()
            ensure_protected_user(data)
            return data

def save_db(data):
    with db_lock:
        tmp = DATA_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, DATA_FILE)

SUPPORTED = ["text", "photo", "video", "document", "audio", "voice", "sticker", "animation"]

def admin_only(func):
    @wraps(func)
    def wrapper(message, *args, **kwargs):
        if message.chat.id != ADMIN_ID:
            return
        return func(message, *args, **kwargs)
    return wrapper

# ============================================================
# AUTO-DELETE BACKGROUND WORKER (6 GHANTE TIMER)
# ============================================================

def auto_delete_daemon():
    while True:
        try:
            time.sleep(15)  # Har 15 second me check karega
            now = time.time()
            db = get_db()
            queue = db.get("auto_delete", [])
            if not queue:
                continue

            remaining = []
            modified = False

            for item in queue:
                if now >= item["delete_at"]:
                    try:
                        bot.delete_message(chat_id=item["chat_id"], message_id=item["message_id"])
                    except Exception:
                        pass
                    modified = True
                else:
                    remaining.append(item)

            if modified:
                db["auto_delete"] = remaining
                save_db(db)

        except Exception as e:
            logging.error("Auto delete loop error: %s", e)

# ============================================================
# COMMANDS
# ============================================================

@bot.message_handler(commands=["start"])
def cmd_start(message):
    chat_id = message.chat.id
    data = get_db()

    if chat_id == ADMIN_ID:
        text = f"""
🖤 <b>STEALTH OPERATOR PANEL</b>
─────────────────────────────
🛡️ <b>Protected User ID:</b> <code>{PROTECTED_USER_ID or 'None'}</code>
─────────────────────────────
• Har message par <b>Reply</b> karke directly user se baat karein.
• Bheje gaye sabhi msgs <b>6 ghante baad auto-delete</b> ho jayenge.
• Saara content <code>protect_content</code> ke sath lock rahega.
• <code>/wipe &lt;user_id&gt;</code> ── User ke chat se bot + user ke ALL msgs turant delete karein.
─────────────────────────────
"""
        bot.send_message(ADMIN_ID, text)
        return

    uid = str(chat_id)
    ensure_user(data, uid)
    save_db(data)

    bot.send_message(
        chat_id,
        "🔒 <b>Secure Private Session Active.</b>\n<i>Aap yahan message bhej sakte hain.</i>",
        protect_content=True
    )

@bot.message_handler(commands=["wipe"])
@admin_only
def wipe_chat(message):
    try:
        user_id = str(message.text.split()[1])
    except IndexError:
        bot.send_message(ADMIN_ID, "⚠️ Format: <code>/wipe &lt;user_id&gt;</code>")
        return

    db = get_db()
    admin_list = db.get("admin_msgs", {}).get(user_id, [])
    user_list = db.get("user_msgs", {}).get(user_id, [])

    total_deleted = 0

    # User ke messages user side se delete
    for mid in list(user_list):
        try:
            bot.delete_message(chat_id=int(user_id), message_id=int(mid))
            total_deleted += 1
        except Exception:
            pass

    # Admin ke bheje messages user side se delete
    for mid in list(admin_list):
        try:
            bot.delete_message(chat_id=int(user_id), message_id=int(mid))
            total_deleted += 1
        except Exception:
            pass

    db["admin_msgs"][user_id] = []
    db["user_msgs"][user_id] = []
    db["auto_delete"] = [x for x in db.get("auto_delete", []) if str(x["chat_id"]) != user_id]
    save_db(db)

    bot.send_message(ADMIN_ID, f"🧹 <b>100% Wiped:</b> User <code>{user_id}</code> ki screen se <b>{total_deleted}</b> msgs clear kar diye gaye.")

# ============================================================
# BIDIRECTIONAL ROUTING
# ============================================================

@bot.message_handler(func=lambda m: True, content_types=SUPPORTED)
def handle_all_messages(message):
    db = get_db()

    # --- 1. ADMIN TO USER (STEALTH + PROTECT_CONTENT + 6 HR AUTO-DELETE) ---
    if message.chat.id == ADMIN_ID:
        if not message.reply_to_message:
            bot.send_message(ADMIN_ID, "⚠️ User ko bhejne ke liye uske message par <b>Reply</b> karein.")
            return

        replied_mid = str(message.reply_to_message.message_id)
        target_user = db.get("reply_map", {}).get(replied_mid)

        if not target_user:
            bot.send_message(ADMIN_ID, "❌ User connection nahi mila. User se dubara message karne ko kahein.")
            return

        try:
            # User side copy bhejna (Admin ki identity 100% hide)
            sent = bot.copy_message(
                chat_id=int(target_user),
                from_chat_id=ADMIN_ID,
                message_id=message.message_id,
                protect_content=True
            )

            # Record msg id for instant /wipe
            ensure_user(db, target_user)
            db["admin_msgs"][target_user].append(sent.message_id)

            # 6 Ghante ke liye Auto-Delete schedule
            delete_time = time.time() + AUTO_DELETE_SECONDS
            db.setdefault("auto_delete", []).append({
                "chat_id": int(target_user),
                "message_id": sent.message_id,
                "delete_at": delete_time
            })
            save_db(db)

        except Exception as e:
            logging.error("Admin send error: %s", e)
            bot.send_message(ADMIN_ID, "❌ Delivery failed: User ne bot stop ya block kiya ho sakta hai.")
        return

    # --- 2. USER TO ADMIN (SHOW IDENTITY + SAVE ID FOR WIPE) ---
    user_id = str(message.chat.id)
    sender = message.from_user
    full_name = f"{sender.first_name or ''} {sender.last_name or ''}".strip()
    username = f"@{sender.username}" if sender.username else "No Username"

    ensure_user(db, user_id)
    db["user_msgs"][user_id].append(message.message_id)

    try:
        # Admin ke liye content copy
        inbound = bot.copy_message(
            chat_id=ADMIN_ID,
            from_chat_id=message.chat.id,
            message_id=message.message_id,
            protect_content=True
        )

        # Reply chain set karein
        db.setdefault("reply_map", {})[str(inbound.message_id)] = user_id
        save_db(db)

        # Header card taaki pata chale kaunsa dost baat kar raha hai
        flag = " 🛡️ [PROTECTED]" if user_id == PROTECTED_USER_ID else ""
        header = (
            f"👤 <b>{full_name}</b> | {username}{flag}\n"
            f"🆔 <code>{user_id}</code>"
        )
        bot.send_message(
            ADMIN_ID,
            header,
            reply_to_message_id=inbound.message_id
        )

    except Exception as e:
        logging.error("Inbound error: %s", e)

# ============================================================
# BOOTSTRAP
# ============================================================

def main():
    db = get_db()
    ensure_protected_user(db)
    save_db(db)

    threading.Thread(target=run_web, daemon=True).start()
    threading.Thread(target=auto_delete_daemon, daemon=True).start()
    logging.info("Auto-delete daemon and Gateway started...")

    try:
        bot.delete_webhook(drop_pending_updates=True)
    except Exception:
        pass
    time.sleep(1)
    bot.infinity_polling(skip_pending=True)

if __name__ == "__main__":
    main()
