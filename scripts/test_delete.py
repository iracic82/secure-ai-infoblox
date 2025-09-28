import os
import sys
import time
import random
import requests
import uuid
from sandbox_api import SandboxAccountAPI

# ----------------------------------
# Configuration
# ----------------------------------
BASE_URL = "https://csp.infoblox.com/v2"
TOKEN = os.environ.get("Infoblox_Token")
SANDBOX_ID_FILE = "sandbox_id.txt"

# Startup jitter (avoid host collisions)
time.sleep(random.uniform(1, 10))

# --- Read sandbox ID ---
try:
    with open(SANDBOX_ID_FILE, "r") as f:
        sandbox_id = f.read().strip()
except FileNotFoundError:
    print(f"❌ {SANDBOX_ID_FILE} not found. Run create_sandbox.py first.", flush=True)
    sys.exit(1)

if not sandbox_id:
    print("❌ Empty sandbox ID. Aborting.", flush=True)
    sys.exit(1)

api = SandboxAccountAPI(base_url=BASE_URL, token=TOKEN)
endpoint = f"{api.base_url}/sandbox/accounts/{sandbox_id}"

# --- Retry loop for deletion ---
max_retries = 5
retryable_statuses = {502, 503, 504}

# Add idempotency header (safe for delete)
headers = {**api._headers(), "X-Request-ID": str(uuid.uuid4())}

for attempt in range(max_retries):
    try:
        print(f"🔗 DELETE {endpoint} (attempt {attempt+1})", flush=True)
        resp = requests.delete(endpoint, headers=headers, timeout=(5, 20))

        if resp.status_code in (200, 204):
            print(f"✅ Sandbox {sandbox_id} deleted.", flush=True)
            try:
                os.remove(SANDBOX_ID_FILE)
                print(f"📁 Removed {SANDBOX_ID_FILE}", flush=True)
            except OSError as e:
                print(f"⚠️ Could not remove {SANDBOX_ID_FILE}: {e}", flush=True)
            sys.exit(0)

        elif resp.status_code in retryable_statuses:
            print(f"⚠️ Retryable error {resp.status_code}: {resp.text}", flush=True)
        else:
            print(f"❌ Non-retryable error {resp.status_code}: {resp.text}", flush=True)
            sys.exit(1)

    except Exception as e:
        print(f"⚠️ Exception on attempt {attempt+1}: {e}", flush=True)

    # Full jitter backoff, capped
    sleep_time = min(random.uniform(0, 2 ** attempt), 30)
    time.sleep(sleep_time)

print("❌ Sandbox deletion failed after retries. Manual cleanup required.", flush=True)
sys.exit(1)
