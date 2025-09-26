import os
import sys
import time
import random
import requests

BASE_URL = "https://csp.infoblox.com/v2"
TOKEN = os.environ.get("Infoblox_Token")
USER_ID_FILE = "user_id.txt"

if not TOKEN:
    print("❌ Missing Infoblox_Token.", flush=True)
    sys.exit(1)

# --- Read user ID ---
try:
    with open(USER_ID_FILE, "r") as f:
        user_id = f.read().strip()
except FileNotFoundError:
    print(f"❌ {USER_ID_FILE} not found. Run create_user.py first.", flush=True)
    sys.exit(1)

if not user_id:
    print("❌ User ID file empty.", flush=True)
    sys.exit(1)

endpoint = f"{BASE_URL}/users/{user_id}"
headers = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"}

# --- Retry loop for deletion ---
max_retries = 5
for attempt in range(max_retries):
    try:
        print(f"🔗 DELETE {endpoint} (attempt {attempt+1})", flush=True)
        resp = requests.delete(endpoint, headers=headers)
        if resp.status_code == 204:
            print(f"✅ User {user_id} deleted.", flush=True)
            try:
                os.remove(USER_ID_FILE)
                print(f"📁 Removed {USER_ID_FILE}", flush=True)
            except OSError as e:
                print(f"⚠️ Could not remove {USER_ID_FILE}: {e}", flush=True)
            sys.exit(0)
        else:
            print(f"⚠️ Status {resp.status_code}: {resp.text}", flush=True)
    except Exception as e:
        print(f"⚠️ Error: {e}", flush=True)
    time.sleep((2**attempt) + random.random())

print("❌ User deletion failed after retries. Manual cleanup required.", flush=True)
sys.exit(1)
