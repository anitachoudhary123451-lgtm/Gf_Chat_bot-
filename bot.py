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
# LOCAL NATURE BRAIN (NO API REQUIRED - INSTANT & DYNAMIC)
# ============================================================

# 1. Admin Unavailable Prefixes (Har baar alag opening)
PREFIXES = [
    "🌿 <b>Unique Nature</b> की टीम अभी कुछ कार्यों में व्यस्त है, लेकिन एक प्राकृतिक साथी के रूप में मैं आपके साथ हूँ।\n\n",
    "🌸 नमस्कार! एडमिन अभी प्रकृति की छाँव में थोड़ा विश्राम कर रहे हैं। तब तक आइए कुछ ज्ञान की बातें करें।\n\n",
    "🪴 हमारी टीम अभी उपलब्ध नहीं है, लेकिन प्रकृति के इस मंच पर आपका स्वागत है।\n\n",
    "🌍 हेलो! 'Unique Nature' के मुख्य सदस्य अभी ऑफलाइन हैं। जब तक वे आते हैं, मैं आपको प्रकृति के कुछ अद्भुत रहस्य बताता हूँ:\n\n",
    "🍃 स्वागत है! एडमिन जल्द ही आपसे जुड़ेंगे। तब तक प्रकृति की शांति का आनंद लें।\n\n"
]

# 2. Botany & Flora Facts (Medicinal Plants)
BOTANY_FACTS = [
    "क्या आप जानते हैं? गिलोय (Giloy) और अश्वगंधा (Ashwagandha) हमारे स्थानीय पर्यावरण के सबसे शक्तिशाली औषधीय पौधे हैं, जो सदियों से हमारी रोग प्रतिरोधक क्षमता बढ़ाते आ रहे हैं। 🌿",
    "नीम (Neem) और ग्वारपाठा (Aloe Vera) का हमारे दैनिक जीवन में बहुत महत्व है। ये त्वचा और स्वास्थ्य दोनों के लिए साक्षात् प्रकृति का वरदान हैं। 🌱",
    "तुलसी (Tulsi) केवल एक धार्मिक पौधा नहीं, बल्कि एक संपूर्ण औषधालय है। इसके पत्ते हमारे आस-पास की हवा को भी शुद्ध करते हैं। 🍃",
    "सहजन (Drumstick/Moringa) के पत्ते पोषण का खजाना होते हैं। प्रकृति ने हमें स्वस्थ रहने के सारे साधन हमारे आस-पास ही दिए हैं, बस हमें उन्हें पहचानने की जरूरत है। 🌳",
    "आँवला (Amla) विटामिन सी का सबसे बेहतरीन प्राकृतिक स्रोत है। हमारे स्थानीय वनस्पतियों में बीमारियों से लड़ने का ऐसा जादू छिपा है जो आधुनिक दवाओं में भी नहीं मिलता! 🍏",
    "पेड़-पौधे बिना कुछ बोले ही हमें प्राणवायु (Oxygen) देते हैं। एक बड़ा पेड़ दिन भर में 4 लोगों के लिए पर्याप्त ऑक्सीजन पैदा करता है। 🌳"
]

# 3. Zoology & Fauna Facts (Wildlife, Birds, Poultry)
ZOOLOGY_FACTS = [
    "पक्षियों और जीवों की दुनिया भी अद्भुत है! कड़कनाथ (Kadaknath) जैसी स्थानीय प्रजातियां अपनी विशेष रोग प्रतिरोधक क्षमता और उच्च पोषण के लिए जानी जाती हैं। 🐓",
    "सफेद लेगहॉर्न (White Leghorn) और असील (Aseel) जैसी नस्लें जैव विविधता का बेहतरीन उदाहरण हैं, जो न केवल पर्यावरण का हिस्सा हैं बल्कि ग्रामीण अर्थव्यवस्था को भी ताकत देती हैं। 🐣",
    "हमारे आस-पास के जीव-जंतु (Fauna) पर्यावरण का संतुलन बनाए रखने में बहुत बड़ी भूमिका निभाते हैं। एक छोटी सी मधुमक्खी भी अगर दुनिया से खत्म हो जाए, तो इंसानों का जीवन खतरे में पड़ जाएगा! 🐝",
    "प्रकृति ने हर जीव को एक विशेष कार्य दिया है। जंगल के छोटे कीड़ों से लेकर बड़े जानवरों तक, सभी एक 'फूड चेन' का महत्वपूर्ण हिस्सा हैं। 🐾"
]

# 4. General Environment & Conservation Facts
GENERAL_FACTS = [
    "आधुनिक जीवन की भागदौड़ में हम अक्सर भूल जाते हैं कि असली शांति मोबाइल स्क्रीन पर नहीं, बल्कि पेड़ों की छांव में ही मिलती है। 🌳",
    "प्रकृति संरक्षण (Nature Conservation) केवल पेड़ लगाना नहीं है, बल्कि अपने आस-पास की हर छोटी-बड़ी वनस्पति और जीव का सम्मान करना है। 🌍",
    "जल, जंगल और ज़मीन - ये तीन तत्व ही हमारे और हमारी आने वाली पीढ़ियों के भविष्य की नींव हैं। आइए इन्हें बचाएं। 💧",
    "क्या आप जानते हैं? प्लास्टिक को पूरी तरह से नष्ट होने में 500 से ज्यादा साल लगते हैं। प्रकृति को स्वच्छ रखना हमारी सबसे बड़ी जिम्मेदारी है। ♻️",
    "प्रकृति कभी जल्दबाजी नहीं करती, फिर भी उसका हर काम समय पर पूरा हो जाता है। हमें भी प्रकृति से यह धैर्य सीखना चाहिए। 🌸"
]

# 5. Closings (Har baar alag ending)
CLOSINGS = [
    "\n\n💬 <i>आप अपना संदेश या सवाल यहाँ छोड़ सकते हैं, एडमिन के आते ही आपको रिप्लाई मिल जाएगा।</i>",
    "\n\n💬 <i>हमारी टीम जल्द ही आपके संदेश का उत्तर देगी। प्रकृति से जुड़े रहें!</i>",
    "\n\n💬 <i>अगर आपका कोई विशेष सवाल है, तो टाइप कर दें। Unique Nature टीम जल्द संपर्क करेगी।</i>"
]

def get_smart_reply(user_text):
    text = user_text.lower()
    
    # 1. Random Prefix
    response = random.choice(PREFIXES)
    
    # 2. Smart Keyword Detection
    # Agar user paudho/botany ki baat kare
    if any(word in text for word in ['paudhe', 'plant', 'botany', 'tree', 'ped', 'bimari', 'medicine', 'aushadhi', 'leaf', 'patti']):
        response += random.choice(BOTANY_FACTS)
    # Agar user janwaro/zoology ki baat kare
    elif any(word in text for word in ['janwar', 'animal', 'bird', 'zoology', 'murga', 'poultry', 'जीव', 'पक्षी']):
        response += random.choice(ZOOLOGY_FACTS)
    # Agar general baat (hi, hello, etc.) ho
    else:
        # Mix sabhi facts me se koi ek random
        all_facts = BOTANY_FACTS + ZOOLOGY_FACTS + GENERAL_FACTS
        response += random.choice(all_facts)
        
    # 3. Random Closing
    response += random.choice(CLOSINGS)
    
    return response

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
        "_id": "master_state", "users": {}, "reply_map": {}, "msg_map_a2u": {}, "msg_map_u2a": {}, 
        "blocked": [], "alerts": [], "selected_user": None, "auto_delete": []
    }

def ensure_user(data, user_id):
    user_id = str(user_id)
    if user_id not in data["users"]:
        data["users"][user_id] = {"admin_msgs": [], "user_msgs": [], "auto_delete_enabled": True, "ai_mode": False}
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
🤖 <b>AUTO-REPLY (NATURE MODE):</b>
• <code>/ai on &lt;id&gt;</code> ── Turn ON Auto-Reply
• <code>/ai off &lt;id&gt;</code> ── Turn OFF Auto-Reply
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🧹 <b>PURGE & DELETION:</b>
• <code>/wipe &lt;id&gt;</code> ── 100% Instant Wipe
• <code>/purge &lt;id&gt;</code> ── Wipe all history
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
👥 <b>MANAGEMENT:</b>
• <code>/users</code> ── List all users
"""
        bot.send_message(ADMIN_ID, panel)
        return

    user_id = str(chat_id)
    if user_id in data["blocked"]:
        return

    ensure_user(data, user_id)
    save_data(data)

    welcome_text = """
🌿 <b>Unique Nature में आपका हार्दिक स्वागत है!</b> 🌿
<blockquote>
प्रकृति की इस शांत और खूबसूरत दुनिया में आपका अभिनंदन।
पेड़-पौधे, पक्षी, और शुद्ध हवा ही हमारे जीवन का असली धन हैं।
</blockquote>
💬 <i>अपना संदेश नीचे लिखें, हमारी टीम जल्द ही आपसे जुड़ेगी।</i>
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
    data = load_data()
    ensure_user(data, user_id)
    
    if action == "on":
        data["users"][user_id]["ai_mode"] = True
        bot.send_message(ADMIN_ID, f"🌿 <b>Nature Mode ENABLED</b> for <code>{user_id}</code>.\n(Ab bot inhe sundar nature facts ke sath auto-reply dega)")
    else:
        data["users"][user_id]["ai_mode"] = False
        bot.send_message(ADMIN_ID, f"🛑 <b>Nature Mode DISABLED</b> for <code>{user_id}</code>.")
    save_data(data)

@bot.my_chat_member_handler()
def handle_my_chat_member(message):
    new_status = message.new_chat_member.status
    user_id = message.chat.id
    if new_status == "kicked":
        try: bot.send_message(ADMIN_ID, f"⚠️ <b>ALERT:</b> User <code>{user_id}</code> ne bot ko BLOCK kar diya hai!")
        except Exception: pass
    elif new_status == "member":
        try: bot.send_message(ADMIN_ID, f"✅ <b>INFO:</b> User <code>{user_id}</code> ne bot ko UNBLOCK kar diya hai!")
        except Exception: pass

# ============================================================
# CORE ROUTING ENGINE & LOCAL SMART LOGIC
# ============================================================

@bot.message_handler(func=lambda message: True, content_types=SUPPORTED_TYPES)
def handle_all_messages(message):
    chat_id = message.chat.id
    message_id = message.message_id
    data = load_data()

    # ADMIN -> USER
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
            return

        try:
            quote_arg = {"reply_to_message_id": int(target_quote_id)} if target_quote_id else {}
            if message.content_type == "photo": sent = bot.send_photo(target_user, message.photo[-1].file_id, caption=message.caption or "", protect_content=True, **quote_arg)
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
        except Exception:
            pass
        return

    # USER -> ADMIN & SMART AUTO-REPLY
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
    except Exception: pass
        
    u_data = data["users"][user_id]
    if u_data.get("ai_mode", False) and message.content_type == "text":
        try:
            bot.send_chat_action(int(user_id), 'typing')
            time.sleep(1.5) # Thoda natural feel dene ke liye 1.5s ka delay
            
            # Local Smart Reply generate karna
            ai_text = get_smart_reply(message.text)
            ai_msg = bot.send_message(int(user_id), ai_text, protect_content=True)
            
            data["users"][user_id]["admin_msgs"].append(ai_msg.message_id)
            if u_data.get("auto_delete_enabled", True):
                data.setdefault("auto_delete", []).append({"chat_id": int(user_id), "message_id": ai_msg.message_id, "delete_at": time.time() + AUTO_DELETE_SECONDS})
            save_data(data)
            
            bot.send_message(ADMIN_ID, f"🤖 <b>[Auto-Replied]:</b>\n\n{ai_text}", reply_to_message_id=copied.message_id)
        except Exception:
            pass

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
