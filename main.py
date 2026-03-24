import os
import random
import string
import uuid
import requests
from datetime import datetime
import base64
import json
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# ========== Instagram Reset Logic ==========
def generate_device_info():
    ANDROID_ID = f"android-{''.join(random.choices(string.hexdigits.lower(), k=16))}"
    USER_AGENT = f"Instagram 394.0.0.46.81 Android ({random.choice(['28/9','29/10','30/11','31/12'])}; {random.choice(['240dpi','320dpi','480dpi'])}; {random.choice(['720x1280','1080x1920','1440x2560'])}; {random.choice(['samsung','xiaomi','huawei','oneplus','google'])}; {random.choice(['SM-G975F','Mi-9T','P30-Pro','ONEPLUS-A6003','Pixel-4'])}; intel; en_US; {random.randint(100000000,999999999)})"
    WATERFALL_ID = str(uuid.uuid4())
    timestamp = int(datetime.now().timestamp())
    nums = ''.join([str(random.randint(1, 100)) for _ in range(4)])
    PASSWORD = f'#PWD_INSTAGRAM:0:{timestamp}:starc@{nums}'
    return ANDROID_ID, USER_AGENT, WATERFALL_ID, PASSWORD

def make_headers(mid="", user_agent=""):
    return {
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Bloks-Version-Id": "e061cacfa956f06869fc2b678270bef1583d2480bf51f508321e64cfb5cc12bd",
        "X-Mid": mid,
        "User-Agent": user_agent,
        "Content-Length": "9481"
    }

def get_username(user_id):
    try:
        url = f"https://i.instagram.com/api/v1/users/{user_id}/info/"
        headers = {"User-Agent": "Instagram 219.0.0.12.117 Android"}
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            return r.json()["user"]["username"]
        else:
            logger.error(f"Failed to get username: {r.text}")
            return None
    except Exception as e:
        logger.error(f"Error getting username: {e}")
        return None

def reset_instagram_password(reset_link):
    try:
        ANDROID_ID, USER_AGENT, WATERFALL_ID, PASSWORD = generate_device_info()
        # Extract uidb36 and token from link
        uidb36 = reset_link.split("uidb36=")[1].split("&token=")[0]
        token = reset_link.split("&token=")[1].split(":")[0]

        url = "https://i.instagram.com/api/v1/accounts/password_reset/"
        data = {
            "source": "one_click_login_email",
            "uidb36": uidb36,
            "device_id": ANDROID_ID,
            "token": token,
            "waterfall_id": WATERFALL_ID
        }
        r = requests.post(url, headers=make_headers(user_agent=USER_AGENT), data=data, timeout=10)

        if "user_id" not in r.text:
            return {"success": False, "error": f"Reset request failed: {r.text}"}

        mid = r.headers.get("Ig-Set-X-Mid")
        resp_json = r.json()
        user_id = resp_json.get("user_id")
        cni = resp_json.get("cni")
        nonce_code = resp_json.get("nonce_code")
        challenge_context = resp_json.get("challenge_context")

        url2 = "https://i.instagram.com/api/v1/bloks/apps/com.instagram.challenge.navigation.take_challenge/"
        data2 = {
            "user_id": str(user_id),
            "cni": str(cni),
            "nonce_code": str(nonce_code),
            "bk_client_context": '{"bloks_version":"e061cacfa956f06869fc2b678270bef1583d2480bf51f508321e64cfb5cc12bd","styles_id":"instagram"}',
            "challenge_context": str(challenge_context),
            "bloks_versioning_id": "e061cacfa956f06869fc2b678270bef1583d2480bf51f508321e64cfb5cc12bd",
            "get_challenge": "true"
        }
        r2 = requests.post(url2, headers=make_headers(mid, USER_AGENT), data=data2, timeout=10).text

        # Extract challenge_context_final (messy but works)
        challenge_context_final = r2.replace('\\', '').split(f'(bk.action.i64.Const, {cni}), "')[1].split('", (bk.action.bool.Const, false)))')[0]

        data3 = {
            "is_caa": "False",
            "source": "",
            "uidb36": "",
            "error_state": {"type_name":"str","index":0,"state_id":1048583541},
            "afv": "",
            "cni": str(cni),
            "token": "",
            "has_follow_up_screens": "0",
            "bk_client_context": {"bloks_version":"e061cacfa956f06869fc2b678270bef1583d2480bf51f508321e64cfb5cc12bd","styles_id":"instagram"},
            "challenge_context": challenge_context_final,
            "bloks_versioning_id": "e061cacfa956f06869fc2b678270bef1583d2480bf51f508321e64cfb5cc12bd",
            "enc_new_password1": PASSWORD,
            "enc_new_password2": PASSWORD
        }
        requests.post(url2, headers=make_headers(mid, USER_AGENT), data=data3, timeout=10)

        new_password = PASSWORD.split(":")[-1]
        username = get_username(user_id)

        return {
            "success": True,
            "username": username if username else "Unknown",
            "password": new_password,
            "user_id": user_id
        }
    except Exception as e:
        logger.exception("Error in reset_instagram_password")
        return {"success": False, "error": str(e)}

# ========== Telegram Bot Handlers ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a welcome message when /start is issued."""
    await update.message.reply_text(
        "👋 Welcome to Instagram Password Reset Bot!\n\n"
        "Send me a valid Instagram password reset link (one-click login email link) and I'll attempt to reset the password and give you the new credentials.\n\n"
        "Example link format:\n"
        "https://www.instagram.com/accounts/password/reset/?uidb36=...&token=...\n\n"
        "⚠️ Use at your own risk."
    )

async def handle_reset_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process the reset link sent by the user."""
    link = update.message.text.strip()
    # Basic validation: must contain "uidb36" and "token"
    if "uidb36=" not in link or "token=" not in link:
        await update.message.reply_text("❌ Invalid reset link. Please send a complete Instagram password reset link.")
        return

    # Let user know we're processing
    processing_msg = await update.message.reply_text("🔄 Processing your request, please wait...")

    # Perform reset
    result = reset_instagram_password(link)

    if result.get("success"):
        # Format success message
        msg = (
            f"✅ **Password Reset Successful!**\n\n"
            f"👤 **Username:** `{result['username']}`\n"
            f"🔑 **New Password:** `{result['password']}`\n"
            f"🆔 **User ID:** `{result['user_id']}`\n\n"
            f"⚠️ Keep this information safe."
        )
        await processing_msg.edit_text(msg, parse_mode="Markdown")
    else:
        error_msg = result.get("error", "Unknown error occurred.")
        await processing_msg.edit_text(f"❌ **Failed to reset password.**\n\nError: `{error_msg}`", parse_mode="Markdown")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Log errors and notify user."""
    logger.error(msg="Exception while handling update:", exc_info=context.error)
    if update and update.effective_message:
        await update.effective_message.reply_text("⚠️ An internal error occurred. Please try again later.")

def main():
    # Read token from environment variable (set in Render)
    TOKEN = os.environ.get("8714176831:AAEDT727dFmSyK4Mm49zp6-230FKs1Lxio8")
    if not TOKEN:
        # Log error and exit – no interactive prompt!
        print("Error: TELEGRAM_BOT_TOKEN environment variable not set.")
        return

    # Create the Application
    application = Application.builder().token(TOKEN).build()

    # Register handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_reset_link))
    application.add_error_handler(error_handler)

    # Start the bot
    print("Bot is running...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
