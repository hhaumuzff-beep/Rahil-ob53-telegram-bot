import os
import telebot
import requests
import time
import threading
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from flask import Flask, request, jsonify

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# === CONFIG ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # Render Link eg: https://your-service.onrender.com

REQUIRED_CHANNELS = ["@eaglelikeera"]
GROUP_JOIN_LINK = "https://t.me/eaglelikeera03"
OWNER_ID = 7118852390
OWNER_USERNAME = "@eaglehitsdiff"

bot = telebot.TeleBot(BOT_TOKEN) if BOT_TOKEN else None
like_tracker = {}   # in-memory usage cache
app = Flask(__name__)

# === DATA RESET ===
def reset_limits():
    while True:
        try:
            now_utc = datetime.now(timezone.utc)
            next_reset = (now_utc + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            sleep_seconds = (next_reset - now_utc).total_seconds()
            time.sleep(sleep_seconds)
            like_tracker.clear()
            logger.info("✅ Daily limits reset at 00:00 UTC.")
        except Exception as e:
            logger.error(f"Error in reset_limits thread: {e}")

threading.Thread(target=reset_limits, daemon=True).start()

# === UTILS ===
def is_user_in_channel(user_id):
    if not bot:
        return True
    try:
        for channel in REQUIRED_CHANNELS:
            member = bot.get_chat_member(channel, user_id)
            if member.status not in ['member', 'administrator', 'creator']:
                return False
        return True
    except Exception as e:
        logger.error(f"Join check failed: {e}")
        return False

def call_api(region, uid):
    # This calls your Like Generation API
    url = f"https://free-fire-like-api-black.vercel.app/like?uid={uid}&server_name={region}"
    try:
        response = requests.get(url, timeout=20)
        if response.status_code != 200:
            return {"⚠️Invalid": " Maximum likes reached for today. Please try again tomorrow."}
        return response.json()
    except requests.exceptions.RequestException:
        return {"error": "API Failed. Please try again later."}

def get_user_limit(user_id):
    if user_id == OWNER_ID:
        return 999999999  # Unlimited for owner
    return 1  # 1 request per day for regular users

# === FLASK WEBHOOK ROUTES ===
@app.route('/')
def home():
    return jsonify({
        'status': 'Bot is running',
        'health': 'OK',
        'mode': 'Webhook Enabled' if WEBHOOK_URL else 'Polling Mode'
    })

@app.route('/health')
def health():
    return jsonify({'status': 'healthy'}), 200

@app.route('/webhook', methods=['POST'])
def webhook():
    if not bot:
        return jsonify({"error": "Bot token not specified"}), 400
    try:
        json_str = request.get_data().decode('UTF-8')
        update = telebot.types.Update.de_json(json_str)
        bot.process_new_updates([update])
        return '', 200
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return '', 500

# === TELEGRAM COMMANDS ===
if bot:
    @bot.message_handler(commands=['start'])
    def start_command(message):
        user_id = message.from_user.id
        if not is_user_in_channel(user_id):
            markup = InlineKeyboardMarkup()
            for channel in REQUIRED_CHANNELS:
                markup.add(InlineKeyboardButton(f"🔗 Join {channel}", url=f"https://t.me/{channel.strip('@')}"))
            bot.reply_to(message, "📢 *Channel Membership Required*\n\nTo use this bot, you must join our channel first!", reply_markup=markup, parse_mode="Markdown")
            return
        
        if user_id not in like_tracker:
            like_tracker[user_id] = {"used": 0, "last_used": datetime.now(timezone.utc) - timedelta(days=1)}
        bot.reply_to(message, "✅ *You are verified!*\n\nUse `/like <server> <uid>` command to send likes.", parse_mode="Markdown")

    @bot.message_handler(commands=['like'])
    def handle_like(message):
        user_id = message.from_user.id
        args = message.text.split()

        if message.chat.type == "private" and user_id != OWNER_ID:
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("🔗 Join Official Group", url=GROUP_JOIN_LINK))
            bot.reply_to(message, "❌ Sorry! command is not allowed here.\n\nJoin our official group:", reply_markup=markup)
            return

        if not is_user_in_channel(user_id):
            markup = InlineKeyboardMarkup()
            for channel in REQUIRED_CHANNELS:
                markup.add(InlineKeyboardButton(f"🔗 Join {channel}", url=f"https://t.me/{channel.strip('@')}"))
            bot.reply_to(message, "❌ You must join our channels to use this command.", reply_markup=markup, parse_mode="Markdown")
            return

        if len(args) != 3:
            bot.reply_to(message, "❌ Format: `/like server_name uid`", parse_mode="Markdown")
            return

        region, uid = args[1], args[2]
        if not region.isalpha() or not uid.isdigit():
            bot.reply_to(message, "⚠️ Invalid input format! Use: `/like server_name uid`", parse_mode="Markdown")
            return

        threading.Thread(target=process_like, args=(message, region, uid)).start()

    def process_like(message, region, uid):
        user_id = message.from_user.id
        now_utc = datetime.now(timezone.utc)
        usage = like_tracker.get(user_id, {"used": 0, "last_used": now_utc - timedelta(days=1)})

        if now_utc.date() > usage["last_used"].date():
            usage["used"] = 0

        max_limit = get_user_limit(user_id)
        if usage["used"] >= max_limit:
            bot.reply_to(message, f"⚠️ You have exceeded your daily request limit!")
            return

        processing_msg = bot.reply_to(message, "⏳ *Please wait... Sending likes...*", parse_mode="Markdown")
        response = call_api(region, uid)

        if "error" in response:
            bot.reply_to(message, f"⚠️ API Error: {response['error']}")
            return

        if not isinstance(response, dict) or response.get("status") != 1:
            bot.reply_to(message, "❌ UID already received max likes. Limit reached for today, try another UID.")
            return

        try:
            player_uid = str(response.get("UID", uid)).strip()
            player_name = response.get("PlayerNickname", "N/A")
            reg = str(response.get("Region", "N/A"))
            likes_before = str(response.get("LikesbeforeCommand", "N/A"))
            likes_after = str(response.get("LikesafterCommand", "N/A"))
            likes_given = str(response.get("LikesGivenByAPI", "N/A"))

            usage["used"] += 1
            usage["last_used"] = now_utc
            like_tracker[user_id] = usage
            
            response_text = f"✅ *Request Processed Successfully*\n\n👤 *Name:* `{player_name}`\n🆔 *UID:* `{player_uid}`\n🌍 *Region:* `{reg}`\n🤡 *Likes Before:* `{likes_before}`\n📈 *Likes Added:* `{likes_given}`\n🗿 *Total Likes Now:* `{likes_after}`\n🔐 *Remaining Requests:* `{max_limit - usage['used']}`"
            bot.edit_message_text(chat_id=processing_msg.chat.id, message_id=processing_msg.message_id, text=response_text, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Error in process_like details: {e}")
            bot.reply_to(message, "⚠️ Likes sent! (Could not parse visual detail payload).")

    @bot.message_handler(commands=["remain"])
    def owner_commands(message):
        if message.from_user.id != OWNER_ID:
            return
        lines = ["📊 *Remaining Daily Requests Per User:*"]
        if not like_tracker:
            lines.append("❌ No users active today.")
        else:
            for uid, usage in like_tracker.items():
                limit = get_user_limit(uid)
                used = usage.get("used", 0)
                limit_str = "Unlimited" if limit > 1000 else str(limit)
                lines.append(f"👤 `{uid}` ➜ {used}/{limit_str}")
        bot.reply_to(message, "\n".join(lines), parse_mode="Markdown")

    @bot.message_handler(commands=['help'])
    def help_command(message):
        help_text = (
            f"📖 *Bot Commands:*\n\n"
            f"🧑💻 `/like <region> <uid>` - Send likes to UID\n"
            f"🔰 `/start` - Start or verify\n"
            f"🆘 `/help` - Help Menu"
        )
        bot.reply_to(message, help_text, parse_mode="Markdown")

    # === WEBHOOK SETUP VS POLLING BOOT ===
    if WEBHOOK_URL:
        try:
            bot.remove_webhook()
            # Set webhook pointing to Render
            bot.set_webhook(url=f"{WEBHOOK_URL.rstrip('/')}/webhook")
            logger.info(f"🚀 Webhook registered successfully pointing to: {WEBHOOK_URL}")
        except Exception as e:
            logger.error(f"Failed to set webhook, falling back: {e}")
    else:
        def run_polling():
            try:
                bot.remove_webhook()
                bot.infinity_polling(skip_pending_updates=True)
            except Exception as e:
                logger.error(f"Polling crash: {e}")
        threading.Thread(target=run_polling, daemon=True).start()
        logger.info("📡 Safe fallback background polling triggered.")

if __name__ == "__main__":
    PORT = int(os.environ.get("PORT", 10000))
    # Start web app for Webhook & Health requests
    app.run(host="0.0.0.0", port=PORT)
