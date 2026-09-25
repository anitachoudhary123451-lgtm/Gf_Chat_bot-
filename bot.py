import os
import json
import logging
import threading
from threading import Lock
import time

from PIL import Image

try:
    from moviepy.editor import ImageClip
except (ImportError, ModuleNotFoundError):
    try:
        from moviepy import ImageClip
    except (ImportError, ModuleNotFoundError):
        from moviepy.video.VideoClip import ImageClip

from flask import Flask
import telebot
from telebot.types import InputMediaPhoto, InputMediaVideo

# ============================================================
# ENVIRONMENT & CONFIGURATION
# ============================================================

TOKEN = os.getenv("BOT_TOKEN")[span_1](start_span)[span_1](end_span)
ADMIN_ID_RAW = os.getenv("ADMIN_ID")[span_2](start_span)[span_2](end_span)
PROTECTED_USER_ID = os.getenv("PROTECTED_USER_ID", "").strip()[span_3](start_span)[span_3](end_span)

DATA_FILE = "bot_data.json[span_4](start_span)"[span_4](end_span)
CUSTOM_COVER_FILE = "fake_cover.jpg"
AUTO_DELETE_SECONDS = 6 * 3600
REBLUR_INTERVAL_SECONDS = 5

if not TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is not set!")[span_5](start_span)[span_5](end_span)

if not ADMIN_ID_RAW:
    raise RuntimeError("ADMIN_ID environment variable is not set!")[span_6](start_span)[span_6](end_span)

try:
    ADMIN_ID = int(ADMIN_ID_RAW)[span_7](start_span)[span_7](end_span)
except ValueError:
    raise RuntimeError("ADMIN_ID must be a valid integer!")[span_8](start_span)[span_8](end_span)

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")[span_9](start_span)[span_9](end_span)
db_lock = Lock()[span_10](start_span)[span_10](end_span)

active_spoilers = {}
active_spoilers_lock = Lock()

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")[span_11](start_span)[span_11](end_span)

# ============================================================
# WEB SERVER / KEEP ALIVE
# ============================================================

app = Flask(__name__)[span_12](start_span)[span_12](end_span)

@app.route("/")
def home():
    return "⚡ Gateway Service Active ✅", 200[span_13](start_span)[span_13](end_span)

def run_flask():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))[span_14](start_span)[span_14](end_span)

# ============================================================
# DATABASE CORE (INDENTATION STRICTLY 4-SPACES)
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
    }[span_15](start_span)[span_15](end_span)

def ensure_user(data, user_id):
    user_id = str(user_id)[span_16](start_span)[span_16](end_span)
    if user_id not in data["users"]:[span_17](start_span)[span_17](end_span)
        data["users"][user_id] = {
            "admin_msgs": [],
            "user_msgs": []
        }

def ensure_protected_user(data):
    if PROTECTED_USER_ID:[span_18](start_span)[span_18](end_span)
        ensure_user(data, PROTECTED_USER_ID)[span_19](start_span)[span_19](end_span)

def load_data():
    with db_lock:[span_20](start_span)[span_20](end_span)
        if not os.path.exists(DATA_FILE):[span_21](start_span)[span_21](end_span)
            data = empty_db()[span_22](start_span)[span_22](end_span)
            ensure_protected_user(data)[span_23](start_span)[span_23](end_span)
            return data[span_24](start_span)[span_24](end_span)
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:[span_25](start_span)[span_25](end_span)
                data = json.load(f)[span_26](start_span)[span_26](end_span)
            for key in ["users", "reply_map", "msg_map_a2u", "msg_map_u2a", "blocked", "alerts"]:[span_27](start_span)[span_27](end_span)
                if key not in data:[span_28](start_span)[span_28](end_span)
                    data[key] = {} if key in ["users", "reply_map", "msg_map_a2u", "msg_map_u2a"] else [][span_29](start_span)[span_29](end_span)
            data.setdefault("selected_user", None)[span_30](start_span)[span_30](end_span)
            data.setdefault("auto_delete", [])
            ensure_protected_user(data)[span_31](start_span)[span_31](end_span)
            return data[span_32](start_span)[span_32](end_span)
        except Exception as e:
            logging.error("DB Load Error: %s", e)[span_33](start_span)[span_33](end_span)
            data = empty_db()[span_34](start_span)[span_34](end_span)
            ensure_protected_user(data)[span_35](start_span)[span_35](end_span)
            return data[span_36](start_span)[span_36](end_span)

def save_data(data):
    with db_lock:[span_37](start_span)[span_37](end_span)
        temp_file = DATA_FILE + ".tmp[span_38](start_span)"[span_38](end_span)
        try:
            with open(temp_file, "w", encoding="utf-8") as f:[span_39](start_span)[span_39](end_span)
                json.dump(data, f, ensure_ascii=False, indent=2)[span_40](start_span)[span_40](end_span)
            os.replace(temp_file, DATA_FILE)[span_41](start_span)[span_41](end_span)
        except Exception as e:
            logging.error("DB Save Error: %s", e)[span_42](start_span)[span_42](end_span)

SUPPORTED_TYPES = ["text", "photo", "video", "document", "audio", "voice", "sticker", "animation"][span_43](start_span)[span_43](end_span)

# ============================================================
# FAKE THUMBNAIL & VIDEO CONVERTER (CLEAN NO-CAPTION)
# ============================================================

def prepare_thumbnail(input_path, output_path):
    with Image.open(input_path) as img:
        img = img.convert("RGB")
        img.thumbnail((320, 320))
        img.save(output_path, "JPEG", quality=95)

def process_secret_video(photo_file_id, target_user, data, admin_msg_id, quote_id=None):
    real_photo_path = f"temp_real_{admin_msg_id}.jpg"
    temp_video_path = f"temp_video_{admin_msg_id}.mp4"
    ready_thumb_path = f"temp_thumb_{admin_msg_id}.jpg"

    try:
        file_info = bot.get_file(photo_file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        with open(real_photo_path, "wb") as f:
            f.write(downloaded_file)

        with Image.open(real_photo_path) as im:
            width, height = im.size

        if width % 2 != 0:
            width -= 1
        if height % 2 != 0:
            height -= 1

        clip = ImageClip(real_photo_path).set_duration(1.0)
        clip.write_videofile(
            temp_video_path,
            fps=24,
            codec="libx264",
            audio=False,
            preset="ultrafast",
            ffmpeg_params=["-pix_fmt", "yuv420p"],
            logger=None
        )
        clip.close()

        if not os.path.exists(CUSTOM_COVER_FILE):
            bot.send_message(ADMIN_ID, f"❌ '<code>{CUSTOM_COVER_FILE}</code>' nahi mili! Root folder me fake_cover.jpg dalein.")
            return

        prepare_thumbnail(CUSTOM_COVER_FILE, ready_thumb_path)

        kwargs = {
            "chat_id": int(target_user),
            "protect_content": True,
            "supports_streaming": True,
            "duration": 1,
            "width": width,
            "height": height
        }
        if quote_id:
            kwargs["reply_to_message_id"] = int(quote_id)

        with open(temp_video_path, "rb") as video_file, open(ready_thumb_path, "rb") as thumb_file:
            sent = bot.send_video(
                video=video_file,
                thumb=thumb_file,
                **kwargs
            )

        ensure_user(data, target_user)[span_44](start_span)[span_44](end_span)
        data["users"][target_user]["admin_msgs"].append(sent.message_id)[span_45](start_span)[span_45](end_span)

        data.setdefault("auto_delete", []).append({
            "chat_id": int(target_user),
            "message_id": sent.message_id,
            "delete_at": time.time() + AUTO_DELETE_SECONDS
        })

        admin_id_str = str(admin_msg_id)
        user_message_id = str(sent.message_id)
        data["reply_map"][admin_id_str] = target_user[span_46](start_span)[span_46](end_span)
        data["msg_map_a2u"][admin_id_str] = sent.message_id[span_47](start_span)[span_47](end_span)
        data["msg_map_u2a"][f"{target_user}_{user_message_id}"] = admin_msg_id[span_48](start_span)[span_48](end_span)
        save_data(data)[span_49](start_span)[span_49](end_span)

        bot.send_message(ADMIN_ID, f"✅ Fake cover video user <code>{target_user}</code> ko bhej di gayi!")

    except Exception as e:
        logging.error("Secret video error: %s", e)
        bot.send_message(ADMIN_ID, f"❌ Secret video error: {e}")
    finally:
        for p in [real_photo_path, temp_video_path, ready_thumb_path]:
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass

# ============================================================
# CONTINUOUS RE-BLUR LOOP
# ============================================================

def continuous_reblur_daemon():
    while True:
        try:
            time.sleep(REBLUR_INTERVAL_SECONDS)
            with active_spoilers_lock:
                items = list(active_spoilers.items())

            for (chat_id, message_id), media_info in items:
                try:
                    if media_info["type"] == "photo":
                        bot.edit_message_media(
                            chat_id=chat_id,
                            message_id=message_id,
                            media=InputMediaPhoto(
                                media=media_info["file_id"],
                                caption=media_info["caption"],
                                has_spoiler=True
                            )
                        )
                    elif media_info["type"] == "video":
                        bot.edit_message_media(
                            chat_id=chat_id,
                            message_id=message_id,
                            media=InputMediaVideo(
                                media=media_info["file_id"],
                                caption=media_info["caption"],
                                has_spoiler=True
                            )
                        )
                except Exception as e:
                    err_text = str(e).lower()
                    if "message to edit not found" in err_text or "message can't be edited" in err_text:
                        with active_spoilers_lock:
                            active_spoilers.pop((chat_id, message_id), None)
        except Exception as e:
            logging.error("Continuous reblur loop error: %s", e)

# ============================================================
# BACKGROUND AUTO-DELETE WORKER (6 GHANTE)
# ============================================================

def auto_delete_worker():
    while True:
        try:
            time.sleep(15)
            now = time.time()
            data = load_data()[span_50](start_span)[span_50](end_span)
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
                    with active_spoilers_lock:
                        active_spoilers.pop((cid, mid), None)
                    modified = True
                else:
                    remaining.append(item)

            if modified:
                data["auto_delete"] = remaining
                save_data(data)[span_51](start_span)[span_51](end_span)
        except Exception as e:
            logging.error("Auto delete worker error: %s", e)

# ============================================================
# COMMAND HANDLERS
# ============================================================

@bot.message_handler(commands=["start"])
def handle_start(message):
    chat_id = message.chat.id[span_52](start_span)[span_52](end_span)
    data = load_data()[span_53](start_span)[span_53](end_span)

    if chat_id == ADMIN_ID:[span_54](start_span)[span_54](end_span)
        selected = f"<code>{data['selected_user']}</code>" if data.get("selected_user") else "⭕ <i>None (Manual/Reply Mode)</i>[span_55](start_span)"[span_55](end_span)
        panel = f"""
🎛️ <b>CONTROL CONSOLE | ADMIN</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎯 <b>Focused Target:</b> {selected}
🛡️ <b>Protected ID:</b> <code>{PROTECTED_USER_ID or 'None'}</code>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📡 <b>ROUTING & MESSAGING:</b>
• <b>Reply directly</b> to any forwarded user message.
• <code>/select &lt;user_id&gt;</code> ── Lock focus
• <code>/unselect</code> ── Release focus
• <code>/dm &lt;id&gt; &lt;text&gt;</code> ── Send message
• <b>Secret Video:</b> Photo + <code>/secret</code> caption
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🧹 <b>PURGE & DELETION:</b>
• <code>/wipe &lt;id&gt;</code> ── 100% Instant Wipe (User + Admin msgs)
• <code>/clearall &lt;id&gt;</code> ── Delete Admin msgs
• <code>/purge &lt;id&gt;</code> ── Wipe all history + mappings
• <code>/resetdb</code> ── Reset DB state
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
👥 <b>MANAGEMENT:</b>
• <code>/users</code> ── List all users
• <code>/userprofile &lt;id&gt;</code> ── Open profile
• <code>/ban &lt;id&gt;</code> | <code>/unban &lt;id&gt;</code>
• <code>/alert &lt;id&gt;</code> ── Flag / Unflag
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔒 <i>Protection: Photos/Videos auto-blur active. Screenshots blocked. 6 hrs auto-delete enabled.</i>
"""
        bot.send_message(ADMIN_ID, panel)[span_56](start_span)[span_56](end_span)
        return

    user_id = str(chat_id)[span_57](start_span)[span_57](end_span)
    if user_id in data["blocked"]:[span_58](start_span)[span_58](end_span)
        return

    ensure_user(data, user_id)[span_59](start_span)[span_59](end_span)
    save_data(data)[span_60](start_span)[span_60](end_span)

    welcome_text = """
🔒 <b>ENCRYPTED SECURE CHANNEL</b>
<blockquote>
Aapka direct communication session establish ho chuka hai.
Aap yahan apna koi bhi message, photo, video ya document bhej sakte hain.
</blockquote>
💬 <i>Apna sandesh niche type karke send karein.</i>
"""
    bot.send_message(chat_id, welcome_text, protect_content=True)[span_61](start_span)[span_61](end_span)

@bot.message_handler(commands=["wipe"])
def wipe_chat(message):
    if message.chat.id != ADMIN_ID:[span_62](start_span)[span_62](end_span)
        return
    try:
        user_id = message.text.split()[1][span_63](start_span)[span_63](end_span)
    except IndexError:
        data = load_data()[span_64](start_span)[span_64](end_span)
        user_id = data.get("selected_user")[span_65](start_span)[span_65](end_span)
        if not user_id:
            bot.send_message(ADMIN_ID, "⚠️ <b>Format:</b> <code>/wipe &lt;user_id&gt;</code>")
            return

    user_id = str(user_id)[span_66](start_span)[span_66](end_span)
    data = load_data()[span_67](start_span)[span_67](end_span)
    if user_id not in data["users"]:[span_68](start_span)[span_68](end_span)
        bot.send_message(ADMIN_ID, "⚠️ User history not found.")[span_69](start_span)[span_69](end_span)
        return

    user_msgs = list(data["users"][user_id].get("user_msgs", []))[span_70](start_span)[span_70](end_span)
    admin_msgs = list(data["users"][user_id].get("admin_msgs", []))[span_71](start_span)[span_71](end_span)
    total = 0

    for msg_id in user_msgs:
        try:
            bot.delete_message(chat_id=int(user_id), message_id=int(msg_id))[span_72](start_span)[span_72](end_span)
            total += 1
        except Exception:
            pass

    for msg_id in admin_msgs:
        try:
            bot.delete_message(chat_id=int(user_id), message_id=int(msg_id))[span_73](start_span)[span_73](end_span)
            total += 1
        except Exception:
            pass
        with active_spoilers_lock:
            active_spoilers.pop((int(user_id), int(msg_id)), None)

    data["users"][user_id]["user_msgs"] = []
    data["users"][user_id]["admin_msgs"] = [][span_74](start_span)[span_74](end_span)
    data["auto_delete"] = [x for x in data.get("auto_delete", []) if str(x.get("chat_id")) != user_id]
    save_data(data)[span_75](start_span)[span_75](end_span)
    bot.send_message(ADMIN_ID, f"🧹 <b>100% Wiped:</b> User <code>{user_id}</code> ki screen se <b>{total}</b> messages delete kar diye gaye.")

@bot.message_handler(commands=["select"])
def select_user(message):
    if message.chat.id != ADMIN_ID:[span_76](start_span)[span_76](end_span)
        return
    try:
        user_id = message.text.split()[1][span_77](start_span)[span_77](end_span)
    except IndexError:
        bot.send_message(ADMIN_ID, "⚠️ <b>Format:</b> <code>/select &lt;user_id&gt;</code>")[span_78](start_span)[span_78](end_span)
        return
    data = load_data()[span_79](start_span)[span_79](end_span)
    ensure_user(data, user_id)[span_80](start_span)[span_80](end_span)
    data["selected_user"] = str(user_id)[span_81](start_span)[span_81](end_span)
    save_data(data)[span_82](start_span)[span_82](end_span)
    bot.send_message(ADMIN_ID, f"🎯 <b>Focus Locked:</b> <code>{user_id}</code>")[span_83](start_span)[span_83](end_span)

@bot.message_handler(commands=["unselect"])
def unselect_user(message):
    if message.chat.id != ADMIN_ID:[span_84](start_span)[span_84](end_span)
        return
    data = load_data()[span_85](start_span)[span_85](end_span)
    data["selected_user"] = None[span_86](start_span)[span_86](end_span)
    save_data(data)[span_87](start_span)[span_87](end_span)
    bot.send_message(ADMIN_ID, "🎯 <b>Focus Released.</b> Manual/Reply mode active.")[span_88](start_span)[span_88](end_span)

@bot.message_handler(commands=["dm"])
def direct_message(message):
    if message.chat.id != ADMIN_ID:[span_89](start_span)[span_89](end_span)
        return
    try:
        parts = message.text.split(" ", 2)[span_90](start_span)[span_90](end_span)
        user_id = parts[1][span_91](start_span)[span_91](end_span)
        text = parts[2][span_92](start_span)[span_92](end_span)
    except IndexError:
        bot.send_message(ADMIN_ID, "⚠️ <b>Format:</b> <code>/dm &lt;user_id&gt; &lt;text&gt;</code>")[span_93](start_span)[span_93](end_span)
        return
    data = load_data()[span_94](start_span)[span_94](end_span)
    if user_id in data["blocked"]:[span_95](start_span)[span_95](end_span)
        bot.send_message(ADMIN_ID, "⛔ User is blocked.")[span_96](start_span)[span_96](end_span)
        return
    try:
        sent = bot.send_message(int(user_id), text, protect_content=True)[span_97](start_span)[span_97](end_span)
        ensure_user(data, user_id)[span_98](start_span)[span_98](end_span)
        data["users"][user_id]["admin_msgs"].append(sent.message_id)[span_99](start_span)[span_99](end_span)

        data.setdefault("auto_delete", []).append({
            "chat_id": int(user_id),
            "message_id": sent.message_id,
            "delete_at": time.time() + AUTO_DELETE_SECONDS
        })

        admin_message_id = str(message.message_id)[span_100](start_span)[span_100](end_span)
        data["reply_map"][admin_message_id] = str(user_id)[span_101](start_span)[span_101](end_span)
        data["msg_map_a2u"][admin_message_id] = sent.message_id[span_102](start_span)[span_102](end_span)
        data["msg_map_u2a"][f"{user_id}_{sent.message_id}"] = message.message_id[span_103](start_span)[span_103](end_span)
        save_data(data)[span_104](start_span)[span_104](end_span)
        bot.send_message(ADMIN_ID, f"✅ <b>Sent to</b> <code>{user_id}</code> (Protected + Auto-deletes in 6 hrs)")
    except Exception as e:
        logging.error("DM delivery error: %s", e)[span_105](start_span)[span_105](end_span)
        bot.send_message(ADMIN_ID, "❌ <b>Delivery failed.</b>")[span_106](start_span)[span_106](end_span)

@bot.message_handler(commands=["clearall"])
def clear_admin_messages(message):
    if message.chat.id != ADMIN_ID:[span_107](start_span)[span_107](end_span)
        return
    try:
        user_id = message.text.split()[1][span_108](start_span)[span_108](end_span)
    except IndexError:
        data = load_data()[span_109](start_span)[span_109](end_span)
        user_id = data.get("selected_user")[span_110](start_span)[span_110](end_span)
        if not user_id:
            bot.send_message(ADMIN_ID, "⚠️ <b>Format:</b> <code>/clearall &lt;user_id&gt;</code>")[span_111](start_span)[span_111](end_span)
            return
    user_id = str(user_id)[span_112](start_span)[span_112](end_span)
    data = load_data()[span_113](start_span)[span_113](end_span)
    if user_id not in data["users"]:[span_114](start_span)[span_114](end_span)
        bot.send_message(ADMIN_ID, "⚠️ No message history found.")[span_115](start_span)[span_115](end_span)
        return
    admin_msgs = data["users"][user_id].get("admin_msgs", [])[span_116](start_span)[span_116](end_span)
    count = 0
    for msg_id in admin_msgs:
        try:
            bot.delete_message(chat_id=int(user_id), message_id=int(msg_id))[span_117](start_span)[span_117](end_span)
            count += 1
        except Exception:
            pass
        with active_spoilers_lock:
            active_spoilers.pop((int(user_id), int(msg_id)), None)
    data["users"][user_id]["admin_msgs"] = [][span_118](start_span)[span_118](end_span)
    save_data(data)[span_119](start_span)[span_119](end_span)
    bot.send_message(ADMIN_ID, f"🧹 <b>Cleared:</b> {count} Admin messages deleted from <code>{user_id}</code>'s chat.")[span_120](start_span)[span_120](end_span)

@bot.message_handler(commands=["purge"])
def purge_chat(message):
    if message.chat.id != ADMIN_ID:[span_121](start_span)[span_121](end_span)
        return
    try:
        user_id = message.text.split()[1][span_122](start_span)[span_122](end_span)
    except IndexError:
        bot.send_message(ADMIN_ID, "⚠️ <b>Format:</b> <code>/purge &lt;user_id&gt;</code>")[span_123](start_span)[span_123](end_span)
        return
    user_id = str(user_id)[span_124](start_span)[span_124](end_span)
    data = load_data()[span_125](start_span)[span_125](end_span)
    if user_id not in data["users"]:[span_126](start_span)[span_126](end_span)
        bot.send_message(ADMIN_ID, "⚠️ User history not found.")[span_127](start_span)[span_127](end_span)
        return
    user_data = data["users"][user_id][span_128](start_span)[span_128](end_span)
    user_msgs = list(user_data.get("user_msgs", []))[span_129](start_span)[span_129](end_span)
    admin_msgs = list(user_data.get("admin_msgs", []))[span_130](start_span)[span_130](end_span)
    total = 0
    for msg_id in user_msgs:
        try:
            bot.delete_message(chat_id=int(user_id), message_id=int(msg_id))[span_131](start_span)[span_131](end_span)
            total += 1[span_132](start_span)[span_132](end_span)
        except Exception:
            pass[span_133](start_span)[span_133](end_span)
    for msg_id in admin_msgs:
        try:
            bot.delete_message(chat_id=int(user_id), message_id=int(msg_id))[span_134](start_span)[span_134](end_span)
            total += 1[span_135](start_span)[span_135](end_span)
        except Exception:
            pass[span_136](start_span)[span_136](end_span)
        with active_spoilers_lock:
            active_spoilers.pop((int(user_id), int(msg_id)), None)
    reply_map = data.get("reply_map", {})[span_137](start_span)[span_137](end_span)
    msg_map_a2u = data.get("msg_map_a2u", {})[span_138](start_span)[span_138](end_span)
    msg_map_u2a = data.get("msg_map_u2a", {})[span_139](start_span)[span_139](end_span)
    for admin_id, mapped_user in list(reply_map.items()):[span_140](start_span)[span_140](end_span)
        if str(mapped_user) == user_id:[span_141](start_span)[span_141](end_span)
            reply_map.pop(admin_id, None)[span_142](start_span)[span_142](end_span)
            msg_map_a2u.pop(admin_id, None)[span_143](start_span)[span_143](end_span)
    prefix = f"{user_id}_[span_144](start_span)"[span_144](end_span)
    for key in list(msg_map_u2a.keys()):[span_145](start_span)[span_145](end_span)
        if key.startswith(prefix):
            msg_map_u2a.pop(key, None)[span_146](start_span)[span_146](end_span)
    data["users"][user_id] = {"admin_msgs": [], "user_msgs": []}[span_147](start_span)[span_147](end_span)
    data["auto_delete"] = [x for x in data.get("auto_delete", []) if str(x.get("chat_id")) != user_id]
    save_data(data)[span_148](start_span)[span_148](end_span)
    bot.send_message(ADMIN_ID, f"💥 <b>Purge completed.</b>\n\n👤 User: <code>{user_id}</code>\n🗑 Deleted known messages: <b>{total}</b>\n🧹 Routing mappings cleared.")[span_149](start_span)[span_149](end_span)

@bot.message_handler(commands=["resetdb"])
def reset_database(message):
    if message.chat.id != ADMIN_ID:[span_150](start_span)[span_150](end_span)
        return
    with active_spoilers_lock:
        active_spoilers.clear()
    data = empty_db()[span_151](start_span)[span_151](end_span)
    ensure_protected_user(data)[span_152](start_span)[span_152](end_span)
    save_data(data)[span_153](start_span)[span_153](end_span)
    bot.send_message(ADMIN_ID, "♻️ <b>Database Reset:</b> All state logs and mappings cleared.")[span_154](start_span)[span_154](end_span)

@bot.message_handler(commands=["users"])
def list_users(message):
    if message.chat.id != ADMIN_ID:[span_155](start_span)[span_155](end_span)
        return
    data = load_data()[span_156](start_span)[span_156](end_span)
    users_dict = data.get("users", {})[span_157](start_span)[span_157](end_span)
    if not users_dict:[span_158](start_span)[span_158](end_span)
        bot.send_message(ADMIN_ID, "👥 <b>No registered users found.</b>")[span_159](start_span)[span_159](end_span)
        return
    text = "📊 <b>USER DIRECTORY</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n[span_160](start_span)"[span_160](end_span)
    for i, user_id in enumerate(users_dict.keys(), 1):[span_161](start_span)[span_161](end_span)
        if user_id in data["blocked"]:
            status = "⛔ [Banned][span_162](start_span)"[span_162](end_span)
        elif user_id in data["alerts"]:
            status = "🚨 [Flagged][span_163](start_span)"[span_163](end_span)
        elif user_id == PROTECTED_USER_ID:
            status = "🛡️ [Protected]"
        else:
            status = "🟢 [Active][span_164](start_span)"[span_164](end_span)
        text += f"{i}. <code>{user_id}</code> ── {status}\n[span_165](start_span)"[span_165](end_span)
    bot.send_message(ADMIN_ID, text)

@bot.message_handler(commands=["ban"])
def ban_user(message):
    if message.chat.id != ADMIN_ID:[span_166](start_span)[span_166](end_span)
        return
    try:
        user_id = message.text.split()[1][span_167](start_span)[span_167](end_span)
    except IndexError:
        bot.send_message(ADMIN_ID, "⚠️ <b>Format:</b> <code>/ban &lt;user_id&gt;</code>")[span_168](start_span)[span_168](end_span)
        return
    user_id = str(user_id)[span_169](start_span)[span_169](end_span)
    data = load_data()[span_170](start_span)[span_170](end_span)
    if user_id not in data["blocked"]:[span_171](start_span)[span_171](end_span)
        data["blocked"].append(user_id)[span_172](start_span)[span_172](end_span)
        save_data(data)[span_173](start_span)[span_173](end_span)
        bot.send_message(ADMIN_ID, f"⛔ User <code>{user_id}</code> is now blocked.")[span_174](start_span)[span_174](end_span)
    else:
        bot.send_message(ADMIN_ID, "⚠️ User is already blocked.")[span_175](start_span)[span_175](end_span)

@bot.message_handler(commands=["unban"])
def unban_user(message):
    if message.chat.id != ADMIN_ID:[span_176](start_span)[span_176](end_span)
        return
    try:
        user_id = message.text.split()[1][span_177](start_span)[span_177](end_span)
    except IndexError:
        bot.send_message(ADMIN_ID, "⚠️ <b>Format:</b> <code>/unban &lt;user_id&gt;</code>")[span_178](start_span)[span_178](end_span)
        return
    user_id = str(user_id)[span_179](start_span)[span_179](end_span)
    data = load_data()[span_180](start_span)[span_180](end_span)
    if user_id in data["blocked"]:[span_181](start_span)[span_181](end_span)
        data["blocked"].remove(user_id)[span_182](start_span)[span_182](end_span)
        save_data(data)[span_183](start_span)[span_183](end_span)
        bot.send_message(ADMIN_ID, f"✅ User <code>{user_id}</code> unblocked.")[span_184](start_span)[span_184](end_span)
    else:
        bot.send_message(ADMIN_ID, "⚠️ User is not blocked.")[span_185](start_span)[span_185](end_span)

@bot.message_handler(commands=["alert"])
def toggle_alert(message):
    if message.chat.id != ADMIN_ID:[span_186](start_span)[span_186](end_span)
        return
    try:
        user_id = message.text.split()[1][span_187](start_span)[span_187](end_span)
    except IndexError:
        bot.send_message(ADMIN_ID, "⚠️ <b>Format:</b> <code>/alert &lt;user_id&gt;</code>")[span_188](start_span)[span_188](end_span)
        return
    user_id = str(user_id)[span_189](start_span)[span_189](end_span)
    data = load_data()[span_190](start_span)[span_190](end_span)
    if user_id not in data["alerts"]:[span_191](start_span)[span_191](end_span)
        data["alerts"].append(user_id)[span_192](start_span)[span_192](end_span)
        bot.send_message(ADMIN_ID, f"🚨 Alert flag ADDED to <code>{user_id}</code>.")[span_193](start_span)[span_193](end_span)
    else:
        data["alerts"].remove(user_id)[span_194](start_span)[span_194](end_span)
        bot.send_message(ADMIN_ID, f"🏳️ Alert flag REMOVED from <code>{user_id}</code>.")[span_195](start_span)[span_195](end_span)
    save_data(data)

@bot.message_handler(commands=["userprofile"])
def user_profile(message):
    if message.chat.id != ADMIN_ID:[span_196](start_span)[span_196](end_span)
        return
    parts = message.text.split(maxsplit=1)[span_197](start_span)[span_197](end_span)
    if len(parts) < 2:[span_198](start_span)[span_198](end_span)
        bot.send_message(ADMIN_ID, "⚠️ <b>Format:</b> <code>/userprofile &lt;user_id&gt;</code>"); return[span_199](start_span)[span_199](end_span)
    user_id = parts[1].strip()[span_200](start_span)[span_200](end_span)
    if not user_id.lstrip("-").isdigit():[span_201](start_span)[span_201](end_span)
        bot.send_message(ADMIN_ID, "⚠️ Invalid Chat ID."); return[span_202](start_span)[span_202](end_span)
    data = load_data()[span_203](start_span)[span_203](end_span)
    if user_id not in data.get("users", {}):[span_204](start_span)[span_204](end_span)
        if user_id == PROTECTED_USER_ID:[span_205](start_span)[span_205](end_span)
            ensure_protected_user(data)[span_206](start_span)[span_206](end_span)
            save_data(data)[span_207](start_span)[span_207](end_span)
        else:
            bot.send_message(ADMIN_ID, f"⚠️ User <code>{user_id}</code> is not registered."); return[span_208](start_span)[span_208](end_span)
    u = data["users"].get(user_id, {})[span_209](start_span)[span_209](end_span)
    if user_id in data["blocked"]: status = "⛔ Banned[span_210](start_span)"[span_210](end_span)
    elif user_id in data["alerts"]: status = "🚨 Alert[span_211](start_span)"[span_211](end_span)
    elif user_id == PROTECTED_USER_ID: status = "🛡️ Protected"
    else: status = "🟢 Active[span_212](start_span)"[span_212](end_span)
    link = f"tg://user?id={user_id}[span_213](start_span)"[span_213](end_span)
    text = (f"👤 <b>USER PROFILE</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n🆔 <b>Chat ID:</b> <code>{user_id}</code>\n📊 <b>Status:</b> {status}\n💬 <b>User Messages:</b> {len(u.get('user_msgs', []))}\n📨 <b>Admin Messages:</b> {len(u.get('admin_msgs', []))}\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n<a href=\"{link}\">🔗 OPEN TELEGRAM PROFILE</a>")[span_214](start_span)[span_214](end_span)
    bot.send_message(ADMIN_ID, text, disable_web_page_preview=True)[span_215](start_span)[span_215](end_span)

# ============================================================
# CORE ROUTING ENGINE
# ============================================================

@bot.message_handler(func=lambda message: True, content_types=SUPPORTED_TYPES)[span_216](start_span)[span_216](end_span)
def handle_all_messages(message):
    chat_id = message.chat.id[span_217](start_span)[span_217](end_span)
    message_id = message.message_id[span_218](start_span)[span_218](end_span)
    data = load_data()[span_219](start_span)[span_219](end_span)

    # ADMIN -> USER
    if chat_id == ADMIN_ID:[span_220](start_span)[span_220](end_span)
        target_user = None[span_221](start_span)[span_221](end_span)
        target_quote_id = None[span_222](start_span)[span_222](end_span)
        if message.reply_to_message:[span_223](start_span)[span_223](end_span)
            replied_admin_id = str(message.reply_to_message.message_id)[span_224](start_span)[span_224](end_span)
            target_user = data["reply_map"].get(replied_admin_id)[span_225](start_span)[span_225](end_span)
            if target_user:
                target_quote_id = data["msg_map_a2u"].get(replied_admin_id)[span_226](start_span)[span_226](end_span)
        elif data.get("selected_user"):[span_227](start_span)[span_227](end_span)
            target_user = str(data["selected_user"])[span_228](start_span)[span_228](end_span)

        if not target_user:[span_229](start_span)[span_229](end_span)
            bot.send_message(ADMIN_ID, "⚠️ <b>Action Required:</b> Reply directly to a user's forwarded message, or use <code>/select &lt;user_id&gt;</code>.")[span_230](start_span)[span_230](end_span)
            return

        target_user = str(target_user)[span_231](start_span)[span_231](end_span)
        if target_user in data["blocked"]:[span_232](start_span)[span_232](end_span)
            bot.send_message(ADMIN_ID, "⛔ Delivery failed: User is blocked.")[span_233](start_span)[span_233](end_span)
            return

        # /secret PHOTO TO FAKE THUMBNAIL VIDEO
        caption = message.caption or ""
        if message.content_type == "photo" and caption.strip().lower() == "/secret":
            bot.send_message(ADMIN_ID, "⏳ Processing started: Fake thumbnail video create ho rahi hai...")
            photo_file_id = message.photo[-1].file_id
            threading.Thread(
                target=process_secret_video,
                args=(photo_file_id, target_user, data, message_id, target_quote_id),
                daemon=True
            ).start()
            return

        try:
            sent = None
            quote_arg = {"reply_to_message_id": int(target_quote_id)} if target_quote_id else {}

            if message.content_type == "photo":
                file_id = message.photo[-1].file_id
                caption = message.caption or ""
                sent = bot.send_photo(
                    chat_id=int(target_user),
                    photo=file_id,
                    caption=caption,
                    has_spoiler=True,
                    protect_content=True,
                    **quote_arg
                )
                with active_spoilers_lock:
                    active_spoilers[(int(target_user), sent.message_id)] = {
                        "type": "photo",
                        "file_id": file_id,
                        "caption": caption
                    }

            elif message.content_type == "video":
                file_id = message.video.file_id
                caption = message.caption or ""
                sent = bot.send_video(
                    chat_id=int(target_user),
                    video=file_id,
                    caption=caption,
                    has_spoiler=True,
                    protect_content=True,
                    **quote_arg
                )
                with active_spoilers_lock:
                    active_spoilers[(int(target_user), sent.message_id)] = {
                        "type": "video",
                        "file_id": file_id,
                        "caption": caption
                    }

            else:
                args = {
                    "chat_id": int(target_user),
                    "from_chat_id": ADMIN_ID,
                    "message_id": message_id,
                    "protect_content": True
                }[span_234](start_span)[span_234](end_span)
                if target_quote_id:[span_235](start_span)[span_235](end_span)
                    args["reply_to_message_id"] = int(target_quote_id)[span_236](start_span)[span_236](end_span)
                sent = bot.copy_message(**args)[span_237](start_span)[span_237](end_span)

            ensure_user(data, target_user)[span_238](start_span)[span_238](end_span)
            data["users"][target_user]["admin_msgs"].append(sent.message_id)[span_239](start_span)[span_239](end_span)

            data.setdefault("auto_delete", []).append({
                "chat_id": int(target_user),
                "message_id": sent.message_id,
                "delete_at": time.time() + AUTO_DELETE_SECONDS
            })

            admin_id = str(message_id)[span_240](start_span)[span_240](end_span)
            user_message_id = str(sent.message_id)[span_241](start_span)[span_241](end_span)
            data["reply_map"][admin_id] = target_user[span_242](start_span)[span_242](end_span)
            data["msg_map_a2u"][admin_id] = sent.message_id[span_243](start_span)[span_243](end_span)
            data["msg_map_u2a"][f"{target_user}_{user_message_id}"] = message_id[span_244](start_span)[span_244](end_span)
            save_data(data)[span_245](start_span)[span_245](end_span)
        except Exception as e:
            logging.error("Admin -> User routing error: %s", e)[span_246](start_span)[span_246](end_span)
            bot.send_message(ADMIN_ID, "❌ <b>Send Failed.</b>")[span_247](start_span)[span_247](end_span)
        return

    # USER -> ADMIN
    user_id = str(chat_id)[span_248](start_span)[span_248](end_span)
    if user_id in data["blocked"]:[span_249](start_span)[span_249](end_span)
        return
    ensure_user(data, user_id)[span_250](start_span)[span_250](end_span)
    data["users"][user_id]["user_msgs"].append(message_id)[span_251](start_span)[span_251](end_span)

    reply_to_admin_msg_id = None[span_252](start_span)[span_252](end_span)
    if message.reply_to_message:[span_253](start_span)[span_253](end_span)
        replied_user_msg_id = message.reply_to_message.message_id[span_254](start_span)[span_254](end_span)
        lookup_key = f"{user_id}_{replied_user_msg_id}[span_255](start_span)"[span_255](end_span)
        reply_to_admin_msg_id = data["msg_map_u2a"].get(lookup_key)[span_256](start_span)[span_256](end_span)

    try:
        copied = bot.forward_message(chat_id=ADMIN_ID, from_chat_id=chat_id, message_id=message_id)[span_257](start_span)[span_257](end_span)
        admin_message_id = copied.message_id[span_258](start_span)[span_258](end_span)

        if reply_to_admin_msg_id:[span_259](start_span)[span_259](end_span)
            try:
                bot.copy_message(chat_id=ADMIN_ID, from_chat_id=chat_id, message_id=message_id, reply_to_message_id=int(reply_to_admin_msg_id))[span_260](start_span)[span_260](end_span)
                try:
                    bot.delete_message(chat_id=ADMIN_ID, message_id=admin_message_id)[span_261](start_span)[span_261](end_span)
                    admin_message_id = admin_message_id + 1[span_262](start_span)[span_262](end_span)
                except Exception:
                    pass[span_263](start_span)[span_263](end_span)
            except Exception:
                pass[span_264](start_span)[span_264](end_span)

        data["reply_map"][str(admin_message_id)] = user_id[span_265](start_span)[span_265](end_span)
        data["msg_map_a2u"][str(admin_message_id)] = message_id[span_266](start_span)[span_266](end_span)
        data["msg_map_u2a"][f"{user_id}_{message_id}"] = admin_message_id[span_267](start_span)[span_267](end_span)

        if user_id in data["alerts"]:[span_268](start_span)[span_268](end_span)
            try:
                bot.send_message(ADMIN_ID, f"🚨 <b>ALERT: Flagged User Active</b>\n👤 <code>{user_id}</code>", reply_to_message_id=admin_message_id)[span_269](start_span)[span_269](end_span)
            except Exception:
                pass[span_270](start_span)[span_270](end_span)

        save_data(data)[span_271](start_span)[span_271](end_span)
    except Exception as e:
        logging.error("Inbound routing error: %s", e)[span_272](start_span)[span_272](end_span)

# ============================================================
# REACTION & EDIT SYNC
# ============================================================

def _reaction_to_payload(reaction):
    try:
        if reaction.type == "emoji":[span_273](start_span)[span_273](end_span)
            return {"type": "emoji", "emoji": reaction.emoji}[span_274](start_span)[span_274](end_span)
        if reaction.type == "custom_emoji":[span_275](start_span)[span_275](end_span)
            return {"type": "custom_emoji", "custom_emoji_id": reaction.custom_emoji_id}[span_276](start_span)[span_276](end_span)
    except Exception:[span_277](start_span)[span_277](end_span)
        pass[span_278](start_span)[span_278](end_span)
    return None[span_279](start_span)[span_279](end_span)

def _mirror_reaction_to_other_side(source_chat_id, source_message_id, reaction_items, is_user_side):
    data = load_data()[span_280](start_span)[span_280](end_span)
    source_message_id = int(source_message_id)[span_281](start_span)[span_281](end_span)
    if is_user_side:[span_282](start_span)[span_282](end_span)
        user_id = str(source_chat_id)[span_283](start_span)[span_283](end_span)
        counterpart = data["msg_map_u2a"].get(f"{user_id}_{source_message_id}")[span_284](start_span)[span_284](end_span)
        target_chat_id = ADMIN_ID[span_285](start_span)[span_285](end_span)
    else:
        counterpart = data["msg_map_a2u"].get(str(source_message_id))[span_286](start_span)[span_286](end_span)
        target_user = data["reply_map"].get(str(source_message_id))[span_287](start_span)[span_287](end_span)
        if not target_user:[span_288](start_span)[span_288](end_span)
            return
        target_chat_id = int(target_user)[span_289](start_span)[span_289](end_span)
    if not counterpart:[span_290](start_span)[span_290](end_span)
        return
    try:
        bot.set_message_reaction(chat_id=target_chat_id, message_id=int(counterpart), reaction=[])[span_291](start_span)[span_291](end_span)
    except Exception as e:[span_292](start_span)[span_292](end_span)
        logging.warning("Could not clear mirrored reaction: %s", e)[span_293](start_span)[span_293](end_span)
    if not reaction_items:[span_294](start_span)[span_294](end_span)
        return
    for item in reaction_items:[span_295](start_span)[span_295](end_span)
        payload = _reaction_to_payload(item)[span_296](start_span)[span_296](end_span)
        if not payload:[span_297](start_span)[span_297](end_span)
            continue[span_298](start_span)[span_298](end_span)
        try:
            bot.set_message_reaction(chat_id=target_chat_id, message_id=int(counterpart), reaction=[payload])[span_299](start_span)[span_299](end_span)
            break[span_300](start_span)[span_300](end_span)
        except Exception as e:[span_301](start_span)[span_301](end_span)
            logging.warning("Could not mirror reaction: %s", e)[span_302](start_span)[span_302](end_span)

if hasattr(bot, "message_reaction_handler"):[span_303](start_span)[span_303](end_span)
    @bot.message_reaction_handler(func=lambda reaction: True)[span_304](start_span)[span_304](end_span)
    def handle_message_reaction(reaction):
        try:
            is_user = (reaction.chat.id != ADMIN_ID)[span_305](start_span)[span_305](end_span)
            new_reaction = getattr(reaction, "new_reaction", None) or [][span_306](start_span)[span_306](end_span)
            _mirror_reaction_to_other_side(source_chat_id=reaction.chat.id, source_message_id=reaction.message_id, reaction_items=new_reaction, is_user_side=is_user)[span_307](start_span)[span_307](end_span)
        except Exception as e:[span_308](start_span)[span_308](end_span)
            logging.error("Reaction sync error: %s", e)[span_309](start_span)[span_309](end_span)

@bot.edited_message_handler(func=lambda message: True, content_types=SUPPORTED_TYPES)[span_310](start_span)[span_310](end_span)
def handle_edits(message):
    chat_id = message.chat.id[span_311](start_span)[span_311](end_span)
    message_id = message.message_id[span_312](start_span)[span_312](end_span)
    data = load_data()[span_313](start_span)[span_313](end_span)
    if chat_id == ADMIN_ID:[span_314](start_span)[span_314](end_span)
        user_target_msg_id = data["msg_map_a2u"].get(str(message_id))[span_315](start_span)[span_315](end_span)
        target_user = data["reply_map"].get(str(message_id))[span_316](start_span)[span_316](end_span)
        if user_target_msg_id and target_user:[span_317](start_span)[span_317](end_span)
            try:
                if message.content_type == "text":[span_318](start_span)[span_318](end_span)
                    bot.edit_message_text(message.text, int(target_user), int(user_target_msg_id))[span_319](start_span)[span_319](end_span)
            except Exception:[span_320](start_span)[span_320](end_span)
                pass[span_321](start_span)[span_321](end_span)
        return
    user_id = str(chat_id)[span_322](start_span)[span_322](end_span)
    admin_ref_id = data["msg_map_u2a"].get(f"{user_id}_{message_id}")[span_323](start_span)[span_323](end_span)
    if admin_ref_id:[span_324](start_span)[span_324](end_span)
        try:
            if message.content_type == "text":[span_325](start_span)[span_325](end_span)
                bot.send_message(ADMIN_ID, f"✏️ <b>[User Edited Message]</b>\n\n{message.text}", reply_to_message_id=int(admin_ref_id))[span_326](start_span)[span_326](end_span)
        except Exception:[span_327](start_span)[span_327](end_span)
            pass[span_328](start_span)[span_328](end_span)

# ============================================================
# START SERVICES WITH 409 RESILIENCE
# ============================================================

def start_services():
    data = load_data()[span_329](start_span)[span_329](end_span)
    ensure_protected_user(data)[span_330](start_span)[span_330](end_span)
    save_data(data)[span_331](start_span)[span_331](end_span)

    threading.Thread(target=run_flask, daemon=True).start()[span_332](start_span)[span_332](end_span)
    threading.Thread(target=auto_delete_worker, daemon=True).start()
    threading.Thread(target=continuous_reblur_daemon, daemon=True).start()
    logging.info("Core Gateway Server Running with Video Converter, Auto-Delete & Reblur...")

    try:
        bot.delete_webhook(drop_pending_updates=True)[span_333](start_span)[span_333](end_span)
        bot.remove_webhook()[span_334](start_span)[span_334](end_span)
        logging.info("Webhook cleared, waiting 5 sec to resolve instance conflicts...")[span_335](start_span)[span_335](end_span)
    except Exception as e:
        logging.warning(f"Webhook clear warning: {e}")[span_336](start_span)[span_336](end_span)

    time.sleep(5)

    while True:
        try:
            bot.infinity_polling(
                skip_pending=True,
                timeout=20,
                long_polling_timeout=20,
                allowed_updates=["message", "edited_message", "message_reaction"]
            )
        except Exception as e:
            err_str = str(e)
            if "409" in err_str:
                logging.warning("409 Conflict encountered. Waiting 10s for other instance to release...")
                time.sleep(10)
            else:
                logging.error(f"Polling loop encountered: {e}. Retrying in 5s...")
                time.sleep(5)

if __name__ == "__main__":
    start_services()
