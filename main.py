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
        if isinstance(data, dict):
            if "challenge_context" in data:
                return data["challenge_context"]
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
        clean = r2_text.replace('\\', '')
        pattern = f'(bk.action.i64.Const, {cni}), "'
        if pattern in clean:
            part = clean.split(pattern)[1]
            challenge = part.split('", (bk.action.bool.Const, false))')[0]
            return challenge
    except:
        pass

    return None

def reset_instagram_password(reset_link: str):
    """
    Attempt to reset Instagram password using a one-click login email link.
    Returns dict with success status, username, new password, and user_id.
    """
    try:
        parsed = urlparse(reset_link)
        query_params = parse_qs(parsed.query)
        fragment_params = parse_qs(parsed.fragment)
        all_params = {**query_params, **fragment_params}

        uidb36_list = all_params.get("uidb36") or all_params.get("uid")
        token_list = all_params.get("token")

        if not uidb36_list or not token_list:
            return {"success": False, "error": "Missing uidb36/uid or token in the reset link."}

        uidb36 = uidb36_list[0]
        token = token_list[0].split(":")[0]

        ANDROID_ID, USER_AGENT, WATERFALL_ID, PASSWORD = generate_device_info()

        url = "https://i.instagram.com/api/v1/accounts/password_reset/"
        data = {
            "source": "one_click_login_email",
            "uidb36": uidb36,
            "device_id": ANDROID_ID,
            "token": token,
            "waterfall_id": WATERFALL_ID
        }

        logger.info(f"Attempting password reset for uidb36: {uidb36}")
        r = requests.post(url, headers=make_headers(user_agent=USER_AGENT), data=data, timeout=15)

        if r.status_code != 200:
            return {"success": False, "error": f"Initial reset request failed with status {r.status_code}: {r.text[:300]}"}

        logger.info(f"Password reset response: {r.text[:500]}")

        resp_json = r.json()
        logger.debug(f"Parsed JSON: {resp_json}")

        # The response contains 'password_reset_nonce_code', not 'nonce_code'
        nonce_code = resp_json.get("password_reset_nonce_code")
        cni = resp_json.get("cni")
        # The 'user_id' field is a long string; numeric user_id is in the 'uri'
        user_id_str = resp_json.get("user_id")
        uri = resp_json.get("uri", "")
        # Extract numeric user_id from URI: /challenge/action/1234567890/...
        import re
        match = re.search(r'/action/(\d+)/', uri)
        if match:
            numeric_user_id = match.group(1)
        else:
            numeric_user_id = None

        if not all([numeric_user_id, cni, nonce_code]):
            logger.error(f"Missing fields. numeric_user_id={numeric_user_id}, cni={cni}, nonce_code={nonce_code}")
            logger.error(f"Full response: {resp_json}")
            return {"success": False, "error": "Missing required fields (cni/nonce_code) in reset response."}

        # Step 2: Get challenge
        url2 = "https://i.instagram.com/api/v1/bloks/apps/com.instagram.challenge.navigation.take_challenge/"
        data2 = {
            "user_id": str(numeric_user_id),
            "cni": str(cni),
            "nonce_code": str(nonce_code),
            "bk_client_context": json.dumps({
                "bloks_version": "e061cacfa956f06869fc2b678270bef1583d2480bf51f508321e64cfb5cc12bd",
                "styles_id": "instagram"
            }),
            "challenge_context": resp_json.get("challenge_context", ""),
            "bloks_versioning_id": "e061cacfa956f06869fc2b678270bef1583d2480bf51f508321e64cfb5cc12bd",
            "get_challenge": "true"
        }

        mid = r.headers.get("Ig-Set-X-Mid") or ""
        r2 = requests.post(url2, headers=make_headers(mid, USER_AGENT), data=data2, timeout=15)
        r2_text = r2.text

        challenge_context_final = extract_challenge_context(r2_text, cni)
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
        # Get username using the numeric user ID
        username = get_username(numeric_user_id, USER_AGENT) or "Unknown"

        return {
            "success": True,
            "username": username,
            "password": new_password,
            "user_id": numeric_user_id
        }

    except Exception as e:
        logger.exception("Critical error in reset_instagram_password")
        return {"success": False, "error": f"Unexpected error: {str(e)}"}

# ========== Telegram Bot Handlers ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
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

    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_reset_link))
    application.add_error_handler(error_handler)

    logger.info("Bot is running...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()