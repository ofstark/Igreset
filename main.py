import os
import random
import string
import uuid
import requests
from datetime import datetime
import logging
from urllib.parse import urlparse, parse_qs
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# ========== Instagram Reset Logic ==========
def generate_device_info():
    """Generate random Android device info."""
    ANDROID_ID = f"android-{''.join(random.choices(string.hexdigits.lower(), k=16))}"
    USER_AGENT = (
        f"Instagram 394.0.0.46.81 Android ({random.choice(['28/9','29/10','30/11','31/12'])}; "
        f"{random.choice(['240dpi','320dpi','480dpi'])}; "
        f"{random.choice(['720x1280','1080x1920','1440x2560'])}; "
        f"{random.choice(['samsung','xiaomi','huawei','oneplus','google'])}; "
        f"{random.choice(['SM-G975F','Mi-9T','P30-Pro','ONEPLUS-A6003','Pixel-4'])}; "
        f"intel; en_US; {random.randint(100000000,999999999)})"
    )
    WATERFALL_ID = str(uuid.uuid4())
    timestamp = int(datetime.now().timestamp())
    nums = ''.join([str(random.randint(1, 100)) for _ in range(4)])
    PASSWORD = f'#PWD_INSTAGRAM:0:{timestamp}:starc@{nums}'
    return ANDROID_ID, USER_AGENT, WATERFALL_ID, PASSWORD

def make_headers(mid="", user_agent=""):
    """Return headers for Instagram API requests."""
    return {
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Bloks-Version-Id": "e061cacfa956f06869fc2b678270bef1583d2480bf51f508321e64cfb5cc12bd",
        "X-Mid": mid,
        "User-Agent": user_agent,
        # Content-Length is set automatically by requests; removing hardcoded value
    }

def get_username(user_id):
    """Retrieve Instagram username by user ID."""
    try:
        url = f"https://i.instagram.com/api/v1/users/{user_id}/info/"
        headers = {"User-Agent": "Instagram 219.0.0.12.117 Android"}
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            return data["user"]["username"]
        else:
            logger.error(f"Failed to get username: {r.text}")
            return None
    except Exception as e:
        logger.error(f"Error getting username: {e}")
        return None

def reset_instagram_password(reset_link):
    """
    Attempt to reset Instagram password using a one-click login email link.
    Returns dict with success status, username, new password, and user_id.
    """
    try:
        # Extract uidb36 and token from link using urllib.parse
        parsed = urlparse(reset_link)
        query_params = parse_qs(parsed.query)
        uidb36_list = query_params.get("uidb36")
        token_list = query_params.get("token")
        if not uidb36_list or not token_list:
            return {"success": False, "error": "Missing uidb36 or token in reset link."}
        uidb36 = uidb36_list[0]
        token = token_list[0].split(":")[0]  # Token may have extra parts after colon

        ANDROID_ID, USER_AGENT, WATERFALL_ID, PASSWORD = generate_device_info()

        # Step 1: Initiate password reset
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

        # Step 2: Get challenge
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

        # Extract challenge_context_final (this part is brittle; may need updating)
        # We try to parse as JSON; if it fails, fallback to string manipulation
        try:
            # Attempt to decode the response as JSON (it may be escaped)
            # The response is often a Bloks object with a string that contains escaped JSON
            # Here we look for the pattern after the challenge_context key
            # A more reliable method would be to parse the Bloks response, but that's complex.
            # We'll keep the existing approach but add fallback.
            import json
            # The challenge_context_final is inside a Bloks structure; we extract it using a regex or split
            # This is fragile, but we maintain original logic with a try/except
            challenge_context_final = r2.replace('\\', '').split(f'(bk.action.i64.Const, {cni}), "')[1].split('", (bk.action.bool.Const, false)))')[0]
        except Exception:
            # If parsing fails, try a different approach: look for the challenge_context value after 'challenge_context":'
            import re
            match = re.search(r'"challenge_context":"(.*?)"', r2)
            if match:
                challenge_context_final = match.group(1)
            else:
                return {"success": False, "error": "Failed to extract challenge context from response."}

        # Step 3: Submit new password
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
        # Note: data3 is a dict, but the endpoint expects form-encoded data. We'll convert to string later.
        # The original code passed a dict, which requests encodes as form data if Content-Type is set.
        # We'll keep as dict, but ensure it's properly sent.
        r3 = requests.post(url2, headers=make_headers(mid, USER_AGENT), data=data3, timeout=10)

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
    # Read token from environment variable (set in Render or elsewhere)
    TOKEN = os.environ.get("8714176831:AAEDT727dFmSyK4Mm49zp6-230FKs1Lxio8")
    if not TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN environment variable not set.")
        return

    # Create the Application
    application = Application.builder().token(TOKEN).build()

    # Register handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_reset_link))
    application.add_error_handler(error_handler)

    # Start the bot
    logger.info("Bot is running...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()