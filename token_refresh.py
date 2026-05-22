import os
import json
import time
import base64
import ast
import asyncio
import traceback
import requests
from github import Github
from datetime import datetime

# ==========================================
#      DYNAMIC AUTO-REFRESH REPO SYSTEM      
# ==========================================

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
BOT_TOKEN = os.getenv("BOT_TOKEN")

REPO_NAME = "eaglefacts82-hue/Free-Fire-Like-API"

# Default placeholders, auto-overwritten by detection in loop
TOKENS_FILE = "tokens.py"
UIDPASS_FILE = "uidpass.py"

OWNER_ID = 7118852390
REFRESH_DELAY = 600      # 10 minute check interval
ACCOUNT_DELAY = 8

if not GITHUB_TOKEN:
    print("❌ GITHUB_TOKEN Missing! Please configure your token in secrets.")
if not BOT_TOKEN:
    print("❌ BOT_TOKEN Missing! Cannot send alerts.")

try:
    github_client = Github(GITHUB_TOKEN)
    repo = github_client.get_repo(REPO_NAME)
    print("✅ Successfully connected to GitHub Repo:", REPO_NAME)
except Exception as e:
    print(f"❌ Failed to connect to GitHub Repo: {e}")
    repo = None

def send_message(text):
    if not BOT_TOKEN:
        return
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        data = {"chat_id": OWNER_ID, "text": text}
        requests.post(url, data=data, timeout=20)
    except Exception as e:
        print("Telegram sending error:", e)

def log(text):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {text}")

# ========= READ FILE (WITH AUTO DICT DECODING) =========
def read_json_file(filename):
    if not repo:
        log("Cannot read file, Github Repo not initialized.")
        return None, None
    try:
        file = repo.get_contents(filename)
        content = base64.b64decode(file.content).decode("utf-8")
        
        # Safe evaluation parsing custom python dictionary files (.py variables)
        if filename.endswith(".py"):
            try:
                if "=" in content:
                    _, dict_str = content.split("=", 1)
                    parsed_dict = ast.literal_eval(dict_str.strip())
                    if isinstance(parsed_dict, dict):
                        return parsed_dict, file.sha
            except Exception as pe:
                log(f"Python dict parsing error in {filename}: {pe}")
        
        # Fallback to standard JSON parsing
        json_data = json.loads(content)
        return json_data, file.sha
    except Exception as e:
        log(f"Reading {filename} failed or absent: {e}")
        return None, None

# ========= WRITE FILE (WITH FORMAT RETENTION) =========
def update_json_file(filename, data):
    if not repo:
        log("Failed to update: repo is undefined.")
        return False
    try:
        if filename.endswith(".py"):
            # Format cleanly as standard executable Python dict file
            var_name = "tokens" if "token" in filename.lower() else "accounts"
            new_content = f"{var_name} = {json.dumps(data, indent=4)}\n"
        else:
            new_content = json.dumps(data, indent=4)
        
        try:
            file_meta = repo.get_contents(filename)
            latest_sha = file_meta.sha
        except Exception:
            latest_sha = None

        if latest_sha:
            repo.update_file(
                path=filename,
                message=f"🤖 AUTO UPDATE {filename} @ {datetime.now().strftime('%H:%M:%S')}",
                content=new_content,
                sha=latest_sha
            )
            log(f"✅ Successfully updated {filename} on GitHub repo.")
        else:
            repo.create_file(
                path=filename,
                message=f"🤖 AUTO INITIALIZE {filename}",
                content=new_content
            )
            log(f"🌱 Created brand new {filename} file in GitHub repo.")
        return True
    except Exception as e:
        log(f"UPDATE ERROR {filename}: {e}")
        return False

# ========= JWT REFRESH TIMEOUT CHECKS =========
def is_token_expired(token):
    if not token or not isinstance(token, str):
        return True
    try:
        parts = token.split('.')
        if len(parts) != 3:
            return True
        payload_b64 = parts[1]
        rem = len(payload_b64) % 4
        if rem > 0:
            payload_b64 += '=' * (4 - rem)
            
        payload_bytes = base64.b64decode(payload_b64)
        payload = json.loads(payload_bytes.decode('utf-8'))
        
        exp = payload.get("exp")
        if exp:
            # Check if token is expired, or will expire in less than 5 minutes
            if time.time() >= (exp - 300):
                return True
            return False
        return True
    except Exception:
        return True  # Fallback to regenerate just to be resilient

def generate_token(uid, password):
    try:
        url = "https://ff.garena.com/api/login"
        payload = {"uid": uid, "password": password}
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Content-Type": "application/json"
        }
        res = requests.post(url, json=payload, headers=headers, timeout=20)
        if res.status_code == 200:
            data = res.json()
            return data.get("token") or data.get("jwt") or data.get("session_key")
        return None
    except Exception as e:
        log(f"Failed token login generation for UID {uid}: {e}")
        return None

# ========= BOOT MAIN REFRESH ROUTINE =========
async def auto_refresh():
    if not repo:
        log("Github Repo not connected. Auto refresh bypassed.")
        return

    log("AUTO REFRESH ROUTINE ACTIVE [10-MIN SCANNER]")
    global TOKENS_FILE, UIDPASS_FILE

    while True:
        try:
            # 1. Dynamic format lookup
            tokens_data, tokens_sha = read_json_file("tokens.py")
            if tokens_sha is not None:
                TOKENS_FILE = "tokens.py"
            else:
                tokens_data, tokens_sha = read_json_file("tokens.json")
                TOKENS_FILE = "tokens.json"

            if tokens_data is None:
                tokens_data = {}

            uidpass_data, uidpass_sha = read_json_file("uidpass.py")
            if uidpass_sha is not None:
                UIDPASS_FILE = "uidpass.py"
            else:
                uidpass_data, uidpass_sha = read_json_file("uidpass.json")
                UIDPASS_FILE = "uidpass.json"

            if not uidpass_data:
                log("❌ Could not pull or parse uidpass credentials.")
                await asyncio.sleep(300)
                continue

            # Parse credentials securely
            accounts_list = []
            if isinstance(uidpass_data, dict):
                for key_uid, val_pass in uidpass_data.items():
                    accounts_list.append({"uid": str(key_uid).strip(), "password": str(val_pass).strip()})
            elif isinstance(uidpass_data, list):
                for entry in uidpass_data:
                    if isinstance(entry, dict):
                        accounts_list.append({
                            "uid": str(entry.get("uid", "")).strip(),
                            "password": str(entry.get("password", "")).strip()
                        })

            total_accounts = len(accounts_list)
            if total_accounts == 0:
                await asyncio.sleep(300)
                continue

            success_count = 0
            updated = False
            
            for account in accounts_list:
                uid = account.get("uid")
                password = account.get("password")
                if not uid or not password:
                    continue

                # ⚠️ Expired checking: Checks if JWT token has expired or is invalid
                cached_token = tokens_data.get(uid)
                if cached_token and not is_token_expired(cached_token):
                    log(f"Token for UID {uid} is still valid. Skipping update.")
                    continue

                log(f"Generating new token for UID: {uid}")
                new_token = generate_token(uid, password)
                if new_token:
                    tokens_data[uid] = new_token
                    updated = True
                    success_count += 1
                await asyncio.sleep(ACCOUNT_DELAY)

            if updated:
                if update_json_file(TOKENS_FILE, tokens_data):
                    send_message(f"✅ {success_count} Token Updated in repo successfully!")

            log(f"Scan complete. Sleeping for {REFRESH_DELAY} seconds.")
            await asyncio.sleep(REFRESH_DELAY)

        except Exception as e:
            log(f"General crash error: {e}")
            await asyncio.sleep(300)

if __name__ == "__main__":
    asyncio.run(auto_refresh())
