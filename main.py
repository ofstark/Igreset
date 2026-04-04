import os
import random
import string
import uuid
import requests
import re
import json
from datetime import datetime
import logging
from urllib.parse import urlparse, parse_qs
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ========== Helper Functions ==========

def escape_markdown_v2(text: str) -> str:
    """Escape special characters for Telegram MarkdownV2."""
    special_chars = r'_*[]()~`>#+-=|{}.!'
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    return text

# ========== Instagram Reset Logic ==========

def generate_device_info():
    """Generate random Android device info."""
    android_versions = ['28/9', '29/10', '30/11', '31/12', '34/14', '35/15']
    dpis = ['240dpi', '320dpi', '480dpi', '420dpi']
    resolutions = ['720x1280', '1080x1920', '1440x2560', '1080x2400']
    manufacturers = ['samsung', 'xiaomi', 'google', 'oneplus', 'motorola']
    models = ['SM-G975F', 'Mi-9T', 'Pixel-6', 'ONEPLUS-A6003', 'Pixel-7', 'motorola razr 40']

    ANDROID_ID = f"android-{''.join(random.choices(string.hexdigits.lower(), k=16))}"
    USER_AGENT = (
        f"Instagram {random.choice(['394.0.0.46.81', '419.0.0.49.71', '422.0.0.XX.XX'])} "
        f"Android ({random.choice(android_versions)}; "
        f"{random.choice(dpis)}; "
        f"{random.choice(resolutions)}; "
        f"{random.choice(manufacturers)}; "
        f"{random.choice(models)}; "
        f"en_US; {random.randint(100000000, 999999999)})"
    )
    WATERFALL_ID = str(uuid.uuid4())
    timestamp = int(datetime.now().timestamp())
    nums = ''.join([str(random.randint(1, 99)) for _ in range(4)])
    PASSWORD = f'#PWD_INSTAGRAM:0:{timestamp}:starc@{nums}'
    return ANDROID_ID, USER_AGENT, WATERFALL_ID, PASSWORD

def make_headers(mid="", user_agent=""):
    """Return headers for Instagram API requests."""
    return {
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Bloks-Version-Id": "e061cacfa956f06869fc2b678270bef1583d2480bf51f508321e64cfb5cc12bd",
        "X-Mid": mid,
        "User-Agent": user_agent,
        "Accept": "*/*",
        "X-IG-App-ID": "936619743392459",
    }

def get_username(user_id: str, user_agent: str) -> str:
    """Retrieve Instagram username by user ID using a provided user agent."""
    try:
        url = f"https://i.instagram.com/api/v1/users/{user_id}/info/"
        headers = {"User-Agent": user_agent}
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code == 200:
            return r.json()["user"]["username"]
        else:
            logger.error(f"Failed to get username: {r.status_code} - {r.text[:200]}")
            return None
    except Exception as e:
        logger.error(f"Error getting username: {e}")
        return None

def extract_challenge_context(r2_text: str, cni: str) -> str:
    """Extract challenge_context from the Bloks response using multiple fallbacks."""
    # Try to parse as JSON if the response is a JSON string
    try:
        data = json.loads(r2_text)
        # Look for challenge_context in the structure (may be nested)
        if isinstance(data, dict):
            if "challenge_context" in data:
                return data["challenge_context"]
            # Some responses have it inside a "data" field
            if "data" in data and isinstance(data["data"], dict) and "challenge_context" in data["data"]:
                return data["data"]["challenge_context"]
    except:
        pass

    # Try regex to find the challenge_context string
    match = re.search(r'"challenge_context":"(.*?)"', r2_text)
    if match:
        return match.group(1)

    # Fallback: try to use the original splitting method (brittle)
    try:
        # Remove escape characters
        clean = r2_text.replace('\\', '')
        # Extract based on known pattern
        pattern = f'(bk.action.i64.Const, {cni}), "'
        if pattern in clean:
            part = clean.split(pattern)[1]
            challenge = part.split('", (bk.action.bool.Const, false))')[0]
            return challenge
    except:
        pass

    return None

        "Send here a valid Instagram password reset link and I'll try to reset it ✌🏻.\n\n made by ~@ofstark"
# ========== Telegram Bot Handlers ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Welcome to STARK Instagram Password Reset Bot!\n\n"
        "Send here a valid Instagram password reset link and I'll try to reset it ✌🏻.\n\n made by ~@ofstark"
    )

async def handle_reset_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    link = update.message.text.strip()

    if "uidb36" not in link and "uid=" not in link or "token=" not in link:
        await update.message.reply_text("❌ Invalid link. Please send a full Instagram password reset link.")
        return

    processing_msg = await update.message.reply_text("🔄 Processing... This may take a few seconds.")

    result = reset_instagram_password(link)

    if result.get("success"):
        # Escape special characters for MarkdownV2
        username_esc = escape_markdown_v2(result['username'])
        password_esc = escape_markdown_v2(result['password'])
        user_id_esc = escape_markdown_v2(str(result['user_id']))

        msg = (
            f"✅ **Password Reset Successful!**\n\n"
            f"👤 **Username:** `{username_esc}`\n"
            f"🔑 **New Password:** `{password_esc}`\n"
            f"🆔 **User ID:** `{user_id_esc}`\n\n"
            f"⚠️ Change this password immediately after logging in."
        )
        await processing_msg.edit_text(msg, parse_mode="MarkdownV2")
    else:
        error_esc = escape_markdown_v2(result.get("error", "Unknown error"))
        await processing_msg.edit_text(
            f"❌ **Reset Failed**\n\nError: `{error_esc}`",
            parse_mode="MarkdownV2"
        )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Exception while handling update:", exc_info=context.error)
    if update and update.effective_message:
        await update.effective_message.reply_text("⚠️ An internal error occurred. Please try again later.")

def main():
    TOKEN = "8714176831:AAEDT727dFmSyK4Mm49zp6-230FKs1Lxio8"

    if not TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN environment variable is not set!")
        return

    # Build the application with the token
    application = Application.builder().token(TOKEN).build()

    # Register handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_reset_link))
    application.add_error_handler(error_handler)

    logger.info("Bot is running...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()