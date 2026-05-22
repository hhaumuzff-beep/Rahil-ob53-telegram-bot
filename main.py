import os
import telebot
import requests
import time
import threading
import asyncio
import logging
import sys
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

if not BOT_TOKEN:
    logger.error("❌ BOT_TOKEN not found! Please set your bot token in environment variables.")

REQUIRED_CHANNELS = ["@eaglelikeera"]
GROUP_JOIN_LINK = "https://t.me/eaglelikeera03"
OWNER_ID = 7790124713
OWNER_USERNAME = "@eaglehitsdiff"
bot = telebot.TeleBot(BOT_TOKEN) if BOT_TOKEN else None
like_tracker = {}

app = Flask(__name__)

# === LIMIT RESET ===

def reset_limits():
    """Daily reset of usage tracker (in-memory only)."""
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
    url = f"https://free-fire-like-api-black.vercel.app/like?uid={uid}&server_name={region}"
    try:
        response = requests.get(url, timeout=20)
        if response.status_code != 200:
            return {"⚠️Invalid": " Maximum likes reached for today. Please try again tomorrow."}
        return response.json()
    except requests.exceptions.RequestException:
        return {"error": "API Failed. Please try again later."}
    except ValueError:
        return {"error": "Invalid JSON response."}


def get_user_limit(user_id):
    if user_id == OWNER_ID:
        return 999999999
    return 1

# Start background limit reset
threading.Thread(target=reset_limits, daemon=True).start()

# === BACKGROUND TOKEN AUTO UPDATE ===
try:
    from token_refresh import auto_refresh
    threading.Thread(
        target=lambda: asyncio.run(auto_refresh()),
        daemon=True
    ).start()
    logger.info("📡 Token refresh thread is now running safely in background every 10 min loop.")
except ImportError:
    logger.warning("token_refresh.py not found. Skipping auto-refresh feature.")
except Exception as e:
    logger.error(f"Error starting token refresh background daemon: {e}")

# === FLASK ROUTES ===

@app.route('/')
def home():
    return jsonify({
        'status': 'Bot is running',
        'bot': 'Free Fire Likes Bot',
        'health': 'OK'
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
                markup.add(InlineKeyboardButton(f"🔗 Join {channel}", url=f"https://t.me/{channel.strip('@')}") )
            bot.reply_to(message, "📢 Channel Membership Required\nTo use this bot, you must join all our channels first", reply_markup=markup, parse_mode="Markdown")
            return
        if user_id not in like_tracker:
            like_tracker[user_id] = {"used": 0, "last_used": datetime.now(timezone.utc) - timedelta(days=1)}
        bot.reply_to(message, "✅ You're verified! Use /like to send likes.", parse_mode="Markdown")


    @bot.message_handler(commands=['like'])
    def handle_like(message):
        user_id = message.from_user.id
        chat_id = message.chat.id
        args = message.text.split()

        if message.chat.type == "private" and message.from_user.id != OWNER_ID:
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("🔗 Join Official Group", url=GROUP_JOIN_LINK))
            bot.reply_to(message, "❌ Sorry! command is not allowed here.\n\nJoin our official group:", reply_markup=markup)
            return

        if not is_user_in_channel(user_id):
            markup = InlineKeyboardMarkup()
            for channel in REQUIRED_CHANNELS:
                markup.add(InlineKeyboardButton(f"🔗 Join {channel}", url=f"https://t.me/{channel.strip('@')}") )
            bot.reply_to(message, "❌ You must join all our channels to use this command.", reply_markup=markup, parse_mode="Markdown")
            return

        if len(args) != 3:
            bot.reply_to(message, "❌ Format: `/like server_name uid`", parse_mode="Markdown")
            return

        region, uid = args[1], args[2]
        if not region.isalpha() or not uid.isdigit():
            bot.reply_to(message, "⚠️ Invalid input. Use: `/like server_name uid`", parse_mode="Markdown")
            return

        threading.Thread(target=process_like, args=(message, region, uid)).start()


    def process_like(message, region, uid):
        user_id = message.from_user.id
        now_utc = datetime.now(timezone.utc)
        usage = like_tracker.get(user_id, {"used": 0, "last_used": now_utc - timedelta(days=1)})

        last_used_date = usage["last_used"].date()
        current_date = now_utc.date()
        if current_date > last_used_date:
            usage["used"] = 0

        max_limit = get_user_limit(user_id)
        if usage["used"] >= max_limit:
            bot.reply_to(message, f"⚠️ You have exceeded your daily request limit!")
            return

        processing_msg = bot.reply_to(message, "⏳ Please wait... Sending likes...")
        response = call_api(region, uid)

        if "error" in response:
            try:
                bot.edit_message_text(
                    chat_id=processing_msg.chat.id,
                    message_id=processing_msg.message_id,
                    text=f"⚠️ API Error: {response['error']}"
                )
            except:
                bot.reply_to(message, f"⚠️ API Error: {response['error']}")
            return

        if not isinstance(response, dict) or response.get("status") != 1:
            try:
                bot.edit_message_text(
                    chat_id=processing_msg.chat.id,
                    message_id=processing_msg.message_id,
                    text="❌ UID has already received its max amount of likes. Limit reached for today, try another UID or after 24 hrs."
                )
            except:
                bot.reply_to(message, "⚠️ Invalid UID or unable to fetch data.")
            return

        try:
            player_uid = str(response.get("UID", uid)).strip()
            player_name = response.get("PlayerNickname", "N/A")
            region = str(response.get("Region", "N/A"))
            likes_before = str(response.get("LikesbeforeCommand", "N/A"))
            likes_after = str(response.get("LikesafterCommand", "N/A"))
            likes_given = str(response.get("LikesGivenByAPI", "N/A"))

            total_like = likes_after

            usage["used"] += 1
            usage["last_used"] = now_utc
            like_tracker[user_id] = usage
            
            response_text = f"""✅ *Request Processed Successfully*\n\n👤 *Name:* `{player_name}`\n🆔 *UID:* `{player_uid}`\n🌍 *Region:* `{region}`\n🤡 *Likes Before:* `{likes_before}`\n📈 *Likes Added:* `{likes_given}`\n🗿 *Total Likes Now:* `{total_like}`\n🔐 *Remaining Requests:* `{max_limit - usage['used']}`\n👑 *Credit:* @eaglehitsdiff"""

            markup = InlineKeyboardMarkup()

            bot.edit_message_text(
                chat_id=processing_msg.chat.id,
                message_id=processing_msg.message_id,
                text=response_text,
                reply_markup=markup,
                parse_mode="Markdown"
            )

        except Exception as e:
            logger.error(f"Error in process_like: {e}")
            bot.reply_to(message, "⚠️ Something went wrong. Likes Send, I can't decode your info.")


    @bot.message_handler(commands=["remain"])
    def owner_commands(message):
        if message.from_user.id != OWNER_ID:
            return

        args = message.text.split()
        cmd = args[0].lower()

        if cmd == "/remain":
            lines = ["📊 *Remaining Daily Requests Per User:*"]
            if not like_tracker:
                lines.append("❌ No users have used the bot yet today.")
            else:
                for uid, usage in like_tracker.items():
                    limit = get_user_limit(uid)
                    used = usage.get("used", 0)
                    limit_str = "Unlimited" if limit > 1000 else str(limit)
                    lines.append(f"👤 `{uid}` ➜ {used}/{limit_str}")
            bot.reply_to(message, "\n".join(lines), parse_mode="Markdown")


    @bot.message_handler(commands=['help'])
    def help_command(message):
        user_id = message.from_user.id

        if user_id == OWNER_ID:
            help_text = (
                f"📖 *Bot Commands:*\n\n"
                f"🧑💻 `/like <region> <uid>` - Send likes to Free Fire UID\n"
                f"🔰 `/start` - Start or verify\n"
                f"🆘 `/help` - Show this help menu\n\n"
                f"👑 *Owner Commands:*\n"
                f"📈 `/remain` - Show all users' usage & stats\n\n"
                f"📞 *Support:* {OWNER_USERNAME}"
            )
            bot.reply_to(message, help_text, parse_mode="Markdown")
            return

        if not is_user_in_channel(user_id):
            markup = InlineKeyboardMarkup()
            for channel in REQUIRED_CHANNELS:
                markup.add(InlineKeyboardButton(f"🔗 Join {channel}", url=f"https://t.me/{channel.strip('@')}") )
            bot.reply_to(message, "❌ You must join all our channels to use this command.", reply_markup=markup, parse_mode="Markdown")
            return

        help_text = (
            f"📖 *Bot Commands:*\n\n"
            f"🧑💻 `/like <region> <uid>` - Send likes to Free Fire UID\n"
            f"🔰 `/start` - Start or verify\n"
            f"🆘 `/help` - Show this help menu\n\n"
            f"📞 *Support:* {OWNER_USERNAME}\n"
            f"🔗 Join our channels for updates!"
        )
        bot.reply_to(message, help_text, parse_mode="Markdown")

# ===== START SERVER =====

if __name__ == "__main__":
    PORT = int(os.environ.get("PORT", 10000))
    print(f"SERVER STARTED ON PORT {PORT}")
    
    # Render is running this using gunicorn as: gunicorn main:app
    # But fallback simple polling is active if ran directly
    if BOT_TOKEN:
        # For development run directly:
        # app.run(host="0.0.0.0", port=PORT)
        # For Telegram Polling mode fallback:
        threading.Thread(target=lambda: bot.infinity_polling(), daemon=True).start()
        app.run(host="0.0.0.0", port=PORT)
    else:
        print("Bot token not provided. Flask server active in standby simulation mode.")
