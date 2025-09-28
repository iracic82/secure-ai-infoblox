import os
import sys
import time
import random
import uuid
import requests
from sandbox_api import SandboxAccountAPI

# ----------------------------------
# Configuration
# ----------------------------------
BASE_URL = "https://csp.infoblox.com/v2"
TOKEN = os.environ.get("Infoblox_Token")
TEAM_ID = os.environ.get("INSTRUQT_PARTICIPANT_ID", "default-team")
SANDBOX_ID_FILE = "sandbox_id.txt"
EXTERNAL_ID_FILE = "external_id.txt"

# Startup jitter (avoid host collisions)
time.sleep(random.uniform(1, 15))

# Request body for sandbox creation
sandbox_request_body = {
    "name": TEAM_ID,
    "description": "Created via Python script Instruqt Demo",
    "state": "active",
    "tags": {"instruqt": "igor"},
    "admin_user": {
        "email": os.environ.get("INFOBLOX_EMAIL"),
        "name": TEAM_ID,
    },
}

# ----------------------------------
# API client initialization
# ----------------------------------
api = SandboxAccountAPI(base_url=BASE_URL, token=TOKEN)

# ----------------------------------
# Retry logic
# ----------------------------------
max_retries = 5
retryable_statuses = {502, 503, 504}

# Build headers with idempotency key
headers = {**api._headers(), "X-Request-ID": str(uuid.uuid4())}

create_response = None
for attempt in range(max_retries):
    try:
        resp = requests.post(
            f"{BASE_URL}/sandbox/accounts",
            json=sandbox_request_body,
            headers=headers,
            timeout=(5, 20),  # connect=5s, read=20s
        )

        if resp.status_code in (200, 201):
            create_response = resp.json()
            break
        elif resp.status_code in retryable_statuses:
            raise requests.HTTPError(f"Retryable error {resp.status_code}")
        else:
            print(f"❌ Non-retryable error {resp.status_code}: {resp.text}", flush=True)
            sys.exit(1)

    except Exception as e:
        print(f"⚠️ Attempt {attempt+1} failed: {e}", flush=True)
        sleep_time = min(random.uniform(0, 2 ** attempt), 60)  # full jitter, capped
        time.sleep(sleep_time)

else:
    print("❌ Sandbox creation failed after retries", flush=True)
    sys.exit(1)

print("✅ Sandbox created successfully.", flush=True)
sandbox_data = create_response.get("data", {})

# ----------------------------------
# Extract sandbox_id
# ----------------------------------
sandbox_id = None
if isinstance(sandbox_data, dict):
    if "result" in sandbox_data and "id" in sandbox_data["result"]:
        sandbox_id = sandbox_data["result"]["id"]
    elif "id" in sandbox_data:
        sandbox_id = sandbox_data["id"]

if sandbox_id and sandbox_id.startswith("identity/accounts/"):
    sandbox_id = sandbox_id.split("/")[-1]

if not sandbox_id:
    print("❌ Sandbox ID not found. Aborting.", flush=True)
    sys.exit(1)

with open(SANDBOX_ID_FILE, "w") as f:
    f.write(sandbox_id)
print(f"✅ Sandbox ID saved to {SANDBOX_ID_FILE}: {sandbox_id}", flush=True)

# ----------------------------------
# Extract external_id
# ----------------------------------
admin_user = sandbox_data.get("result", {}).get("admin_user")
external_id = None
if admin_user and "account_id" in admin_user:
    external_id = admin_user["account_id"].split("/")[-1]

if not external_id:
    print("❌ External ID not found in admin_user.account_id. Aborting.", flush=True)
    sys.exit(1)

with open(EXTERNAL_ID_FILE, "w") as f:
    f.write(external_id)
print(f"✅ External ID saved to {EXTERNAL_ID_FILE}: {external_id}", flush=True)
