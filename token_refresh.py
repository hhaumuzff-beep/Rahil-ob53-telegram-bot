import os
import json
import time
import base64
import asyncio
import traceback
import requests
from github import Github
from datetime import datetime

# ========= CONFIG =========
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
BOT_TOKEN = os.getenv("BOT_TOKEN", "8812061930:AAHfNmIA9M14bS72PWP4bQ3a0_UYWp4abyI")

# 🔴 CRITICAL FIX: PyGithub expects 'username/repo', NOT the full URL
REPO_NAME = "eaglefacts82-hue/Free-Fire-Like-API"

TOKENS_FILE = "tokens.json"
UIDPASS_FILE = "uidpass.json"

OWNER_ID = 7790124713

REFRESH_DELAY = 600
ACCOUNT_DELAY = 8

# ========= CHECK =========
if not GITHUB_TOKEN:
    print("❌ GITHUB_TOKEN Missing! Token refresh system will fail. Set in environment variables.")
if not BOT_TOKEN:
    print("❌ BOT_TOKEN Missing! Cannot send Telegram alerts.")

# ========= GITHUB CONTEXT =========
try:
    github_client = Github(GITHUB_TOKEN)
    repo = github_client.get_repo(REPO_NAME)
    print("✅ Successfully connected to GitHub Repo:", REPO_NAME)
except Exception as e:
    print(f"❌ Failed to connect to GitHub Repo: {e}")
    repo = None

# ========= TELEGRAM MESSAGE =========
def send_message(text):
    if not BOT_TOKEN:
        return
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        data = {
            "chat_id": OWNER_ID,
            "text": text
        }
        res = requests.post(url, data=data, timeout=20)
        print(f"📡 Sent Telegram alert message: '{text}' [Status {res.status_code}]")
    except Exception as e:
        print("Telegram Alert Error:", e)

# ========= LOGS =========
def log(text):
    current = datetime.now().strftime("%H:%M:%S")
    print(f"[{current}] {text}")

# ========= READ FILE (WITH FALLBACK) =========
import ast

def read_json_file(filename):
    if not repo:
        log("Cannot read file, Github Repo not initialized.")
        return None, None
    try:
        file = repo.get_contents(filename)
        content = base64.b64decode(file.content).decode("utf-8")
        
        if filename.endswith(".py"):
            try:
                if "=" in content:
                    _, dict_str = content.split("=", 1)
                    parsed_dict = ast.literal_eval(dict_str.strip())
                    if isinstance(parsed_dict, dict):
                        return parsed_dict, file.sha
            except Exception as pe:
                log(f"Python dictionary parse error in {filename}: {pe}")
        
        json_data = json.loads(content)
        return json_data, file.sha
    except Exception as e:
        log(f"READ ERROR {filename}: {e}. Initializing empty structure.")
        return {}, None

# ========= UPDATE FILE (CRITICAL FIX FOR 409 CONFLICT) =========
def update_json_file(filename, data):
    if not repo:
        log("Failed to update: repo is undefined or offline.")
        return False
    try:
        if filename.endswith(".py"):
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
                message=f"🤖 AUTO UPDATE {filename} @ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
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

# ========= TOKEN VALIDITY CHECK =========
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
        payload_str = payload_bytes.decode('utf-8')
        payload = json.loads(payload_str)
        
        exp = payload.get("exp")
        if exp:
            if time.time() >= (exp - 300):
                return True
            return False
        return True
    except Exception:
        return True

# ========= TOKEN GENERATOR =========
def generate_token(uid, password):
    try:
        url = "https://ff.garena.com/api/login"
        payload = {
            "uid": uid,
            "password": password
        }
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        response = requests.post(url, json=payload, headers=headers, timeout=20)
        
        if response.status_code != 200:
            log(f"LOGIN FAILED FOR UID {uid}. HTTP Status: {response.status_code}")
            return None
            
        data = response.json()
        token = data.get("token") or data.get("jwt") or data.get("session_key")
        
        if token:
            return token
        return None
    except Exception as e:
        log(f"TOKEN GENERATOR EXCEPTION FOR UID {uid}: {e}")
        return None

# ========= MAIN REFRESH ROUTINE =========
async def auto_refresh():
    if not repo:
        log("Github Repo not connected. Auto refresh stopped.")
        return

    log("AUTO REFRESH ROUTINE BOOTED")

    global TOKENS_FILE, UIDPASS_FILE
    while True:
        try:
            tokens_data, tokens_sha = read_json_file("tokens.py")
            if tokens_sha is not None:
                TOKENS_FILE = "tokens.py"
                log("📌 Detected tokens.py as the file format on GitHub.")
            else:
                tokens_data, tokens_sha = read_json_file("tokens.json")
                TOKENS_FILE = "tokens.json"
                log("📌 Defaulted to tokens.json as file format.")

            uidpass_data, uidpass_sha = read_json_file("uidpass.py")
            if uidpass_sha is not None:
                UIDPASS_FILE = "uidpass.py"
                log("📌 Detected uidpass.py as the file format on GitHub.")
            else:
                uidpass_data, uidpass_sha = read_json_file("uidpass.json")
                UIDPASS_FILE = "uidpass.json"
                log("📌 Defaulted to uidpass.json as file format.")

            if tokens_data is None:
                tokens_data = {}
            
            if not uidpass_data:
                log("❌ uidpass.json loading failed! Please configure login credentials.")
                await asyncio.sleep(300)
                continue

            accounts_list = []
            if isinstance(uidpass_data, dict):
                log("🔄 uidpass.json detected as dictionary format. Converting to lists...")
                for key_uid, val_pass in uidpass_data.items():
                    accounts_list.append({"uid": str(key_uid).strip(), "password": str(val_pass).strip()})
            elif isinstance(uidpass_data, list):
                log("🔄 uidpass.json detected as standard list format.")
                for entry in uidpass_data:
                    if isinstance(entry, dict):
                        accounts_list.append({
                            "uid": str(entry.get("uid", "")).strip(),
                            "password": str(entry.get("password", "")).strip()
                        })
                    elif isinstance(entry, (list, tuple)) and len(entry) >= 2:
                        accounts_list.append({"uid": str(entry[0]).strip(), "password": str(entry[1]).strip()})

            total_accounts = len(accounts_list)
            if total_accounts == 0:
                log("⚠️ No accounts found within uidpass.json")
                await asyncio.sleep(300)
                continue

            success_count = 0
            failed_count = 0
            updated = False

            log(f"TOTAL INSTANCES TO REFRESH: {total_accounts}")
            
            for account in accounts_list:
                try:
                    uid = account.get("uid")
                    password = account.get("password")

                    if not uid or not password:
                        failed_count += 1
                        continue

                    cached_token = tokens_data.get(uid)
                    if cached_token and not is_token_expired(cached_token):
                        log(f"Token for UID {uid} is still valid. Skipping update.")
                        continue

                    log(f"Querying login token for UID: {uid}")
                    new_token = generate_token(uid, password)

                    if new_token:
                        tokens_data[uid] = new_token
                        updated = True
                        success_count += 1
                        log(f"Token dynamically processed: {uid}")
                    else:
                        failed_count += 1
                        log(f"Token generation failed: {uid}")

                    await asyncio.sleep(ACCOUNT_DELAY)

                except Exception as acc_err:
                    failed_count += 1
                    log(f"Local Account Loop Error: {acc_err}")

            if updated:
                save_success = update_json_file(TOKENS_FILE, tokens_data)
                if save_success:
                    send_message(f"{success_count} token updated")
                    log(f"SUCCESS: {success_count} tokens rewritten. Notification sent.")
                else:
                    log(f"❌ File Upload Failed (Success was {success_count})")
            else:
                log("⚠️ No credentials succeeded. Skip file upload.")

            log(f"Routine completed. Dormant for {REFRESH_DELAY} seconds.")
            await asyncio.sleep(REFRESH_DELAY)

        except Exception as e:
            error_msg = traceback.format_exc()
            log(f"CRASH LOGS:\n{error_msg}")
            await asyncio.sleep(300)
