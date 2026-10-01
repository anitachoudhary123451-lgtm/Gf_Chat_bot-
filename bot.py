import os
import logging
import threading
from threading import Lock
import time
import random

from flask import Flask
import telebot
from telebot.types import InputMediaPhoto, InputMediaVideo
from pymongo import MongoClient

# ============================================================
# ENVIRONMENT & CONFIGURATION
# ============================================================

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID_RAW = os.getenv("ADMIN_ID")
PROTECTED_USER_ID = os.getenv("PROTECTED_USER_ID", "").strip()
MONGO_URI = os.getenv("MONGO_URI")

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
# LOCAL NATURE BRAIN (SMART & FAST)
# ============================================================
PREFIXES = [
    "🌿 <b>Unique Nature</b> की टीम अभी कुछ कार्यों में व्यस्त है, लेकिन एक प्राकृतिक साथी के रूप में मैं आपके साथ हूँ।\n\n",
    "🌸 नमस्कार! टीम अभी प्रकृति की छाँव में थोड़ा विश्राम कर रही है। तब तक आइए कुछ ज्ञान की बातें करें।\n\n",
    "🪴 हमारी टीम अभी उपलब्ध नहीं है, लेकिन प्रकृति के इस मंच पर आपका स्वागत है।\n\n"
]

BOTANY_FACTS = [
    "क्या आप जानते हैं? गिलोय (Giloy) और अश्वगंधा (Ashwagandha) हमारे स्थानीय पर्यावरण के सबसे शक्तिशाली औषधीय पौधे हैं, जो रोग प्रतिरोधक क्षमता बढ़ाते हैं। 🌿",
    "नीम (Neem) और ग्वारपाठा (Aloe Vera) का हमारे दैनिक जीवन में बहुत महत्व है। ये साक्षात् प्रकृति का वरदान हैं। 🌱",
    "तुलसी (Tulsi) केवल एक धार्मिक पौधा नहीं, बल्कि एक संपूर्ण औषधालय है। इसके पत्ते हमारे आस-पास की हवा को भी शुद्ध करते हैं। 🍃",
    "सहजन (Drumstick) के पत्ते पोषण का खजाना होते हैं। प्रकृति ने हमें स्वस्थ रहने के सारे साधन हमारे आस-पास ही दिए हैं। 🌳"
]

ZOOLOGY_FACTS = [
    "पक्षियों और जीवों की दुनिया भी अद्भुत है! कड़कनाथ जैसी स्थानीय प्रजातियां अपनी विशेष रोग प्रतिरोधक क्षमता के लिए जानी जाती हैं। 🐓",
    "सफेद लेगहॉर्न और असील जैसी नस्लें जैव विविधता का बेहतरीन उदाहरण हैं। 🐣",
    "एक छोटी सी मधुमक्खी भी अगर दुनिया से खत्म हो जाए, तो इंसानों का जीवन खतरे में पड़ जाएगा! 🐝"
]

GENERAL_FACTS = [
    "प्रकृति संरक्षण (Nature Conservation) केवल पेड़ लगाना नहीं है, बल्कि अपने आस-पास की हर छोटी-बड़ी वनस्पति और जीव का सम्मान करना है। 🌍",
    "जल, जंगल और ज़मीन - ये तीन तत्व ही हमारे भविष्य की नींव हैं। 💧",
    "क्या आप जानते हैं? प्लास्टिक को नष्ट होने में 500 से ज्यादा साल लगते हैं। प्रकृति को स्वच्छ रखना हमारी जिम्मेदारी है। ♻️"
]

CLOSINGS = [
    "\n\n💬 <i>आप अपना संदेश या सवाल यहाँ छोड़ सकते हैं, टीम के आते ही आपको रिप्लाई मिल जाएगा।</i>",
    "\n\n💬 <i>हमारी टीम जल्द ही आपके संदेश का उत्तर देगी। प्रकृति से जुड़े रहें!</i>"
]

def get_smart_reply(user_text):
    text = str(user_text).lower()
    response = random.choice(PREFIXES)
    
    if any(word in text for word in ['paudhe', 'plant', 'botany', 'tree', 'ped', 'bimari', 'medicine', 'leaf']):
        response += random.choice(BOTANY_FACTS)
    elif any(word in text for word in ['janwar', 'animal', 'bird', 'zoology', 'murga', 'poultry', 'जीव', 'पक्षी']):
        response += random.choice(ZOOLOGY_FACTS)
    else:
        response += random.choice(BOTANY_FACTS + ZOOLOGY_FACTS + GENERAL_FACTS)
        
    response += random.choice(CLOSINGS)
    return response

# ============================================================
# WEB SERVER & DATABASE CORE
# ============================================================
app = Flask(__name__)

@app.route("/")
def home():
    return "⚡ Unique Nature Gateway Active ✅", 200

def run_flask():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

def empty_db():
    return {"_id": "master_state", "users": {}, "reply_map": {}, "msg_map_a2u": {}, "msg_map_u2a": {}, "blocked": [], "alerts": [], "selected_user": None, "auto_delete": []}

def ensure_user(data, user_id):
    user_id = str(user_id)
    if user_id not in data["users"]:
        data["users"][user_id] = {"admin_msgs": [], "user_msgs": [], "auto_delete_enabled": True, "ai_mode": False}

def load_data():
    with db_lock:
        try:
            data = state_collection.find_one({"_id": "master_state"})
            if not data:
                data = empty_db()
                state_collection.insert_one(data)
                return data
            data.setdefault("selected_user", None)
            data.setdefault("auto_delete", [])
            return data
        except Exception:
            return empty_db()

def save_data(data):
    with db_lock:
        try:
            state_collection.replace_one({"_id": "master_state"}, data, upsert=True)
        except Exception:
            pass

SUPPORTED_TYPES = ["text", "photo", "video", "document", "audio", "voice", "sticker", "animation"]

def auto_delete_worker():
    while True:
        try:
            time.sleep(15)
            now = time.time()
            data = load_data()
            queue = data.get("auto_delete", [])
            if not queue: continue
            remaining = []
            modified = False
            for item in queue:
                if now >= item.get("delete_at", 0):
                    try: bot.delete_message(chat_id=item["chat_id"], message_id=item["message_id"])
                    except: pass
                    modified = True
                else:
                    remaining.append(item)
            if modified:
                data["auto_delete"] = remaining
                save_data(data)
        except: pass

# ============================================================
# ALL FULLY WORKING ADMIN COMMANDS
# ============================================================

@bot.message_handler(commands=["start"])
def handle_start(message):
    chat_id = message.chat.id
    data = load_data()

    if chat_id == ADMIN_ID:
        selected = f"<code>{data['selected_user']}</code>" if data.get("selected_user") else "⭕ <i>None (Reply Mode)</i>"
        panel = f"""
🌿 <b>UNIQUE NATURE | ADMIN CONSOLE</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎯 <b>Focused Target:</b> {selected}
🤖 <b>AUTO-REPLY:</b> <code>/ai on &lt;id&gt;</code> | <code>/ai off &lt;id&gt;</code>
📡 <b>ROUTING:</b> <code>/select &lt;id&gt;</code> | <code>/unselect</code> | <code>/dm &lt;id&gt; &lt;text&gt;</code>
🧹 <b>PURGE:</b> <code>/wipe &lt;id&gt;</code> (or /purge)
⚙️ <b>SETTINGS:</b> <code>/autodelete on|off &lt;id&gt;</code>
👥 <b>MANAGEMENT:</b> <code>/users</code> | <code>/userprofile &lt;id&gt;</code>
"""
        bot.send_message(ADMIN_ID, panel)
        return

    user_id = str(chat_id)
    ensure_user(data, user_id)
    save_data(data)
    welcome_text = "🌿 <b>Unique Nature में आपका हार्दिक स्वागत है!</b> 🌿\n<blockquote>प्रकृति की इस शांत और खूबसूरत दुनिया में आपका अभिनंदन।</blockquote>\n💬 <i>अपना संदेश नीचे लिखें, हमारी टीम जल्द ही आपसे जुड़ेगी।</i>"
    bot.send_message(chat_id, welcome_text, protect_content=True)

@bot.message_handler(commands=["ai"])
def toggle_ai(message):
    if message.chat.id != ADMIN_ID: return
    parts = message.text.split()
    if len(parts) < 3:
        bot.send_message(ADMIN_ID, "⚠️ <b>Format:</b> <code>/ai on|off <user_id></code>")
        return
    action, user_id = parts[1].lower(), str(parts[2])
    data = load_data()
    ensure_user(data, user_id)
    if action == "on":
        data["users"][user_id]["ai_mode"] = True
        bot.send_message(ADMIN_ID, f"🌿 <b>Nature Mode ENABLED</b> for <code>{user_id}</code>.")
    else:
        data["users"][user_id]["ai_mode"] = False
        bot.send_message(ADMIN_ID, f"🛑 <b>Nature Mode DISABLED</b> for <code>{user_id}</code>.")
    save_data(data)

@bot.message_handler(commands=["select"])
def handle_select(message):
    if message.chat.id != ADMIN_ID: return
    parts = message.text.split()
    if len(parts) < 2:
        bot.send_message(ADMIN_ID, "⚠️ Format: /select <user_id>")
        return
    data = load_data()
    data["selected_user"] = parts[1]
    save_data(data)
    bot.send_message(ADMIN_ID, f"🎯 Locked focus to: <code>{parts[1]}</code>")

@bot.message_handler(commands=["unselect"])
def handle_unselect(message):
    if message.chat.id != ADMIN_ID: return
    data = load_data()
    data["selected_user"] = None
    save_data(data)
    bot.send_message(ADMIN_ID, "⭕ Focus released. Now in standard reply mode.")

@bot.message_handler(commands=["dm"])
def handle_dm(message):
    if message.chat.id != ADMIN_ID: return
    parts = message.text.split(" ", 2)
    if len(parts) < 3:
        bot.send_message(ADMIN_ID, "⚠️ Format: /dm <user_id> <message_text>")
        return
    user_id, text = str(parts[1]), parts[2]
    try:
        sent = bot.send_message(int(user_id), text, protect_content=True)
        data = load_data()
        ensure_user(data, user_id)
        data["users"][user_id]["admin_msgs"].append(sent.message_id)
        if data["users"][user_id].get("auto_delete_enabled", True):
            data.setdefault("auto_delete", []).append({"chat_id": int(user_id), "message_id": sent.message_id, "delete_at": time.time() + AUTO_DELETE_SECONDS})
        save_data(data)
        bot.send_message(ADMIN_ID, f"✅ DM sent securely to <code>{user_id}</code>")
    except Exception as e:
        bot.send_message(ADMIN_ID, f"❌ Failed to send DM. User might have blocked the bot.")

@bot.message_handler(commands=["autodelete"])
def handle_autodelete(message):
    if message.chat.id != ADMIN_ID: return
    parts = message.text.split()
    if len(parts) < 3:
        bot.send_message(ADMIN_ID, "⚠️ Format: /autodelete on|off <user_id>")
        return
    action, user_id = parts[1].lower(), str(parts[2])
    data = load_data()
    ensure_user(data, user_id)
    if action == "on":
        data["users"][user_id]["auto_delete_enabled"] = True
        bot.send_message(ADMIN_ID, f"✅ <b>Auto-Delete ENABLED</b> (6 Hours) for <code>{user_id}</code>.")
    else:
        data["users"][user_id]["auto_delete_enabled"] = False
        bot.send_message(ADMIN_ID, f"🛑 <b>Auto-Delete DISABLED</b> for <code>{user_id}</code>.")
    save_data(data)

@bot.message_handler(commands=["users"])
def handle_users(message):
    if message.chat.id != ADMIN_ID: return
    data = load_data()
    users = data.get("users", {})
    if not users:
        bot.send_message(ADMIN_ID, "No users found.")
        return
    msg = "👥 <b>Registered Users:</b>\n\n"
    for uid in users.keys():
        msg += f"• <code>{uid}</code>\n"
    bot.send_message(ADMIN_ID, msg)

@bot.message_handler(commands=["userprofile"])
def handle_userprofile(message):
    if message.chat.id != ADMIN_ID: return
    parts = message.text.split()
    if len(parts) < 2:
        bot.send_message(ADMIN_ID, "⚠️ Format: /userprofile <user_id>")
        return
    user_id = str(parts[1])
    data = load_data()
    if user_id not in data["users"]:
        bot.send_message(ADMIN_ID, f"⚠️ User <code>{user_id}</code> not found in database.")
        return
    u = data["users"][user_id]
    profile = f"""
👤 <b>Profile:</b> <code>{user_id}</code>
━━━━━━━━━━━━━━━━━
🤖 <b>AI Mode:</b> {'ON ✅' if u.get('ai_mode') else 'OFF ❌'}
⏳ <b>Auto-Delete:</b> {'ON (6h) ✅' if u.get('auto_delete_enabled') else 'OFF ❌'}
📩 <b>User Msgs:</b> {len(u.get('user_msgs', []))}
📤 <b>Admin Msgs:</b> {len(u.get('admin_msgs', []))}
"""
    bot.send_message(ADMIN_ID, profile)

@bot.message_handler(commands=["purge", "wipe"])
def purge_chat(message):
    if message.chat.id != ADMIN_ID: return
    parts = message.text.split()
    if len(parts) < 2:
        bot.send_message(ADMIN_ID, "⚠️ Format: /purge <user_id>")
        return
    user_id = str(parts[1])
    data = load_data()
    if user_id not in data["users"]:
        bot.send_message(ADMIN_ID, "User not found.")
        return
    
    u_data = data["users"][user_id]
    total = 0
    for mid in u_data.get("user_msgs", []) + u_data.get("admin_msgs", []):
        try:
            bot.delete_message(chat_id=int(user_id), message_id=int(mid))
            total += 1
        except: pass
        
    data["users"][user_id]["user_msgs"] = []
    data["users"][user_id]["admin_msgs"] = []
    save_data(data)
    bot.send_message(ADMIN_ID, f"💥 <b>Purge completed for {user_id}.</b> Deleted {total} messages.")

# ============================================================
# BLOCK / UNBLOCK TRACKER
# ============================================================
@bot.my_chat_member_handler()
def handle_my_chat_member(message):
    new_status = message.new_chat_member.status
    user_id = message.chat.id
    if new_status == "kicked":
        try: bot.send_message(ADMIN_ID, f"⚠️ <b>ALERT:</b> User <code>{user_id}</code> ne bot ko BLOCK kar diya hai!")
        except: pass
    elif new_status == "member":
        try: bot.send_message(ADMIN_ID, f"✅ <b>INFO:</b> User <code>{user_id}</code> ne bot ko UNBLOCK kar diya hai!")
        except: pass

# ============================================================
# CORE ROUTING ENGINE (100% SECURE & HIDDEN)
# ============================================================
@bot.message_handler(func=lambda message: True, content_types=SUPPORTED_TYPES)
def handle_all_messages(message):
    chat_id = message.chat.id
    message_id = message.message_id
    text = message.text or ""
    data = load_data()

    # ========================================
    # ADMIN -> USER (ADMIN IS COMPLETELY HIDDEN)
    # ========================================
    if chat_id == ADMIN_ID:
        if text.startswith("/"):
            bot.send_message(ADMIN_ID, "⚠️ Invalid Command. Please check spelling.")
            return

        target_user = None
        target_quote_id = None
        if message.reply_to_message:
            replied_admin_id = str(message.reply_to_message.message_id)
            target_user = data["reply_map"].get(replied_admin_id)
            if target_user: target_quote_id = data["msg_map_a2u"].get(replied_admin_id)
        elif data.get("selected_user"):
            target_user = str(data["selected_user"])

        if not target_user: return

        try:
            quote_arg = {"reply_to_message_id": int(target_quote_id)} if target_quote_id else {}
            
            if message.content_type == "photo": 
                sent = bot.send_photo(target_user, message.photo[-1].file_id, caption=message.caption or "", protect_content=True, **quote_arg)
            elif message.content_type == "video":
                sent = bot.send_video(target_user, message.video.file_id, caption=message.caption or "", protect_content=True, **quote_arg)
            else:
                args = {"chat_id": int(target_user), "from_chat_id": ADMIN_ID, "message_id": message_id, "protect_content": True}
                if target_quote_id: args["reply_to_message_id"] = int(target_quote_id)
                sent = bot.copy_message(**args)

            ensure_user(data, target_user)
            data["users"][target_user]["admin_msgs"].append(sent.message_id)
            
            if data["users"][target_user].get("auto_delete_enabled", True):
                data.setdefault("auto_delete", []).append({"chat_id": int(target_user), "message_id": sent.message_id, "delete_at": time.time() + AUTO_DELETE_SECONDS})

            data["reply_map"][str(message_id)] = target_user
            data["msg_map_a2u"][str(message_id)] = sent.message_id
            data["msg_map_u2a"][f"{target_user}_{sent.message_id}"] = message_id
            
            if data["users"][target_user].get("ai_mode", False):
                data["users"][target_user]["ai_mode"] = False
                bot.send_message(ADMIN_ID, f"ℹ️ Auto-Reply Mode for <code>{target_user}</code> disabled kyunki tumne khud reply kiya.")
            save_data(data)
        except Exception: pass
        return

    # ========================================
    # USER -> ADMIN & SMART AUTO-REPLY
    # ========================================
    user_id = str(chat_id)
    if user_id in data["blocked"]: return
    ensure_user(data, user_id)
    data["users"][user_id]["user_msgs"].append(message_id)

    try:
        copied = bot.forward_message(chat_id=ADMIN_ID, from_chat_id=chat_id, message_id=message_id)
        data["reply_map"][str(copied.message_id)] = user_id
        data["msg_map_a2u"][str(copied.message_id)] = message_id
        data["msg_map_u2a"][f"{user_id}_{message_id}"] = copied.message_id
        save_data(data)
    except: pass
        
    u_data = data["users"][user_id]
    if u_data.get("ai_mode", False) and message.content_type == "text":
        try:
            bot.send_chat_action(int(user_id), 'typing')
            time.sleep(1.5)
            
            ai_text = get_smart_reply(text)
            
            ai_msg = bot.send_message(int(user_id), ai_text, protect_content=True)
            
            data["users"][user_id]["admin_msgs"].append(ai_msg.message_id)
            if u_data.get("auto_delete_enabled", True):
                data.setdefault("auto_delete", []).append({"chat_id": int(user_id), "message_id": ai_msg.message_id, "delete_at": time.time() + AUTO_DELETE_SECONDS})
            save_data(data)
            
            bot.send_message(ADMIN_ID, f"🤖 <b>[Auto-Replied]:</b>\n\n{ai_text}", reply_to_message_id=copied.message_id)
        except: pass

def start_services():
    data = load_data()
    save_data(data)
    threading.Thread(target=run_flask, daemon=True).start()
    threading.Thread(target=auto_delete_worker, daemon=True).start()
    try:
        bot.delete_webhook(drop_pending_updates=True)
        bot.remove_webhook()
    except: pass
    time.sleep(3)
    bot.infinity_polling(skip_pending=True, allowed_updates=["message", "edited_message", "message_reaction", "my_chat_member"])

if __name__ == "__main__":
    start_services()
