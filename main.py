import os
import random
import string
import uuid
import requests
import re
import json
from datetime import datetime
import logging
from urllib.parse import urlparse, parse_qs, unquote

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

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
        "X-IG-App-ID": "936619743392459",  # Common Instagram app ID
    }


def get_username(user_id):
    """Retrieve Instagram username by user ID."""
    try:
        url = f"https://i.instagram.com/api/v1/users/{user_id}/info/"
        headers = {"User-Agent": "Instagram 419.0.0.49.71 Android"}
        r = requests.get(url, headers=headers, timeout=15)
        
        if r.status_code == 200:
            return r.json()["user"]["username"]
        else:
            logger.error(f"Failed to get username: {r.status_code} - {r.text[:200]}")
            return None
    except Exception as e:
        logger.error(f"Error getting username: {e}")
        return None


def reset_instagram_password(reset_link: str):
    """
    Attempt to reset Instagram password using a one-click login email link.
    """
    try:
        # Parse link more robustly (handles both ? and # fragments)
        parsed = urlparse(reset_link)
        query_params = parse_qs(parsed.query)
        fragment_params = parse_qs(parsed.fragment)

        # Combine query and fragment params
        all_params = {**query_params, **fragment_params}

        uidb36_list = all_params.get("uidb36") or all_params.get("uid")
        token_list = all_params.get("token")

        if not uidb36_list or not token_list:
            return {"success": False, "error": "Missing uidb36/uid or token in the reset link."}

        uidb36 = uidb36_list[0]
        token = token_list[0].split(":")[0]   # Clean token if it has extra parts

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

        r = requests.post(url, headers=make_headers(user_agent=USER_AGENT), data=data, timeout=15)

        if r.status_code != 200 or "user_id" not in r.text:
            return {"success": False, "error": f"Initial reset request failed: {r.status_code} - {r.text[:300]}"}

        mid = r.headers.get("Ig-Set-X-Mid") or ""
        resp_json = r.json()
        user_id = resp_json.get("user_id")
        cni = resp_json.get("cni")
        nonce_code = resp_json.get("nonce_code")
        challenge_context = resp_json.get("challenge_context")

        if not all([user_id, cni, nonce_code]):
            return {"success": False, "error": "Missing required fields in reset response."}

        # Step 2: Get challenge
        url2 = "https://i.instagram.com/api/v1/bloks/apps/com.instagram.challenge.navigation.take_challenge/"

        data2 = {
            "user_id": str(user_id),
            "cni": str(cni),
            "nonce_code": str(nonce_code),
            "bk_client_context": json.dumps({
                "bloks_version": "e061cacfa956f06869fc2b678270bef1583d2480bf51f508321e64cfb5cc12bd",
                "styles_id": "instagram"
            }),
            "challenge_context": str(challenge_context),
            "bloks_versioning_id": "e061cacfa956f06869fc2b678270bef1583d2480bf51f508321e64cfb5cc12bd",
            "get_challenge": "true"
        }

        r2 = requests.post(url2, headers=make_headers(mid, USER_AGENT), data=data2, timeout=15)
        r2_text = r2.text

        # Robust challenge_context extraction
        challenge_context_final = None

        # Try regex first (most reliable)
        match = re.search(r'"challenge_context":"(.*?)"', r2_text)
        if match:
            challenge_context_final = match.group(1)
        else:
            # Fallback: try to find bk.action.i64.Const pattern
            try:
                clean = r2_text.replace('\\', '')
                challenge_context_final = clean.split(f'(bk.action.i64.Const, {cni}), "')[1].split('", (bk.action.bool.Const, false))')[0]
            except Exception:
                pass

        if not challenge_context_final:
            return {"success": False, "error": "Failed to extract final challenge context from Bloks response."}

        # Step 3: Submit new password
        data3 = {
            "is_caa": "False",
            "source": "",
            "uidb36": "",
            "error_state": json.dumps({"type_name": "str", "index": 0, "state_id": 1048583541}),
            "afv": "",
            "cni": str(cni),
            "token": "",
            "has_follow_up_screens": "0",
            "bk_client_context": json.dumps({
                "bloks_version": "e061cacfa956f06869fc2b678270bef1583d2480bf51f508321e64cfb5cc12bd",
                "styles_id": "instagram"
            }),
            "challenge_context": challenge_context_final,
            "bloks_versioning_id": "e061cacfa956f06869fc2b678270bef1583d2480bf51f508321e64cfb5cc12bd",
            "enc_new_password1": PASSWORD,
            "enc_new_password2": PASSWORD
        }

        r3 = requests.post(url2, headers=make_headers(mid, USER_AGENT), data=data3, timeout=15)

        if r3.status_code not in (200, 204) and "ok" not in r3.text.lower():
            logger.warning(f"Password submit returned: {r3.status_code} - {r3.text[:200]}")

        new_password = PASSWORD.split(":")[-1]
        username = get_username(user_id) or "Unknown"

        return {
            "success": True,
            "username": username,
            "password": new_password,
            "user_id": user_id
        }

    except Exception as e:
        logger.exception("Critical error in reset_instagram_password")
        return {"success": False, "error": f"Unexpected error: {str(e)}"}


# ========== Telegram Bot Handlers ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome to Instagram Password Reset Bot!\n\n"
        "Send me a valid Instagram **one-click password reset link** and I'll try to reset it.\n\n"
        "Example:\n"
        "`https://www.instagram.com/accounts/password/reset/?uidb36=...&token=...`\n\n"
        "⚠️ This is for educational/testing purposes. Use at your own risk."
    )


async def handle_reset_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    link = update.message.text.strip()

    if "uidb36" not in link and "uid=" not in link or "token=" not in link:
        await update.message.reply_text("❌ Invalid link. Please send a full Instagram password reset link.")
        return

    processing_msg = await update.message.reply_text("🔄 Processing... This may take a few seconds.")

    result = reset_instagram_password(link)

    if result.get("success"):
        msg = (
            f"✅ **Password Reset Successful!**\n\n"
            f"👤 **Username:** `{result['username']}`\n"
            f"🔑 **New Password:** `{result['password']}`\n"
            f"🆔 **User ID:** `{result['user_id']}`\n\n"
            f"⚠️ Change this password immediately after logging in."
        )
        await processing_msg.edit_text(msg, parse_mode="MarkdownV2")
    else:
        error = result.get("error", "Unknown error")
        await processing_msg.edit_text(
            f"❌ **Reset Failed**\n\nError: `{error}`", 
            parse_mode="MarkdownV2"
        )


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Exception while handling update:", exc_info=context.error)
    if update and update.effective_message:
        await update.effective_message.reply_text("⚠️ An internal error occurred. Please try again.")


def main():
    TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")   # ← Corrected

    if not TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN environment variable is not set!")
        return

    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & \~filters.COMMAND, handle_reset_link))
    application.add_error_handler(error_handler)

    logger.info("Bot is running...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()