#!/usr/bin/env python3
import os
import sys
import time
import random
import requests

# === Constants & File References ===
BASE_URL = "https://csp.infoblox.com"
EMAIL = os.getenv("INFOBLOX_EMAIL")
PASSWORD = os.getenv("INFOBLOX_PASSWORD")
EXTERNAL_ID_FILE = "external_id.txt"
USER_ID_FILE = "user_id.txt"

# === Step 0: Validate required inputs ===
if not all([EMAIL, PASSWORD]):
    sys.exit("❌ Missing required environment variables: INFOBLOX_EMAIL or INFOBLOX_PASSWORD")

if not (os.path.exists(EXTERNAL_ID_FILE) and os.path.exists(USER_ID_FILE)):
    sys.exit("❌ external_id.txt or user_id.txt not found. Run the user creation script first.")

with open(EXTERNAL_ID_FILE, "r") as f:
    external_id = f.read().strip()
with open(USER_ID_FILE, "r") as f:
    user_id = f.read().strip()

if not external_id or not user_id:
    sys.exit("❌ external_id.txt or user_id.txt is empty.")

# === Step 1: Authenticate ===
auth_url = f"{BASE_URL}/v2/session/users/sign_in"
auth_payload = {"email": EMAIL, "password": PASSWORD}
auth_resp = requests.post(auth_url, json=auth_payload)
auth_resp.raise_for_status()
jwt = auth_resp.json()["jwt"]
headers = {"Authorization": f"Bearer {jwt}", "Content-Type": "application/json"}
print("✅ Authenticated successfully.", flush=True)

# === Step 2: Switch to sandbox account (external_id) ===
switch_url = f"{BASE_URL}/v2/session/account_switch"
switch_payload = {"id": f"identity/accounts/{external_id}"}
switch_resp = requests.post(switch_url, headers=headers, json=switch_payload)
switch_resp.raise_for_status()
jwt = switch_resp.json()["jwt"]
headers["Authorization"] = f"Bearer {jwt}"
print(f"🔁 Switched to account (external_id): {external_id}", flush=True)

# === Step 3: Delete user with retries ===
endpoint = f"{BASE_URL}/v2/users/{user_id}"
max_retries = 5

for attempt in range(max_retries):
    try:
        print(f"🧹 DELETE {endpoint} (attempt {attempt + 1})", flush=True)
        resp = requests.delete(endpoint, headers=headers)

        if resp.status_code == 204:
            print(f"✅ User {user_id} deleted successfully.", flush=True)
            os.remove(USER_ID_FILE)
            print(f"📁 Removed {USER_ID_FILE}", flush=True)
            sys.exit(0)
        else:
            print(f"⚠️ Status {resp.status_code}: {resp.text}", flush=True)
    except Exception as e:
        print(f"⚠️ Error: {e}", flush=True)

    # Exponential backoff with jitter
    sleep_time = (2 ** attempt) + random.random()
    print(f"⏳ Retrying in {sleep_time:.1f}s...", flush=True)
    time.sleep(sleep_time)

sys.exit("❌ User deletion failed after multiple retries.")
