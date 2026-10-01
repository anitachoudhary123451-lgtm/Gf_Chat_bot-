import os
import logging
import threading
from threading import Lock
import time
import random

from flask import Flask
import telebot
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
BOTANY_FACTS = ["क्या आप जानते हैं? गिलोय (Giloy) और अश्वगंधा (Ashwagandha) औषधीय पौधे हैं, जो रोग प्रतिरोधक क्षमता बढ़ाते हैं। 🌿", "नीम (Neem) और ग्वारपाठा (Aloe Vera) साक्षात् प्रकृति का वरदान हैं। 🌱", "तुलसी (Tulsi) एक संपूर्ण औषधालय है। इसके पत्ते हवा को भी शुद्ध करते हैं। 🍃", "सहजन (Drumstick) के पत्ते पोषण का खजाना होते हैं। 🌳"]
ZOOLOGY_FACTS = ["पक्षियों की दुनिया अद्भुत है! कड़कनाथ जैसी स्थानीय प्रजातियां अपनी रोग प्रतिरोधक क्षमता के लिए जानी जाती हैं। 🐓", "सफेद लेगहॉर्न और असील जैसी नस्लें जैव विविधता का बेहतरीन उदाहरण हैं। 🐣", "एक छोटी सी मधुमक्खी भी दुनिया से खत्म हो जाए, तो इंसानों का जीवन खतरे में पड़ जाएगा! 🐝"]
GENERAL_FACTS = ["प्रकृति संरक्षण केवल पेड़ लगाना नहीं है, बल्कि वनस्पति और जीव का सम्मान करना है। 🌍", "जल, जंगल और ज़मीन - ये तीन तत्व ही हमारे भविष्य की नींव हैं। 💧", "प्लास्टिक को नष्ट होने में 500 से ज्यादा साल लगते हैं। ♻️"]
CLOSINGS = ["\n\n💬 <i>आप अपना संदेश या सवाल यहाँ छोड़ सकते हैं, टीम के आते ही आपको रिप्लाई मिल जाएगा।</i>", "\n\n💬 <i>हमारी टीम जल्द ही आपके संदेश का उत्तर देगी। प्रकृति से जुड़े रहें!</i>"]

def get_smart_reply(user_text):
    text = str(user_text).lower()
    response = random.choice(PREFIXES)
    if any(word in text for word in ['paudhe', 'plant', 'botany', 'tree', 'ped', 'bimari', 'medicine']): response += random.choice(BOTANY_FACTS)
    elif any(word in text for word in ['janwar', 'animal', 'bird', 'zoology', 'murga', 'poultry', 'जीव', 'पक्षी']): response += random.choice(ZOOLOGY_FACTS)
    else: response += random.choice(BOTANY_FACTS + ZOOLOGY_FACTS + GENERAL_FACTS)
    response += random.choice(CLOSINGS)
    return response

# ============================================================
# DATABASE CORE & HELPERS
# ============================================================
app = Flask(__name__)
@app.route("/")
def home(): return "⚡ Unique Nature Gateway Active ✅", 200
def run_flask(): app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

def empty_db():
    return {"_id": "master_state", "users": {}, "reply_map": {}, "msg_map_a2u": {}, "msg_map_u2a": {}, "blocked": [], "alerts": [], "selected_user": None, "auto_delete": []}

def ensure_user(data, user_id):
    user_id = str(user_id)
    if user_id not in data["users"]:
        data["users"][user_id] = {"admin_msgs": [], "user_msgs": [], "auto_delete_enabled": True, "ai_mode": False}

def get_user_status(data, user_id):
    user_id = str(user_id)
    if user_id == str(PROTECTED_USER_ID): return "🛡️ Protected"
    if user_id in data.get("blocked", []): return "⛔ Banned"
    if user_id in data.get("alerts", []): return "🚨 Flagged"
    return "🟢 Active"

def load_data():
    with db_lock:
        try:
            data = state_collection.find_one({"_id": "master_state"})
            if not data:
                data = empty_db()
                state_collection.insert_one(data)
                return data
            for key in ["users", "reply_map", "msg_map_a2u", "msg_map_u2a", "blocked", "alerts", "auto_delete"]:
                data.setdefault(key, {} if key in ["users", "reply_map", "msg_map_a2u", "msg_map_u2a"] else [])
            data.setdefault("selected_user", None)
            return data
        except: return empty_db()

def save_data(data):
    with db_lock:
        try: state_collection.replace_one({"_id": "master_state"}, data, upsert=True)
        except: pass

SUPPORTED_TYPES = ["text", "photo", "video", "document", "audio", "voice", "sticker", "animation"]

def auto_delete_worker():
    while True:
        try:
            time.sleep(15)
            now = time.time()
            data = load_data()
            queue = data.get("auto_delete", [])
            if not queue: continue
            remaining, modified = [], False
            for item in queue:
                if now >= item.get("delete_at", 0):
                    try: bot.delete_message(chat_id=item["chat_id"], message_id=item["message_id"])
                    except: pass
                    modified = True
                else: remaining.append(item)
            if modified:
                data["auto_delete"] = remaining
                save_data(data)
        except: pass

# ============================================================
# SYNC WORKERS (EDIT & REACTION)
# ============================================================
@bot.edited_message_handler(func=lambda message: True)
def handle_edit(message):
    chat_id, msg_id = message.chat.id, str(message.message_id)
    data = load_data()
    if chat_id == ADMIN_ID:
        target_user = data["reply_map"].get(msg_id)
        user_msg_id = data["msg_map_a2u"].get(msg_id)
        if target_user and user_msg_id:
            try: bot.edit_message_text(message.text, int(target_user), int(user_msg_id))
            except: pass
    else:
        admin_msg_id = data["msg_map_u2a"].get(f"{chat_id}_{msg_id}")
        if admin_msg_id:
            try: bot.edit_message_text(f"✏️ <i>[Edited by User]</i>\n{message.text}", ADMIN_ID, int(admin_msg_id))
            except: pass

@bot.message_reaction_handler(func=lambda message: True)
def handle_reaction(message):
    chat_id, msg_id = message.chat.id, str(message.message_id)
    new_reactions = message.new_reaction
    data = load_data()
    if chat_id == ADMIN_ID:
        target_user = data["reply_map"].get(msg_id)
        user_msg_id = data["msg_map_a2u"].get(msg_id)
        if target_user and user_msg_id:
            try: bot.set_message_reaction(int(target_user), int(user_msg_id), new_reactions)
            except: pass
    else:
        admin_msg_id = data["msg_map_u2a"].get(f"{chat_id}_{msg_id}")
        if admin_msg_id:
            try: bot.set_message_reaction(ADMIN_ID, int(admin_msg_id), new_reactions)
            except: pass

# ============================================================
# ALL ADMIN COMMANDS (GOD LEVEL CONSOLE)
# ============================================================
@bot.message_handler(commands=["start"])
def handle_start(message):
    chat_id, data = message.chat.id, load_data()
    if chat_id == ADMIN_ID:
        selected = f"<code>{data['selected_user']}</code>" if data.get("selected_user") else "⭕ <i>None (Reply Mode)</i>"
        panel = f"""
🌿 <b>UNIQUE NATURE | MASTER CONSOLE</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎯 <b>Focused Target:</b> {selected}
🛡️ <b>Protected ID:</b> <code>{PROTECTED_USER_ID or 'None'}</code>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🤖 <b>AI MODE:</b> <code>/ai on|off &lt;id&gt;</code>
📡 <b>ROUTING:</b> <code>/select &lt;id&gt;</code> | <code>/unselect</code> | <code>/dm &lt;id&gt; &lt;text&gt;</code>
🧹 <b>PURGE:</b> 
 • <code>/wipe &lt;id&gt;</code> (100% Delete User+Admin msg)
 • <code>/clearall &lt;id&gt;</code> (Delete ONLY Admin msg)
 • <code>/purge &lt;id&gt;</code> (Wipe + Clear Mapping)
 • <code>/resetdb</code> (Format Database)
⚙️ <b>SETTINGS:</b> <code>/autodelete on|off &lt;id&gt;</code>
👥 <b>USER MGMT:</b> 
 • <code>/users</code> (List All)
 • <code>/userprofile &lt;id&gt;</code> (Check Details)
 • <code>/ban &lt;id&gt;</code> | <code>/unban &lt;id&gt;</code> 
 • <code>/alert &lt;id&gt;</code> (Flag User)
"""
        bot.send_message(ADMIN_ID, panel)
        return

    user_id = str(chat_id)
    if user_id in data.get("blocked", []): return
    ensure_user(data, user_id)
    save_data(data)
    welcome_text = "🌿 <b>Unique Nature में आपका हार्दिक स्वागत है!</b> 🌿\n<blockquote>प्रकृति की इस शांत और खूबसूरत दुनिया में आपका अभिनंदन।</blockquote>\n💬 <i>अपना संदेश नीचे लिखें, हमारी टीम जल्द ही आपसे जुड़ेगी।</i>"
    bot.send_message(chat_id, welcome_text, protect_content=True)

@bot.message_handler(commands=["ai", "select", "dm", "autodelete", "ban", "unban", "alert", "userprofile"])
def handle_various_commands(message):
    if message.chat.id != ADMIN_ID: return
    parts = message.text.split()
    cmd = parts[0].lower()
    data = load_data()

    if cmd == "/ai":
        if len(parts) < 3: return bot.send_message(ADMIN_ID, "⚠️ /ai on|off <id>")
        uid, action = str(parts[2]), parts[1].lower()
        ensure_user(data, uid)
        data["users"][uid]["ai_mode"] = (action == "on")
        bot.send_message(ADMIN_ID, f"{'🌿 AI ON' if action=='on' else '🛑 AI OFF'} for <code>{uid}</code>")
        
    elif cmd == "/select":
        if len(parts) < 2: return bot.send_message(ADMIN_ID, "⚠️ /select <id>")
        data["selected_user"] = str(parts[1])
        bot.send_message(ADMIN_ID, f"🎯 Locked focus to: <code>{parts[1]}</code>")
        
    elif cmd == "/dm":
        parts = message.text.split(" ", 2)
        if len(parts) < 3: return bot.send_message(ADMIN_ID, "⚠️ /dm <id> <text>")
        uid, text = str(parts[1]), parts[2]
        try:
            sent = bot.send_message(int(uid), text, protect_content=True)
            ensure_user(data, uid)
            data["users"][uid]["admin_msgs"].append(sent.message_id)
            if data["users"][uid].get("auto_delete_enabled", True):
                data.setdefault("auto_delete", []).append({"chat_id": int(uid), "message_id": sent.message_id, "delete_at": time.time() + AUTO_DELETE_SECONDS})
            bot.send_message(ADMIN_ID, f"✅ DM sent to <code>{uid}</code>")
        except: bot.send_message(ADMIN_ID, "❌ Failed to send DM.")
        
    elif cmd == "/autodelete":
        if len(parts) < 3: return bot.send_message(ADMIN_ID, "⚠️ /autodelete on|off <id>")
        uid, action = str(parts[2]), parts[1].lower()
        ensure_user(data, uid)
        if action == "off":
            data["users"][uid]["auto_delete_enabled"] = False
            data["auto_delete"] = [x for x in data.get("auto_delete", []) if str(x["chat_id"]) != uid]
            bot.send_message(ADMIN_ID, f"🛑 Auto-Delete OFF & Queue Cleared for <code>{uid}</code>")
        else:
            data["users"][uid]["auto_delete_enabled"] = True
            bot.send_message(ADMIN_ID, f"✅ Auto-Delete ON for <code>{uid}</code>")

    elif cmd == "/ban":
        if len(parts) < 2: return bot.send_message(ADMIN_ID, "⚠️ /ban <id>")
        uid = str(parts[1])
        if uid not in data.get("blocked", []): data.setdefault("blocked", []).append(uid)
        bot.send_message(ADMIN_ID, f"⛔ User <code>{uid}</code> BANNED.")

    elif cmd == "/unban":
        if len(parts) < 2: return bot.send_message(ADMIN_ID, "⚠️ /unban <id>")
        uid = str(parts[1])
        if uid in data.get("blocked", []): data["blocked"].remove(uid)
        bot.send_message(ADMIN_ID, f"✅ User <code>{uid}</code> UNBANNED.")

    elif cmd == "/alert":
        if len(parts) < 2: return bot.send_message(ADMIN_ID, "⚠️ /alert <id>")
        uid = str(parts[1])
        if uid in data.get("alerts", []):
            data["alerts"].remove(uid)
            bot.send_message(ADMIN_ID, f"✅ Flag REMOVED for <code>{uid}</code>.")
        else:
            data.setdefault("alerts", []).append(uid)
            bot.send_message(ADMIN_ID, f"🚨 User <code>{uid}</code> FLAGGED.")

    elif cmd == "/userprofile":
        if len(parts) < 2: return bot.send_message(ADMIN_ID, "⚠️ /userprofile <id>")
        uid = str(parts[1])
        ensure_user(data, uid)
        u = data["users"][uid]
        status = get_user_status(data, uid)
        profile = f"""👤 <b>Profile:</b> <a href="tg://user?id={uid}">{uid}</a>
━━━━━━━━━━━━━━━━━
📊 <b>Status:</b> {status}
🤖 <b>AI Mode:</b> {'ON' if u.get('ai_mode') else 'OFF'}
⏳ <b>Auto-Delete:</b> {'ON' if u.get('auto_delete_enabled') else 'OFF'}
📩 <b>User Msgs:</b> {len(u.get('user_msgs', []))}
📤 <b>Admin Msgs:</b> {len(u.get('admin_msgs', []))}"""
        bot.send_message(ADMIN_ID, profile)
        
    save_data(data)

@bot.message_handler(commands=["unselect"])
def handle_unselect(message):
    if message.chat.id != ADMIN_ID: return
    data = load_data()
    data["selected_user"] = None
    save_data(data)
    bot.send_message(ADMIN_ID, "⭕ Focus released.")

@bot.message_handler(commands=["users"])
def handle_users(message):
    if message.chat.id != ADMIN_ID: return
    data = load_data()
    users = data.get("users", {})
    msg = "👥 <b>Registered Users:</b>\n\n"
    for uid in users.keys():
        status = get_user_status(data, uid)
        msg += f"• <code>{uid}</code> - {status}\n"
    bot.send_message(ADMIN_ID, msg if users else "No users found.")

@bot.message_handler(commands=["wipe", "clearall", "purge"])
def handle_deletions(message):
    if message.chat.id != ADMIN_ID: return
    parts = message.text.split()
    cmd = parts[0].lower()
    if len(parts) < 2: return bot.send_message(ADMIN_ID, f"⚠️️ Format: {cmd} <id>")
    
    uid = str(parts[1])
    data = load_data()
    if uid not in data["users"]: return bot.send_message(ADMIN_ID, "User not found.")
    
    u_data = data["users"][uid]
    total = 0
    
    if cmd == "/wipe" or cmd == "/purge":
        # Delete BOTH
        for mid in u_data.get("user_msgs", []) + u_data.get("admin_msgs", []):
            try: bot.delete_message(int(uid), int(mid)); total += 1
            except: pass
        data["users"][uid]["user_msgs"] = []
        data["users"][uid]["admin_msgs"] = []
    
    elif cmd == "/clearall":
        # Delete ONLY Admin msgs
        for mid in u_data.get("admin_msgs", []):
            try: bot.delete_message(int(uid), int(mid)); total += 1
            except: pass
        data["users"][uid]["admin_msgs"] = []

    if cmd == "/purge":
        # Clear Mappings
        for k, v in list(data["reply_map"].items()):
            if str(v) == uid: del data["reply_map"][k]
        for k in list(data["msg_map_a2u"].keys()):
            if data["reply_map"].get(k) == uid: del data["msg_map_a2u"][k]
        prefix = f"{uid}_"
        for k in list(data["msg_map_u2a"].keys()):
            if k.startswith(prefix): del data["msg_map_u2a"][k]

    save_data(data)
    bot.send_message(ADMIN_ID, f"💥 <b>{cmd.upper()} completed for {uid}.</b> Deleted {total} messages.")

@bot.message_handler(commands=["resetdb"])
def handle_resetdb(message):
    if message.chat.id != ADMIN_ID: return
    with db_lock:
        state_collection.replace_one({"_id": "master_state"}, empty_db(), upsert=True)
    bot.send_message(ADMIN_ID, "☢️ <b>DATABASE RESET SUCCESSFUL.</b> All history, mappings, and users wiped.")

@bot.my_chat_member_handler()
def handle_my_chat_member(message):
    if message.new_chat_member.status == "kicked":
        try: bot.send_message(ADMIN_ID, f"⚠️ <b>ALERT:</b> User <code>{message.chat.id}</code> ne bot ko BLOCK kar diya!")
        except: pass
    elif message.new_chat_member.status == "member":
        try: bot.send_message(ADMIN_ID, f"✅ <b>INFO:</b> User <code>{message.chat.id}</code> ne bot UNBLOCK kar diya!")
        except: pass

# ============================================================
# CORE ROUTING (AUTO-SPOILERS & PROTECTED)
# ============================================================
@bot.message_handler(func=lambda message: True, content_types=SUPPORTED_TYPES)
def handle_all_messages(message):
    chat_id, message_id, text = message.chat.id, message.message_id, message.text or ""
    data = load_data()

    # ADMIN -> USER
    if chat_id == ADMIN_ID:
        if text.startswith("/"): return bot.send_message(ADMIN_ID, "⚠️ Invalid Command.")
        target_user = None
        target_quote_id = None
        if message.reply_to_message:
            r_id = str(message.reply_to_message.message_id)
            target_user = data["reply_map"].get(r_id)
            if target_user: target_quote_id = data["msg_map_a2u"].get(r_id)
        elif data.get("selected_user"): target_user = str(data["selected_user"])

        if not target_user: return

        try:
            quote_arg = {"reply_to_message_id": int(target_quote_id)} if target_quote_id else {}
            
            # AUTO-SPOILER & PROTECTION
            if message.content_type == "photo": 
                sent = bot.send_photo(target_user, message.photo[-1].file_id, caption=message.caption or "", protect_content=True, has_spoiler=True, **quote_arg)
            elif message.content_type == "video":
                sent = bot.send_video(target_user, message.video.file_id, caption=message.caption or "", protect_content=True, has_spoiler=True, **quote_arg)
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
                bot.send_message(ADMIN_ID, f"ℹ️ Auto-Reply disabled for <code>{target_user}</code> (Manual Override).")
            save_data(data)
        except: pass
        return

    # USER -> ADMIN
    user_id = str(chat_id)
    if user_id in data.get("blocked", []): return
    ensure_user(data, user_id)
    
    # Flagged Alert check
    if user_id in data.get("alerts", []):
        try: bot.send_message(ADMIN_ID, f"🚨 <b>ALERT: Flagged User <code>{user_id}</code> Active!</b>")
        except: pass

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
    try: bot.delete_webhook(drop_pending_updates=True); bot.remove_webhook()
    except: pass
    time.sleep(2)
    bot.infinity_polling(skip_pending=True, allowed_updates=["message", "edited_message", "message_reaction", "my_chat_member"])

if __name__ == "__main__":
    start_services()
