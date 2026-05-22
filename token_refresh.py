import os
import json
import time
import base64
import asyncio
import traceback
import requests
from github import Github
from datetime import datetime

# ╔══════════════════════════════════════╗
# ║      AUTO TOKEN REFRESH SYSTEM       ║
# ║             BY ANKIT                 ║
# ╚══════════════════════════════════════╝

# ========= CONFIG =========

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
BOT_TOKEN = os.getenv("BOT_TOKEN")

# 🔴 CRITICAL FIX: PyGithub expects 'username/repo', NOT the full URL
REPO_NAME = "eaglefacts82-hue/Free-Fire-Like-API"

TOKENS_FILE = "tokens.json"
UIDPASS_FILE = "uidpass.json"

OWNER_ID = 7118852390

REFRESH_DELAY = 3600
ACCOUNT_DELAY = 8

# ========= CHECK =========

if not GITHUB_TOKEN:
    print("❌ GITHUB_TOKEN Missing! Token refresh system will fail.")
if not BOT_TOKEN:
    print("❌ BOT_TOKEN Missing! Cannot send Telegram alerts.")

# ========= GITHUB =========

try:
    github_client = Github(GITHUB_TOKEN)
    repo = github_client.get_repo(REPO_NAME)
except Exception as e:
    print(f"❌ Failed to connect to GitHub Repo: {e}")
    repo = None

# ========= TELEGRAM =========

def send_message(text):
    if not BOT_TOKEN:
        return
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        data = {
            "chat_id": OWNER_ID,
            "text": text
        }
        requests.post(url, data=data, timeout=20)
    except Exception as e:
        print("Telegram Error:", e)

# ========= LOG =========

def log(text):
    current = datetime.now().strftime("%H:%M:%S")
    print(f"[{current}] {text}")

# ========= READ FILE =========

def read_json_file(filename):
    if not repo:
        log("Cannot read file, Github Repo not initialized.")
        return None, None
    try:
        file = repo.get_contents(filename)
        content = base64.b64decode(file.content).decode("utf-8")
        json_data = json.loads(content)
        return json_data, file.sha
    except Exception as e:
        log(f"READ ERROR {filename}: {e}")
        return None, None

# ========= UPDATE FILE =========

def update_json_file(filename, data, sha):
    if not repo:
        return False
    try:
        new_content = json.dumps(data, indent=4)
        repo.update_file(
            path=filename,
            message=f"AUTO UPDATE {filename}",
            content=new_content,
            sha=sha
        )
        return True
    except Exception as e:
        log(f"UPDATE ERROR {filename}: {e}")
        return False

# ========= TOKEN API =========

def generate_token(uid, password):
    try:
        url = "https://ff.garena.com/api/login"
        payload = {
            "uid": uid,
            "password": password
        }
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Content-Type": "application/json"
        }
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        
        if response.status_code != 200:
            log(f"LOGIN FAILED STATUS: {response.status_code}")
            return None
            
        data = response.json()
        token = data.get("token")
        
        if token:
            return token
        return None
    except Exception as e:
        log(f"TOKEN ERROR: {e}")
        return None

# ========= MAIN REFRESH =========

async def auto_refresh():
    if not repo:
        log("Github Repo not connected. Auto refresh stopped.")
        return

    send_message("✅ AUTO TOKEN REFRESH SYSTEM STARTED")
    log("AUTO REFRESH STARTED")

    while True:
        try:
            tokens_data, tokens_sha = read_json_file(TOKENS_FILE)
            uidpass_data, uidpass_sha = read_json_file(UIDPASS_FILE)

            if not tokens_data:
                send_message("❌ tokens.json load failed")
                await asyncio.sleep(300)
                continue

            if not uidpass_data:
                send_message("❌ uidpass.json load failed")
                await asyncio.sleep(300)
                continue

            total_accounts = len(uidpass_data)
            success_count = 0
            failed_count = 0

            log(f"TOTAL ACCOUNT: {total_accounts}")
            send_message(f"🔄 TOKEN REFRESH STARTED\n\nTOTAL ACCOUNT: {total_accounts}")

            updated = False

            for account in uidpass_data:
                try:
                    uid = str(account.get("uid", "")).strip()
                    password = str(account.get("password", "")).strip()

                    if not uid or not password:
                        failed_count += 1
                        continue

                    log(f"REFRESHING UID: {uid}")
                    new_token = generate_token(uid, password)

                    if new_token:
                        tokens_data[uid] = new_token
                        updated = True
                        success_count += 1
                        log(f"TOKEN UPDATED: {uid}")
                    else:
                        failed_count += 1
                        log(f"TOKEN FAILED: {uid}")

                    await asyncio.sleep(ACCOUNT_DELAY)

                except Exception as acc_error:
                    failed_count += 1
                    log(f"ACCOUNT ERROR: {acc_error}")

            # ===== SAVE TOKENS =====
            if updated:
                save = update_json_file(TOKENS_FILE, tokens_data, tokens_sha)
                if save:
                    send_message(f"✅ TOKENS.JSON UPDATED\n\nSUCCESS: {success_count}\nFAILED: {failed_count}")
                    log("TOKENS.JSON UPDATED")
                else:
                    send_message("❌ TOKENS.JSON UPDATE FAILED")
            else:
                send_message("⚠️ NO TOKEN UPDATED")

            # ===== WAIT =====
            log(f"WAITING {REFRESH_DELAY} SECONDS...")
            await asyncio.sleep(REFRESH_DELAY)

        except Exception as e:
            error_text = traceback.format_exc()
            log(error_text)
            send_message(f"❌ AUTO REFRESH CRASHED\n\n{str(e)}")
            await asyncio.sleep(300)